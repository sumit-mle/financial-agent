"""
Action Registry — maps action names (as decided by the LLM) to
concrete async callables.

Every action the LLM can select in reasoning_node.py must be
registered here. At runtime the action execution node looks up the
action by name, validates parameters, calls it, and returns the result.

Mirrors the "ACTION EXECUTION LAYER" (Layer 5) from the architecture:
  CRM | Billing/Payments | Orders/Returns | Subscriptions | ERP/Finance | Shipping
"""
from typing import Any, Callable, Awaitable
from dataclasses import dataclass

from app.core.logging import get_logger

logger = get_logger(__name__)

ActionFn = Callable[..., Awaitable[dict[str, Any]]]


@dataclass
class ActionSpec:
    """Metadata + callable for one agent action."""
    name: str
    description: str
    parameters: dict[str, str]   # param_name → description
    required_params: list[str]
    fn: ActionFn
    category: str                # crm | billing | complaint | notification


# ── Global registry ────────────────────────────────────────────────────────────
_REGISTRY: dict[str, ActionSpec] = {}


def register(spec: ActionSpec) -> ActionSpec:
    """Register an action. Called at module import time via decorators."""
    _REGISTRY[spec.name] = spec
    return spec


def get_action(name: str) -> ActionSpec | None:
    """Look up an action by name."""
    return _REGISTRY.get(name)


def list_actions() -> list[str]:
    """Return names of all registered actions."""
    return list(_REGISTRY.keys())


async def execute_action(
    name: str,
    parameters: dict[str, Any],
) -> dict[str, Any]:
    """
    Look up and execute a named action with the given parameters.

    Returns a result dict with at minimum:
        { "success": bool, "result": Any, "error": str | None }
    """
    spec = get_action(name)
    if spec is None:
        logger.warning("Unknown action requested", action=name)
        return {
            "success": False,
            "result": None,
            "error": f"Unknown action: {name}",
        }

    # Validate required parameters
    missing = [p for p in spec.required_params if p not in parameters]
    if missing:
        return {
            "success": False,
            "result": None,
            "error": f"Missing required parameters for {name}: {missing}",
        }

    try:
        logger.info("Executing action", action=name, params=list(parameters.keys()))
        result = await spec.fn(**parameters)
        return {"success": True, "result": result, "error": None}
    except Exception as exc:
        logger.error("Action execution failed", action=name, error=str(exc))
        return {
            "success": False,
            "result": None,
            "error": str(exc),
        }
