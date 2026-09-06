"""
RAG Pipeline — single entry point that wires together:
    Query → Retriever → Reranker → ContextAssembler → AssembledContext

This is what the orchestration layer (LangGraph) calls.
All three stages are exposed as a single .run() method,
and also individually for tracing / testing.

Architecture diagram (Layer 3):
  ┌─────────────────────────────────────────────────────┐
  │                 RAG PIPELINE                        │
  │                                                     │
  │  query ──► Retriever ──► Reranker ──► Assembler    │
  │              (Qdrant)    (FlashRank)   (context)   │
  │                                           │         │
  │                                           ▼         │
  │                                  AssembledContext   │
  └─────────────────────────────────────────────────────┘
"""
from dataclasses import dataclass
from typing import Any

from app.core.logging import get_logger
from app.ingestion.processors.embedder import Embedder
from app.retrieval.context_assembler import ContextAssembler
from app.retrieval.reranker import Reranker
from app.retrieval.retriever import MultiCollectionRetriever
from app.retrieval.schemas import AssembledContext, RetrievedChunk

logger = get_logger(__name__)


@dataclass
class RAGResult:
    """Full result from the RAG pipeline including intermediate artifacts."""
    context: AssembledContext
    raw_candidates: list[RetrievedChunk]
    reranked: list[RetrievedChunk]
    query: str


class RAGPipeline:
    """
    Orchestrates the full retrieve → rerank → assemble flow.

    Shared across all agent nodes — instantiate once and reuse.
    Thread-safe: each call to .run() is fully independent.
    """

    def __init__(
        self,
        embedder: Embedder | None = None,
        retriever: MultiCollectionRetriever | None = None,
        reranker: Reranker | None = None,
        assembler: ContextAssembler | None = None,
    ) -> None:
        # Shared embedder — one model loaded once
        _embedder = embedder or Embedder()
        self.retriever = retriever or MultiCollectionRetriever(embedder=_embedder)
        self.reranker = reranker or Reranker()
        self.assembler = assembler or ContextAssembler()
        logger.info("RAGPipeline ready")

    def run(
        self,
        query: str,
        customer_data: dict[str, Any] | None = None,
        conversation_history: list[dict[str, str]] | None = None,
        filters: dict[str, Any] | None = None,
        collection_override: str | None = None,
        reranker_top_k: int | None = None,
    ) -> RAGResult:
        """
        Execute the full RAG pipeline for a given query.

        Args:
            query: The user's message / question.
            customer_data: Structured customer profile from CRM.
            conversation_history: Previous conversation turns.
            filters: Optional Qdrant metadata filters.
            collection_override: Search a single collection only.
            reranker_top_k: Override number of passages to keep after reranking.

        Returns:
            RAGResult with the assembled context + intermediate artifacts.
        """
        logger.info("RAG pipeline start", query=query[:80])

        # ── Step 1: Retrieve ───────────────────────────────────────────────
        raw_candidates = self.retriever.retrieve(
            query=query,
            filters=filters,
            collection_override=collection_override,
        )
        logger.debug("Retrieved candidates", count=len(raw_candidates))

        # ── Step 2: Rerank ─────────────────────────────────────────────────
        reranked = self.reranker.rerank(
            query=query,
            chunks=raw_candidates,
            top_k=reranker_top_k,
        )
        logger.debug("Reranked", count=len(reranked))

        # ── Step 3: Assemble context ───────────────────────────────────────
        collections_searched = list(
            {c.metadata.get("collection", "") for c in raw_candidates}
        )
        context = self.assembler.assemble(
            query=query,
            ranked_chunks=reranked,
            customer_data=customer_data,
            conversation_history=conversation_history,
            collections_searched=collections_searched,
            total_candidates=len(raw_candidates),
        )

        logger.info(
            "RAG pipeline complete",
            passages_in_context=len(context.passages),
            collections=collections_searched,
        )

        return RAGResult(
            context=context,
            raw_candidates=raw_candidates,
            reranked=reranked,
            query=query,
        )

    def retrieve_only(
        self,
        query: str,
        filters: dict[str, Any] | None = None,
    ) -> list[RetrievedChunk]:
        """Run only the retrieval step. Used for debugging."""
        return self.retriever.retrieve(query=query, filters=filters)

    def rerank_only(
        self,
        query: str,
        chunks: list[RetrievedChunk],
    ) -> list[RetrievedChunk]:
        """Run only the reranking step. Used for debugging."""
        return self.reranker.rerank(query=query, chunks=chunks)
