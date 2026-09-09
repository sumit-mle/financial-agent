"""
Chat routes — the core conversation API.

POST /api/v1/chat          → single-turn request/response
POST /api/v1/chat/stream   → SSE streaming response
POST /api/v1/feedback      → thumbs-up/down + rating
"""
import json
import uuid
from typing import AsyncGenerator

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
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
from app.core.repository import persist_feedback, persist_turn
from app.models.dependencies import get_fin_agent
from app.observability.tracer import get_tracer

logger = get_logger(__name__)
router = APIRouter(prefix="/chat", tags=["Chat"])
tracer = get_tracer()


@router.post("", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    background_tasks: BackgroundTasks,
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

    # Persist the completed turn after the response is returned (best-effort).
    background_tasks.add_task(persist_turn, state)

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

    Tokens arrive incrementally from the LLM as they are generated.
    The final 'done' event carries full metadata (intent, confidence, citations…).
    """
    session_id = request.session_id or str(uuid.uuid4())
    history = [
        {"role": m.role, "content": m.content}
        for m in request.conversation_history
    ]

    async def event_stream() -> AsyncGenerator[str, None]:
        try:
            # Run the full agent pipeline (safety, retrieval, intent, …) first.
            # Only the final LLM reasoning step streams tokens to the client.
            state = await agent.run(
                user_message=request.message,
                session_id=session_id,
                customer_id=request.customer_id,
                conversation_history=history,
                streaming=True,          # signal the reasoning node to stream
            )

            # If the agent populated a streaming_generator, consume it token by token.
            stream_gen = getattr(state, "streaming_generator", None)
            if stream_gen is not None:
                async for token in stream_gen:
                    chunk = StreamChunk(type="token", content=token)
                    yield f"data: {chunk.model_dump_json()}\n\n"
            else:
                # Fallback: agent ran non-streaming (e.g. safety short-circuit).
                # Emit the complete text as a single token so the client still
                # receives a well-formed stream.
                chunk = StreamChunk(type="token", content=state.final_response)
                yield f"data: {chunk.model_dump_json()}\n\n"

            # Persist after all tokens have been sent (best-effort).
            await persist_turn(state)

            # Final metadata event.
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
                    "actions_taken": state.actions_taken,
                    "should_escalate": state.should_escalate,
                    "escalation_reason": state.escalation_reason or None,
                },
            )
            yield f"data: {done_chunk.model_dump_json()}\n\n"

        except Exception as exc:
            logger.error("Streaming error", error=str(exc), session_id=session_id)
            error_chunk = StreamChunk(
                type="error",
                content="Something went wrong while generating a response. Please try again.",
            )
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
        # Durably record feedback (Langfuse is best-effort telemetry only).
        stored = await persist_feedback(
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
            stored=stored,
        )
        return FeedbackResponse(accepted=True, message="Thank you for your feedback.")
    except Exception as exc:
        logger.warning("Feedback logging failed", error=str(exc))
        return FeedbackResponse(accepted=False, message="Feedback could not be recorded.")
