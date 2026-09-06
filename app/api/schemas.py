"""
Pydantic request/response schemas for the FastAPI layer.
These are the public API contracts — keep them stable across versions.
"""
from typing import Any, Literal
from pydantic import BaseModel, Field


# ── Chat / Conversation ───────────────────────────────────────────────────────

class ChatMessage(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000, description="Customer message")
    session_id: str | None = Field(None, description="Session ID for multi-turn conversations")
    customer_id: str | None = Field(None, description="Customer identifier for CRM lookup")
    conversation_history: list[ChatMessage] = Field(
        default_factory=list,
        description="Prior conversation turns (max 20)",
        max_length=20,
    )

    class Config:
        json_schema_extra = {
            "example": {
                "message": "I was charged twice for the same transaction last week.",
                "session_id": "sess_abc123",
                "customer_id": "cust_456",
                "conversation_history": [],
            }
        }


class ChatResponse(BaseModel):
    session_id: str
    turn_id: str
    response: str
    response_type: Literal["answer", "clarification", "action_confirmation", "escalation"]
    intent: str
    confidence: float
    citations: list[str] = Field(default_factory=list)
    follow_up_suggestions: list[str] = Field(default_factory=list)
    actions_taken: list[dict[str, Any]] = Field(default_factory=list)
    should_escalate: bool
    escalation_reason: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


# ── Streaming ─────────────────────────────────────────────────────────────────

class StreamChunk(BaseModel):
    """Server-sent event payload for streaming responses."""
    type: Literal["token", "metadata", "done", "error"]
    content: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


# ── Feedback ──────────────────────────────────────────────────────────────────

class FeedbackRequest(BaseModel):
    session_id: str
    turn_id: str
    rating: Literal[1, 2, 3, 4, 5] = Field(..., description="1=poor, 5=excellent")
    helpful: bool
    comment: str | None = Field(None, max_length=500)


class FeedbackResponse(BaseModel):
    accepted: bool
    message: str


# ── Ingestion ─────────────────────────────────────────────────────────────────

class IngestRequest(BaseModel):
    source: Literal["cfpb", "sec", "policy", "all"] = "all"
    sample_mode: bool = Field(False, description="Use 5K sample for CFPB (faster for dev)")


class IngestResponse(BaseModel):
    status: Literal["started", "complete", "error"]
    message: str
    stats: dict[str, Any] = Field(default_factory=dict)


# ── Health ────────────────────────────────────────────────────────────────────

class HealthResponse(BaseModel):
    status: Literal["ok", "degraded", "error"]
    version: str
    services: dict[str, str]  # service_name → "ok" | "error"


# ── Vector Store Status ───────────────────────────────────────────────────────

class VectorStoreStatus(BaseModel):
    complaints: int
    policies: int
    faq: int
    total: int
