"""
Node: Reasoning & Decision (Layer 4 — Fin Apex LLM)

The core LLM call. Given the assembled context, the model:
  1. Decides whether to answer, execute an action, clarify, or escalate
  2. If answering: generates the response
  3. If acting: outputs the action name + parameters as structured JSON
  4. Always outputs a confidence score (0.0–1.0)

Maps to: "Fin Apex 1.0 LLM — Reasoning, Answer Generation,
          Conversation, Procedure Execution, Decision Making"
"""
import json
import re
import time
from typing import Optional

from app.agent.state import AgentDecision, AgentState
from app.core.config import settings
from app.core.logging import get_logger
from app.experimentation.integration import experiment_prompt_override
from app.experimentation.prompt_experiments import get_prompt_manager

logger = get_logger(__name__)

_REASONING_PROMPT = """You are Fin, a specialized financial customer support AI agent.

{assembled_context}

## Current Customer Message
{user_message}

## Your Task
Analyze the customer's message and the context above. Then respond with a JSON object
in EXACTLY this format (no other text, no markdown):

{{
  "decision": "<answer | execute_action | clarify | escalate>",
  "confidence": <0.0 to 1.0>,
  "response": "<Your response to the customer. Be empathetic, clear, and concise.>",
  "action_name": "<function_name or null>",
  "action_parameters": {{}} ,
  "reasoning": "<One sentence: why you made this decision>",
  "follow_up_suggestions": ["<suggestion 1>", "<suggestion 2>"]
}}

Decision guide:
- "answer": You can fully resolve this from the knowledge context. Confidence >= 0.65.
- "execute_action": Customer needs you to do something (check status, reschedule, log ticket).
                   Set action_name to the exact function name from Available Actions.
- "clarify": You need more info from the customer to proceed (confidence < 0.50).
- "escalate": Issue involves fraud, loan decisions, legal matters, or confidence < {escalation_threshold}.

Confidence calibration:
- 0.9+  : Highly confident, answer directly grounded in retrieved context
- 0.7–0.9: Confident but partial — answer with caveats
- 0.5–0.7: Uncertain — consider clarifying
- < 0.5 : Escalate to human agent

Current iteration: {iteration}/{max_iterations}
"""


