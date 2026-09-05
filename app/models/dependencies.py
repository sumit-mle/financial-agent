"""
Dependency injection — lazy singletons for FastAPI request handlers.

All heavy objects (LLM clients, RAG pipeline, FinAgent) are created
on first use, not at import time. This prevents startup crashes when
optional credentials (OPENAI_API_KEY) aren't set.
"""
from functools import lru_cache

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


@lru_cache(maxsize=1)
def get_rag_pipeline():
    """Singleton RAGPipeline — embedder + Qdrant client loaded once."""
    from app.retrieval.rag_pipeline import RAGPipeline
    logger.info("Initialising RAGPipeline singleton")
    return RAGPipeline()


@lru_cache(maxsize=1)
def get_llm_client():
    """
    Singleton LLM client. Returns None if no provider is configured —
    the agent falls back to heuristic responses gracefully.
    """
    if not settings.openai_api_key and settings.llm_provider == "openai":
        logger.warning(
            "OPENAI_API_KEY is not set — agent will use heuristic fallbacks. "
            "Set OPENAI_API_KEY in .env to enable full LLM responses."
        )
        return None
    try:
        from app.models.llm_factory import get_default_llm
        return get_default_llm()
    except Exception as exc:
        logger.warning("LLM client init failed", error=str(exc))
        return None


@lru_cache(maxsize=1)
def get_fast_llm_client():
    """Cheaper LLM for guardrail evaluations. Falls back to main LLM."""
    if not settings.openai_api_key and settings.llm_provider == "openai":
        return None
    try:
        from app.models.llm_factory import get_fast_llm
        return get_fast_llm()
    except Exception as exc:
        logger.warning("Fast LLM client init failed", error=str(exc))
        return None


@lru_cache(maxsize=1)
def get_guardrails():
    """Singleton GuardrailModels."""
    from app.models.guardrails import GuardrailModels
    return GuardrailModels(llm_client=get_fast_llm_client())


@lru_cache(maxsize=1)
def get_validator():
    """Singleton ResponseValidator."""
    from app.validation.validator import ResponseValidator
    return ResponseValidator(guardrails=get_guardrails())


@lru_cache(maxsize=1)
def get_fin_agent():
    """
    Singleton FinAgent with all dependencies injected.
    Safe to call even without OPENAI_API_KEY — agent degrades gracefully.
    """
    from app.agent.graph import FinAgent
    logger.info("Initialising FinAgent singleton")
    return FinAgent(
        llm_client=get_llm_client(),
        rag_pipeline=get_rag_pipeline(),
    )
