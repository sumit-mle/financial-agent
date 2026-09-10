"""
Integration layer for A/B testing with the main agent pipeline.

Provides decorators and utilities to seamlessly integrate experimentation
into the agent's reasoning and response generation process.
"""
import time
from functools import wraps
from typing import Any, Callable, Dict, Optional

from app.experimentation.prompt_experiments import get_prompt_manager
from app.experimentation.framework import get_experiment_engine
from app.core.logging import get_logger

logger = get_logger(__name__)


def experiment_prompt_override(func: Callable) -> Callable:
    """
    Decorator for methods that can be overridden by A/B testing experiments.
    
    This decorator allows experimental prompt configurations to override
    default prompts during A/B testing. The decorated method should return
    an experimental prompt or None to use the default.
    
    Usage:
        @experiment_prompt_override
        async def _get_experimental_prompt(self, base_prompt: str, state: AgentState) -> Optional[str]:
            # Method logic that may return experimental prompt
            return experimental_prompt or None
    """
    @wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            result = await func(*args, **kwargs)
            return result
        except Exception as e:
            logger.warning(f"Experiment prompt override failed: {e}")
            # Return None to fall back to default behavior
            return None
    
    return wrapper


def with_prompt_experimentation(func: Callable) -> Callable:
    """
    Decorator to enable prompt experimentation in reasoning nodes.
    
    Automatically:
    1. Retrieves experimental prompt configuration
    2. Applies it to the reasoning process
    3. Tracks performance metrics
    """
    @wraps(func)
    async def wrapper(self, state, *args, **kwargs):
        session_id = getattr(state, 'session_id', None)
        detected_intent = getattr(state, 'detected_intent', None)
        
        if not session_id:
            # No session ID, use default behavior
            return await func(self, state, *args, **kwargs)
        
        # Get experimental prompt configuration
        prompt_manager = await get_prompt_manager()
        prompt_config = await prompt_manager.get_prompt_config(
            session_id=session_id,
            intent=detected_intent
        )
        
        if prompt_config:
            logger.debug(f"Using experimental prompt config for session {session_id}")
            
            # Store original prompt and apply experimental one
            original_prompt = getattr(self, '_reasoning_prompt', None)
            
            # Apply experimental configuration
            if hasattr(self, '_apply_experimental_config'):
                self._apply_experimental_config(prompt_config)
            
            # Track start time for response time metric
            start_time = time.time()
            
            try:
                # Execute with experimental configuration
                result = await func(self, state, *args, **kwargs)
                
                # Track response time
                response_time_ms = (time.time() - start_time) * 1000
                
                # Extract confidence from result
                confidence = getattr(result, 'confidence', getattr(state, 'confidence', 0.5))
                
                # Track metrics
                await prompt_manager.track_response_metrics(
                    session_id=session_id,
                    response_time_ms=response_time_ms,
                    confidence_score=confidence
                )
                
                return result
                
            except Exception as e:
                logger.error(f"Error in experimental reasoning: {e}")
                # Restore original configuration and retry
                if original_prompt:
                    setattr(self, '_reasoning_prompt', original_prompt)
                return await func(self, state, *args, **kwargs)
                
            finally:
                # Restore original configuration
                if original_prompt:
                    setattr(self, '_reasoning_prompt', original_prompt)
        else:
            # No experimental configuration, use default behavior
            return await func(self, state, *args, **kwargs)
    
    return wrapper


def track_user_feedback(session_id: str, 
                       helpful: bool, 
                       rating: Optional[int] = None,
                       escalated: bool = False) -> None:
    """
    Track user feedback for experimental analysis.
    
    Args:
        session_id: User session ID
        helpful: Whether the response was helpful
        rating: Optional 1-5 rating
        escalated: Whether the interaction was escalated
    """
    async def _track():
        try:
            prompt_manager = await get_prompt_manager()
            
            # Convert rating to response quality score
            response_quality = None
            if rating is not None:
                response_quality = rating / 5.0  # Normalize to 0-1
            
            await prompt_manager.track_response_metrics(
                session_id=session_id,
                response_quality=response_quality,
                user_satisfied=helpful,
                escalated=escalated
            )
            
        except Exception as e:
            logger.error(f"Failed to track feedback: {e}")
    
    # Run async tracking
    import asyncio
    try:
        asyncio.create_task(_track())
    except:
        # If no event loop, run synchronously
        asyncio.run(_track())


