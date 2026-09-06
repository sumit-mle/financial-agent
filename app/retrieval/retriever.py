"""
Multi-collection semantic retriever backed by Qdrant.

Strategy — for each query we search across multiple collections
simultaneously and merge results by score:
  - complaints   : similar past complaints + their resolutions
  - policies     : regulatory rules, 10-K risk disclosures
  - faq          : exact-match intent answers

This implements the "RETRIEVAL" block from Layer 3 of the architecture.
"""
from typing import Any

from qdrant_client import QdrantClient  # type: ignore[import]
from qdrant_client.http import models as qmodels  # type: ignore[import]

from app.core.config import settings
from app.core.logging import get_logger
from app.ingestion.processors.embedder import Embedder
from app.retrieval.schemas import RetrievedChunk

logger = get_logger(__name__)

# Which collections to search, and how many candidates to pull from each
COLLECTION_TOP_K: dict[str, int] = {
    settings.qdrant_collection_complaints: 8,
    settings.qdrant_collection_policies: 6,
    settings.qdrant_collection_faq: 4,
}


class MultiCollectionRetriever:
    """
    Performs semantic search across all three Qdrant collections,
    merges candidates by score, and returns top-K results.

    Supports optional metadata filtering (e.g. filter by product category).
    """

    def __init__(
        self,
        embedder: Embedder | None = None,
        top_k: int | None = None,
    ) -> None:
        self._client = QdrantClient(
            url=settings.qdrant_url,
            api_key=settings.qdrant_api_key or None,
            timeout=10,
        )
        self.embedder = embedder or Embedder()
        self.top_k = top_k or settings.retrieval_top_k
        logger.info("Retriever initialized", top_k=self.top_k)

    def _build_filter(
        self, filters: dict[str, Any] | None
    ) -> qmodels.Filter | None:
        """Convert a simple {field: value} dict into a Qdrant filter."""
        if not filters:
            return None

        conditions = []
        for field_name, value in filters.items():
            if isinstance(value, list):
                conditions.append(
                    qmodels.FieldCondition(
                        key=field_name,
                        match=qmodels.MatchAny(any=value),
                    )
                )
            else:
                conditions.append(
                    qmodels.FieldCondition(
                        key=field_name,
                        match=qmodels.MatchValue(value=value),
                    )
                )
        return qmodels.Filter(must=conditions)

    def _search_collection(
        self,
        collection_name: str,
        query_vector: list[float],
        top_k: int,
        filters: dict[str, Any] | None = None,
    ) -> list[RetrievedChunk]:
        """Search a single Qdrant collection."""
        try:
            results = self._client.search(
                collection_name=collection_name,
                query_vector=query_vector,
                limit=top_k,
                query_filter=self._build_filter(filters),
                with_payload=True,
                score_threshold=0.30,  # Drop irrelevant results early
            )
        except Exception as exc:
            # Collection may not exist yet (not yet ingested)
            logger.warning(
                "Collection search failed",
                collection=collection_name,
                error=str(exc),
            )
            return []

        chunks = []
        for hit in results:
            payload = hit.payload or {}
            text = payload.pop("text", "")
            chunks.append(
                RetrievedChunk(
                    text=text,
                    score=float(hit.score),
                    metadata={**payload, "collection": collection_name},
                )
            )
        return chunks

    def retrieve(
        self,
        query: str,
        filters: dict[str, Any] | None = None,
        collection_override: str | None = None,
    ) -> list[RetrievedChunk]:
        """
        Retrieve top-K relevant chunks for a query.

        Args:
            query: The user query string.
            filters: Optional metadata filters, e.g. {"product": "Mortgage"}.
            collection_override: If set, search only this collection.

        Returns:
            List of RetrievedChunk sorted by score descending.
        """
        logger.debug("Retrieving", query=query[:80], filters=filters)

        # Embed the query
        query_vector = self.embedder.embed_query(query)

        # Determine which collections to search
        if collection_override:
            search_plan = {collection_override: self.top_k}
        else:
            search_plan = COLLECTION_TOP_K

        # Search all collections in parallel (sequential here; parallelise
        # with concurrent.futures if latency becomes a concern)
        all_chunks: list[RetrievedChunk] = []
        for collection, k in search_plan.items():
            chunks = self._search_collection(
                collection_name=collection,
                query_vector=query_vector,
                top_k=k,
                filters=filters,
            )
            all_chunks.extend(chunks)

        # Merge and sort by score, deduplicate near-identical texts
        all_chunks.sort(key=lambda c: c.score, reverse=True)
        deduped = self._deduplicate(all_chunks)

        # Return top_k after dedup
        final = deduped[: self.top_k]
        logger.debug(
            "Retrieval complete",
            candidates=len(all_chunks),
            after_dedup=len(deduped),
            returned=len(final),
        )
        return final

    @staticmethod
    def _deduplicate(
        chunks: list[RetrievedChunk], similarity_threshold: float = 0.92
    ) -> list[RetrievedChunk]:
        """
        Remove near-duplicate chunks using simple prefix matching.
        Two chunks are considered duplicates if one starts with 80%+ of the other.
        """
        seen_prefixes: list[str] = []
        unique: list[RetrievedChunk] = []

        for chunk in chunks:
            prefix = chunk.text[:150].lower().strip()
            is_dup = any(
                prefix in seen or seen in prefix
                for seen in seen_prefixes
            )
            if not is_dup:
                unique.append(chunk)
                seen_prefixes.append(prefix)

        return unique