class ReasoningNode:
    """
    Core LLM reasoning node — produces decision + response + action spec.
    Integrated with A/B testing for prompt experimentation.
    """

    def __init__(self, llm_client=None) -> None:
        self._llm = llm_client
        self._prompt_manager = None

    async def _get_prompt_manager(self):
        """Lazy initialization of prompt manager."""
        if self._prompt_manager is None:
            self._prompt_manager = await get_prompt_manager()
        return self._prompt_manager

    def _build_base_prompt(self, state: AgentState) -> str:
        """Build the base reasoning prompt."""
        context = state.assembled_context
        # When retrieval returned nothing, tell the model explicitly so it
        # grounds on "no sources" rather than inventing policy/account facts.
        if state.metadata.get("context_empty") or not context.strip():
            context = (
                "## Knowledge Context\n"
                "NO knowledge base passages were retrieved for this query. "
                "Do NOT fabricate specific policies, account details, balances, "
                "fees, or case facts. If answering requires such specifics, choose "
                "\"clarify\" (ask the customer for what you need) or \"escalate\"."
            )
        return _REASONING_PROMPT.format(
            assembled_context=context,
            user_message=state.user_message,
            escalation_threshold=settings.agent_escalation_threshold,
            iteration=state.iteration_count,
            max_iterations=settings.agent_max_iterations,
        )

    def _retrieval_failure_response(self, state: AgentState) -> dict:
        """Escalation fallback when the knowledge/retrieval layer is unavailable."""
        return {
            "decision": "escalate",
            "confidence": 0.0,
            "response": (
                "I'm unable to access our knowledge base at the moment, so I don't "
                "want to risk giving you inaccurate information. Let me connect you "
                "with a human specialist who can help right away."
            ),
            "action_name": None,
            "action_parameters": {},
            "reasoning": "Retrieval layer failed — escalating instead of answering ungrounded",
            "follow_up_suggestions": [],
        }

    @experiment_prompt_override
    async def _get_experimental_prompt(self, base_prompt: str, state: AgentState) -> Optional[str]:
        """
        Get experimental prompt if user is in A/B test.
        This method is decorated with @experiment_prompt_override.
        """
        try:
            prompt_manager = await self._get_prompt_manager()
            
            # Get experimental prompt config based on user's intent
            config = await prompt_manager.get_prompt_config(
                session_id=state.session_id,
                intent=getattr(state, 'intent', None)
            )
            
            if config is None:
                return None  # Use default prompt
            
            # Build experimental prompt from config
            experimental_prompt = f"""You are Fin, a specialized financial customer support AI agent.

{config.system_prompt}

{state.assembled_context}

## Current Customer Message
{state.user_message}

## Your Task
{config.reasoning_prompt}

{config.response_template}

Decision guide:
- "answer": You can fully resolve this from the knowledge context. Confidence >= 0.65.
- "execute_action": Customer needs you to do something (check status, reschedule, log ticket).
                   Set action_name to the exact function name from Available Actions.
- "clarify": You need more info from the customer to proceed (confidence < 0.50).
- "escalate": Issue involves fraud, loan decisions, legal matters, or confidence < {settings.agent_escalation_threshold}.

Confidence calibration:
- 0.9+  : Highly confident, answer directly grounded in retrieved context
- 0.7–0.9: Confident but partial — answer with caveats
- 0.5–0.7: Uncertain — consider clarifying
- < 0.5 : Escalate to human agent

Current iteration: {state.iteration_count}/{settings.agent_max_iterations}

Examples:
{chr(10).join(config.examples) if config.examples else ""}
"""
            
            return experimental_prompt
            
        except Exception as e:
            logger.warning(f"Failed to get experimental prompt: {e}")
            return None

    def _parse_llm_output(self, raw: str) -> dict:
        """Extract JSON from LLM response, handling markdown code blocks."""
        # Strip markdown fences if present
        text = raw.strip()
        if "```" in text:
            match = re.search(r"```(?:json)?\s*([\s\S]+?)```", text)
            if match:
                text = match.group(1).strip()
        # Find JSON object
        match = re.search(r"\{[\s\S]+\}", text)
        if match:
            return json.loads(match.group(0))
        raise ValueError(f"No JSON found in LLM output: {text[:200]}")

    def _fallback_response(self, state: AgentState) -> dict:
        """Safe fallback when LLM call fails."""
        return {
            "decision": "escalate",
            "confidence": 0.0,
            "response": (
                "I'm having trouble processing your request right now. "
                "Let me connect you with a human specialist who can assist you immediately."
            ),
            "action_name": None,
            "action_parameters": {},
            "reasoning": "LLM unavailable — escalating as safety measure",
            "follow_up_suggestions": [],
        }

    async def run(self, state: AgentState) -> AgentState:
        """Execute LLM reasoning and parse the structured output."""
        state.iteration_count += 1
        start_time = time.time()

        if state.metadata.get("retrieval_failed"):
            # Knowledge layer is down — never answer ungrounded, escalate.
            logger.warning(
                "Retrieval failed upstream — escalating without LLM call",
                session_id=state.session_id,
            )
            parsed = self._retrieval_failure_response(state)
        elif self._llm is None:
            logger.warning("No LLM client configured — using fallback response")
            parsed = self._fallback_response(state)
        else:
            # Build base prompt
            base_prompt = self._build_base_prompt(state)
            
            # Try to get experimental prompt through A/B testing
            experimental_prompt = await self._get_experimental_prompt(base_prompt, state)
            final_prompt = experimental_prompt if experimental_prompt else base_prompt
            
            # Track which prompt version was used
            prompt_version = "experimental" if experimental_prompt else "control"
            
            try:
                if state.metadata.get("streaming") and hasattr(self._llm, "astream"):
                    # ── Streaming path ───────────────────────────────────────
                    # Collect all tokens first (we need the full text to parse
                    # the JSON structure), then expose them via a generator so
                    # the SSE endpoint can replay them token-by-token.
                    tokens: list[str] = []
                    async for chunk in self._llm.astream(final_prompt):
                        token = (
                            chunk.content
                            if hasattr(chunk, "content")
                            else str(chunk)
                        )
                        tokens.append(token)
                    raw = "".join(tokens)

                    async def _token_gen(toks: list[str]):
                        for t in toks:
                            yield t

                    state.streaming_generator = _token_gen(tokens)
                else:
                    # ── Non-streaming path (default) ─────────────────────────
                    response = await self._llm.ainvoke(final_prompt)
                    raw = response.content if hasattr(response, "content") else str(response)

                state.llm_response_raw = raw
                parsed = self._parse_llm_output(raw)

                # Track A/B testing metrics
                await self._track_experiment_metrics(
                    state,
                    prompt_version,
                    parsed,
                    time.time() - start_time,
                )

            except Exception as exc:
                logger.error(
                    "Reasoning node LLM call failed",
                    error=str(exc),
                    session_id=state.session_id,
                )
                parsed = self._fallback_response(state)

        # ── Map parsed output → state ──────────────────────────────────────
        decision: AgentDecision = parsed.get("decision", "escalate")  # type: ignore[assignment]
        valid_decisions = {"answer", "execute_action", "clarify", "escalate"}
        if decision not in valid_decisions:
            decision = "escalate"

        state.agent_decision = decision
        state.confidence_score = float(parsed.get("confidence", 0.0))
        state.final_response = parsed.get("response", "")
        state.action_to_execute = parsed.get("action_name") or ""
        state.action_parameters = parsed.get("action_parameters") or {}
        state.follow_up_suggestions = parsed.get("follow_up_suggestions") or []

        state.add_reasoning(
            f"Decision: {decision} | Confidence: {state.confidence_score:.2f} | "
            f"Reason: {parsed.get('reasoning', '')}"
        )

        # Auto-escalate if confidence too low
        if state.confidence_score < settings.agent_escalation_threshold:
            if decision not in ("escalate", "execute_action"):
                state.agent_decision = "escalate"
                state.should_escalate = True
                state.escalation_reason = (
                    f"Confidence too low ({state.confidence_score:.2f} < "
                    f"{settings.agent_escalation_threshold})"
                )
                state.add_reasoning(
                    f"Auto-escalating: confidence {state.confidence_score:.2f} below threshold"
                )

        logger.info(
            "Reasoning complete",
            decision=state.agent_decision,
            confidence=state.confidence_score,
            session_id=state.session_id,
        )
        return state

    async def _track_experiment_metrics(
        self, 
        state: AgentState, 
        prompt_version: str, 
        parsed_output: dict, 
        response_time: float
    ) -> None:
        """Track metrics for A/B testing experiments."""
        try:
            prompt_manager = await self._get_prompt_manager()
            
            # Calculate response quality score (simplified heuristic)
            response_quality = self._calculate_response_quality(parsed_output, state)
            
            # Determine user satisfaction (based on confidence and decision)
            user_satisfied = (
                parsed_output.get("confidence", 0.0) >= 0.7 and
                parsed_output.get("decision") in ["answer", "execute_action"]
            )
            
            # Determine if escalated
            escalated = parsed_output.get("decision") == "escalate"
            
            await prompt_manager.track_response_metrics(
                session_id=state.session_id,
                response_quality=response_quality,
                user_satisfied=user_satisfied,
                escalated=escalated,
                response_time_ms=response_time * 1000,
                confidence_score=parsed_output.get("confidence", 0.0)
            )
            
            logger.debug(
                "Tracked experiment metrics",
                session_id=state.session_id,
                prompt_version=prompt_version,
                response_quality=response_quality,
                user_satisfied=user_satisfied,
                escalated=escalated
            )
            
        except Exception as e:
            logger.warning(f"Failed to track experiment metrics: {e}")

    def _calculate_response_quality(self, parsed_output: dict, state: AgentState) -> float:
        """
        Calculate response quality score (1-5 scale).
        This is a simplified heuristic - in production you'd want more sophisticated scoring.
        """
        quality_score = 3.0  # Base score
        
        # Adjust based on confidence
        confidence = parsed_output.get("confidence", 0.0)
        if confidence >= 0.9:
            quality_score += 1.5
        elif confidence >= 0.7:
            quality_score += 1.0
        elif confidence >= 0.5:
            quality_score += 0.5
        else:
            quality_score -= 1.0
        
        # Adjust based on decision appropriateness
        decision = parsed_output.get("decision", "")
        if decision == "answer" and confidence >= 0.7:
            quality_score += 0.5
        elif decision == "escalate" and confidence < 0.5:
            quality_score += 0.5
        elif decision == "clarify" and 0.4 <= confidence <= 0.6:
            quality_score += 0.3
        
        # Adjust based on response length and structure
        response = parsed_output.get("response", "")
        if response and len(response.split()) > 5:  # Not too short
            quality_score += 0.2
        
        # Ensure score is within bounds
        return max(1.0, min(5.0, quality_score))
