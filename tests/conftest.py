"""
Pytest configuration and shared fixtures.

Design notes
------------
* The FastAPI app is imported once. Handlers that need the agent go through the
  ``get_fin_agent`` dependency, so tests inject a controllable ``FakeAgent`` via
  ``app.dependency_overrides`` (the ``fake_agent`` fixture) instead of trying to
  monkeypatch an already-imported singleton — reassigning ``config.settings``
  after import does *not* rebind references other modules already captured.
* Admin routes are guarded by a Bearer token compared against
  ``settings.admin_token``; ``admin_headers`` reads that same value so auth works
  in every environment.
"""
import os
import sys
from typing import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient

# Add repo root to path for `app` / `tests` imports.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.agent.state import AgentState
from app.core.config import Settings, settings
from app.main import app
from app.models.dependencies import get_fin_agent


# ── Agent test doubles ─────────────────────────────────────────────────────────

def make_agent_state(**overrides) -> AgentState:
    """Build a completed AgentState with sensible defaults for API tests."""
    state = AgentState(
        session_id="test-session",
        customer_id="test-customer",
        turn_id="test-turn",
        user_message="hello",
        detected_intent="general",
        confidence_score=0.8,
        final_response="Here is how I can help.",
        response_type="answer",
    )
    for key, value in overrides.items():
        setattr(state, key, value)
    return state


class FakeAgent:
    """
    Stand-in for FinAgent. Tests set ``next_state`` (or ``raise_exc``); the router
    calls ``run`` exactly as it would the real agent, so the HTTP layer is
    exercised end-to-end without the LangGraph pipeline.
    """

    def __init__(self) -> None:
        self.next_state: AgentState = make_agent_state()
        self.raise_exc: Exception | None = None
        self.last_call: dict = {}

    async def run(
        self,
        user_message: str,
        session_id: str | None = None,
        customer_id: str | None = None,
        conversation_history=None,
        customer_data=None,
        streaming: bool = False,
    ) -> AgentState:
        self.last_call = {
            "user_message": user_message,
            "session_id": session_id,
            "customer_id": customer_id,
            "conversation_history": conversation_history or [],
            "streaming": streaming,
        }
        if self.raise_exc is not None:
            raise self.raise_exc
        state = self.next_state
        # Mirror the real runner: the returned turn always carries identifiers.
        state.session_id = session_id or state.session_id or "test-session"
        state.turn_id = state.turn_id or "test-turn"

        if streaming:
            async def _fake_token_stream():
                for word in ["I", " can", " help"]:
                    yield word
            state.streaming_generator = _fake_token_stream()

        return state


@pytest.fixture
def fake_agent():
    """Override the agent dependency with a controllable fake for one test."""
    agent = FakeAgent()
    app.dependency_overrides[get_fin_agent] = lambda: agent
    try:
        yield agent
    finally:
        app.dependency_overrides.pop(get_fin_agent, None)


# ── HTTP client + auth ──────────────────────────────────────────────────────────

