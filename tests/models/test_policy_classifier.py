"""
Tests for the regulatory policy classifier
(``app.models.specialized.policy_classifier``).

Keyword/rule-based (no ML dependency), so tested directly. Scoring: each policy
keyword adds 0.2 and each high-risk indicator adds 0.5 (capped at 1.0). Risk
level is ``critical`` when any critical regulatory term appears, else ``high``
(max score ≥ 0.7), ``medium`` (≥ 0.4 or a generic concern word), else ``low``;
escalation is required for high/critical.
"""
import pytest

from app.models.specialized.policy_classifier import (
    PolicyClassificationResult,
    RegulatoryPolicyClassifier,
    get_policy_classifier,
)


@pytest.fixture
def classifier() -> RegulatoryPolicyClassifier:
    return RegulatoryPolicyClassifier()


@pytest.mark.models
class TestPolicyClassificationResult:
    def test_holds_its_fields(self):
        result = PolicyClassificationResult(
            policy_categories=["debt_collection"],
            compliance_requirements=["FDCPA compliance check"],
            risk_level="high",
            regulatory_flags=["Harassment complaint"],
            required_actions=["fdcpa_assessment"],
            escalation_required=True,
            confidence_scores={"debt_collection": 1.0},
        )

        assert result.policy_categories == ["debt_collection"]
        assert result.risk_level == "high"
        assert result.escalation_required is True
        assert result.confidence_scores["debt_collection"] == 1.0


@pytest.mark.models
class TestClassifyPolicyCompliance:
    async def test_critical_regulatory_term_forces_critical(
        self, classifier: RegulatoryPolicyClassifier
    ):
        result = await classifier.classify_policy_compliance(
            "I am filing a class action lawsuit against your bank"
        )

        assert result.risk_level == "critical"
        assert result.escalation_required is True
        assert "Class action reference" in result.regulatory_flags

    async def test_high_risk_from_strong_signals(
        self, classifier: RegulatoryPolicyClassifier
    ):
        result = await classifier.classify_policy_compliance(
            "The debt collector is engaging in harassment and this is an fdcpa violation"
        )

        assert result.risk_level == "high"
        assert result.escalation_required is True
        assert "debt_collection" in result.policy_categories

    async def test_generic_concern_is_medium(
        self, classifier: RegulatoryPolicyClassifier
    ):
        result = await classifier.classify_policy_compliance(
            "I have a general problem with my account"
        )

        assert result.risk_level == "medium"
        assert result.escalation_required is False

    async def test_plain_message_is_low(
        self, classifier: RegulatoryPolicyClassifier
    ):
        result = await classifier.classify_policy_compliance(
            "I would like to know my current balance"
        )

        assert result.risk_level == "low"
        assert result.escalation_required is False


@pytest.mark.models
class TestPolicyHelpers:
    async def test_requires_immediate_escalation_true(
        self, classifier: RegulatoryPolicyClassifier
    ):
        should, reason = await classifier.requires_immediate_escalation(
            "I am filing a class action lawsuit"
        )
        assert should is True
        assert "critical" in reason.lower()

    async def test_requires_immediate_escalation_false(
        self, classifier: RegulatoryPolicyClassifier
    ):
        should, reason = await classifier.requires_immediate_escalation(
            "What is my balance?"
        )
        assert should is False
        assert reason == ""

    async def test_get_compliance_requirements(
        self, classifier: RegulatoryPolicyClassifier
    ):
        reqs = await classifier.get_compliance_requirements(
            "The debt collector is engaging in harassment and this is an fdcpa violation"
        )
        assert "FDCPA compliance check" in reqs


@pytest.mark.models
class TestSingleton:
    async def test_returns_same_instance(self):
        first = await get_policy_classifier()
        second = await get_policy_classifier()

        assert isinstance(first, RegulatoryPolicyClassifier)
        assert first is second
