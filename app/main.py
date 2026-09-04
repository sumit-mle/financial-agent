"""
FastAPI application entry point.

Startup sequence:
  1. Configure structured logging
  2. Register middleware (CORS, request ID, rate limiting)
  3. Mount routers (/api/v1/chat, /api/v1/admin)
  4. Warm up singleton dependencies (lazy — won't crash if keys missing)
  5. Initialize metrics collection
  6. Serve

Dev:  uvicorn app.main:app --reload --port 8000
Prod: /app/scripts/start.sh  (inside Docker)
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from prometheus_fastapi_instrumentator import Instrumentator

from app.core.config import settings
from app.core.logging import configure_logging, get_logger

# Configure logging before anything else
configure_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup / shutdown lifecycle."""
    logger.info(
        "═══ Fin AI Agent starting ═══",
        version=settings.app_version,
        env=settings.app_env,
        llm_provider=settings.llm_provider,
        qdrant_url=settings.qdrant_url,
    )

    # Initialize Prometheus metrics
    try:
        instrumentator = Instrumentator()
        instrumentator.instrument(app).expose(app)
        logger.info("✓ Prometheus metrics initialized")
    except Exception as exc:
        logger.warning("Metrics initialization failed", error=str(exc))

    # Warm up singletons — deferred import so startup never crashes
    try:
        from app.models.dependencies import get_fin_agent, get_rag_pipeline
        get_rag_pipeline()   # loads Embedder + Qdrant client
        get_fin_agent()      # compiles LangGraph graph
        logger.info("✓ Agent singletons ready")
    except Exception as exc:
        # Non-fatal: app starts, first request will re-init
        logger.warning("Singleton warm-up failed (non-fatal)", error=str(exc))

    logger.info(
        "✓ API ready",
        docs=f"http://0.0.0.0:{settings.api_port}/docs",
        health=f"http://0.0.0.0:{settings.api_port}/health",
        metrics=f"http://0.0.0.0:{settings.api_port}/metrics",
    )

    yield

    logger.info("═══ Fin AI Agent shutting down ═══")


app = FastAPI(
    title="Fin AI Agent",
    description=(
        "Production-grade Financial Complaint Resolution AI Agent. "
        "Compound AI architecture: LangGraph + Enhanced RAG over "
        "CFPB complaints (7.8M) + SEC 10-K filings + regulatory PDFs."
    ),
    version=settings.app_version,
    # Disable Swagger/ReDoc in production
    docs_url="/docs" if not settings.is_production else None,
    redoc_url="/redoc" if not settings.is_production else None,
    lifespan=lifespan,
)

# ── Middleware ────────────────────────────────────────────────────────────────
from app.api.middleware import register_middleware  # noqa: E402
register_middleware(app)

# ── Routers ───────────────────────────────────────────────────────────────────
from app.api.routes.chat import router as chat_router    # noqa: E402
from app.api.routes.admin import router as admin_router  # noqa: E402
from app.api.routes.experiments import router as experiments_router  # noqa: E402
from app.api.routes.mlops import router as mlops_router  # noqa: E402
from app.api.routes.analytics import router as analytics_router  # noqa: E402

app.include_router(chat_router, prefix=settings.api_prefix)
app.include_router(admin_router, prefix=settings.api_prefix)
app.include_router(experiments_router, prefix=f"{settings.api_prefix}/admin")
app.include_router(mlops_router, prefix=f"{settings.api_prefix}/admin")
app.include_router(analytics_router, prefix=f"{settings.api_prefix}/admin")


# ── Root + Health ─────────────────────────────────────────────────────────────
@app.get("/", include_in_schema=False)
async def root():
    return JSONResponse({
        "name": settings.app_name,
        "version": settings.app_version,
        "docs": "/docs",
        "health": "/health",
        "chat": f"{settings.api_prefix}/chat",
    })


@app.get("/health", include_in_schema=False)
async def health():
    """Lightweight liveness probe — always returns 200 if process is up."""
    return JSONResponse({"status": "ok", "version": settings.app_version})