@pytest.fixture
async def test_client() -> AsyncGenerator[AsyncClient, None]:
    """Async HTTP client bound directly to the ASGI app (no sockets)."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.fixture
def admin_headers() -> dict[str, str]:
    """Authorization header carrying the configured admin bearer token."""
    return {"Authorization": f"Bearer {settings.admin_token}"}


@pytest.fixture
def test_settings() -> Settings:
    """A Settings instance pinned to the test environment (valid fields only)."""
    return Settings(
        app_env="test",
        database_url="sqlite+aiosqlite:///test.db",
        redis_url="redis://localhost:6379/1",
        qdrant_url="http://localhost:6333",
        openai_api_key="test-key",
        secret_key="test-secret-key-for-testing-only",
    )


# ── Sample data fixtures (consumed by the model/guardrail test modules) ─────────

@pytest.fixture
def mock_openai():
    """Mock OpenAI client."""
    from unittest.mock import AsyncMock, MagicMock

    mock = AsyncMock()
    mock.chat.completions.acreate.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content='{"test": "response"}'))]
    )
    return mock


@pytest.fixture
def mock_qdrant():
    """Mock Qdrant client."""
    from unittest.mock import MagicMock

    mock = MagicMock()
    mock.search.return_value = []
    mock.get_collections.return_value = MagicMock(collections=[])
    return mock


@pytest.fixture
def sample_complaint_data():
    """Sample CFPB complaint data for testing."""
    return {
        "complaint_id": "12345",
        "product": "Credit card",
        "sub_product": "General-purpose credit card or charge card",
        "issue": "Billing disputes",
        "sub_issue": "Problem with a purchase shown on your statement",
        "complaint_text": "I was charged for a purchase I did not make. The merchant refuses to provide a refund.",
        "company_response": "Company has responded to the consumer and the response is on file with the CFPB",
        "timely": "Yes",
        "consumer_disputed": "N/A",
        "state": "CA",
        "zip_code": "90210",
        "submitted_via": "Web",
    }


@pytest.fixture
def sample_customer_data():
    """Sample customer data for testing."""
    return {
        "customer_id": "CUST12345",
        "name": "John Doe",
        "email": "john.doe@example.com",
        "phone": "(555) 123-4567",
        "account_status": "active",
        "products": ["Checking Account", "Credit Card"],
        "account_since": "2019-01-15",
    }


@pytest.fixture
def sample_pii_text():
    """Sample text containing PII for testing."""
    return """
    My name is John Smith and my SSN is 123-45-6789.
    Please call me at (555) 123-4567 or email john.smith@email.com.
    My credit card number is 4532-1234-5678-9012.
    I live at 123 Main Street, Anytown, CA 12345.
    """


@pytest.fixture
def sample_financial_messages():
    """Sample financial messages for sentiment analysis."""
    return [
        {
            "text": "I am extremely frustrated with the unauthorized charges on my account!",
            "expected_sentiment": "negative",
            "expected_escalation": True,
        },
        {
            "text": "Thank you for resolving my issue so quickly. Great service!",
            "expected_sentiment": "positive",
            "expected_escalation": False,
        },
        {
            "text": "Can you help me understand my statement?",
            "expected_sentiment": "neutral",
            "expected_escalation": False,
        },
        {
            "text": "This is the worst bank ever! I'm closing my account immediately!",
            "expected_sentiment": "negative",
            "expected_escalation": True,
        },
    ]


@pytest.fixture
def sample_product_queries():
    """Sample queries for product classification."""
    return [
        {
            "text": "I have a problem with my credit card billing",
            "expected_products": ["credit_card"],
            "expected_primary": "credit_card",
        },
        {
            "text": "My checking account was charged an overdraft fee",
            "expected_products": ["checking_account"],
            "expected_primary": "checking_account",
        },
        {
            "text": "I need help with my mortgage payment",
            "expected_products": ["mortgage"],
            "expected_primary": "mortgage",
        },
        {
            "text": "Issues with both my savings account and credit card",
            "expected_products": ["savings_account", "credit_card"],
            "expected_primary": "credit_card",  # Credit cards often prioritized
        },
    ]


@pytest.fixture
def sample_policy_queries():
    """Sample queries for policy classification."""
    return [
        {
            "text": "What are the CFPB regulations for credit reporting?",
            "expected_categories": ["consumer_rights"],
            "expected_primary": "consumer_rights",
        },
        {
            "text": "What fees can banks charge for overdrafts?",
            "expected_categories": ["fee_disclosure"],
            "expected_primary": "fee_disclosure",
        },
        {
            "text": "How do I dispute an error on my credit report?",
            "expected_categories": ["dispute_resolution"],
            "expected_primary": "dispute_resolution",
        },
        {
            "text": "What are my rights under the Fair Credit Reporting Act?",
            "expected_categories": ["consumer_rights", "credit_reporting"],
            "expected_primary": "consumer_rights",
        },
    ]
