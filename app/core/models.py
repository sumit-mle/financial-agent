"""
Core ORM models — conversation history, turns, and customer feedback.

These are the durable record of every customer interaction (Layer 1/6 in the
architecture): what was asked, what the agent answered, how confident it was,
whether it escalated, and any feedback the customer left afterward.

Portable column types (generic JSON, string UUIDs) are used deliberately so the
same schema runs on Postgres in production and SQLite in tests.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


def _uuid() -> str:
    return uuid.uuid4().hex


class Conversation(Base):
    """One customer session — groups many turns under a stable session_id."""

    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    session_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    customer_id: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    turns: Mapped[list["Turn"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="Turn.created_at",
    )


class Turn(Base):
    """A single request/response exchange within a conversation."""

    __tablename__ = "turns"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    conversation_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    turn_id: Mapped[str] = mapped_column(String(64), index=True)

    user_message: Mapped[str] = mapped_column(Text)
    agent_response: Mapped[str] = mapped_column(Text, default="")
    response_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    detected_intent: Mapped[str | None] = mapped_column(String(64), nullable=True)
    confidence_score: Mapped[float] = mapped_column(Float, default=0.0)
    should_escalate: Mapped[bool] = mapped_column(Boolean, default=False)
    escalation_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)

    citations: Mapped[list] = mapped_column(JSON, default=list)
    actions_taken: Mapped[list] = mapped_column(JSON, default=list)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    conversation: Mapped["Conversation"] = relationship(back_populates="turns")


class Feedback(Base):
    """Thumbs-up/down + rating a customer leaves on a specific turn."""

    __tablename__ = "feedback"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    session_id: Mapped[str] = mapped_column(String(64), index=True)
    turn_id: Mapped[str] = mapped_column(String(64), index=True)
    rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    helpful: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


# Composite index for the common "latest feedback for a session" lookup.
Index("ix_feedback_session_turn", Feedback.session_id, Feedback.turn_id)
