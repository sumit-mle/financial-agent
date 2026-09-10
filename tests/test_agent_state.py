"""Unit tests for AgentState serialisation round-trip."""
from app.agent.state import AgentState


def test_default_state_fields():
    state = AgentState()
    assert state.safety_check_passed is True
    assert state.should_escalate is False
    assert state.iteration_count == 0
    assert state.messages == []
    assert state.citations == []


def test_add_message():
    state = AgentState()
    state.add_message("user", "Hello")
    state.add_message("assistant", "Hi there!")
    assert len(state.messages) == 2
    assert state.messages[0]["role"] == "user"
    assert state.messages[1]["content"] == "Hi there!"


def test_add_reasoning():
    state = AgentState()
    state.add_reasoning("Step 1: classified intent")
    state.add_reasoning("Step 2: retrieved 5 chunks")
    assert len(state.reasoning_trace) == 2
    assert "Step 1" in state.reasoning_trace[0]


def test_serialisation_round_trip():
    state = AgentState(
        session_id="sess_test",
        user_message="What is my balance?",
        detected_intent="account_inquiry",
        confidence_score=0.85,
    )
    state.add_message("user", "What is my balance?")
    state.citations = ["CFPB Complaint (Credit card)", "Policy Document"]

    d = state.to_dict()
    restored = AgentState.from_dict(d)

    assert restored.session_id == "sess_test"
    assert restored.detected_intent == "account_inquiry"
    assert restored.confidence_score == 0.85
    assert len(restored.messages) == 1
    assert restored.citations == ["CFPB Complaint (Credit card)", "Policy Document"]


def test_from_dict_ignores_unknown_fields():
    """from_dict should not crash on extra keys (forward compatibility)."""
    d = {"session_id": "x", "unknown_future_field": "value"}
    state = AgentState.from_dict(d)
    assert state.session_id == "x"
