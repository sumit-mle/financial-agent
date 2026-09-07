"""
Node: Routing Decision (Layer 2)

Pure routing logic — reads state and returns the name of the next
node to visit. This is the LangGraph conditional edge function.

Maps to: "Routing Decision — Answer, Clarify, Action, or Handoff"
"""
from app.agent.state import AgentState
from app.core.logging import get_logger

logger = get_logger(__name__)

# Node name constants — must match graph node names in graph.py
NODE_ANSWER = "deliver_response"
NODE_ACTION = "execute_action"
NODE_CLARIFY = "deliver_response"   # Clarifications delivered same as answers
NODE_ESCALATE = "escalate"
NODE_SAFETY_EXIT = "deliver_response"


def route_after_safety(state: AgentState) -> str:
    """
    After safety check — either short-circuit to delivery or continue to retrieval.
    """
    if not state.safety_check_passed:
        return NODE_SAFETY_EXIT
    return "retrieve"


def route_after_reasoning(state: AgentState) -> str:
    """
    Core routing decision after the LLM has reasoned.
    Returns the next node name for LangGraph to execute.
    """
    # Fraud always escalates immediately
    if state.detected_intent == "fraud_report":
        logger.info("Routing to escalation: fraud intent", session_id=state.session_id)
        return NODE_ESCALATE

    # Explicit escalation flag (set by safety checker or low confidence)
    if state.should_escalate:
        logger.info(
            "Routing to escalation",
            reason=state.escalation_reason,
            session_id=state.session_id,
        )
        return NODE_ESCALATE

    # Max iterations guard
    from app.core.config import settings
    if state.iteration_count >= settings.agent_max_iterations:
        logger.warning(
            "Max iterations reached — escalating",
            iterations=state.iteration_count,
            session_id=state.session_id,
        )
        state.escalation_reason = "Maximum reasoning iterations exceeded"
        return NODE_ESCALATE

    decision = state.agent_decision

    if decision == "execute_action":
        if state.action_to_execute:
            logger.info(
                "Routing to action execution",
                action=state.action_to_execute,
                session_id=state.session_id,
            )
            return NODE_ACTION
        else:
            # Decision was execute_action but no action specified — fallback to answer
            logger.warning("execute_action decision but no action_to_execute set — answering")
            return NODE_ANSWER

    if decision == "escalate":
        return NODE_ESCALATE

    # answer or clarify — both go to deliver_response
    return NODE_ANSWER


def route_after_action(state: AgentState) -> str:
    """
    After action execution — loop back to reasoning if more steps needed,
    or deliver if we have a complete response.
    """
    # If action failed or resulted in escalation
    if state.should_escalate:
        return NODE_ESCALATE

    # If we have a response ready, deliver it
    if state.final_response and state.agent_decision != "execute_action":
        return NODE_ANSWER

    # Otherwise loop back to reasoning with action results in state
    return "reason"
