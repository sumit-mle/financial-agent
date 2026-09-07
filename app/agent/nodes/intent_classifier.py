"""
Node: Intent Understanding (Layer 2)

Classifies the user message into one of 7 intent categories.
Uses a lightweight zero-shot LLM call (fast, cheap).
Falls back to keyword heuristics if LLM is unavailable.

Maps to: "Intent Understanding — NLU, intent classification" in the architecture.
"""
from app.agent.state import AgentState, IntentCategory
from app.core.logging import get_logger

logger = get_logger(__name__)

# Keyword fallback rules — ordered from most specific to least
_KEYWORD_RULES: list[tuple[list[str], IntentCategory]] = [
    (["fraud", "unauthorized", "stolen", "identity theft", "scam"], "fraud_report"),
    (["complaint", "filed complaint", "complaint id", "complaint status", "case number"], "complaint_status"),
    (["payment", "charge", "transaction", "dispute", "refund", "overcharged",
      "double charged", "wrong amount", "reschedule"], "payment_issue"),
    (["balance", "statement", "account", "my account", "credit score",
      "credit report", "history"], "account_inquiry"),
    (["loan", "mortgage", "eligibility", "apply", "interest rate", "apr",
      "qualify", "credit card", "product"], "product_question"),
    (["policy", "regulation", "rule", "law", "requirement", "fee", "terms",
      "condition", "right", "cfpb", "fdic"], "policy_question"),
]

# Full intent descriptions for the LLM prompt
_INTENT_DESCRIPTIONS = """
- complaint_status: Customer asking about an existing complaint, case, or ticket status
- account_inquiry: Questions about account balance, statements, credit score, or account details
- payment_issue: Payment failures, disputes, charge reversals, refunds, or payment rescheduling
- policy_question: Questions about bank policies, fees, regulations, consumer rights, or legal requirements
- product_question: Questions about loan/mortgage eligibility, credit card features, or product applications
- fraud_report: Reports of unauthorized transactions, stolen card, identity theft, or account compromise
- general: Everything else — greetings, unclear intent, or off-topic messages
"""


class IntentClassifierNode:
    """
    Classifies user intent using LLM with keyword fallback.

    Fast path: keyword heuristic (< 1ms, no API call)
    Slow path: LLM zero-shot classification (50–200ms)
    """

    def __init__(self, llm_client=None) -> None:
        self._llm = llm_client  # Injected at graph construction time

    def _keyword_classify(self, text: str) -> tuple[IntentCategory, float]:
        """Rule-based fallback classifier."""
        text_lower = text.lower()
        for keywords, intent in _KEYWORD_RULES:
            if any(kw in text_lower for kw in keywords):
                return intent, 0.70  # Medium confidence for heuristic
        return "general", 0.50

    async def _llm_classify(self, text: str) -> tuple[IntentCategory, float]:
        """Zero-shot LLM classification."""
        if self._llm is None:
            return self._keyword_classify(text)

        prompt = f"""Classify the following customer message into exactly one intent category.

Intent categories:
{_INTENT_DESCRIPTIONS}

Customer message: "{text}"

Respond with ONLY a JSON object in this exact format:
{{"intent": "<category>", "confidence": <0.0 to 1.0>, "reasoning": "<one sentence>"}}
"""
        try:
            response = await self._llm.ainvoke(prompt)
            import json
            content = response.content if hasattr(response, "content") else str(response)
            # Extract JSON from response (handle markdown code blocks)
            if "```" in content:
                content = content.split("```")[1].strip()
                if content.startswith("json"):
                    content = content[4:].strip()
            parsed = json.loads(content)
            intent = parsed.get("intent", "general")
            confidence = float(parsed.get("confidence", 0.70))
            # Validate intent is one of our categories
            valid_intents = {
                "complaint_status", "account_inquiry", "payment_issue",
                "policy_question", "product_question", "fraud_report", "general"
            }
            if intent not in valid_intents:
                intent = "general"
            return intent, confidence  # type: ignore[return-value]
        except Exception as exc:
            logger.warning("LLM intent classification failed, using keyword fallback", error=str(exc))
            return self._keyword_classify(text)

    async def run(self, state: AgentState) -> AgentState:
        """Classify intent and mutate state."""
        text = state.user_message.strip()
        if not text:
            state.detected_intent = "general"
            state.intent_confidence = 0.0
            return state

        # Primary intent classification
        intent, confidence = await self._llm_classify(text)
        state.detected_intent = intent
        state.intent_confidence = confidence
        
        # Enhanced classification with product detection
        try:
            from app.models.specialized import get_product_classifier
            product_classifier = await get_product_classifier()
            
            # Detect products for better routing
            product_result = await product_classifier.classify_products(text)
            
            # Store product information in state metadata
            state.metadata.update({
                "detected_products": product_result.all_products,
                "primary_product": product_result.primary_product,
                "routing_suggestions": product_result.routing_suggestions,
                "product_confidence": product_result.confidence_scores
            })
            
            # Adjust intent based on product classification for better accuracy
            if product_result.primary_product in ["debt_collection", "payday_loan"]:
                # High-risk products should escalate by default
                if intent == "general":
                    intent = "complaint_status"  # Treat as complaint for proper handling
                    state.detected_intent = intent
                    
            state.add_reasoning(
                f"Intent: '{intent}' (conf: {confidence:.2f}), "
                f"Products: {product_result.all_products[:2]}, "
                f"Routing: {product_result.routing_suggestions[0] if product_result.routing_suggestions else 'general'}"
            )
            
        except Exception as e:
            logger.warning(f"Product classification failed: {e}")
            state.add_reasoning(f"Intent classified as '{intent}' with confidence {confidence:.2f}")

        logger.info(
            "Intent classified",
            intent=intent,
            confidence=confidence,
            products=state.metadata.get("detected_products", []),
            session_id=state.session_id,
        )
        return state
