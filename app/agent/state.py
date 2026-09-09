"""
Agent state — the single shared object that flows through every
LangGraph node. Every node reads from it and writes back to it.

Design principles:
  - Immutable fields (set once, never changed): session_id, customer_id
  - Accumulating fields (append-only): messages, retrieved_chunks, actions_taken
  - Overwritable fields: current_intent, confidence_score, final_response
  - Control fields: next_action, should_escalate, iteration_count

The TypedDict approach gives us full static type checking + LangGraph
graph state reducers compatibility.
"""
from typing import Annotated, Any, Literal
import operator
from dataclasses import dataclass, field


# ── Intent categories (maps to BANKING77 labels, grouped into 7 buckets) ──────
IntentCategory = Literal[
    "complaint_status",      # "Where is my complaint?" / "Any update?"
    "account_inquiry",       # Balance, statements, account details
    "payment_issue",         # Payment failed, reschedule, dispute charge
    "policy_question",       # "What are your fees?" / regulatory Q&A
    "product_question",      # Loan eligibility, card features
    "fraud_report",          # Fraud detection — always escalate
    "general",               # Fallback / unclear
]

# ── Agent decision after each reasoning cycle ─────────────────────────────────
AgentDecision = Literal[
    "answer",           # Deliver response directly to customer
    "execute_action",   # Call an external API / take action
    "clarify",          # Ask customer for more information
    "escalate",         # Hand off to human agent
]


@dataclass
class AgentState:
    """
    Full mutable state for one agent turn (one customer message → one response).

    A new AgentState is created per conversation turn. Conversation history
    (prior turns) is passed in via `messages` from the session store.
    """

    # ── Session identifiers ───────────────────────────────────────────────────
    session_id: str = ""
    customer_id: str = ""
    turn_id: str = ""                      # Unique ID for this specific turn

    # ── Input ─────────────────────────────────────────────────────────────────
    user_message: str = ""                 # Current raw user input
    messages: list[dict[str, str]] = field(default_factory=list)  # Full history

    # ── Layer 2: Orchestration & Conversation Processing ─────────────────────
    detected_intent: IntentCategory = "general"
    intent_confidence: float = 0.0
    refined_query: str = ""               # After query refinement node
    safety_check_passed: bool = True
    safety_violation: str = ""            # If failed, the reason

    # ── Layer 3: RAG retrieval artifacts ──────────────────────────────────────
    retrieved_chunks: list[dict[str, Any]] = field(default_factory=list)
    reranked_chunks: list[dict[str, Any]] = field(default_factory=list)
    assembled_context: str = ""            # Final rendered context string

    # ── Layer 4: Model layer ──────────────────────────────────────────────────
    agent_decision: AgentDecision = "answer"
    action_to_execute: str = ""            # Which action tool to call
    action_parameters: dict[str, Any] = field(default_factory=dict)
    llm_response_raw: str = ""             # Raw LLM output before validation
    reasoning_trace: list[str] = field(default_factory=list)  # Chain-of-thought

    # ── Layer 5: Action execution ─────────────────────────────────────────────
    actions_taken: list[dict[str, Any]] = field(default_factory=list)
    action_results: list[dict[str, Any]] = field(default_factory=list)
    customer_data: dict[str, Any] = field(default_factory=dict)  # From CRM

    # ── Layer 6: Post-generation validation ───────────────────────────────────
    groundedness_score: float = 0.0        # 0.0–1.0, grounded in retrieved context
    confidence_score: float = 0.0          # 0.0–1.0, overall response confidence
    factual_issues: list[str] = field(default_factory=list)
    policy_compliant: bool = True
    should_escalate: bool = False
    escalation_reason: str = ""

    # ── Output ────────────────────────────────────────────────────────────────
    final_response: str = ""               # Validated response sent to customer
    response_type: Literal[
        "answer", "clarification", "action_confirmation", "escalation"
    ] = "answer"
    citations: list[str] = field(default_factory=list)  # Source labels for UI
    follow_up_suggestions: list[str] = field(default_factory=list)

    # ── Control ───────────────────────────────────────────────────────────────
    iteration_count: int = 0
    error: str = ""                        # Set if any node fails
    metadata: dict[str, Any] = field(default_factory=dict)
    # Set by ReasoningNode when streaming=True; the SSE endpoint iterates it.
    streaming_generator: Any = None        # AsyncGenerator[str, None] | None

    def add_message(self, role: str, content: str) -> None:
        """Append a message to the conversation history."""
        self.messages.append({"role": role, "content": content})

    def add_reasoning(self, step: str) -> None:
        """Append a reasoning step for tracing."""
        self.reasoning_trace.append(step)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to plain dict for LangGraph state passing."""
        return {
            k: v for k, v in self.__dict__.items()
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AgentState":
        """Deserialize from plain dict."""
        obj = cls()
        for k, v in data.items():
            if hasattr(obj, k):
                setattr(obj, k, v)
        return obj
