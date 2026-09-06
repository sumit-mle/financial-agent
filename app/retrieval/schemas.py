"""
Shared data models for the retrieval layer.
These flow through retriever → reranker → context assembler → LLM.
"""
from dataclasses import dataclass, field
from typing import Any


@dataclass
class RetrievedChunk:
    """
    A single chunk returned from the vector store,
    optionally re-scored by the reranker.
    """
    text: str
    score: float                          # Cosine similarity from vector search
    rerank_score: float | None = None     # Score from reranker (higher = more relevant)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def final_score(self) -> float:
        """Use rerank score if available, else vector score."""
        return self.rerank_score if self.rerank_score is not None else self.score

    @property
    def source_label(self) -> str:
        """Human-readable source tag for citation."""
        src = self.metadata.get("source", "unknown")
        company = self.metadata.get("company", "")
        product = self.metadata.get("product", "")
        if src == "cfpb":
            return f"CFPB Complaint ({product})" if product else "CFPB Complaint"
        if src == "sec_edgar":
            return f"{company} 10-K" if company else "SEC Filing"
        if src in ("policy_pdf", "policy_pdf_local"):
            return self.metadata.get("document_name", "Policy Document")
        return src.replace("_", " ").title()


@dataclass
class AssembledContext:
    """
    Final context package delivered to the LLM.
    Combines top-ranked passages + structured customer/action data.
    """
    # Core retrieved passages
    passages: list[RetrievedChunk] = field(default_factory=list)

    # Customer/transaction data injected from CRM (Layer 5)
    customer_data: dict[str, Any] = field(default_factory=dict)

    # Available agent actions for this customer
    available_actions: list[str] = field(default_factory=list)

    # Recent conversation history (last N turns)
    conversation_history: list[dict[str, str]] = field(default_factory=list)

    # System instructions and policies (always included)
    system_instructions: str = ""

    # Metadata about the retrieval
    query: str = ""
    collections_searched: list[str] = field(default_factory=list)
    total_candidates: int = 0

    def to_context_string(self, max_tokens: int = 8000) -> str:
        """
        Render the assembled context as a single string for the LLM prompt.
        Respects max_tokens budget (approximate, by character count).
        """
        parts: list[str] = []
        char_budget = max_tokens * 4  # ~4 chars per token

        # ── System instructions ─────────────────────────────────────────────
        if self.system_instructions:
            parts.append(f"## System Instructions\n{self.system_instructions}")
            char_budget -= len(self.system_instructions)

        # ── Customer context ────────────────────────────────────────────────
        if self.customer_data:
            customer_str = "\n".join(
                f"  {k}: {v}" for k, v in self.customer_data.items()
            )
            section = f"## Customer Context\n{customer_str}"
            parts.append(section)
            char_budget -= len(section)

        # ── Available actions ───────────────────────────────────────────────
        if self.available_actions:
            actions_str = "\n".join(f"  - {a}" for a in self.available_actions)
            section = f"## Available Actions\n{actions_str}"
            parts.append(section)
            char_budget -= len(section)

        # ── Retrieved passages ───────────────────────────────────────────────
        if self.passages:
            passage_parts: list[str] = []
            for i, chunk in enumerate(self.passages, 1):
                if char_budget <= 0:
                    break
                citation = chunk.source_label
                passage = (
                    f"[{i}] Source: {citation} (score: {chunk.final_score:.3f})\n"
                    f"{chunk.text}"
                )
                passage_parts.append(passage)
                char_budget -= len(passage)
            parts.append("## Relevant Knowledge\n" + "\n\n".join(passage_parts))

        # ── Conversation history ─────────────────────────────────────────────
        if self.conversation_history:
            history_parts = []
            for turn in self.conversation_history[-6:]:  # Last 6 turns max
                role = turn.get("role", "user").capitalize()
                content = turn.get("content", "")
                history_parts.append(f"{role}: {content}")
            parts.append("## Conversation History\n" + "\n".join(history_parts))

        return "\n\n".join(parts)
