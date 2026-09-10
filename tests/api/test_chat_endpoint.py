"""
Tests for the chat API (`/api/v1/chat`, `/api/v1/chat/stream`, `/api/v1/chat/feedback`).

The agent is replaced with a controllable ``FakeAgent`` (see conftest) so these
tests exercise the HTTP layer — request validation, response shaping, SSE
framing, and error sanitisation — without invoking the real LangGraph pipeline.
"""
import json

import pytest
from httpx import AsyncClient

from tests.conftest import make_agent_state


@pytest.mark.api
class TestChatEndpoint:
    """HTTP contract tests for the chat routes."""

    async def test_chat_success(self, test_client: AsyncClient, fake_agent):
        fake_agent.next_state = make_agent_state(
            final_response="I can help you check your account balance.",
            detected_intent="account_inquiry",
            confidence_score=0.85,
            response_type="answer",
            citations=["Account Services FAQ"],
            follow_up_suggestions=["Check recent transactions", "Set up alerts"],
        )

        resp = await test_client.post(
            "/api/v1/chat",
            json={"message": "What is my balance?", "session_id": "s1"},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["response"] == "I can help you check your account balance."
        assert data["intent"] == "account_inquiry"
        assert data["confidence"] == 0.85
        assert data["should_escalate"] is False
        assert data["session_id"] == "s1"
        assert len(data["follow_up_suggestions"]) == 2

    async def test_chat_escalation(self, test_client: AsyncClient, fake_agent):
        fake_agent.next_state = make_agent_state(
            final_response="Let me connect you with a fraud specialist.",
            detected_intent="fraud_report",
            confidence_score=0.92,
            response_type="escalation",
            should_escalate=True,
            escalation_reason="Fraud report requires human review",
            actions_taken=[{"action": "escalate_to_human", "success": True}],
        )

        resp = await test_client.post(
            "/api/v1/chat",
            json={"message": "Someone stole my card!", "session_id": "s2"},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["response_type"] == "escalation"
        assert data["should_escalate"] is True
        assert data["escalation_reason"]
        assert len(data["actions_taken"]) == 1

    async def test_chat_passes_conversation_history(
        self, test_client: AsyncClient, fake_agent
    ):
        history = [
            {"role": "user", "content": "I asked about account fees"},
            {"role": "assistant", "content": "I explained the fee schedule"},
        ]

        resp = await test_client.post(
            "/api/v1/chat",
            json={
                "message": "What did I ask about?",
                "session_id": "s3",
                "conversation_history": history,
            },
        )

        assert resp.status_code == 200
        # The route must forward prior turns to the agent verbatim.
        assert fake_agent.last_call["conversation_history"] == history

    async def test_chat_missing_message_is_422(self, test_client: AsyncClient, fake_agent):
        resp = await test_client.post("/api/v1/chat", json={"session_id": "s4"})
        assert resp.status_code == 422

    async def test_chat_empty_message_is_422(self, test_client: AsyncClient, fake_agent):
        # message has min_length=1 → an empty string fails schema validation.
        resp = await test_client.post(
            "/api/v1/chat", json={"message": "", "session_id": "s5"}
        )
        assert resp.status_code == 422

    async def test_chat_oversized_message_is_422(self, test_client: AsyncClient, fake_agent):
        # message has max_length=4000.
        resp = await test_client.post(
            "/api/v1/chat", json={"message": "x" * 5000, "session_id": "s5b"}
        )
        assert resp.status_code == 422

    async def test_chat_agent_failure_is_sanitized_500(
        self, test_client: AsyncClient, fake_agent
    ):
        fake_agent.raise_exc = RuntimeError("boom: internal stack detail")

        resp = await test_client.post(
            "/api/v1/chat", json={"message": "hello", "session_id": "s6"}
        )

        assert resp.status_code == 500
        detail = resp.json()["detail"]
        assert "failed" in detail.lower()
        # Internal exception text must never leak to the client.
        assert "boom" not in detail

    async def test_stream_returns_sse_tokens_and_done(
        self, test_client: AsyncClient, fake_agent
    ):
        fake_agent.next_state = make_agent_state(
            final_response="I can help", detected_intent="general"
        )

        resp = await test_client.post(
            "/api/v1/chat/stream",
            json={"message": "hi", "session_id": "s7"},
        )

        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")

        tokens: list[str] = []
        done_seen = False
        for line in resp.text.splitlines():
            if not line.startswith("data: "):
                continue
            chunk = json.loads(line[len("data: ") :])
            if chunk["type"] == "token":
                tokens.append(chunk["content"])
            elif chunk["type"] == "done":
                done_seen = True
                assert chunk["metadata"]["session_id"] == "s7"

        assert "".join(tokens).strip() == "I can help"
        assert done_seen

    async def test_feedback_success(self, test_client: AsyncClient):
        resp = await test_client.post(
            "/api/v1/chat/feedback",
            json={
                "session_id": "s8",
                "turn_id": "t1",
                "rating": 4,
                "helpful": True,
                "comment": "Great help with my question",
            },
        )

        assert resp.status_code == 200
        data = resp.json()
        # FeedbackResponse contract: {accepted: bool, message: str}
        assert "accepted" in data
        assert isinstance(data["accepted"], bool)
        assert data["message"]

    async def test_feedback_invalid_rating_is_422(self, test_client: AsyncClient):
        resp = await test_client.post(
            "/api/v1/chat/feedback",
            json={
                "session_id": "s9",
                "turn_id": "t1",
                "rating": 6,  # rating is constrained to 1–5
                "helpful": True,
            },
        )
        assert resp.status_code == 422
