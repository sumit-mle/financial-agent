"""
Reranker — takes the top-K candidates from the retriever and re-scores them
for relevance to the query using a cross-encoder model.

This is the "RERANKING (Top-K Reranking)" block from Layer 3.

Two backends supported:
  - FlashRank  : free, local, zero latency, good quality (default)
  - Cohere     : API-based, best quality, requires API key

FlashRank is the default — it runs fully locally, no API key, no cost.
"""
from typing import Literal

from app.core.config import settings
from app.core.logging import get_logger
from app.retrieval.schemas import RetrievedChunk

logger = get_logger(__name__)

RerankerBackend = Literal["flashrank", "cohere"]


class Reranker:
    """
    Cross-encoder reranker that re-scores retrieved chunks.

    Usage:
        reranker = Reranker()
        top_chunks = reranker.rerank(query, chunks, top_k=5)
    """

    def __init__(
        self,
        backend: RerankerBackend | None = None,
        top_k: int | None = None,
    ) -> None:
        self.backend: RerankerBackend = backend or settings.reranker_provider  # type: ignore[assignment]
        self.top_k = top_k or settings.reranker_top_k
        self._model = None

        if self.backend == "flashrank":
            self._init_flashrank()
        elif self.backend == "cohere":
            self._init_cohere()

        logger.info("Reranker initialized", backend=self.backend, top_k=self.top_k)

    # ── Backend initialisation ─────────────────────────────────────────────

    def _init_flashrank(self) -> None:
        """
        FlashRank: fast local cross-encoder, no API key needed.
        Model: ms-marco-MiniLM-L-12-v2 (downloaded on first use, ~33MB)
        """
        try:
            from flashrank import Ranker  # type: ignore[import]
            self._model = Ranker(
                model_name="ms-marco-MiniLM-L-12-v2",
                cache_dir=".cache/flashrank",
            )
        except ImportError:
            logger.warning(
                "FlashRank not installed — falling back to score passthrough. "
                "Install with: pip install flashrank"
            )
            self._model = None

    def _init_cohere(self) -> None:
        """Cohere rerank API — best quality, requires COHERE_API_KEY."""
        if not settings.cohere_api_key:
            logger.warning("COHERE_API_KEY not set — falling back to FlashRank")
            self.backend = "flashrank"
            self._init_flashrank()
            return
        try:
            import cohere  # type: ignore[import]
            self._model = cohere.Client(settings.cohere_api_key)
        except ImportError:
            logger.warning("cohere package not installed. Run: pip install cohere")
            self._model = None

    # ── Reranking logic ────────────────────────────────────────────────────

    def _rerank_flashrank(
        self, query: str, chunks: list[RetrievedChunk]
    ) -> list[RetrievedChunk]:
        """Rerank using FlashRank local model."""
        if self._model is None:
            # No model — return as-is, preserving original scores
            return chunks[: self.top_k]

        from flashrank import RerankRequest  # type: ignore[import]

        passages = [{"id": i, "text": c.text} for i, c in enumerate(chunks)]
        request = RerankRequest(query=query, passages=passages)
        result = self._model.rerank(request)

        # Map scores back to chunks
        score_map: dict[int, float] = {
            r.get("id", 0): float(r.get("score", 0.0)) for r in result
        }
        for i, chunk in enumerate(chunks):
            chunk.rerank_score = score_map.get(i, 0.0)

        ranked = sorted(chunks, key=lambda c: c.rerank_score or 0.0, reverse=True)
        return ranked[: self.top_k]

    def _rerank_cohere(
        self, query: str, chunks: list[RetrievedChunk]
    ) -> list[RetrievedChunk]:
        """Rerank using Cohere API."""
        if self._model is None:
            return chunks[: self.top_k]

        texts = [c.text for c in chunks]
        response = self._model.rerank(  # type: ignore[union-attr]
            query=query,
            documents=texts,
            model="rerank-english-v3.0",
            top_n=self.top_k,
        )

        reranked_chunks: list[RetrievedChunk] = []
        for result in response.results:
            chunk = chunks[result.index]
            chunk.rerank_score = float(result.relevance_score)
            reranked_chunks.append(chunk)

        return reranked_chunks

    def rerank(
        self,
        query: str,
        chunks: list[RetrievedChunk],
        top_k: int | None = None,
    ) -> list[RetrievedChunk]:
        """
        Re-score and re-rank chunks for the given query.

        Args:
            query: The original user query.
            chunks: Candidates from the retriever.
            top_k: How many to return (defaults to self.top_k).

        Returns:
            Top-K chunks sorted by rerank score descending.
        """
        effective_top_k = top_k or self.top_k

        if not chunks:
            return []

        # If only a few candidates, skip reranking overhead
        if len(chunks) <= 2:
            return chunks[:effective_top_k]

        logger.debug("Reranking", candidates=len(chunks), top_k=effective_top_k)

        if self.backend == "cohere":
            result = self._rerank_cohere(query, chunks)
        else:
            result = self._rerank_flashrank(query, chunks)

        # Override top_k if caller specified a different value
        final = result[:effective_top_k]
        logger.debug(
            "Reranking complete",
            returned=len(final),
            top_score=round(final[0].final_score, 3) if final else 0,
        )
        return final
