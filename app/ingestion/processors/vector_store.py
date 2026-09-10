"""
Vector store writer — indexes embedded documents into Qdrant.

Qdrant collections:
  - complaints   : CFPB consumer complaint narratives + resolutions
  - policies     : SEC 10-K sections + FDIC/CFPB regulatory PDFs
  - faq          : Banking77 intents + curated FAQ pairs

Each collection has:
  - Dense vectors (semantic search)
  - Payload (metadata for filtering)
"""
import uuid
from typing import Any

from qdrant_client import QdrantClient  # type: ignore[import]
from qdrant_client.http import models as qdrant_models  # type: ignore[import]

from app.core.config import settings
from app.core.logging import get_logger
from app.ingestion.sources.base import RawDocument

logger = get_logger(__name__)

# Map collection name → embedding dimension
COLLECTION_DIMS: dict[str, int] = {
    settings.qdrant_collection_complaints: 1536,   # OpenAI text-embedding-3-small
    settings.qdrant_collection_policies: 1536,
    settings.qdrant_collection_faq: 1536,
}

# For local (sentence-transformers) models, override dim here
LOCAL_DIMS: dict[str, int] = {
    settings.qdrant_collection_complaints: 768,    # BAAI/bge-base-en-v1.5
    settings.qdrant_collection_policies: 768,
    settings.qdrant_collection_faq: 768,
}


