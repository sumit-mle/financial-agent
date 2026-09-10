"""
Observability — Langfuse tracing + structured span management.

Every agent turn is traced as a Langfuse trace with child spans for:
  - Intent classification
  - Query refinement
  - Retrieval (with retrieved passages logged)
  - LLM reasoning (prompt + response logged)
  - Validation (guardrail scores logged)
  - Action execution

In development: traces go to Langfuse Cloud or self-hosted.
If keys are not set: no-op tracer is used (zero overhead).

Maps to: "OBSERVABILITY & LEARNING — Logs & Traces" in the architecture.
"""
import contextlib
from typing import Any, Generator

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class NoOpSpan:
    """Null span — used when Langfuse is not configured."""

    def set_attribute(self, key: str, value: Any) -> None:
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


class LangfuseTracer:
    """
    Thin wrapper around the Langfuse Python SDK.
    Exposes span context managers and feedback logging.
    """

    def __init__(self) -> None:
        self._client = None
        if settings.observability_enabled:
            try:
                from langfuse import Langfuse  # type: ignore[import]
                self._client = Langfuse(
                    public_key=settings.langfuse_public_key,
                    secret_key=settings.langfuse_secret_key,
                    host=settings.langfuse_host,
                )
                logger.info("Langfuse tracer connected", host=settings.langfuse_host)
            except Exception as exc:
                logger.warning("Langfuse init failed — using no-op tracer", error=str(exc))

    @contextlib.contextmanager
    def start_span(
        self,
        name: str,
        session_id: str = "",
        **attributes: Any,
    ) -> Generator:
        """Context manager that wraps a logical unit of work in a Langfuse span."""
        if self._client is None:
            span = NoOpSpan()
            yield span
            return

        trace = self._client.trace(
            name=name,
            session_id=session_id or None,
            metadata=attributes,
        )
        try:
            yield trace
        finally:
            try:
                trace.update(output=attributes)
            except Exception:
                pass

    def log_llm_call(
        self,
        session_id: str,
        prompt: str,
        response: str,
        model: str = "",
        usage: dict | None = None,
        metadata: dict | None = None,
    ) -> None:
        """Log a single LLM call — prompt, response, token usage."""
        if self._client is None:
            return
        try:
            self._client.generation(
                name="llm_call",
                session_id=session_id or None,
                model=model or settings.openai_model,
                input=prompt,
                output=response,
                usage=usage,
                metadata=metadata,
            )
        except Exception as exc:
            logger.debug("Langfuse log_llm_call failed", error=str(exc))

    def log_retrieval(
        self,
        session_id: str,
        query: str,
        retrieved: list[dict],
        metadata: dict | None = None,
    ) -> None:
        """Log retrieval results for RAG quality monitoring."""
        if self._client is None:
            return
        try:
            self._client.span(
                name="retrieval",
                session_id=session_id or None,
                input={"query": query},
                output={"retrieved_count": len(retrieved), "chunks": retrieved[:3]},
                metadata=metadata,
            )
        except Exception as exc:
            logger.debug("Langfuse log_retrieval failed", error=str(exc))

    def log_feedback(
        self,
        session_id: str,
        turn_id: str,
        rating: int,
        helpful: bool,
        comment: str | None = None,
    ) -> None:
        """Log customer feedback — feeds the learn-and-improve loop."""
        if self._client is None:
            logger.info(
                "Feedback (no-op tracer)",
                session_id=session_id,
                rating=rating,
                helpful=helpful,
            )
            return
        try:
            self._client.score(
                trace_id=turn_id,
                name="customer_feedback",
                value=rating / 5.0,
                comment=f"helpful={helpful}" + (f" | {comment}" if comment else ""),
            )
        except Exception as exc:
            logger.debug("Langfuse log_feedback failed", error=str(exc))

    def flush(self) -> None:
        """Force-flush pending events. Call at shutdown."""
        if self._client:
            try:
                self._client.flush()
            except Exception:
                pass


# ── Evaluation pipeline ──────────────────────────────────────────────────────

class RAGEvaluator:
    """
    Automated RAG evaluation using RAGAS metrics.
    Runs offline against a golden test set to track quality over time.

    Metrics tracked:
      - Faithfulness      (is the answer grounded in context?)
      - Answer Relevancy  (is the answer relevant to the question?)
      - Context Precision (are the retrieved chunks precise?)
      - Context Recall    (are all necessary chunks retrieved?)

    Target production thresholds (from marsdevs.com 2026 guide):
      faithfulness >= 0.90
      answer_relevancy >= 0.85
      context_precision >= 0.80
    """

    THRESHOLDS = {
        "faithfulness": 0.90,
        "answer_relevancy": 0.85,
        "context_precision": 0.80,
    }

    def evaluate_batch(
        self,
        questions: list[str],
        answers: list[str],
        contexts: list[list[str]],
        ground_truths: list[str] | None = None,
    ) -> dict[str, float]:
        """
        Run RAGAS evaluation on a batch of QA pairs.

        Requires: pip install ragas datasets  (not in main requirements.txt)

        Production thresholds (marsdevs.com 2026 guide):
          faithfulness >= 0.90
          answer_relevancy >= 0.85
          context_precision >= 0.80
        """
        try:
            from datasets import Dataset  # type: ignore[import]
            from ragas import evaluate  # type: ignore[import]
            from ragas.metrics import (  # type: ignore[import]
                answer_relevancy,
                context_precision,
                faithfulness,
            )
        except ImportError:
            logger.warning(
                "RAGAS not installed — skipping evaluation. "
                "Install with: pip install ragas datasets"
            )
            return {}

        data = {
            "question": questions,
            "answer": answers,
            "contexts": contexts,
        }
        if ground_truths:
            data["ground_truth"] = ground_truths

        dataset = Dataset.from_dict(data)
        metrics = [faithfulness, answer_relevancy, context_precision]

        try:
            result = evaluate(dataset, metrics=metrics)
            scores = {k: round(float(v), 4) for k, v in result.items()}

            # Log threshold violations
            for metric, threshold in self.THRESHOLDS.items():
                score = scores.get(metric, 0.0)
                if score < threshold:
                    logger.warning(
                        "RAG metric below threshold",
                        metric=metric,
                        score=score,
                        threshold=threshold,
                    )

            logger.info("RAGAS evaluation complete", scores=scores)
            return scores
        except Exception as exc:
            logger.error("RAGAS evaluation failed", error=str(exc))
            return {}


# ── Singleton ─────────────────────────────────────────────────────────────────
_tracer_instance: LangfuseTracer | None = None


def get_tracer() -> LangfuseTracer:
    """Return the global tracer singleton."""
    global _tracer_instance
    if _tracer_instance is None:
        _tracer_instance = LangfuseTracer()
    return _tracer_instance
