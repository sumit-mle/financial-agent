"""
Persistence helpers for conversations, turns, and feedback.

Every function here is best-effort and self-contained: it opens its own session
and swallows/logs failures so a database outage degrades logging, not the
customer-facing request. The chat endpoint stays up even if Postgres is down.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import select

from app.core.db import get_sessionmaker
from app.core.logging import get_logger
from app.core.models import Conversation, Feedback, Turn

logger = get_logger(__name__)


async def persist_turn(state: Any) -> None:
    """
    Upsert the conversation for this session and append the completed turn.
    Accepts the agent's AgentState (duck-typed) after a turn finishes.
    """
    try:
        async with get_sessionmaker()() as session:
            async with session.begin():
                conv = (
                    await session.execute(
                        select(Conversation).where(
                            Conversation.session_id == state.session_id
                        )
                    )
                ).scalar_one_or_none()

                if conv is None:
                    conv = Conversation(
                        session_id=state.session_id,
                        customer_id=state.customer_id or None,
                    )
                    session.add(conv)
                    await session.flush()  # populate conv.id

                session.add(
                    Turn(
                        conversation_id=conv.id,
                        turn_id=state.turn_id,
                        user_message=state.user_message,
                        agent_response=state.final_response or "",
                        response_type=state.response_type,
                        detected_intent=state.detected_intent,
                        confidence_score=float(state.confidence_score or 0.0),
                        should_escalate=bool(state.should_escalate),
                        escalation_reason=state.escalation_reason or None,
                        citations=list(state.citations or []),
                        actions_taken=list(state.actions_taken or []),
                    )
                )
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning(
            "persist_turn failed (non-fatal)",
            error=str(exc),
            session_id=getattr(state, "session_id", None),
        )


async def persist_feedback(
    session_id: str,
    turn_id: str,
    rating: int | None = None,
    helpful: bool | None = None,
    comment: str | None = None,
) -> bool:
    """Record customer feedback for a turn. Returns True on success."""
    try:
        async with get_sessionmaker()() as session:
            async with session.begin():
                session.add(
                    Feedback(
                        session_id=session_id,
                        turn_id=turn_id,
                        rating=rating,
                        helpful=helpful,
                        comment=comment,
                    )
                )
        return True
    except Exception as exc:
        logger.warning("persist_feedback failed", error=str(exc), session_id=session_id)
        return False
