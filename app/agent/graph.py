"""
LangGraph Agent Graph — wires all nodes into a stateful execution graph.

LangGraph 0.2.x API:
  - StateGraph requires a TypedDict schema (not bare dict)
  - set_entry_point() sets the first node
  - add_conditional_edges() takes (node, fn, mapping)
  - compile() returns a runnable graph

Full agent flow:
  START
    │
    ▼
  classify_intent   ← NLU: 7 banking intent categories
    │
    ▼
  refine_query      ← Expand + rephrase for better retrieval
    │
    ▼
  check_safety      ← PII / injection / regulated-advice guard
    │ fail ──────────────────────────────────────────────────────────┐
    │ pass                                                           │
    ▼                                                               │
  retrieve          ← Multi-collection Qdrant + FlashRank rerank    │
    │                                                               │
    ▼                                                               │
  reason            ← Fin Apex LLM: answer/action/clarify/escalate  │
    │                                                               │
    ├─► execute_action  ← CRM / ticketing / payment APIs            │
    │         │                                                      │
    │         └────────────────────────────────────────┐            │
    │                                                  │            │
    ├─► escalate  ← set escalation context             │            │
    │         │                                        │            │
    │         ▼                                        ▼            │
    └───► deliver_response  ← validate + enrich ◄─────┘            │
                │                                                   │
                │ ◄─────────────────────────────────────────────────┘
                ▼
              END
"""
import uuid
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph  # type: ignore[import]

from app.agent.nodes.action_node import ActionExecutionNode
from app.agent.nodes.intent_classifier import IntentClassifierNode
from app.agent.nodes.query_refiner import QueryRefinerNode
from app.agent.nodes.reasoning_node import ReasoningNode
from app.agent.nodes.retrieval_node import RetrievalNode
from app.agent.nodes.routing_node import (
    route_after_action,
    route_after_reasoning,
    route_after_safety,
)
from app.agent.nodes.safety_checker import SafetyCheckerNode
from app.agent.state import AgentState
from app.core.logging import get_logger
from app.retrieval.rag_pipeline import RAGPipeline
from app.validation.validator import ValidationNode

logger = get_logger(__name__)


# ── LangGraph state schema (TypedDict) ────────────────────────────────────────
# LangGraph 0.2 requires a TypedDict. We use a single "data" key that holds
# the serialised AgentState dict. This keeps LangGraph's internal state
# machinery happy while we manage all state in AgentState ourselves.

class GraphState(TypedDict):
    data: dict[str, Any]


# ── Escalation node ───────────────────────────────────────────────────────────

async def _escalate_node(state_dict: GraphState) -> GraphState:
    """Sets escalation context before handing off to validation node."""
    state = AgentState.from_dict(state_dict["data"])
    reason = state.escalation_reason or "Requested by customer or policy"
    summary = (
        f"Customer issue: {state.user_message[:200]}\n"
        f"Intent: {state.detected_intent}\n"
        f"Confidence: {state.confidence_score:.2f}\n"
        f"Reason for escalation: {reason}"
    )
    state.response_type = "escalation"
    state.should_escalate = True
    state.metadata["escalation_summary"] = summary
    state.add_reasoning(f"Escalated: {reason}")
    logger.info("Escalation node", reason=reason, session_id=state.session_id)
    return {"data": state.to_dict()}


# ── Graph builder ─────────────────────────────────────────────────────────────

