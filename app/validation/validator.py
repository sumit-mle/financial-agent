"""
Post-Generation Validation (Layer 6)

Runs every LLM response through six checks before delivery:
  1. Grounding Check       — claims supported by retrieved context
  2. Factual Consistency   — no internal contradictions
  3. Policy & Compliance   — no regulated advice slipping through
  4. Confidence Score      — composite score from guardrail models
  5. Escalation Decision   — final escalation gate
  6. Learn & Improve       — feedback loop signal (logged to Langfuse)

Maps to: "POST-GENERATION VALIDATION & OUTCOME" (Layer 6) in the architecture.
"""
import re
from dataclasses import dataclass

from app.agent.state import AgentState
from app.core.config import settings
from app.core.logging import get_logger
from app.models.guardrails import GuardrailModels, GuardrailSuite

logger = get_logger(__name__)


@dataclass
class ValidationResult:
    """Outcome of the full validation pipeline."""
    passed: bool
    final_response: str
    guardrail_scores: dict
    should_escalate: bool
    escalation_reason: str
    policy_violations: list[str]
    confidence_score: float


# ── Policy compliance patterns (post-LLM filter) ──────────────────────────────
_POLICY_VIOLATIONS = [
    (re.compile(r"\byou should (invest|buy|sell)\b", re.IGNORECASE), "investment_advice"),
    (re.compile(r"\bguaranteed (return|profit|yield)\b", re.IGNORECASE), "guarantee_claim"),
    (re.compile(r"\byour (SSN|social security|password) is\b", re.IGNORECASE), "pii_in_response"),
    (re.compile(r"\bI (made up|fabricated|invented)\b", re.IGNORECASE), "hallucination_admission"),
]

_LOW_CONFIDENCE_DISCLAIMER = (
    "\n\n*Note: For complex issues or if this doesn't resolve your concern, "
    "our specialists are available 24/7.*"
)

_CITATION_FOOTER = "\n\n**Sources**: {citations}"


class ResponseValidator:
    """
    Runs the complete post-generation validation pipeline on an agent response.
    """

    def __init__(self, guardrails: GuardrailModels | None = None) -> None:
        self._guardrails = guardrails or GuardrailModels()

    def _check_policy_compliance(self, response: str) -> list[str]:
        """Return list of policy violation types found in the response."""
        violations = []
        for pattern, violation_type in _POLICY_VIOLATIONS:
            if pattern.search(response):
                violations.append(violation_type)
        return violations

    def _add_citations(self, response: str, citations: list[str]) -> str:
        """Append source citations to the response if available."""
        if citations:
            citation_str = " | ".join(f"[{c}]" for c in citations[:3])
            if citation_str not in response:
                return response + _CITATION_FOOTER.format(citations=citation_str)
        return response

    def _add_low_confidence_disclaimer(self, response: str) -> str:
        if _LOW_CONFIDENCE_DISCLAIMER not in response:
            return response + _LOW_CONFIDENCE_DISCLAIMER
        return response

    async def validate(self, state: AgentState) -> ValidationResult:
        """
        Full validation pipeline for a generated response.
        Returns ValidationResult with potentially modified response
        and final escalation decision.
        """
        response = state.final_response
        query = state.user_message
        context_excerpt = ""
        if state.reranked_chunks:
            context_excerpt = state.reranked_chunks[0].get("text", "")[:400]

        # ── 1. Policy compliance (deterministic, fast) ─────────────────────
        policy_violations = self._check_policy_compliance(response)
        if policy_violations:
            logger.warning(
                "Policy violations in LLM response — escalating",
                violations=policy_violations,
                session_id=state.session_id,
            )
            return ValidationResult(
                passed=False,
                final_response=(
                    "I need to connect you with a specialist for this request. "
                    "One of our team members will be in touch shortly."
                ),
                guardrail_scores={},
                should_escalate=True,
                escalation_reason=f"Policy violation: {policy_violations}",
                policy_violations=policy_violations,
                confidence_score=0.0,
            )

        # ── 2. Guardrail model evaluation ──────────────────────────────────
        suite: GuardrailSuite = await self._guardrails.evaluate(
            query=query,
            response=response,
            context_excerpt=context_excerpt,
        )

        composite_confidence = suite.composite_confidence

        # ── 3. Escalation decision ──────────────────────────────────────────
        should_escalate = state.should_escalate  # May already be set upstream
        escalation_reason = state.escalation_reason

        if suite.escalation_needed.passed and not should_escalate:
            should_escalate = True
            escalation_reason = f"Guardrail escalation model triggered (score={suite.escalation_needed.score:.2f})"

        if composite_confidence < settings.agent_escalation_threshold and not should_escalate:
            should_escalate = True
            escalation_reason = (
                f"Composite confidence too low ({composite_confidence:.2f} < "
                f"{settings.agent_escalation_threshold})"
            )

        # ── 4. Response enrichment ──────────────────────────────────────────
        final_response = response

        # Add citations when confidence is high enough to present sources
        if composite_confidence >= settings.agent_confidence_threshold and state.citations:
            final_response = self._add_citations(final_response, state.citations)

        # Add disclaimer for borderline confidence (not for escalations)
        if (
            settings.agent_escalation_threshold <= composite_confidence < settings.agent_confidence_threshold
            and not should_escalate
        ):
            final_response = self._add_low_confidence_disclaimer(final_response)

        validation_passed = (
            suite.groundedness.passed
            and suite.relevance.passed
            and not policy_violations
            and not should_escalate
        )

        logger.info(
            "Validation complete",
            passed=validation_passed,
            confidence=composite_confidence,
            should_escalate=should_escalate,
            groundedness=suite.groundedness.score,
            relevance=suite.relevance.score,
            session_id=state.session_id,
        )

        return ValidationResult(
            passed=validation_passed,
            final_response=final_response,
            guardrail_scores=suite.to_dict(),
            should_escalate=should_escalate,
            escalation_reason=escalation_reason,
            policy_violations=policy_violations,
            confidence_score=composite_confidence,
        )