class ExperimentalPromptProvider:
    """
    Provider class for experimental prompts in reasoning nodes.
    
    Usage in reasoning node:
        def __init__(self):
            self.prompt_provider = ExperimentalPromptProvider()
        
        async def run(self, state):
            prompt = await self.prompt_provider.get_prompt(
                session_id=state.session_id,
                intent=state.detected_intent,
                default_prompt=self._default_prompt
            )
            # Use prompt for LLM call
    """
    
    def __init__(self):
        self._prompt_manager = None
    
    async def _get_manager(self):
        if self._prompt_manager is None:
            self._prompt_manager = await get_prompt_manager()
        return self._prompt_manager
    
    async def get_prompt(self,
                        session_id: str,
                        intent: Optional[str] = None,
                        default_prompt: str = "",
                        prompt_type: str = "reasoning_prompt") -> str:
        """Get experimental prompt or fallback to default."""
        
        try:
            manager = await self._get_manager()
            config = await manager.get_prompt_config(
                session_id=session_id,
                intent=intent
            )
            
            if config:
                if prompt_type == "system_prompt":
                    return config.system_prompt
                elif prompt_type == "reasoning_prompt":
                    return config.reasoning_prompt
                elif prompt_type == "response_template":
                    return config.response_template
                    
        except Exception as e:
            logger.error(f"Failed to get experimental prompt: {e}")
        
        return default_prompt
    
    async def get_model_params(self,
                              session_id: str,
                              intent: Optional[str] = None,
                              default_params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Get experimental model parameters or fallback to default."""
        
        try:
            manager = await self._get_manager()
            config = await manager.get_prompt_config(
                session_id=session_id,
                intent=intent
            )
            
            if config:
                return {
                    "temperature": config.temperature,
                    "max_tokens": config.max_tokens,
                    **config.model_params
                }
                
        except Exception as e:
            logger.error(f"Failed to get experimental model params: {e}")
        
        return default_params or {}


class ExperimentTracker:
    """
    Utility class for tracking experiment events and metrics.
    """
    
    def __init__(self):
        self._engine = None
    
    async def _get_engine(self):
        if self._engine is None:
            self._engine = await get_experiment_engine()
        return self._engine
    
    async def track_conversion(self,
                              session_id: str,
                              metric_name: str,
                              success: bool):
        """Track a conversion event (success/failure)."""
        
        try:
            engine = await self._get_engine()
            
            # Track for all active experiments
            for exp_id in engine._experiments.keys():
                await engine.track_metric(
                    experiment_id=exp_id,
                    session_id=session_id,
                    metric_name=metric_name,
                    value=success
                )
                
        except Exception as e:
            logger.error(f"Failed to track conversion: {e}")
    
    async def track_numeric_metric(self,
                                  session_id: str,
                                  metric_name: str,
                                  value: float):
        """Track a numeric metric value."""
        
        try:
            engine = await self._get_engine()
            
            # Track for all active experiments
            for exp_id in engine._experiments.keys():
                await engine.track_metric(
                    experiment_id=exp_id,
                    session_id=session_id,
                    metric_name=metric_name,
                    value=value
                )
                
        except Exception as e:
            logger.error(f"Failed to track numeric metric: {e}")


# Global instances
_experiment_tracker = None
_prompt_provider = None

def get_experiment_tracker() -> ExperimentTracker:
    """Get global experiment tracker instance."""
    global _experiment_tracker
    if _experiment_tracker is None:
        _experiment_tracker = ExperimentTracker()
    return _experiment_tracker

def get_prompt_provider() -> ExperimentalPromptProvider:
    """Get global experimental prompt provider instance."""
    global _prompt_provider
    if _prompt_provider is None:
        _prompt_provider = ExperimentalPromptProvider()
    return _prompt_provider