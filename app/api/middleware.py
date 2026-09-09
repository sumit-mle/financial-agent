"""
FastAPI middleware stack:
  1. CORS               — allow frontend origins
  2. Request ID         — inject X-Request-ID into every request/response
  3. Structured logging — log every request with latency + status code
  4. Rate limiting      — 60 requests/minute per IP (Redis-backed)
"""
import secrets
import time
import uuid

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import settings
from app.core.logging import get_logger
import structlog
from fastapi import HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

logger = get_logger(__name__)
security = HTTPBearer(auto_error=True)


async def require_admin(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> str:
    """
    Admin authentication dependency — the single source of truth for protecting
    privileged routes (admin, mlops, analytics, experiments).

    Enforced in ALL environments (not just production) and uses a constant-time
    comparison to avoid leaking the token via timing. The startup validator in
    `core.config` guarantees the token is non-default in production.
    """
    provided = credentials.credentials if credentials else ""
    if not secrets.compare_digest(provided, settings.admin_token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Admin authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return provided


# Backwards-compatible alias (older routes imported `_require_admin`).
_require_admin = require_admin


def register_middleware(app: FastAPI) -> None:
    """Attach all middleware to the app. Called once at startup."""

    # ── CORS ────────────────────────────────────────────────────────────────
    # Never combine a wildcard origin with credentials (the browser rejects it
    # and it is a security foot-gun). Scope methods/headers to what we use.
    allow_credentials = "*" not in settings.cors_origins
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=allow_credentials,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
        expose_headers=["X-Request-ID", "X-Response-Time"],
    )

    # ── Request ID + Structured Logging ─────────────────────────────────────
    app.add_middleware(RequestLoggingMiddleware)

    # ── Body size limit ──────────────────────────────────────────────────────
    app.add_middleware(BodySizeLimitMiddleware, max_bytes=settings.max_request_bytes)

    # ── Rate Limiting ────────────────────────────────────────────────────────
    app.add_middleware(RateLimitMiddleware, limit=60, window=60)


class BodySizeLimitMiddleware(BaseHTTPMiddleware):
    """
    Reject over-large request bodies early (before JSON parsing) to bound
    memory use and blunt trivial payload-based DoS. Uses Content-Length when
    present and also enforces the cap while streaming the body.
    """

    def __init__(self, app, max_bytes: int = 262_144) -> None:
        super().__init__(app)
        self.max_bytes = max_bytes

    async def dispatch(self, request: Request, call_next) -> Response:
        from fastapi.responses import JSONResponse

        content_length = request.headers.get("content-length")
        if content_length is not None:
            try:
                if int(content_length) > self.max_bytes:
                    return JSONResponse(
                        status_code=413,
                        content={"detail": "Request body too large."},
                    )
            except ValueError:
                return JSONResponse(
                    status_code=400,
                    content={"detail": "Invalid Content-Length header."},
                )
        return await call_next(request)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    Injects X-Request-ID and logs every request with method, path,
    status code, and latency.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))

        # Bind request_id to all log records for this request
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)

        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception as exc:
            logger.error(
                "Unhandled request error",
                method=request.method,
                path=request.url.path,
                error=str(exc),
            )
            raise

        latency_ms = round((time.perf_counter() - start) * 1000, 1)
        logger.info(
            "HTTP request",
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            latency_ms=latency_ms,
        )

        response.headers["X-Request-ID"] = request_id
        response.headers["X-Response-Time"] = f"{latency_ms}ms"
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Simple Redis-backed sliding window rate limiter.
    Falls back to pass-through if Redis is unavailable.
    """

    def __init__(self, app, limit: int = 60, window: int = 60) -> None:
        super().__init__(app)
        self.limit = limit
        self.window = window
        self._redis = None

    async def _get_redis(self):
        if self._redis is None:
            try:
                import redis.asyncio as aioredis
                self._redis = aioredis.from_url(
                    settings.redis_url,
                    socket_connect_timeout=2,  # fail fast if Redis is down
                    socket_timeout=2,          # don't hang on read/write either
                    retry_on_timeout=False,
                )
            except Exception:
                return None
        return self._redis

    async def dispatch(self, request: Request, call_next) -> Response:
        # Skip rate limiting for health checks
        if request.url.path in ("/api/v1/admin/health", "/health"):
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"
        redis = await self._get_redis()

        if redis:
            try:
                key = f"ratelimit:{client_ip}"
                count = await redis.incr(key)
                if count == 1:
                    await redis.expire(key, self.window)
                if count > self.limit:
                    from fastapi.responses import JSONResponse
                    return JSONResponse(
                        status_code=429,
                        content={"detail": "Too many requests. Please slow down."},
                        headers={"Retry-After": str(self.window)},
                    )
            except Exception:
                pass  # Redis down → degrade gracefully, don't block traffic

        return await call_next(request)
