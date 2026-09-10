"""initial conversation, turn, and feedback tables

Revision ID: 0001_initial
Revises:
Create Date: 2026-09-08

Creates the durable conversation record: conversations → turns (1:N) and a
standalone feedback table keyed by session_id/turn_id.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "conversations",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("customer_id", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_conversations_session_id", "conversations", ["session_id"], unique=True
    )
    op.create_index(
        "ix_conversations_customer_id", "conversations", ["customer_id"], unique=False
    )

    op.create_table(
        "turns",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("conversation_id", sa.String(length=32), nullable=False),
        sa.Column("turn_id", sa.String(length=64), nullable=False),
        sa.Column("user_message", sa.Text(), nullable=False),
        sa.Column("agent_response", sa.Text(), nullable=False),
        sa.Column("response_type", sa.String(length=32), nullable=True),
        sa.Column("detected_intent", sa.String(length=64), nullable=True),
        sa.Column("confidence_score", sa.Float(), nullable=False),
        sa.Column("should_escalate", sa.Boolean(), nullable=False),
        sa.Column("escalation_reason", sa.String(length=255), nullable=True),
        sa.Column("citations", sa.JSON(), nullable=True),
        sa.Column("actions_taken", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"], ["conversations.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_turns_conversation_id", "turns", ["conversation_id"], unique=False
    )
    op.create_index("ix_turns_turn_id", "turns", ["turn_id"], unique=False)

    op.create_table(
        "feedback",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("turn_id", sa.String(length=64), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=True),
        sa.Column("helpful", sa.Boolean(), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_feedback_session_id", "feedback", ["session_id"], unique=False)
    op.create_index("ix_feedback_turn_id", "feedback", ["turn_id"], unique=False)
    op.create_index(
        "ix_feedback_session_turn", "feedback", ["session_id", "turn_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_feedback_session_turn", table_name="feedback")
    op.drop_index("ix_feedback_turn_id", table_name="feedback")
    op.drop_index("ix_feedback_session_id", table_name="feedback")
    op.drop_table("feedback")

    op.drop_index("ix_turns_turn_id", table_name="turns")
    op.drop_index("ix_turns_conversation_id", table_name="turns")
    op.drop_table("turns")

    op.drop_index("ix_conversations_customer_id", table_name="conversations")
    op.drop_index("ix_conversations_session_id", table_name="conversations")
    op.drop_table("conversations")
