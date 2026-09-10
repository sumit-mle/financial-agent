"""
Integration tests for the Layer-4 specialized models working together.

These drive the four classifiers through realistic customer messages and assert
that their outputs are *mutually consistent* — the thing unit tests can't check.

Two deliberate choices:

* The PII detector and sentiment analyzer are pinned to their deterministic
  fallbacks (``_initialized = "fallback"``). Presidio/spaCy and the HuggingFace
  sentiment model are heavy optional dependencies; without pinning, this module
  either downloads multi-GB weights or silently tests a different code path
  depending on what happens to be installed on the machine.
* The product and policy classifiers are keyword-based with no optional deps, so
  they run as-is.

Assertions are written against the real result objects:

* ``PIIDetectionResult``: has_pii, pii_types, redacted_text, confidence_scores
* ``SentimentResult``: overall_sentiment, escalation_recommended, emotions, …
* ``ProductClassificationResult``: primary_product, all_products, routing_suggestions
* ``PolicyClassificationResult``: policy_categories, risk_level, escalation_required, …
"""
import pytest

import app.models.specialized.pii_detector as pii_mod
import app.models.specialized.product_classifier as product_mod
import app.models.specialized.policy_classifier as policy_mod
import app.models.specialized.sentiment_analyzer as sentiment_mod
from app.models.specialized import (
    get_pii_detector,
    get_policy_classifier,
    get_product_classifier,
    get_sentiment_analyzer,
)


@pytest.fixture(autouse=True)
def _pinned_models(monkeypatch):
    """
    Pre-seed all four singletons so no test loads a model or downloads weights.

    Seeding the module-level singletons (rather than patching the accessors)
    means `get_*()` returns these instances, and the singleton identity that the
    rest of the suite relies on still holds within a test.
    """
    pii = pii_mod.AdvancedPIIDetector()
    pii._initialized = "fallback"
    monkeypatch.setattr(pii_mod, "_pii_detector_instance", pii)

    sentiment = sentiment_mod.FinancialSentimentAnalyzer()
    sentiment._initialized = "fallback"
    monkeypatch.setattr(sentiment_mod, "_sentiment_analyzer_instance", sentiment)

    # Keyword-based, no optional dependency — just skip re-initialization.
    products = product_mod.BankingProductClassifier()
    products._initialized = True
    monkeypatch.setattr(product_mod, "_product_classifier_instance", products)

    policies = policy_mod.RegulatoryPolicyClassifier()
    policies._initialized = True
    monkeypatch.setattr(policy_mod, "_policy_classifier_instance", policies)


