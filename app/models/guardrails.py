"""
Guardrail Models (Layer 4 — Evaluation / Guardrail Models)

Five specialised evaluators that run on every LLM response before delivery:

  1. GroundednessModel    — Is the answer supported by retrieved context?
  2. RelevanceModel       — Is the response relevant to the query?
  3. ConfidenceModel      — Overall confidence score (composite)
  4. EscalationModel      — Should this be escalated to a human?
  5. CustomerResponseModel — Is the response clear and appropriate for a customer?

These map directly to the "EVALUATION / GUARDRAIL MODELS" block in Layer 4.
Each model returns a score (0.0–1.0) plus a brief reason string.

All evaluators share a single LLM client (injected) to minimise cold-start.
For production, these can run concurrently with asyncio.gather().
"""
import json
import re
from dataclasses import dataclass

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class GuardrailResult:
    """Result from a single guardrail model."""
    score: float           # 0.0–1.0
    passed: bool           # True if above threshold
    reason: str            # Brief explanation
    model_name: str


@dataclass
class GuardrailSuite:
    """Aggregated results from all guardrail models."""
    groundedness: GuardrailResult
    relevance: GuardrailResult
    confidence: GuardrailResult
    escalation_needed: GuardrailResult
    customer_appropriateness: GuardrailResult

    @property
    def overall_passed(self) -> bool:
        return (
            self.groundedness.passed
            and self.relevance.passed
            and self.customer_appropriateness.passed
            and not self.escalation_needed.passed  # escalation_needed.passed means SHOULD escalate
        )

    @property
    def composite_confidence(self) -> float:
        """Weighted average of key scores."""
        return (
            self.groundedness.score * 0.35
            + self.relevance.score * 0.25
            + self.confidence.score * 0.25
            + self.customer_appropriateness.score * 0.15
        )

    def to_dict(self) -> dict:
        return {
            "groundedness": self.groundedness.score,
            "relevance": self.relevance.score,
            "confidence": self.confidence.score,
            "escalation_needed": self.escalation_needed.score,
            "customer_appropriateness": self.customer_appropriateness.score,
            "overall_passed": self.overall_passed,
            "composite_confidence": round(self.composite_confidence, 3),
        }


# ── Prompt templates ──────────────────────────────────────────────────────────

_EVAL_PROMPT = """You are an evaluator for a financial AI customer support system.
Evaluate the following response on the given criterion.

Query: "{query}"
Response: "{response}"
Retrieved Context (excerpt): "{context_excerpt}"

Criterion: {criterion}
Description: {description}

Respond with ONLY this JSON:
{{"score": <0.0 to 1.0>, "passed": <true|false>, "reason": "<one sentence>"}}
"""

_EVALUATORS = {
    "groundedness": {
        "criterion": "Groundedness",
        "description": (
            "Is the response factually grounded in the retrieved context? "
            "Score 1.0 if every claim traces to the context. "
            "Score 0.0 if the response contains invented facts not in the context."
        ),
        "threshold": 0.70,
    },
    "relevance": {
        "criterion": "Relevance",
        "description": (
            "Does the response directly address the customer's query? "
            "Score 1.0 if fully on-topic. Score 0.0 if completely off-topic."
        ),
        "threshold": 0.65,
    },
    "confidence": {
        "criterion": "Confidence",
        "description": (
            "How confident should we be in this response? "
            "Consider: completeness, specificity, and absence of hedging language. "
            "Score 1.0 = fully confident, complete answer. Score 0.0 = very uncertain."
        ),
        "threshold": 0.60,
    },
    "escalation": {
        "criterion": "Escalation Need",
        "description": (
            "Should this query be escalated to a human agent? "
            "Score 1.0 = DEFINITELY escalate (fraud, legal, complex complaint, low confidence). "
            "Score 0.0 = no escalation needed, AI can handle fully."
        ),
        "threshold": 0.60,  # score > threshold means SHOULD escalate
    },
    "customer_appropriateness": {
        "criterion": "Customer Appropriateness",
        "description": (
            "Is the response clear, empathetic, professional, and appropriate for "
            "a financial customer support context? No jargon, no blame, concise. "
            "Score 1.0 = excellent tone and clarity. Score 0.0 = inappropriate or confusing."
        ),
        "threshold": 0.70,
    },
}