class ValidationNode:
    """
    LangGraph node wrapper for ResponseValidator.
    Replaces the stub _deliver_response_node in graph.py.
    """

    def __init__(self, validator: ResponseValidator | None = None) -> None:
        self._validator = validator or ResponseValidator()

    async def run(self, state: AgentState) -> AgentState:
        """Validate the response and update state accordingly."""
        # Skip validation for safety short-circuits (already safe responses)
        if not state.safety_check_passed and state.final_response:
            return state

        # Guard: if LLM produced no response at all, set a safe fallback
        if not state.final_response or not state.final_response.strip():
            state.final_response = (
                "I wasn't able to generate a response for your request. "
                "Let me connect you with a specialist who can assist you directly."
            )
            state.should_escalate = True
            state.escalation_reason = "Empty LLM response"
            state.response_type = "escalation"
            return state

        result = await self._validator.validate(state)

        # Write validation results back to state
        state.final_response = result.final_response
        state.groundedness_score = result.guardrail_scores.get("groundedness", 0.0)
        state.confidence_score = result.confidence_score
        state.factual_issues = result.policy_violations
        state.policy_compliant = not bool(result.policy_violations)
        state.should_escalate = result.should_escalate
        state.escalation_reason = result.escalation_reason
        state.metadata["guardrail_scores"] = result.guardrail_scores

        # Determine response type
        if result.should_escalate:
            state.response_type = "escalation"
            state.final_response = (
                "I'm connecting you with a specialist who can best assist you.\n\n"
                f"**Reason**: {result.escalation_reason or 'Complex issue requiring human review'}\n\n"
                "A team member will reach out shortly. Your conversation summary has been shared."
            )
        elif state.agent_decision == "clarify":
            state.response_type = "clarification"
        elif state.actions_taken:
            state.response_type = "action_confirmation"
        else:
            state.response_type = "answer"

        state.add_reasoning(
            f"Validation: passed={result.passed}, confidence={result.confidence_score:.2f}, "
            f"escalate={result.should_escalate}"
        )
        return state
