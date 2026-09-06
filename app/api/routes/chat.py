"""
Chat routes — the core conversation API.

POST /api/v1/chat          → single-turn request/response
POST /api/v1/chat/stream   → SSE streaming response
POST /api/v1/feedback      → thumbs-up/down + rating
"""
import json
import uuid
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse

from app.agent.graph import FinAgent
from app.api.schemas import (
    ChatRequest,
    ChatResponse,
    FeedbackRequest,
    FeedbackResponse,
    StreamChunk,
)
from app.core.logging import get_logger
from app.models.dependencies import get_fin_agent
from app.observability.tracer import get_tracer

logger = get_logger(__name__)
router = APIRouter(prefix="/chat", tags=["Chat"])
tracer = get_tracer()


@router.post("", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    agent: FinAgent = Depends(get_fin_agent),
) -> ChatResponse:
    """
    Process a single customer message and return a full response.

    The agent runs the complete pipeline:
    intent → refine → safety → retrieve → reason → validate → respond
    """
    session_id = request.session_id or str(uuid.uuid4())

    # Convert Pydantic ChatMessage → plain dicts for agent state
    history = [
        {"role": m.role, "content": m.content}
        for m in request.conversation_history
    ]

    try:
        with tracer.start_span("chat_request", session_id=session_id) as span:
            state = await agent.run(
                user_message=request.message,
                session_id=session_id,
                customer_id=request.customer_id,
                conversation_history=history,
            )
            span.set_attribute("intent", state.detected_intent)
            span.set_attribute("confidence", state.confidence_score)
            span.set_attribute("response_type", state.response_type)

    except Exception as exc:
        logger.error("Chat endpoint error", error=str(exc), session_id=session_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Agent processing failed. Please try again.",
        )

    return ChatResponse(
        session_id=state.session_id,
        turn_id=state.turn_id,
        response=state.final_response,
        response_type=state.response_type,
        intent=state.detected_intent,
        confidence=round(state.confidence_score, 3),
        citations=state.citations,
        follow_up_suggestions=state.follow_up_suggestions,
        actions_taken=state.actions_taken,
        should_escalate=state.should_escalate,
        escalation_reason=state.escalation_reason or None,
        metadata={
            "reasoning_steps": len(state.reasoning_trace),
            "retrieved_chunks": len(state.retrieved_chunks),
            "guardrail_scores": state.metadata.get("guardrail_scores", {}),
        },
    )


@router.post("/stream")
async def chat_stream(
    request: ChatRequest,
    agent: FinAgent = Depends(get_fin_agent),
) -> StreamingResponse:
    """
    Streaming version of the chat endpoint using Server-Sent Events (SSE).
    The frontend receives tokens as they're generated.
    """
    session_id = request.session_id or str(uuid.uuid4())
    history = [
        {"role": m.role, "content": m.content}
        for m in request.conversation_history
    ]

    async def event_stream() -> AsyncGenerator[str, None]:
        try:
            state = await agent.run(
                user_message=request.message,
                session_id=session_id,
                customer_id=request.customer_id,
                conversation_history=history,
            )

            # Simulate streaming by yielding tokens from the complete response
            # In production, wire a streaming LLM (streaming=True in llm_factory)
            words = state.final_response.split(" ")
            for i, word in enumerate(words):
                chunk = StreamChunk(
                    type="token",
                    content=word + (" " if i < len(words) - 1 else ""),
                )
                yield f"data: {chunk.model_dump_json()}\n\n"

            # Final metadata event
            done_chunk = StreamChunk(
                type="done",
                metadata={
                    "session_id": state.session_id,
                    "turn_id": state.turn_id,
                    "intent": state.detected_intent,
                    "confidence": round(state.confidence_score, 3),
                    "response_type": state.response_type,
                    "citations": state.citations,
                    "follow_up_suggestions": state.follow_up_suggestions,
                    "should_escalate": state.should_escalate,
                },
            )
            yield f"data: {done_chunk.model_dump_json()}\n\n"

        except Exception as exc:
            logger.error("Streaming error", error=str(exc), session_id=session_id)
            error_chunk = StreamChunk(type="error", content=str(exc))
            yield f"data: {error_chunk.model_dump_json()}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/feedback", response_model=FeedbackResponse)
async def submit_feedback(request: FeedbackRequest) -> FeedbackResponse:
    """
    Capture customer feedback on a response.
    Logged to Langfuse for the learn-and-improve loop (Layer 6).
    """
    try:
        tracer.log_feedback(
            session_id=request.session_id,
            turn_id=request.turn_id,
            rating=request.rating,
            helpful=request.helpful,
            comment=request.comment,
        )
        logger.info(
            "Feedback received",
            session_id=request.session_id,
            rating=request.rating,
            helpful=request.helpful,
        )
        return FeedbackResponse(accepted=True, message="Thank you for your feedback.")
    except Exception as exc:
        logger.warning("Feedback logging failed", error=str(exc))
        return FeedbackResponse(accepted=False, message="Feedback could not be recorded.")
