"""
Tests for the financial sentiment analyzer
(``app.models.specialized.sentiment_analyzer``).

The transformer model (HuggingFace + torch) is a heavy optional dependency, so
these tests pin ``_initialized = "fallback"`` and exercise the keyword-based
escalation heuristic that actually ships when transformers is absent. The
fallback contract is:

* ≥2 distress keywords  → negative, escalate, "Multiple distress indicators detected"
* 1 distress keyword    → negative, escalate, "Financial distress detected"
* ≥1 satisfaction word  → positive, no escalation
* otherwise             → neutral,  no escalation
"""
import pytest

from app.models.specialized.sentiment_analyzer import (
    FinancialSentimentAnalyzer,
    SentimentResult,
)


@pytest.fixture
def analyzer() -> FinancialSentimentAnalyzer:
    """An analyzer pinned to keyword-fallback mode (no transformers required)."""
    a = FinancialSentimentAnalyzer()
    a._initialized = "fallback"
    return a


@pytest.mark.models
class TestSentimentResult:
    def test_holds_its_fields(self):
        result = SentimentResult(
            overall_sentiment="negative",
            confidence=0.8,
            emotional_intensity=0.9,
            emotions={"anger": 0.7},
            escalation_recommended=True,
            escalation_reason="High anger detected",
        )

        assert result.overall_sentiment == "negative"
        assert result.confidence == 0.8
        assert result.emotional_intensity == 0.9
        assert result.emotions["anger"] == 0.7
        assert result.escalation_recommended is True
        assert result.escalation_reason


@pytest.mark.models
class TestFallbackSentiment:
    async def test_multiple_distress_indicators_escalate(
        self, analyzer: FinancialSentimentAnalyzer
    ):
        # "manager" + "lawyer" → two distress keywords.
        result = await analyzer.analyze_sentiment(
            "I need a manager and will contact my lawyer about this"
        )

        assert result.overall_sentiment == "negative"
        assert result.escalation_recommended is True
        assert result.confidence == 0.8
        assert result.escalation_reason == "Multiple distress indicators detected"

    async def test_single_distress_indicator_escalates(
        self, analyzer: FinancialSentimentAnalyzer
    ):
        # "urgent" → exactly one distress keyword.
        result = await analyzer.analyze_sentiment("This is urgent, please help")

        assert result.overall_sentiment == "negative"
        assert result.escalation_recommended is True
        assert result.confidence == 0.6
        assert result.escalation_reason == "Financial distress detected"

    async def test_satisfaction_is_positive_no_escalation(
        self, analyzer: FinancialSentimentAnalyzer
    ):
        result = await analyzer.analyze_sentiment(
            "Thank you so much, this was very helpful"
        )

        assert result.overall_sentiment == "positive"
        assert result.escalation_recommended is False
        assert result.confidence == 0.7

    async def test_plain_message_is_neutral(
        self, analyzer: FinancialSentimentAnalyzer
    ):
        result = await analyzer.analyze_sentiment("What is my account balance today")

        assert result.overall_sentiment == "neutral"
        assert result.escalation_recommended is False


@pytest.mark.models
class TestImmediateEscalationHelper:
    async def test_returns_true_and_reason_for_distress(
        self, analyzer: FinancialSentimentAnalyzer
    ):
        should, reason = await analyzer.should_escalate_immediately(
            "I need a manager and my attorney involved"
        )
        assert should is True
        assert reason

    async def test_returns_false_for_neutral(
        self, analyzer: FinancialSentimentAnalyzer
    ):
        should, reason = await analyzer.should_escalate_immediately(
            "Please tell me my balance"
        )
        assert should is False
        assert reason == ""


@pytest.mark.models
class TestSingleton:
    async def test_returns_same_instance(self, monkeypatch):
        # Stub `_initialize` so the accessor never tries to load transformers /
        # download a model — this is a unit test of the singleton contract, not
        # of model loading.
        import app.models.specialized.sentiment_analyzer as mod

        async def fake_init(self):
            self._initialized = "fallback"

        monkeypatch.setattr(mod.FinancialSentimentAnalyzer, "_initialize", fake_init)
        monkeypatch.setattr(mod, "_sentiment_analyzer_instance", None)

        first = await mod.get_sentiment_analyzer()
        second = await mod.get_sentiment_analyzer()

        assert isinstance(first, FinancialSentimentAnalyzer)
        assert first is second