class GuardrailModels:
    """
    Runs all five evaluation models on an LLM response.
    Falls back to heuristic scoring if LLM is unavailable.
    """

    def __init__(self, llm_client=None) -> None:
        self._llm = llm_client

    async def _evaluate_single(
        self,
        evaluator_key: str,
        query: str,
        response: str,
        context_excerpt: str,
    ) -> GuardrailResult:
        """Run a single evaluator via LLM."""
        cfg = _EVALUATORS[evaluator_key]

        if self._llm is None:
            return self._heuristic_score(evaluator_key, query, response, context_excerpt)

        prompt = _EVAL_PROMPT.format(
            query=query[:300],
            response=response[:500],
            context_excerpt=context_excerpt[:400],
            criterion=cfg["criterion"],
            description=cfg["description"],
        )

        try:
            resp = await self._llm.ainvoke(prompt)
            content = resp.content if hasattr(resp, "content") else str(resp)
            # Extract JSON
            match = re.search(r"\{[\s\S]+?\}", content)
            if match:
                parsed = json.loads(match.group(0))
                score = float(parsed.get("score", 0.5))
                passed = bool(parsed.get("passed", score >= cfg["threshold"]))
                reason = str(parsed.get("reason", ""))
                return GuardrailResult(
                    score=score,
                    passed=passed,
                    reason=reason,
                    model_name=evaluator_key,
                )
        except Exception as exc:
            logger.warning(
                "Guardrail LLM eval failed, using heuristic",
                evaluator=evaluator_key,
                error=str(exc),
            )

        return self._heuristic_score(evaluator_key, query, response, context_excerpt)

    def _heuristic_score(
        self,
        evaluator_key: str,
        query: str,
        response: str,
        context_excerpt: str,
    ) -> GuardrailResult:
        """Rule-based fallback when LLM is unavailable."""
        cfg = _EVALUATORS[evaluator_key]
        score = 0.70  # Optimistic default

        if evaluator_key == "groundedness":
            # Check if response shares keywords with context
            resp_words = set(response.lower().split())
            ctx_words = set(context_excerpt.lower().split())
            overlap = len(resp_words & ctx_words) / max(len(resp_words), 1)
            score = min(0.95, 0.40 + overlap * 1.5)

        elif evaluator_key == "relevance":
            # Check query-response word overlap
            q_words = set(query.lower().split())
            r_words = set(response.lower().split())
            overlap = len(q_words & r_words) / max(len(q_words), 1)
            score = min(0.95, 0.50 + overlap)

        elif evaluator_key == "confidence":
            # Penalise hedging phrases
            hedges = ["i'm not sure", "i don't know", "unclear", "might be", "possibly"]
            penalty = sum(1 for h in hedges if h in response.lower()) * 0.10
            score = max(0.30, 0.80 - penalty)

        elif evaluator_key == "escalation":
            # Check for high-risk phrases
            escalation_triggers = ["fraud", "legal", "lawsuit", "stolen", "unauthorized"]
            score = 0.10  # Default: don't escalate
            if any(t in response.lower() for t in escalation_triggers):
                score = 0.80

        elif evaluator_key == "customer_appropriateness":
            # Check for inappropriate length or tone markers
            too_short = len(response) < 30
            too_long = len(response) > 1500
            score = 0.80 if not (too_short or too_long) else 0.50

        threshold = cfg["threshold"]
        passed = score >= threshold
        if evaluator_key == "escalation":
            passed = score >= threshold  # passed=True means SHOULD escalate

        return GuardrailResult(
            score=round(score, 3),
            passed=passed,
            reason=f"Heuristic evaluation (score={score:.2f})",
            model_name=evaluator_key,
        )

    async def evaluate(
        self,
        query: str,
        response: str,
        context_excerpt: str = "",
    ) -> GuardrailSuite:
        """
        Run all five guardrail evaluators concurrently.

        Args:
            query: The original user query.
            response: The LLM-generated response to evaluate.
            context_excerpt: Snippet of the retrieved context for grounding check.

        Returns:
            GuardrailSuite with all five results.
        """
        import asyncio

        results = await asyncio.gather(
            self._evaluate_single("groundedness", query, response, context_excerpt),
            self._evaluate_single("relevance", query, response, context_excerpt),
            self._evaluate_single("confidence", query, response, context_excerpt),
            self._evaluate_single("escalation", query, response, context_excerpt),
            self._evaluate_single("customer_appropriateness", query, response, context_excerpt),
        )

        suite = GuardrailSuite(
            groundedness=results[0],
            relevance=results[1],
            confidence=results[2],
            escalation_needed=results[3],
            customer_appropriateness=results[4],
        )

        logger.info(
            "Guardrail evaluation complete",
            scores=suite.to_dict(),
            overall_passed=suite.overall_passed,
        )
        return suite
