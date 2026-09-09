"""
Admin routes — ingestion control, vector store status, health checks.
Protected by API key in production.
"""
import asyncio

from fastapi import APIRouter, BackgroundTasks, Depends

from app.api.middleware import require_admin
from app.api.schemas import (
    HealthResponse,
    IngestRequest,
    IngestResponse,
    VectorStoreStatus,
)
from app.core.config import settings
from app.core.logging import get_logger
from app.ingestion.pipeline import IngestionPipeline
from app.ingestion.processors.vector_store import VectorStoreWriter

logger = get_logger(__name__)
router = APIRouter(prefix="/admin", tags=["Admin"])


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """
    Health check — verifies connectivity to all downstream services.
    Used by Docker healthcheck and load balancer probes.
    """
    services: dict[str, str] = {}

    # Check Qdrant
    try:
        from qdrant_client import QdrantClient
        client = QdrantClient(url=settings.qdrant_url, timeout=3)
        client.get_collections()
        services["qdrant"] = "ok"
    except Exception as exc:
        logger.warning("Health check: Qdrant unreachable", error=str(exc))
        services["qdrant"] = "error"

    # Check Redis
    try:
        import redis.asyncio as aioredis
        r = aioredis.from_url(settings.redis_url, socket_timeout=2)
        await r.ping()
        await r.aclose()
        services["redis"] = "ok"
    except Exception as exc:
        logger.warning("Health check: Redis unreachable", error=str(exc))
        services["redis"] = "error"

    # Check Postgres
    try:
        from sqlalchemy.ext.asyncio import create_async_engine
        engine = create_async_engine(settings.database_url, pool_timeout=3)
        async with engine.connect() as conn:
            await conn.execute(__import__("sqlalchemy").text("SELECT 1"))
        await engine.dispose()
        services["postgres"] = "ok"
    except Exception as exc:
        logger.warning("Health check: Postgres unreachable", error=str(exc))
        services["postgres"] = "error"

    # Check Salesforce CRM
    try:
        if all([settings.salesforce_username, settings.salesforce_client_id]):
            from app.integrations.salesforce import get_salesforce_client
            sf_client = get_salesforce_client()
            sf_health = await sf_client.health_check()
            services["salesforce"] = (
                "ok" if sf_health["status"] == "healthy" else "error"
            )
        else:
            services["salesforce"] = "not_configured"
    except Exception as exc:
        logger.warning("Health check: Salesforce unreachable", error=str(exc))
        services["salesforce"] = "error"

    overall = (
        "ok"
        if all(v in ["ok", "not_configured"] for v in services.values())
        else "degraded"
    )

    return HealthResponse(
        status=overall,
        version=settings.app_version,
        services=services,
    )


@router.get("/status", response_model=VectorStoreStatus)
async def vector_store_status(
    _: str = Depends(require_admin),
) -> VectorStoreStatus:
    """Return current document counts per Qdrant collection."""
    writer = VectorStoreWriter()
    complaints = writer.collection_count(settings.qdrant_collection_complaints)
    policies = writer.collection_count(settings.qdrant_collection_policies)
    faq = writer.collection_count(settings.qdrant_collection_faq)
    return VectorStoreStatus(
        complaints=complaints,
        policies=policies,
        faq=faq,
        total=complaints + policies + faq,
    )


_ingest_lock = asyncio.Lock()
_ingest_running = False


@router.post("/ingest", response_model=IngestResponse)
async def trigger_ingestion(
    request: IngestRequest,
    background_tasks: BackgroundTasks,
    _: str = Depends(require_admin),
) -> IngestResponse:
    """
    Trigger data ingestion pipeline in the background.
    Only one ingestion job runs at a time.
    """
    global _ingest_running
    if _ingest_running:
        return IngestResponse(
            status="error",
            message="Ingestion already in progress. Check logs for status.",
        )

    async def run_ingest() -> None:
        global _ingest_running
        _ingest_running = True
        try:
            pipeline = IngestionPipeline()
            source_map = {
                "cfpb": lambda: pipeline.run_cfpb(sample_mode=request.sample_mode),
                "sec": pipeline.run_sec,
                "policy": pipeline.run_policy,
                "all": lambda: pipeline.run_all(sample_cfpb=request.sample_mode),
            }
            stats = source_map[request.source]()
            logger.info("Background ingestion complete", source=request.source, stats=stats)
        except Exception as exc:
            logger.error("Background ingestion failed", error=str(exc))
        finally:
            _ingest_running = False

    background_tasks.add_task(run_ingest)
    return IngestResponse(
        status="started",
        message=f"Ingestion started for source='{request.source}'. Monitor via /admin/status.",
    )
