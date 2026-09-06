"""
Embedding processor — converts text chunks into dense vector representations.

Supports:
  - OpenAI text-embedding-3-small (default, best quality/cost ratio)
  - Local sentence-transformers (free, no API key, good for dev)

Handles batching, retries, and rate limit backoff automatically.
"""
import time
from typing import Literal

from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import settings
from app.core.logging import get_logger
from app.ingestion.sources.base import RawDocument

logger = get_logger(__name__)

EmbeddingProvider = Literal["openai", "local"]


class Embedder:
    """
    Wraps embedding providers with batching and retry logic.

    Usage:
        embedder = Embedder(provider="openai")
        vectors = embedder.embed_documents(chunks)
    """

    EMBEDDING_DIMS = {
        "text-embedding-3-small": 1536,
        "text-embedding-3-large": 3072,
        "all-MiniLM-L6-v2": 384,
        "BAAI/bge-base-en-v1.5": 768,
    }

    def __init__(
        self,
        provider: EmbeddingProvider = "openai",
        model: str | None = None,
        batch_size: int | None = None,
    ) -> None:
        self.provider = provider
        self.batch_size = batch_size or settings.embedding_batch_size
        self._client = None

        if provider == "openai":
            self.model = model or settings.openai_embedding_model
            self._init_openai()
        else:
            self.model = model or "BAAI/bge-base-en-v1.5"
            self._init_local()

        self.embedding_dim = self.EMBEDDING_DIMS.get(self.model, 768)
        logger.info(
            "Embedder initialized",
            provider=provider,
            model=self.model,
            dim=self.embedding_dim,
        )

    def _init_openai(self) -> None:
        from openai import OpenAI  # type: ignore[import]
        self._client = OpenAI(api_key=settings.openai_api_key)

    def _init_local(self) -> None:
        from sentence_transformers import SentenceTransformer  # type: ignore[import]
        logger.info("Loading local embedding model", model=self.model)
        self._local_model = SentenceTransformer(self.model)

    # ── Core embedding methods ───────────────────────────────────────────────

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        reraise=True,
    )
    def _embed_batch_openai(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts via OpenAI API."""
        # Clean texts: remove newlines which can hurt embedding quality
        cleaned = [t.replace("\n", " ").strip() for t in texts]
        response = self._client.embeddings.create(  # type: ignore[union-attr]
            model=self.model,
            input=cleaned,
        )
        return [item.embedding for item in response.data]

    def _embed_batch_local(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch using local sentence-transformers."""
        vectors = self._local_model.encode(  # type: ignore[attr-defined]
            texts,
            batch_size=self.batch_size,
            show_progress_bar=False,
            normalize_embeddings=True,
        )
        return vectors.tolist()

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """
        Embed a list of texts, processing in batches.
        Returns one vector per input text.
        """
        all_vectors: list[list[float]] = []
        total_batches = (len(texts) + self.batch_size - 1) // self.batch_size

        for i in range(0, len(texts), self.batch_size):
            batch = texts[i : i + self.batch_size]
            batch_num = i // self.batch_size + 1

            if self.provider == "openai":
                vectors = self._embed_batch_openai(batch)
                # Respect OpenAI rate limits in production
                if not settings.is_production:
                    time.sleep(0.05)
            else:
                vectors = self._embed_batch_local(batch)

            all_vectors.extend(vectors)

            if batch_num % 10 == 0:
                logger.info(
                    "Embedding progress",
                    batch=batch_num,
                    total=total_batches,
                    embedded=len(all_vectors),
                )

        return all_vectors

    def embed_documents(
        self, docs: list[RawDocument]
    ) -> list[tuple[RawDocument, list[float]]]:
        """
        Embed a list of RawDocuments.
        Returns list of (doc, vector) pairs.
        """
        texts = [doc.text for doc in docs]
        vectors = self.embed_texts(texts)
        return list(zip(docs, vectors))

    def embed_query(self, query: str) -> list[float]:
        """Embed a single query string (used at retrieval time)."""
        return self.embed_texts([query])[0]
