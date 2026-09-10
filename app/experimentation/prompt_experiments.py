"""
Prompt Experimentation System for Financial AI Agent.

Enables A/B testing of different:
- System prompts
- Reasoning prompts  
- Response templates
- Model parameters
- Chain-of-thought approaches
"""
import json
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union
from enum import Enum

from app.experimentation.framework import (
    Experiment, 
    ExperimentVariant, 
    ExperimentMetric,
    TrafficAllocation,
    get_experiment_engine
)
from app.core.logging import get_logger

logger = get_logger(__name__)


class PromptComponent(Enum):
    """Components of prompts that can be experimented with."""
    SYSTEM_PROMPT = "system_prompt"
    REASONING_PROMPT = "reasoning_prompt"
    RESPONSE_TEMPLATE = "response_template"
    EXAMPLES = "examples"
    INSTRUCTIONS = "instructions"
    CONTEXT_FORMAT = "context_format"


@dataclass
class PromptConfig:
    """
    Configuration for a prompt variant.

    ``max_tokens`` and ``temperature`` are first-class fields because that is
    what the reasoning node and ``ExperimentalPromptProvider.get_model_params``
    read. Putting them *only* inside ``model_params`` silently leaves the fields
    at their defaults, so the variant's intended values never reach the LLM —
    always set the fields (mirroring them into ``model_params`` is optional).
    """
    system_prompt: str
    reasoning_prompt: str
    response_template: str
    model_params: Dict[str, Any]
    use_chain_of_thought: bool = True
    max_tokens: int = 1000
    temperature: float = 0.7
    examples: List[str] = field(default_factory=list)


