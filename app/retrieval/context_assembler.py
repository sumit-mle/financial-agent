"""
Context Assembler — combines top-ranked passages with structured
customer data, available actions, conversation history, and system
instructions into a single AssembledContext object.

This is the "CONTEXT ASSEMBLY → DELIVER TO LLM" block from Layer 3.

The assembled context feeds directly into the LLM prompt.
"""
from app.core.config import settings
from app.core.logging import get_logger
from app.retrieval.schemas import AssembledContext, RetrievedChunk

logger = get_logger(__name__)

# ── System prompt for the financial complaint agent ──────────────────────────
SYSTEM_INSTRUCTIONS = """You are Fin, an AI-powered financial customer support agent.

Your responsibilities:
1. Help customers resolve complaints about financial products (credit cards, loans, mortgages, banking).
2. Provide accurate, policy-grounded answers — always cite the source of your information.
3. Execute available actions (check status, reschedule payments, log complaints) when appropriate.
4. Escalate to a human agent when: confidence is low, the issue involves fraud, regulatory advice,
   or loan approval decisions.

Rules you must follow:
- NEVER make up account balances, transaction details, or policy terms.
- NEVER provide legal or investment advice.
- ALWAYS ground your answers in the provided knowledge context.
- If you don't know something, say so clearly rather than guessing.
- Keep responses concise, empathetic, and professional.
- If escalating, briefly explain why and summarize the conversation for the human agent.
"""

# Actions available to the agent — injected into context so the LLM knows
# what it can do. Actual execution happens in the action layer (Layer 5).
AVAILABLE_ACTIONS = [
    "lookup_complaint_status(complaint_id)",
    "lookup_account_summary(customer_id)",
    "lookup_transaction_history(customer_id, days=30)",
    "reschedule_payment(customer_id, new_date)",
    "create_complaint_ticket(customer_id, issue_description, product)",
    "update_complaint_status(complaint_id, status)",
    "send_notification(customer_id, message)",
    "escalate_to_human(reason, conversation_summary)",
]


class ContextAssembler:
    """
    Assembles the final context package from retrieved chunks
    plus structured data (customer profile, actions, history).

    This is what gets sent to the LLM — nothing more, nothing less.
    """

    def __init__(self, max_tokens: int | None = None) -> None:
        self.max_tokens = max_tokens or settings.context_max_tokens

    def assemble(
        self,
        query: str,
        ranked_chunks: list[RetrievedChunk],
        customer_data: dict | None = None,
        conversation_history: list[dict] | None = None,
        available_actions: list[str] | None = None,
        collections_searched: list[str] | None = None,
        total_candidates: int = 0,
    ) -> AssembledContext:
        """
        Build a complete AssembledContext ready for LLM consumption.

        Args:
            query: The current user query.
            ranked_chunks: Reranked passages from the retriever.
            customer_data: Structured customer info from CRM (optional).
            conversation_history: Prior turns in this session (optional).
            available_actions: Override default action list (optional).
            collections_searched: Which Qdrant collections were searched.
            total_candidates: Total raw candidates before reranking.

        Returns:
            AssembledContext with all fields populated.
        """
        # Filter out very low-quality chunks even after reranking
        quality_chunks = [
            c for c in ranked_chunks
            if c.final_score >= 0.25 and len(c.text.strip()) >= 50
        ]

        if len(quality_chunks) < len(ranked_chunks):
            logger.debug(
                "Filtered low-quality chunks",
                before=len(ranked_chunks),
                after=len(quality_chunks),
            )

        context = AssembledContext(
            query=query,
            passages=quality_chunks,
            customer_data=customer_data or {},
            available_actions=available_actions or AVAILABLE_ACTIONS,
            conversation_history=conversation_history or [],
            system_instructions=SYSTEM_INSTRUCTIONS,
            collections_searched=collections_searched or [],
            total_candidates=total_candidates,
        )

        # Log context size for observability
        rendered = context.to_context_string(self.max_tokens)
        estimated_tokens = len(rendered) // 4
        logger.debug(
            "Context assembled",
            passages=len(quality_chunks),
            estimated_tokens=estimated_tokens,
            max_tokens=self.max_tokens,
            has_customer_data=bool(customer_data),
            history_turns=len(conversation_history or []),
        )

        if estimated_tokens > self.max_tokens * 0.9:
            logger.warning(
                "Context approaching token limit",
                estimated_tokens=estimated_tokens,
                limit=self.max_tokens,
            )

        return context
