"""
Tests for the banking product classifier
(``app.models.specialized.product_classifier``).

This classifier is purely keyword-based (no ML dependency), so it is tested
directly. Scoring weights: primary keyword 0.4, secondary 0.2, context 0.1,
capped at 1.0; products scoring ≥ ``threshold`` (default 0.3) qualify, and a
message that matches nothing defaults to ``other`` at 0.5.
"""
import pytest

from app.models.specialized.product_classifier import (
    BankingProductClassifier,
    ProductClassificationResult,
    get_product_classifier,
)


@pytest.fixture
def classifier() -> BankingProductClassifier:
    return BankingProductClassifier()


@pytest.mark.models
class TestProductClassificationResult:
    def test_holds_its_fields(self):
        result = ProductClassificationResult(
            primary_product="credit_card",
            all_products=["credit_card", "checking_savings"],
            confidence_scores={"credit_card": 0.9},
            routing_suggestions=["credit_card_team"],
        )

        assert result.primary_product == "credit_card"
        assert result.all_products == ["credit_card", "checking_savings"]
        assert result.confidence_scores["credit_card"] == 0.9
        assert result.routing_suggestions == ["credit_card_team"]


@pytest.mark.models
class TestClassifyProducts:
    async def test_credit_card(self, classifier: BankingProductClassifier):
        result = await classifier.classify_products(
            "I have unauthorized charges on my Visa credit card statement"
        )

        assert result.primary_product == "credit_card"
        assert "credit_card" in result.all_products
        assert result.confidence_scores["credit_card"] >= 0.3
        assert "credit_card_team" in result.routing_suggestions

    async def test_mortgage_is_high_risk_routing(
        self, classifier: BankingProductClassifier
    ):
        result = await classifier.classify_products(
            "I need help with my mortgage refinance and escrow"
        )

        assert result.primary_product == "mortgage"
        # High-risk products route to their dedicated queues first.
        assert "mortgage_team" in result.routing_suggestions

    async def test_debt_collection(self, classifier: BankingProductClassifier):
        result = await classifier.classify_products(
            "A debt collector keeps calling about my debt"
        )

        assert result.primary_product == "debt_collection"
        assert "collections_compliance" in result.routing_suggestions

    async def test_multiple_products_ranked_by_confidence(
        self, classifier: BankingProductClassifier
    ):
        result = await classifier.classify_products(
            "Problems with both my savings account and my credit card"
        )

        assert len(result.all_products) >= 2
        assert "credit_card" in result.all_products
        assert "checking_savings" in result.all_products

    async def test_unknown_message_defaults_to_other(
        self, classifier: BankingProductClassifier
    ):
        result = await classifier.classify_products(
            "I want to know your branch hours and location"
        )

        assert result.primary_product == "other"
        assert result.confidence_scores["other"] == 0.5
        assert "general_support" in result.routing_suggestions

    async def test_empty_text_defaults_to_other(
        self, classifier: BankingProductClassifier
    ):
        result = await classifier.classify_products("")
        assert result.primary_product == "other"


@pytest.mark.models
class TestConvenienceHelpers:
    async def test_get_primary_product(self, classifier: BankingProductClassifier):
        assert await classifier.get_primary_product("my mortgage escrow") == "mortgage"

    async def test_is_high_risk_product(self, classifier: BankingProductClassifier):
        assert await classifier.is_high_risk_product("payday loan rollover") is True
        assert await classifier.is_high_risk_product("branch hours please") is False

    async def test_get_routing_team(self, classifier: BankingProductClassifier):
        team = await classifier.get_routing_team("A debt collector is harassing me")
        assert team == "collections_compliance"


@pytest.mark.models
class TestSingleton:
    async def test_returns_same_instance(self):
        first = await get_product_classifier()
        second = await get_product_classifier()

        assert isinstance(first, BankingProductClassifier)
        assert first is second
