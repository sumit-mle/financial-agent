"""
Tests for the PII detection model (``app.models.specialized.pii_detector``).

These exercise the *fallback* regex detector, which is what runs whenever
Microsoft Presidio is not installed (a heavy optional dependency). Forcing
``_initialized = "fallback"`` keeps the suite deterministic and dependency-light
while still covering the public contract used by the safety checker and logging
middleware: ``detect_pii`` / ``is_safe_for_processing`` / ``get_redacted_text``.
"""
import pytest

from app.models.specialized.pii_detector import (
    AdvancedPIIDetector,
    PIIDetectionResult,
)


@pytest.fixture
def detector() -> AdvancedPIIDetector:
    """A detector pinned to regex-fallback mode (no Presidio required)."""
    det = AdvancedPIIDetector()
    # `_initialize` short-circuits on a truthy flag, so this both selects the
    # fallback path and prevents any attempt to import/load Presidio.
    det._initialized = "fallback"
    return det


@pytest.mark.models
class TestPIIDetectionResult:
    def test_holds_its_fields(self):
        result = PIIDetectionResult(
            has_pii=True,
            pii_types=["SSN", "EMAIL"],
            redacted_text="[SSN_REDACTED]",
            confidence_scores={"SSN": 0.7},
            entities=[],
        )

        assert result.has_pii is True
        assert result.pii_types == ["SSN", "EMAIL"]
        assert result.redacted_text == "[SSN_REDACTED]"
        assert result.confidence_scores["SSN"] == 0.7
        assert result.entities == []


@pytest.mark.models
class TestFallbackDetection:
    async def test_detects_and_redacts_ssn(self, detector: AdvancedPIIDetector):
        result = await detector.detect_pii("My SSN is 123-45-6789 please help")

        assert result.has_pii is True
        assert "SSN" in result.pii_types
        assert "[SSN_REDACTED]" in result.redacted_text
        assert "123-45-6789" not in result.redacted_text
        assert result.confidence_scores["SSN"] == 0.7

    async def test_detects_and_redacts_credit_card(self, detector: AdvancedPIIDetector):
        result = await detector.detect_pii("Card number 4532-1234-5678-9012 was charged")

        assert result.has_pii is True
        assert "CREDIT_CARD" in result.pii_types
        assert "[CREDIT_CARD_REDACTED]" in result.redacted_text
        assert "4532-1234-5678-9012" not in result.redacted_text

    async def test_detects_and_redacts_phone_number(self, detector: AdvancedPIIDetector):
        result = await detector.detect_pii("Call me at 555-123-4567 today")

        assert result.has_pii is True
        assert "PHONE_NUMBER" in result.pii_types
        assert "[PHONE_NUMBER_REDACTED]" in result.redacted_text

    async def test_detects_and_redacts_email(self, detector: AdvancedPIIDetector):
        result = await detector.detect_pii("Reach me at john.doe@example.com anytime")

        assert result.has_pii is True
        assert "EMAIL" in result.pii_types
        assert "[EMAIL_REDACTED]" in result.redacted_text
        assert "john.doe@example.com" not in result.redacted_text

    async def test_detects_multiple_pii_types(self, detector: AdvancedPIIDetector):
        result = await detector.detect_pii(
            "My SSN is 123-45-6789 and email is jane@test.com"
        )

        assert result.has_pii is True
        assert set(result.pii_types) == {"SSN", "EMAIL"}

    async def test_clean_text_has_no_pii(self, detector: AdvancedPIIDetector):
        text = "I would like to check my account balance please."
        result = await detector.detect_pii(text)

        assert result.has_pii is False
        assert result.pii_types == []
        assert result.redacted_text == text  # unchanged


@pytest.mark.models
class TestSafetyHelpers:
    async def test_is_safe_for_processing(self, detector: AdvancedPIIDetector):
        assert await detector.is_safe_for_processing("What are your hours?") is True
        assert await detector.is_safe_for_processing("SSN 123-45-6789") is False

    async def test_get_redacted_text(self, detector: AdvancedPIIDetector):
        redacted = await detector.get_redacted_text("email me at a@b.com")
        assert "a@b.com" not in redacted
        assert "[EMAIL_REDACTED]" in redacted


@pytest.mark.models
class TestSingleton:
    async def test_returns_same_instance(self, monkeypatch):
        # Stub `_initialize` so the accessor never loads Presidio / spaCy models
        # (which may be present in CI). This verifies only the singleton contract.
        import app.models.specialized.pii_detector as mod

        async def fake_init(self):
            self._initialized = "fallback"

        monkeypatch.setattr(mod.AdvancedPIIDetector, "_initialize", fake_init)
        monkeypatch.setattr(mod, "_pii_detector_instance", None)

        first = await mod.get_pii_detector()
        second = await mod.get_pii_detector()

        assert isinstance(first, AdvancedPIIDetector)
        assert first is second
