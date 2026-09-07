"""
Node: Query Refinement (Layer 2)

Rephrases, expands, and decomposes the user query to improve
retrieval quality. A poorly phrased question like "why charge me?"
becomes "Why was an unexpected charge applied to my account?
What is the dispute process for unauthorized transactions?"

Maps to: "Query Refinement — Rephrases, expand, decompose" in the architecture.
"""
from app.agent.state import AgentState
from app.core.logging import get_logger

logger = get_logger(__name__)

_REFINEMENT_PROMPT = """You are a query refinement assistant for a financial customer support system.

Your job: Take a customer's raw message and rewrite it as a clear, detailed search query
that will retrieve the most relevant information from a financial knowledge base.

Rules:
1. Expand abbreviations and informal language into precise financial terminology.
2. Add context from the intent category if helpful.
3. If the message implies multiple sub-questions, list them separated by newlines.
4. Keep the refinement under 200 words.
5. Do NOT answer the question — only refine it for search.

Intent detected: {intent}
Customer message: "{message}"

Return ONLY the refined search query text, nothing else.
"""


class QueryRefinerNode:
    """
    Refines the user query for better vector search performance.

    If no LLM is available, applies simple rule-based expansion.
    """

    # Intent-specific expansion terms to append when no LLM is available
    _INTENT_EXPANSIONS: dict[str, str] = {
        "complaint_status": "complaint case status update resolution timeline",
        "account_inquiry": "account balance statement history credit report",
        "payment_issue": "payment dispute refund reversal charge transaction",
        "policy_question": "bank policy regulation rule fee terms consumer rights CFPB FDIC",
        "product_question": "loan mortgage eligibility credit card application interest rate",
        "fraud_report": "fraud unauthorized transaction identity theft account compromise security",
        "general": "",
    }

    def __init__(self, llm_client=None) -> None:
        self._llm = llm_client

    def _rule_based_refine(self, state: AgentState) -> str:
        """Simple rule-based expansion when LLM is not available."""
        base = state.user_message.strip()
        expansion = self._INTENT_EXPANSIONS.get(state.detected_intent, "")
        if expansion:
            return f"{base} {expansion}"
        return base

    async def run(self, state: AgentState) -> AgentState:
        """Refine the query and store result in state.refined_query."""
        if not state.user_message.strip():
            state.refined_query = state.user_message
            return state

        if self._llm is None:
            state.refined_query = self._rule_based_refine(state)
            state.add_reasoning(f"Query refined (rule-based): '{state.refined_query[:80]}...'")
            return state

        try:
            prompt = _REFINEMENT_PROMPT.format(
                intent=state.detected_intent,
                message=state.user_message,
            )
            response = await self._llm.ainvoke(prompt)
            content = response.content if hasattr(response, "content") else str(response)
            state.refined_query = content.strip()
        except Exception as exc:
            logger.warning("Query refinement LLM failed, using rule-based", error=str(exc))
            state.refined_query = self._rule_based_refine(state)

        state.add_reasoning(f"Query refined to: '{state.refined_query[:80]}...'")
        logger.debug(
            "Query refined",
            original=state.user_message[:60],
            refined=state.refined_query[:60],
        )
        return state
