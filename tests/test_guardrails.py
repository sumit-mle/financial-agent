"""Regression tests for score-based guardrail decisions."""

from types import SimpleNamespace

from app.models.guardrails import GuardrailModels


class FakeLLM:
    def __init__(self, content: str) -> None:
        self.content = content

    async def ainvoke(self, _prompt: str):
        return SimpleNamespace(content=self.content)


async def test_escalation_score_overrides_contradictory_passed_flag():
    guardrails = GuardrailModels(
        llm_client=FakeLLM('{"score": 0.0, "passed": true, "reason": "safe"}')
    )

    result = await guardrails._evaluate_single(
        "escalation", "credit score", "Here are general steps.", "credit report"
    )

    assert result.score == 0.0
    assert result.passed is False


async def test_escalation_score_can_trigger_despite_false_passed_flag():
    guardrails = GuardrailModels(
        llm_client=FakeLLM('{"score": 0.9, "passed": false, "reason": "risk"}')
    )

    result = await guardrails._evaluate_single(
        "escalation", "fraud report", "Someone stole my card.", "fraud"
    )

    assert result.score == 0.9
    assert result.passed is True