class PromptExperimentManager:
    """Manages prompt experiments for the Financial AI Agent."""
    
    def __init__(self):
        self.active_experiments: Dict[str, Experiment] = {}
        
    async def create_prompt_experiment(self,
                                     name: str,
                                     description: str,
                                     prompt_variants: Dict[str, PromptConfig],
                                     target_intent: Optional[str] = None,
                                     traffic_split: float = 0.1) -> str:
        """Create a new prompt experiment."""
        
        # Create experiment variants
        variants = []
        control_created = False
        
        for variant_id, prompt_config in prompt_variants.items():
            variant = ExperimentVariant(
                id=variant_id,
                name=variant_id.replace('_', ' ').title(),
                description=f"Prompt variant: {variant_id}",
                config={
                    "prompt_config": {
                        "system_prompt": prompt_config.system_prompt,
                        "reasoning_prompt": prompt_config.reasoning_prompt,
                        "response_template": prompt_config.response_template,
                        "model_params": prompt_config.model_params,
                        "use_chain_of_thought": prompt_config.use_chain_of_thought,
                        "max_tokens": prompt_config.max_tokens,
                        "temperature": prompt_config.temperature,
                        "examples": prompt_config.examples or []
                    },
                    "target_intent": target_intent
                },
                traffic_weight=traffic_split if not control_created else (1 - traffic_split),
                is_control=not control_created
            )
            variants.append(variant)
            control_created = True
        
        # Define metrics to track
        metrics = [
            ExperimentMetric(
                name="response_quality",
                type="numeric",
                description="Response quality score (1-5)",
                higher_is_better=True
            ),
            ExperimentMetric(
                name="user_satisfaction", 
                type="conversion",
                description="User satisfaction rate",
                higher_is_better=True
            ),
            ExperimentMetric(
                name="escalation_rate",
                type="conversion", 
                description="Rate of escalation to human agents",
                higher_is_better=False
            ),
            ExperimentMetric(
                name="response_time",
                type="duration",
                description="Response generation time",
                higher_is_better=False
            ),
            ExperimentMetric(
                name="confidence_score",
                type="numeric",
                description="Model confidence in response",
                higher_is_better=True
            )
        ]
        
        # Create experiment
        experiment_id = f"prompt_exp_{int(time.time())}"
        experiment = Experiment(
            id=experiment_id,
            name=name,
            description=description,
            variants=variants,
            metrics=metrics,
            traffic_allocation=TrafficAllocation.WEIGHTED,
            target_population="all"
        )
        
        # Register with engine
        engine = await get_experiment_engine()
        await engine.register_experiment(experiment)
        
        self.active_experiments[experiment_id] = experiment
        
        logger.info(f"Created prompt experiment: {name} ({experiment_id})")
        return experiment_id
    
    async def get_prompt_config(self,
                              session_id: str,
                              user_id: Optional[str] = None,
                              intent: Optional[str] = None) -> Optional[PromptConfig]:
        """
        Get the appropriate prompt configuration for a session.

        Returns ``None`` — meaning "use the default prompts" — both when no
        experiment applies and when the experiment engine fails. Experimentation
        is an optional overlay on the reasoning path, so an outage here must
        degrade to the control prompts rather than break the agent.
        """
        try:
            engine = await get_experiment_engine()

            # Check all active prompt experiments
            for exp_id, experiment in self.active_experiments.items():
                # Skip experiments that target a *different* intent. An
                # experiment is relevant when at least one of its variants is
                # untargeted or targets this intent.
                #
                # The previous version ran `continue` inside a nested loop over
                # the variants, which only advanced that inner loop and then
                # fell through to `get_variant` regardless — so intent targeting
                # never actually filtered anything.
                targets = {
                    variant.config.get("target_intent")
                    for variant in experiment.variants.values()
                }
                if intent is not None and targets and all(
                    target is not None and target != intent for target in targets
                ):
                    continue

                # Get variant assignment
                variant = await engine.get_variant(
                    experiment_id=exp_id,
                    session_id=session_id,
                    user_id=user_id,
                    context={"intent": intent}
                )

                if variant:
                    config_data = variant.config["prompt_config"]
                    return PromptConfig(
                        system_prompt=config_data["system_prompt"],
                        reasoning_prompt=config_data["reasoning_prompt"],
                        response_template=config_data["response_template"],
                        model_params=config_data["model_params"],
                        use_chain_of_thought=config_data["use_chain_of_thought"],
                        max_tokens=config_data["max_tokens"],
                        temperature=config_data["temperature"],
                        examples=config_data["examples"]
                    )
        except Exception as e:
            logger.warning(f"Prompt experiment lookup failed, using defaults: {e}")

        return None  # Use default configuration

    async def track_response_metrics(self,
                                   session_id: str,
                                   response_quality: Optional[float] = None,
                                   user_satisfied: Optional[bool] = None,
                                   escalated: Optional[bool] = None,
                                   response_time_ms: Optional[float] = None,
                                   confidence_score: Optional[float] = None) -> None:
        """
        Track metrics for prompt experiments.

        Never raises: metric tracking is fire-and-forget telemetry called from
        the reasoning node's happy path, so a failing engine must not surface as
        a failed customer response.
        """
        try:
            engine = await get_experiment_engine()

            # Track metrics for all active experiments
            for exp_id in self.active_experiments.keys():
                if response_quality is not None:
                    await engine.track_metric(exp_id, session_id, "response_quality", response_quality)

                if user_satisfied is not None:
                    await engine.track_metric(exp_id, session_id, "user_satisfaction", user_satisfied)

                if escalated is not None:
                    await engine.track_metric(exp_id, session_id, "escalation_rate", escalated)

                if response_time_ms is not None:
                    await engine.track_metric(exp_id, session_id, "response_time", response_time_ms / 1000.0)

                if confidence_score is not None:
                    await engine.track_metric(exp_id, session_id, "confidence_score", confidence_score)
        except Exception as e:
            logger.warning(f"Prompt experiment metric tracking failed: {e}")


