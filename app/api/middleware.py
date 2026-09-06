"""
FastAPI middleware stack:
  1. CORS               — allow frontend origins
  2. Request ID         — inject X-Request-ID into every request/response
  3. Structured logging — log every request with latency + status code
  4. Rate limiting      — 60 requests/minute per IP (Redis-backed)
"""
import time
import uuid

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import settings
from app.core.logging import get_logger
import structlog
from fastapi import HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

logger = get_logger(__name__)
security = HTTPBearer()


async def _require_admin(credentials: HTTPAuthorizationCredentials = Depends(security)) -> str:
    """
    Simple admin authentication check.
    In production, replace with proper JWT validation.
    """
    # For now, just check for a simple admin token
    if credentials.credentials != settings.admin_token:
        raise HTTPException(
            status_code=401,
            detail="Admin access required"
        )
    return credentials.credentials


def register_middleware(app: FastAPI) -> None:
    """Attach all middleware to the app. Called once at startup."""

    # ── CORS ────────────────────────────────────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Request ID + Structured Logging ─────────────────────────────────────
    app.add_middleware(RequestLoggingMiddleware)

    # ── Rate Limiting ────────────────────────────────────────────────────────
    app.add_middleware(RateLimitMiddleware, limit=60, window=60)


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
                self._redis = aioredis.from_url(settings.redis_url)
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
