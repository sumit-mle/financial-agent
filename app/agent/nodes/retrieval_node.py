"""
Node: Retrieval (Layer 3)

Calls the RAG pipeline with the refined query + customer context.
Populates state with retrieved chunks and assembled context string.

Maps to: "RETRIEVAL / RAG LAYER" in the architecture.
"""
from typing import Any

from starlette.concurrency import run_in_threadpool

from app.agent.state import AgentState
from app.core.config import settings
from app.core.logging import get_logger
from app.retrieval.rag_pipeline import RAGPipeline

logger = get_logger(__name__)

# Map intent categories to product filters for more targeted retrieval
_INTENT_PRODUCT_FILTERS: dict[str, list[str]] = {
    "complaint_status": [],           # Search all products
    "payment_issue": ["Credit card", "Checking or savings account"],
    "account_inquiry": ["Checking or savings account", "Credit card"],
    "product_question": ["Mortgage", "Personal loan", "Student loan"],
    "fraud_report": ["Credit card", "Checking or savings account"],
    "policy_question": [],            # Search all
    "general": [],
}


class RetrievalNode:
    """
    Executes the full RAG pipeline (retrieve → rerank → assemble)
    and writes results into agent state.
    """

    def __init__(self, rag_pipeline: RAGPipeline | None = None) -> None:
        self._rag = rag_pipeline or RAGPipeline()

    async def run(self, state: AgentState) -> AgentState:
        """Run RAG and populate state with context."""
        query = state.refined_query or state.user_message
        if not query.strip():
            state.add_reasoning("Retrieval skipped: empty query")
            return state

        # Build optional product filter based on intent
        product_filters = _INTENT_PRODUCT_FILTERS.get(state.detected_intent, [])
        filters: dict[str, Any] | None = None
        if product_filters:
            filters = {"product": product_filters}

        try:
            # RAGPipeline.run is synchronous (embedding + Qdrant + rerank);
            # run it in a worker thread so it never blocks the event loop.
            result = await run_in_threadpool(
                self._rag.run,
                query=query,
                customer_data=state.customer_data or None,
                conversation_history=state.messages,
                filters=filters,
            )

            # Store retrieved chunks as plain dicts for state serialization
            state.retrieved_chunks = [
                {
                    "text": c.text,
                    "score": c.score,
                    "source": c.source_label,
                    "metadata": c.metadata,
                }
                for c in result.raw_candidates
            ]
            state.reranked_chunks = [
                {
                    "text": c.text,
                    "score": c.final_score,
                    "source": c.source_label,
                    "metadata": c.metadata,
                }
                for c in result.reranked
            ]
            # Render context string to pass to LLM
            state.assembled_context = result.context.to_context_string(
                max_tokens=settings.context_max_tokens
            )
            # Extract citation labels for the UI
            state.citations = list(
                dict.fromkeys(c.source_label for c in result.reranked)
            )

            state.add_reasoning(
                f"Retrieved {len(result.raw_candidates)} candidates, "
                f"reranked to {len(result.reranked)} passages"
            )
            # Flag a grounded-context miss so the reasoning node won't fabricate
            # policy/account specifics out of parametric memory.
            state.metadata["retrieval_failed"] = False
            state.metadata["context_empty"] = len(result.reranked) == 0
            logger.info(
                "Retrieval node complete",
                candidates=len(result.raw_candidates),
                reranked=len(result.reranked),
                intent=state.detected_intent,
                session_id=state.session_id,
            )

        except Exception as exc:
            logger.error("Retrieval node failed", error=str(exc), session_id=state.session_id)
            state.error = f"retrieval_failed:{exc}"
            state.assembled_context = ""
            # Hard failure — the knowledge layer is down. The reasoning node must
            # escalate rather than answer from an empty context.
            state.metadata["retrieval_failed"] = True
            state.metadata["context_empty"] = True

        return state