# Pre-defined prompt experiments
PROMPT_EXPERIMENTS = {
    "reasoning_style": {
        "control": PromptConfig(
            system_prompt="""You are Fin, a helpful financial AI assistant. Provide accurate, helpful responses about banking and financial services.""",
            reasoning_prompt="""Analyze the customer's question and provide a direct response.""",
            response_template="""Based on your question about {topic}, here's what I can help with:

{response}

{follow_up}""",
            model_params={"temperature": 0.7, "max_tokens": 500},
            # The control is the *direct answer* arm — chain-of-thought is the
            # treatment being measured against it.
            use_chain_of_thought=False,
            max_tokens=500,
            temperature=0.7
        ),
        "chain_of_thought": PromptConfig(
            system_prompt="""You are Fin, a helpful financial AI assistant. Think step by step about each customer question to provide the most accurate and helpful response.""",
            reasoning_prompt="""Let me think through this step by step:
1. What is the customer asking?
2. What information do I need to provide?
3. What's the most helpful way to structure my response?
4. Are there any important warnings or next steps?

Now I'll provide my response:""",
            response_template="""I understand you're asking about {topic}. Let me help you with that.

{response}

{follow_up}""",
            model_params={"temperature": 0.5, "max_tokens": 600},
            use_chain_of_thought=True,
            max_tokens=600,
            temperature=0.5
        )
    },
    
    "empathy_level": {
        "standard": PromptConfig(
            system_prompt="""You are Fin, a financial AI assistant. Provide helpful and professional responses.""",
            reasoning_prompt="""Provide a clear, professional response to the customer's question.""",
            response_template="""{response}

Is there anything else I can help you with?""",
            model_params={"temperature": 0.7},
            temperature=0.7
        ),
        "high_empathy": PromptConfig(
            system_prompt="""You are Fin, a caring and empathetic financial AI assistant. You understand that financial issues can be stressful and personal. Always respond with warmth, understanding, and genuine care for the customer's situation.""",
            reasoning_prompt="""Consider the customer's emotional state and potential stress level. Provide a response that is both helpful and emotionally supportive.""",
            response_template="""I understand this situation might be concerning for you. {response}

I'm here to help you through this. What other questions do you have?""",
            model_params={"temperature": 0.8},
            temperature=0.8
        )
    },
    
    "response_length": {
        "concise": PromptConfig(
            system_prompt="""You are Fin, a financial AI assistant. Provide concise, direct answers. Keep responses brief but complete.""",
            reasoning_prompt="""Provide the most important information in a concise format.""",
            response_template="""{response}""",
            model_params={"temperature": 0.6, "max_tokens": 300},
            max_tokens=300,
            temperature=0.6
        ),
        "detailed": PromptConfig(
            system_prompt="""You are Fin, a financial AI assistant. Provide comprehensive, detailed explanations to help customers fully understand their financial options.""",
            reasoning_prompt="""Provide a thorough explanation covering all relevant aspects of the customer's question.""",
            response_template="""Let me provide you with a comprehensive explanation:

{response}

Additional considerations:
{additional_info}

Next steps:
{next_steps}""",
            model_params={"temperature": 0.7, "max_tokens": 800},
            max_tokens=800,
            temperature=0.7
        )
    }
}


# Global prompt experiment manager
_prompt_manager: Optional[PromptExperimentManager] = None

async def get_prompt_manager() -> PromptExperimentManager:
    """Get singleton prompt experiment manager."""
    global _prompt_manager
    if _prompt_manager is None:
        _prompt_manager = PromptExperimentManager()
    return _prompt_manager


async def initialize_default_experiments():
    """Initialize default prompt experiments."""
    manager = await get_prompt_manager()
    
    # Create reasoning style experiment
    await manager.create_prompt_experiment(
        name="Reasoning Style Comparison",
        description="Compare direct responses vs chain-of-thought reasoning",
        prompt_variants=PROMPT_EXPERIMENTS["reasoning_style"],
        traffic_split=0.2
    )
    
    # Create empathy level experiment  
    await manager.create_prompt_experiment(
        name="Empathy Level Testing", 
        description="Test impact of empathetic language on user satisfaction",
        prompt_variants=PROMPT_EXPERIMENTS["empathy_level"],
        traffic_split=0.15
    )
    
    # Create response length experiment
    await manager.create_prompt_experiment(
        name="Response Length Optimization",
        description="Optimize response length for user engagement", 
        prompt_variants=PROMPT_EXPERIMENTS["response_length"],
        traffic_split=0.1
    )