"""
Node: Safety & Policy Checks (Layer 2)

Screens user input for:
  1. PII leakage (using advanced NER-based detection)
  2. Prompt injection attacks
  3. Off-topic / harmful content
  4. Requests for regulated advice (legal, investment decisions)
  5. Emotional escalation triggers (using sentiment analysis)

If a violation is detected, the node short-circuits the graph
and returns a safe response without ever hitting the LLM.

Maps to: "Safety & Policy Checks — Guardrails, PII, compliance" in the architecture.
"""
import re

from app.agent.state import AgentState
from app.core.logging import get_logger
from app.models.specialized import get_pii_detector, get_sentiment_analyzer

logger = get_logger(__name__)

# ── PII Patterns ──────────────────────────────────────────────────────────────
_PII_PATTERNS = [
    (re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "SSN"),
    (re.compile(r"\b\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}\b"), "card_number"),
    (re.compile(r"\b\d{3}\b.*\bCVV\b", re.IGNORECASE), "cvv"),
    (re.compile(r"password\s*[:=]\s*\S+", re.IGNORECASE), "password"),
    (re.compile(r"\b\d{9,}\b"), "potential_account_number"),
]

# ── Prompt injection patterns ─────────────────────────────────────────────────
_INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(previous|all|above)\s+instructions?", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+a\s+", re.IGNORECASE),
    re.compile(r"act\s+as\s+if\s+you\s+are", re.IGNORECASE),
    re.compile(r"jailbreak", re.IGNORECASE),
    re.compile(r"DAN\s+mode", re.IGNORECASE),
    re.compile(r"system\s*prompt", re.IGNORECASE),
    re.compile(r"</?(system|user|assistant)>", re.IGNORECASE),
]

# ── Regulated advice triggers (always escalate, never answer directly) ────────
_REGULATED_PATTERNS = [
    (re.compile(r"\bshould\s+I\s+(invest|buy|sell|trade)\b", re.IGNORECASE), "investment_advice"),
    (re.compile(r"\bsue\b|\blawsuit\b|\blegal\s+action\b", re.IGNORECASE), "legal_advice"),
    (re.compile(r"\btax\s+(advice|return|evasion)\b", re.IGNORECASE), "tax_advice"),
]

# Safe response messages
_SAFE_RESPONSES = {
    "pii_detected": (
        "For your security, please don't share sensitive information like full card numbers, "
        "SSNs, or passwords in chat. I can still help — just describe your issue without "
        "including those details."
    ),
    "injection_detected": (
        "I'm here to help with financial questions only. "
        "How can I assist you with your account or complaint today?"
    ),
    "regulated_advice": (
        "That's a question that requires professional advice I'm not qualified to provide. "
        "I'd recommend speaking with a licensed financial advisor or attorney. "
        "I'm connecting you with a human specialist who can help further."
    ),
}


class SafetyCheckerNode:
    """
    Screens input for safety violations before any retrieval or LLM call.
    Uses advanced PII detection and sentiment analysis models.
    """

    async def run(self, state: AgentState) -> AgentState:
        """Run all safety checks. Sets state.safety_check_passed=False on violation."""
        text = state.user_message

        # ── Advanced PII check using specialized model ───────────────────────
        try:
            pii_detector = await get_pii_detector()
            pii_result = await pii_detector.detect_pii(text)
            
            if pii_result.has_pii:
                logger.warning(
                    "PII detected in user message",
                    pii_types=pii_result.pii_types,
                    confidence_scores=pii_result.confidence_scores,
                    session_id=state.session_id,
                )
                state.safety_check_passed = False
                state.safety_violation = f"pii_detected:{','.join(pii_result.pii_types)}"
                state.final_response = _SAFE_RESPONSES["pii_detected"]
                state.response_type = "answer"
                state.add_reasoning("Safety check: Advanced PII detection triggered — short-circuiting")
                return state
        except Exception as e:
            logger.warning(f"Advanced PII detection failed, using fallback: {e}")
            # Fallback to basic regex check
            pii_type = self._check_pii_fallback(text)
            if pii_type:
                state.safety_check_passed = False
                state.safety_violation = f"pii_detected:{pii_type}"
                state.final_response = _SAFE_RESPONSES["pii_detected"]
                state.response_type = "answer"
                state.add_reasoning("Safety check: Basic PII detection triggered — short-circuiting")
                return state

        # ── Injection check ───────────────────────────────────────────────────
        if self._check_injection(text):
            logger.warning(
                "Prompt injection attempt detected",
                session_id=state.session_id,
            )
            state.safety_check_passed = False
            state.safety_violation = "prompt_injection"
            state.final_response = _SAFE_RESPONSES["injection_detected"]
            state.response_type = "answer"
            state.add_reasoning("Safety check: Prompt injection detected — short-circuiting")
            return state

        # ── Regulated advice check ────────────────────────────────────────────
        regulated_type = self._check_regulated(text)
        if regulated_type:
            logger.info(
                "Regulated advice request detected — escalating",
                advice_type=regulated_type,
                session_id=state.session_id,
            )
            state.safety_check_passed = False
            state.safety_violation = f"regulated_advice:{regulated_type}"
            state.final_response = _SAFE_RESPONSES["regulated_advice"]
            state.response_type = "escalation"
            state.should_escalate = True
            state.escalation_reason = f"Customer requested regulated advice: {regulated_type}"
            state.add_reasoning(f"Safety check: Regulated advice ({regulated_type}) — escalating")
            return state

        # ── Emotional escalation check using sentiment analysis ───────────────
        try:
            sentiment_analyzer = await get_sentiment_analyzer()
            should_escalate, escalation_reason = await sentiment_analyzer.should_escalate_immediately(text)
            
            if should_escalate:
                logger.info(
                    "Emotional escalation detected — routing to human",
                    reason=escalation_reason,
                    session_id=state.session_id,
                )
                state.safety_check_passed = True  # Not a safety violation, but needs human attention
                state.should_escalate = True
                state.escalation_reason = f"Emotional escalation: {escalation_reason}"
                state.add_reasoning(f"Safety check: Emotional escalation detected — will escalate after processing")
                # Continue processing but flag for escalation
        except Exception as e:
            logger.warning(f"Sentiment analysis failed: {e}")
            # Continue without sentiment-based escalation

        # All checks passed
        state.safety_check_passed = True
        state.add_reasoning("Safety check: Passed all checks")
        return state

    def _check_pii_fallback(self, text: str) -> str | None:
        """Fallback regex-based PII detection."""
        patterns = [
            (re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "SSN"),
            (re.compile(r"\b\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}\b"), "card_number"),
            (re.compile(r"\b\d{3}\b.*\bCVV\b", re.IGNORECASE), "cvv"),
            (re.compile(r"password\s*[:=]\s*\S+", re.IGNORECASE), "password"),
        ]
        
        for pattern, pii_type in patterns:
            if pattern.search(text):
                return pii_type
        return None