class VectorStoreWriter:
    """
    Writes (document, vector) pairs into Qdrant collections.

    Handles:
      - Collection creation (idempotent)
      - Batch upserts with configurable batch size
      - Payload indexing for fast metadata filtering
    """

    UPSERT_BATCH_SIZE = 100

    # Stable namespace for deterministic point IDs (content-addressed upserts).
    _ID_NAMESPACE = uuid.UUID("6f9619ff-8b86-d011-b42d-00cf4fc964ff")

    def __init__(self, embedding_provider: str = "openai") -> None:
        self._client = QdrantClient(
            url=settings.qdrant_url,
            api_key=settings.qdrant_api_key or None,
            timeout=30,
        )
        self.dims = COLLECTION_DIMS if embedding_provider == "openai" else LOCAL_DIMS
        logger.info("VectorStoreWriter connected", url=settings.qdrant_url)

    def _stable_point_id(self, collection_name: str, doc: RawDocument) -> str:
        """
        Deterministic point ID so re-ingesting the same document overwrites its
        point instead of creating a duplicate. Content-addressed, namespaced by
        collection and any stable source identifier present in metadata.
        """
        meta = doc.metadata or {}
        parts: list[str] = [collection_name]
        for key in ("doc_id", "complaint_id", "source_id", "id", "chunk_index"):
            if meta.get(key) is not None:
                parts.append(f"{key}={meta[key]}")
        # Include the chunk text so distinct chunks of one document stay unique
        # and edited content produces a fresh point.
        parts.append(doc.text)
        return str(uuid.uuid5(self._ID_NAMESPACE, "|".join(str(p) for p in parts)))

    def ensure_collection(self, collection_name: str) -> None:
        """Create collection if it doesn't exist. Safe to call repeatedly."""
        existing = {c.name for c in self._client.get_collections().collections}
        if collection_name in existing:
            logger.info("Collection already exists", collection=collection_name)
            return

        dim = self.dims.get(collection_name, 1536)
        self._client.create_collection(
            collection_name=collection_name,
            vectors_config=qdrant_models.VectorParams(
                size=dim,
                distance=qdrant_models.Distance.COSINE,
            ),
            # Optimize for low-latency search in production
            hnsw_config=qdrant_models.HnswConfigDiff(
                m=16,
                ef_construct=100,
                full_scan_threshold=10_000,
            ),
            quantization_config=qdrant_models.ScalarQuantization(
                scalar=qdrant_models.ScalarQuantizationConfig(
                    type=qdrant_models.ScalarType.INT8,
                    quantile=0.99,
                    always_ram=True,
                )
            ),
        )

        # Create payload indexes for fast filtering
        for field in ["source", "product", "issue", "company", "collection"]:
            try:
                self._client.create_payload_index(
                    collection_name=collection_name,
                    field_name=field,
                    field_schema=qdrant_models.PayloadSchemaType.KEYWORD,
                )
            except Exception:
                pass  # Index may already exist

        logger.info("Collection created", collection=collection_name, dim=dim)

    def upsert(
        self,
        collection_name: str,
        doc_vector_pairs: list[tuple[RawDocument, list[float]]],
    ) -> int:
        """
        Upsert document-vector pairs into the collection.
        Returns total points written.
        """
        self.ensure_collection(collection_name)

        total = 0
        failed_batches = 0
        for i in range(0, len(doc_vector_pairs), self.UPSERT_BATCH_SIZE):
            batch = doc_vector_pairs[i : i + self.UPSERT_BATCH_SIZE]
            points = []

            for doc, vector in batch:
                point_id = self._stable_point_id(collection_name, doc)
                payload: dict[str, Any] = {
                    "text": doc.text,
                    **doc.metadata,
                }
                points.append(
                    qdrant_models.PointStruct(
                        id=point_id,
                        vector=vector,
                        payload=payload,
                    )
                )

            # Isolate batch failures so one bad batch doesn't abort the whole run.
            try:
                self._client.upsert(
                    collection_name=collection_name,
                    points=points,
                    wait=True,
                )
                total += len(points)
            except Exception as exc:
                failed_batches += 1
                logger.error(
                    "Upsert batch failed — continuing",
                    collection=collection_name,
                    batch_start=i,
                    batch_size=len(points),
                    error=str(exc),
                )
                continue

            if total % 1000 == 0:
                logger.info(
                    "Upsert progress",
                    collection=collection_name,
                    total_upserted=total,
                )

        if failed_batches:
            logger.warning(
                "Upsert completed with failures",
                collection=collection_name,
                total_upserted=total,
                failed_batches=failed_batches,
            )

        return total

    def collection_count(self, collection_name: str) -> int:
        """Return number of points in a collection."""
        try:
            info = self._client.get_collection(collection_name)
            return info.points_count or 0
        except Exception:
            return 0

    def delete_collection(self, collection_name: str) -> None:
        """Drop a collection entirely. Use with care."""
        self._client.delete_collection(collection_name)
        logger.warning("Collection deleted", collection=collection_name)

    def purge_old_pii_vectors(self, collection_name: str, retention_days: int = 30) -> int:
        """
        Delete vectors that contain PII and are older than retention_days.
        Depends on payload containing 'has_pii' (bool) and 'ingested_at' (ISO timestamp).
        """
        from datetime import datetime, timedelta
        import time

        cutoff_date = (datetime.utcnow() - timedelta(days=retention_days)).isoformat()
        try:
            # First create payload index on ingested_at and has_pii if they don't exist
            for field in ["ingested_at", "has_pii"]:
                try:
                    self._client.create_payload_index(
                        collection_name=collection_name,
                        field_name=field,
                        field_schema=qdrant_models.PayloadSchemaType.KEYWORD,
                    )
                except Exception:
                    pass
            
            # Wait a moment for index to be available
            time.sleep(1)

            result = self._client.delete(
                collection_name=collection_name,
                points_selector=qdrant_models.FilterSelector(
                    filter=qdrant_models.Filter(
                        must=[
                            qdrant_models.FieldCondition(
                                key="has_pii",
                                match=qdrant_models.MatchValue(value=True),
                            ),
                            qdrant_models.FieldCondition(
                                key="ingested_at",
                                range=qdrant_models.Range(
                                    lt=cutoff_date,
                                ),
                            ),
                        ]
                    )
                ),
            )
            # The result object doesn't always give exact deleted counts directly, 
            # but we assume success if no exception is raised.
            logger.info("Purged old PII vectors", collection=collection_name, cutoff=cutoff_date)
            return 1 # indicating success
        except Exception as exc:
            logger.error(
                "Failed to purge old PII vectors",
                collection=collection_name,
                error=str(exc)
            )
            return 0

