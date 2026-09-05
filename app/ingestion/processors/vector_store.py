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

    def __init__(self, embedding_provider: str = "openai") -> None:
        self._client = QdrantClient(
            url=settings.qdrant_url,
            api_key=settings.qdrant_api_key or None,
            timeout=30,
        )
        self.dims = COLLECTION_DIMS if embedding_provider == "openai" else LOCAL_DIMS
        logger.info("VectorStoreWriter connected", url=settings.qdrant_url)

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
        for i in range(0, len(doc_vector_pairs), self.UPSERT_BATCH_SIZE):
            batch = doc_vector_pairs[i : i + self.UPSERT_BATCH_SIZE]
            points = []

            for doc, vector in batch:
                point_id = str(uuid.uuid4())
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

            self._client.upsert(
                collection_name=collection_name,
                points=points,
                wait=True,
            )
            total += len(points)

            if total % 1000 == 0:
                logger.info(
                    "Upsert progress",
                    collection=collection_name,
                    total_upserted=total,
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
