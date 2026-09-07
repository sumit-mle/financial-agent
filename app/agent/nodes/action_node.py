"""
Node: Action Execution (Layer 5)

Receives the action name + parameters decided by the reasoning node,
calls the action registry, handles failures gracefully, and builds
a user-facing response from the result.

Replaces the stub _execute_action_node in graph.py.
"""
from app.actions import connectors as _  # noqa: F401 — ensures all actions are registered
from app.actions.registry import execute_action
from app.agent.state import AgentState
from app.core.logging import get_logger

logger = get_logger(__name__)

# These actions always result in escalation regardless of success
_ESCALATION_ACTIONS = {"escalate_to_human"}

# Human-readable result formatters per action category
_RESULT_TEMPLATES = {
    "lookup_account_summary": (
        "Here's your account summary:\n"
        "- **Status**: {account_status}\n"
        "- **Products**: {products}\n"
        "- **Account since**: {account_since}\n"
        "- **Open complaints**: {open_complaints}"
    ),
    "lookup_complaint_status": (
        "Your complaint **{complaint_id}** is currently: **{status}**\n"
        "Last updated: {last_updated}\n"
        "Expected resolution by: {expected_resolution}\n\n"
        "{notes}"
    ),
    "create_complaint_ticket": (
        "Your complaint has been filed successfully.\n"
        "**Reference number**: {ticket_id}\n"
        "**Status**: {status}\n"
        "You'll receive a response within {expected_response_days} business days."
    ),
    "reschedule_payment": (
        "Your payment has been rescheduled.\n"
        "**New date**: {new_payment_date}\n"
        "**Amount**: ${original_amount}\n"
        "**Confirmation ID**: {confirmation_id}\n"
        "A confirmation has been sent to your registered email."
    ),
    "lookup_transaction_history": (
        "Here are your recent transactions (last {period_days} days):\n"
        "{transaction_list}"
    ),
    "escalate_to_human": (
        "I've created an escalation request for you.\n"
        "**Escalation ID**: {escalation_id}\n"
        "**Estimated wait**: {estimated_wait_minutes} minutes\n"
        "A specialist will contact you shortly."
    ),
}


def _format_result(action_name: str, result: dict) -> str:
    """Format action result into a customer-friendly message."""
    template = _RESULT_TEMPLATES.get(action_name)
    if not template:
        # Generic fallback
        return f"Action completed successfully. Reference: {result.get('id', 'N/A')}"

    try:
        # Special case: transaction list formatting
        if action_name == "lookup_transaction_history":
            txns = result.get("transactions", [])
            lines = [
                f"  • {t['date']} — {t['description']}: "
                f"{'−' if t['type']=='debit' else '+'}"
                f"${t['amount']}"
                for t in txns[:10]
            ]
            return template.format(
                period_days=result.get("period_days", 30),
                transaction_list="\n".join(lines) or "No transactions found.",
            )

        # Handle list fields (e.g. products)
        fmt_result = {}
        for k, v in result.items():
            fmt_result[k] = ", ".join(v) if isinstance(v, list) else v
        return template.format(**fmt_result)
    except KeyError:
        # Template has a field not in result — graceful fallback
        return f"Action '{action_name}' completed. Details: {result}"


class ActionExecutionNode:
    """
    Executes the action selected by the LLM and writes results to state.
    """

    async def run(self, state: AgentState) -> AgentState:
        action_name = state.action_to_execute
        params = state.action_parameters or {}

        if not action_name:
            logger.warning("Action node called but no action_to_execute set")
            state.agent_decision = "answer"
            return state

        # Inject customer_id if not already in params
        if "customer_id" not in params and state.customer_id:
            params["customer_id"] = state.customer_id

        # Execute the action
        outcome = await execute_action(action_name, params)

        state.actions_taken.append({
            "action": action_name,
            "parameters": params,
            "success": outcome["success"],
        })
        state.action_results.append(outcome)

        if outcome["success"] and outcome["result"]:
            # Format and set as the final response
            state.final_response = _format_result(action_name, outcome["result"])
            state.agent_decision = "answer"
            state.add_reasoning(
                f"Action '{action_name}' succeeded — response formatted"
            )
        else:
            # Action failed — inform customer and escalate if needed
            error = outcome.get("error", "Unknown error")
            logger.warning("Action failed", action=action_name, error=error)
            state.final_response = (
                f"I encountered an issue while processing your request. "
                f"A specialist will follow up to assist you directly."
            )
            state.should_escalate = True
            state.escalation_reason = f"Action '{action_name}' failed: {error}"
            state.add_reasoning(f"Action '{action_name}' failed — escalating")

        # Escalation actions always set the flag
        if action_name in _ESCALATION_ACTIONS:
            state.should_escalate = True
            state.response_type = "escalation"

        logger.info(
            "Action execution complete",
            action=action_name,
            success=outcome["success"],
            session_id=state.session_id,
        )
        return state