def build_agent_graph(
    llm_client=None,
    rag_pipeline: RAGPipeline | None = None,
) -> Any:
    """
    Construct and compile the full LangGraph agent graph.

    Args:
        llm_client: LangChain-compatible async LLM (e.g. ChatOpenAI).
        rag_pipeline: Pre-built RAGPipeline instance (shared for efficiency).

    Returns:
        Compiled LangGraph graph, callable with .ainvoke({"data": state_dict})
    """
    # ── Instantiate nodes ─────────────────────────────────────────────────────
    intent_node = IntentClassifierNode(llm_client=llm_client)
    refiner_node = QueryRefinerNode(llm_client=llm_client)
    safety_node = SafetyCheckerNode()
    retrieval_node = RetrievalNode(rag_pipeline=rag_pipeline)
    reasoning_node = ReasoningNode(llm_client=llm_client)
    action_node = ActionExecutionNode()
    validation_node = ValidationNode()

    # ── Wrap each async node method into GraphState → GraphState ──────────────
    def wrap(node_fn):
        async def _wrapped(state_dict: GraphState) -> GraphState:
            state = AgentState.from_dict(state_dict["data"])
            updated = await node_fn(state)
            return {"data": updated.to_dict()}
        return _wrapped

    # ── Routing functions (receive GraphState, return node name string) ────────
    def route_safety(state_dict: GraphState) -> str:
        return route_after_safety(AgentState.from_dict(state_dict["data"]))

    def route_reasoning(state_dict: GraphState) -> str:
        return route_after_reasoning(AgentState.from_dict(state_dict["data"]))

    def route_action(state_dict: GraphState) -> str:
        return route_after_action(AgentState.from_dict(state_dict["data"]))

    # ── Build graph ───────────────────────────────────────────────────────────
    graph = StateGraph(GraphState)

    # Add nodes
    graph.add_node("classify_intent",  wrap(intent_node.run))
    graph.add_node("refine_query",     wrap(refiner_node.run))
    graph.add_node("check_safety",     wrap(safety_node.run))
    graph.add_node("retrieve",         wrap(retrieval_node.run))
    graph.add_node("reason",           wrap(reasoning_node.run))
    graph.add_node("execute_action",   wrap(action_node.run))
    graph.add_node("escalate",         _escalate_node)
    graph.add_node("deliver_response", wrap(validation_node.run))

    # ── Edges ─────────────────────────────────────────────────────────────────
    graph.set_entry_point("classify_intent")
    graph.add_edge("classify_intent", "refine_query")
    graph.add_edge("refine_query",    "check_safety")

    graph.add_conditional_edges(
        "check_safety", route_safety,
        {"retrieve": "retrieve", "deliver_response": "deliver_response"},
    )

    graph.add_edge("retrieve", "reason")

    graph.add_conditional_edges(
        "reason", route_reasoning,
        {
            "execute_action":   "execute_action",
            "deliver_response": "deliver_response",
            "escalate":         "escalate",
        },
    )

    graph.add_conditional_edges(
        "execute_action", route_action,
        {
            "reason":           "reason",
            "deliver_response": "deliver_response",
            "escalate":         "escalate",
        },
    )

    graph.add_edge("escalate",         "deliver_response")
    graph.add_edge("deliver_response", END)

    return graph.compile()


# ── High-level runner ─────────────────────────────────────────────────────────

class FinAgent:
    """
    High-level interface for running the agent.
    Wraps the compiled LangGraph graph with a clean async API.

    Usage:
        agent = FinAgent(llm_client=get_default_llm())
        result = await agent.run(
            user_message="Where is my complaint?",
            session_id="sess_123",
            customer_id="cust_456",
        )
        print(result.final_response)
    """

    def __init__(
        self,
        llm_client=None,
        rag_pipeline: RAGPipeline | None = None,
    ) -> None:
        self._graph = build_agent_graph(
            llm_client=llm_client,
            rag_pipeline=rag_pipeline,
        )
        logger.info("FinAgent initialised")

    async def run(
        self,
        user_message: str,
        session_id: str | None = None,
        customer_id: str | None = None,
        conversation_history: list[dict[str, str]] | None = None,
        customer_data: dict[str, Any] | None = None,
    ) -> AgentState:
        """
        Process one customer turn end-to-end.

        Returns completed AgentState with:
          .final_response      — text to send to the customer
          .response_type       — answer | clarification | action_confirmation | escalation
          .citations           — source labels for UI display
          .confidence_score    — 0.0–1.0
          .should_escalate     — True if human handoff needed
        """
        initial_state = AgentState(
            session_id=session_id or str(uuid.uuid4()),
            customer_id=customer_id or "",
            turn_id=str(uuid.uuid4()),
            user_message=user_message,
            messages=conversation_history or [],
            customer_data=customer_data or {},
        )
        initial_state.add_message("user", user_message)

        logger.info(
            "Agent turn started",
            session_id=initial_state.session_id,
            preview=user_message[:60],
        )

        # LangGraph expects {"data": state_dict}
        output: GraphState = await self._graph.ainvoke(
            {"data": initial_state.to_dict()}
        )
        result = AgentState.from_dict(output["data"])

        # Append agent response to history for next turn
        result.add_message("assistant", result.final_response)

        logger.info(
            "Agent turn complete",
            session_id=result.session_id,
            decision=result.agent_decision,
            response_type=result.response_type,
            confidence=round(result.confidence_score, 3),
        )

        return result
