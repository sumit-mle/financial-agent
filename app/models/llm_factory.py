"""
LLM Factory — creates and caches LLM clients based on settings.

Centralises all LLM provider setup so every node in the graph
uses the same configured client. Supports:
  - OpenAI (GPT-4o, GPT-4o-mini)
  - Anthropic (Claude 3.5 Sonnet)
  - Local via Ollama (Llama 3, Mistral — zero cost, fully offline)

The factory is called once at app startup and the client is injected
into every agent node that needs it.
"""
from functools import lru_cache
from typing import Any

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


def create_llm(
    provider: str | None = None,
    model: str | None = None,
    temperature: float = 0.1,
    max_tokens: int = 2048,
    streaming: bool = False,
    **kwargs: Any,
):
    """
    Create a LangChain-compatible async LLM client.

    Args:
        provider: "openai" | "anthropic" | "local". Defaults to settings.llm_provider.
        model: Model name override. Defaults to provider's configured model.
        temperature: Sampling temperature (low = more deterministic).
        max_tokens: Max output tokens.
        streaming: Enable streaming responses.

    Returns:
        LangChain BaseChatModel instance with async support.
    """
    _provider = provider or settings.llm_provider

    if _provider == "openai":
        return _create_openai(model, temperature, max_tokens, streaming, **kwargs)
    elif _provider == "anthropic":
        return _create_anthropic(model, temperature, max_tokens, streaming, **kwargs)
    elif _provider == "local":
        return _create_local(model, temperature, max_tokens, streaming, **kwargs)
    else:
        raise ValueError(f"Unknown LLM provider: {_provider}")


def _create_openai(model, temperature, max_tokens, streaming, **kwargs):
    from langchain_openai import ChatOpenAI  # type: ignore[import]

    _model = model or settings.openai_model
    logger.info("Creating OpenAI LLM client", model=_model)

    return ChatOpenAI(
        api_key=settings.openai_api_key,
        model=_model,
        temperature=temperature,
        max_tokens=max_tokens,
        streaming=streaming,
        timeout=settings.llm_timeout_seconds,
        max_retries=settings.llm_max_retries,
        **kwargs,
    )


def _create_anthropic(model, temperature, max_tokens, streaming, **kwargs):
    from langchain_anthropic import ChatAnthropic  # type: ignore[import]

    _model = model or settings.anthropic_model
    logger.info("Creating Anthropic LLM client", model=_model)

    return ChatAnthropic(
        api_key=settings.anthropic_api_key,
        model_name=_model,
        temperature=temperature,
        max_tokens=max_tokens,
        streaming=streaming,
        timeout=settings.llm_timeout_seconds,
        max_retries=settings.llm_max_retries,
        **kwargs,
    )


def _create_local(model, temperature, max_tokens, streaming, **kwargs):
    """
    Local LLM via Ollama — zero cost, fully offline.
    Install: https://ollama.com — then: ollama pull llama3
    """
    try:
        from langchain_community.chat_models import ChatOllama  # type: ignore[import]
    except ImportError:
        raise ImportError(
            "langchain-community not installed for local LLM. "
            "Run: pip install langchain-community"
        )

    _model = model or "llama3"
    logger.info("Creating local Ollama LLM client", model=_model)

    return ChatOllama(
        model=_model,
        temperature=temperature,
        num_predict=max_tokens,
        timeout=settings.llm_timeout_seconds,
        **kwargs,
    )


@lru_cache(maxsize=4)
def get_default_llm():
    """Return the cached default LLM client for the configured provider."""
    return create_llm(
        provider=settings.llm_provider,
        temperature=0.1,      # Low temp = consistent, reliable answers
        max_tokens=2048,
        streaming=False,
    )


@lru_cache(maxsize=2)
def get_fast_llm():
    """
    A cheaper/faster LLM for classification and refinement tasks.
    Uses gpt-4o-mini for OpenAI — same quality for short tasks, lower cost.
    """
    if settings.llm_provider == "openai":
        return create_llm(provider="openai", model="gpt-4o-mini", temperature=0.0)
    return get_default_llm()