@pytest.mark.integration
class TestModelsIntegration:
    """The four specialized models, driven together over realistic messages."""

    async def test_full_pipeline_fraud_scenario(self):
        """A card-fraud complaint carrying PII should trip every model at once."""
        text = (
            "I am extremely angry! Someone used my credit card 4532-1234-5678-9012 "
            "for unauthorized purchases. My SSN is 123-45-6789. "
            "This is fraud and I want to file a complaint immediately!"
        )

        pii_detector = await get_pii_detector()
        sentiment_analyzer = await get_sentiment_analyzer()
        product_classifier = await get_product_classifier()
        policy_classifier = await get_policy_classifier()

        # PII: both the card and the SSN are found and masked out of the text.
        pii_result = await pii_detector.detect_pii(text)
        assert pii_result.has_pii is True
        assert {"SSN", "CREDIT_CARD"} <= set(pii_result.pii_types)
        assert "123-45-6789" not in pii_result.redacted_text
        assert "4532-1234-5678-9012" not in pii_result.redacted_text

        # Sentiment: "complaint" + "immediately" are two distress indicators.
        sentiment_result = await sentiment_analyzer.analyze_sentiment(text)
        assert sentiment_result.overall_sentiment == "negative"
        assert sentiment_result.escalation_recommended is True

        # Product: routed to the credit-card team.
        product_result = await product_classifier.classify_products(text)
        assert "credit_card" in product_result.all_products
        assert "credit_card_team" in product_result.routing_suggestions

        # Policy: a dispute over an unauthorized transaction.
        policy_result = await policy_classifier.classify_policy_compliance(
            "I need to dispute an unauthorized transaction and get a billing error fixed."
        )
        assert "dispute_resolution" in policy_result.policy_categories

    async def test_pipeline_neutral_inquiry(self):
        """A plain product question should trip nothing."""
        text = "I would like to know about your checking account fees and interest rates."

        pii_detector = await get_pii_detector()
        sentiment_analyzer = await get_sentiment_analyzer()
        product_classifier = await get_product_classifier()

        pii_result = await pii_detector.detect_pii(text)
        sentiment_result = await sentiment_analyzer.analyze_sentiment(text)
        product_result = await product_classifier.classify_products(text)

        assert pii_result.has_pii is False
        assert pii_result.redacted_text == text  # nothing masked
        assert sentiment_result.overall_sentiment in ("neutral", "positive")
        assert sentiment_result.escalation_recommended is False
        assert product_result.primary_product == "checking_savings"

    async def test_pipeline_policy_question(self):
        """A disclosure complaint should classify as a policy matter, not PII."""
        text = (
            "Your disclosure did not mention these hidden fees and the APR terms "
            "were misleading."
        )

        pii_detector = await get_pii_detector()
        product_classifier = await get_product_classifier()
        policy_classifier = await get_policy_classifier()

        pii_result = await pii_detector.detect_pii(text)
        product_result = await product_classifier.classify_products(text)
        policy_result = await policy_classifier.classify_policy_compliance(text)

        assert pii_result.has_pii is False
        assert "disclosure" in policy_result.policy_categories
        assert policy_result.risk_level in ("low", "medium", "high", "critical")
        # Compliance requirements are derived from the matched categories.
        assert "Fee transparency check" in policy_result.compliance_requirements
        # An APR complaint is a credit-card signal.
        assert product_result.primary_product in ("credit_card", "other")

    async def test_regulatory_threat_escalates(self):
        """A CFPB complaint is a critical-term match and must escalate."""
        policy_classifier = await get_policy_classifier()

        result = await policy_classifier.classify_policy_compliance(
            "I am filing a CFPB complaint about this deceptive and unfair practice."
        )

        assert "consumer_protection" in result.policy_categories
        assert result.risk_level in ("high", "critical")
        assert result.escalation_required is True

        should_escalate, reason = await policy_classifier.requires_immediate_escalation(
            "I am filing a CFPB complaint about this deceptive and unfair practice."
        )
        assert should_escalate is True
        assert reason

    async def test_escalation_decision_matrix(self):
        """
        The composite escalation rule the agent applies: escalate on emotional
        distress, or when PII is exposed alongside a negative message.
        """
        scenarios = [
            # "lawsuit" + "attorney" → two distress indicators.
            ("I am filing a lawsuit and my attorney will be in touch!", True),
            ("Thank you for helping me understand my statement.", False),
            # "urgent" → one distress indicator, and an SSN is exposed.
            ("My SSN is 123-45-6789, this is urgent.", True),
            ("What are your current mortgage rates?", False),
        ]

        pii_detector = await get_pii_detector()
        sentiment_analyzer = await get_sentiment_analyzer()

        for text, expected in scenarios:
            pii_result = await pii_detector.detect_pii(text)
            sentiment_result = await sentiment_analyzer.analyze_sentiment(text)

            should_escalate = sentiment_result.escalation_recommended or (
                pii_result.has_pii
                and sentiment_result.overall_sentiment == "negative"
            )

            assert should_escalate is expected, f"Escalation mismatch for: {text}"

    async def test_model_performance_consistency(self):
        """Repeated calls on the same text must give identical classifications."""
        text = "I have a problem with my credit card billing statement."

        product_classifier = await get_product_classifier()
        sentiment_analyzer = await get_sentiment_analyzer()

        products = []
        sentiments = []
        for _ in range(3):
            products.append((await product_classifier.classify_products(text)).primary_product)
            sentiments.append((await sentiment_analyzer.analyze_sentiment(text)).overall_sentiment)

        assert len(set(products)) == 1, f"Product classification inconsistent: {products}"
        assert len(set(sentiments)) == 1, f"Sentiment analysis inconsistent: {sentiments}"

    async def test_models_return_complete_results_for_trivial_input(self):
        """Every model must return a fully-populated result, never a partial one."""
        text = "Test message for error recovery"

        pii_result = await (await get_pii_detector()).detect_pii(text)
        assert pii_result.has_pii is False
        assert pii_result.pii_types == []
        assert pii_result.redacted_text == text
        assert pii_result.confidence_scores == {}

        sentiment_result = await (await get_sentiment_analyzer()).analyze_sentiment(text)
        assert sentiment_result.overall_sentiment == "neutral"
        assert sentiment_result.emotions  # never empty

        product_result = await (await get_product_classifier()).classify_products(text)
        assert product_result.primary_product == "other"
        assert "general_support" in product_result.routing_suggestions

    async def test_cross_model_validation(self):
        """Outputs across models should tell a coherent story about one message."""
        fraud_text = (
            "Someone stole my credit card and I need this fixed immediately — "
            "I am filing a complaint."
        )

        sentiment_analyzer = await get_sentiment_analyzer()
        product_classifier = await get_product_classifier()

        sentiment_result = await sentiment_analyzer.analyze_sentiment(fraud_text)
        product_result = await product_classifier.classify_products(fraud_text)

        assert "credit_card" in product_result.all_products
        # A distressed complaint about card theft must read as negative…
        assert sentiment_result.overall_sentiment == "negative"
        # …and escalation must be backed by an actual emotion score.
        assert sentiment_result.escalation_recommended is True
        assert any(score > 0.6 for score in sentiment_result.emotions.values())

    async def test_model_singleton_behavior(self):
        """The accessors hand back one shared instance per model."""
        assert await get_pii_detector() is await get_pii_detector()
        assert await get_sentiment_analyzer() is await get_sentiment_analyzer()
        assert await get_product_classifier() is await get_product_classifier()
        assert await get_policy_classifier() is await get_policy_classifier()
