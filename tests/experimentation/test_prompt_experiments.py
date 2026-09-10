"""
Tests for Prompt Experimentation System.

Note on patch targets: ``prompt_experiments`` binds ``get_experiment_engine``
at import time, so these tests patch it *there* rather than in
``app.experimentation.framework`` — patching the defining module leaves the
already-bound name untouched and the real engine would be used instead.
"""
import pytest
from types import SimpleNamespace
from unittest.mock import patch, AsyncMock

from app.experimentation.prompt_experiments import (
    PromptExperimentManager,
    PromptConfig,
    get_prompt_manager,
    PROMPT_EXPERIMENTS
)


@pytest.mark.models
@pytest.mark.unit
class TestPromptExperiments:
    """Test suite for prompt experimentation."""
    
    @pytest.fixture
    def prompt_config(self):
        """Sample prompt configuration."""
        return PromptConfig(
            system_prompt="You are a helpful AI assistant.",
            reasoning_prompt="Think carefully about the user's question.",
            response_template="Here's my response: {response}",
            model_params={"temperature": 0.7},
            use_chain_of_thought=True,
            max_tokens=500,
            temperature=0.7,
            examples=["Example 1", "Example 2"]
        )
    
    def test_prompt_config_dataclass(self, prompt_config):
        """Test PromptConfig dataclass creation."""
        assert prompt_config.system_prompt == "You are a helpful AI assistant."
        assert prompt_config.reasoning_prompt == "Think carefully about the user's question."
        assert prompt_config.model_params["temperature"] == 0.7
        assert prompt_config.use_chain_of_thought is True
        assert prompt_config.max_tokens == 500
        assert len(prompt_config.examples) == 2
    
    @pytest.mark.asyncio
    async def test_prompt_experiment_manager_creation(self):
        """Test prompt experiment manager creation."""
        manager = PromptExperimentManager()
        assert manager.active_experiments == {}
    
    @pytest.mark.asyncio
    async def test_create_prompt_experiment(self):
        """Test creating a prompt experiment."""
        manager = PromptExperimentManager()
        
        # Sample prompt variants
        prompt_variants = {
            "control": PromptConfig(
                system_prompt="Standard prompt",
                reasoning_prompt="Standard reasoning",
                response_template="Standard response: {response}",
                model_params={"temperature": 0.7}
            ),
            "experimental": PromptConfig(
                system_prompt="Experimental prompt with more empathy",
                reasoning_prompt="Consider emotional context",
                response_template="I understand your concern: {response}",
                model_params={"temperature": 0.8}
            )
        }
        
        with patch('app.experimentation.prompt_experiments.get_experiment_engine') as mock_engine:
            mock_engine_instance = AsyncMock()
            mock_engine.return_value = mock_engine_instance
            
            experiment_id = await manager.create_prompt_experiment(
                name="Empathy Test",
                description="Test empathetic responses",
                prompt_variants=prompt_variants,
                target_intent="complaint",
                traffic_split=0.2
            )
            
            assert experiment_id is not None
            assert experiment_id in manager.active_experiments
            assert mock_engine_instance.register_experiment.called
    
    @pytest.mark.asyncio 
    async def test_get_prompt_config_with_experiment(self):
        """Test getting prompt config when experiment is active."""
        manager = PromptExperimentManager()
        
        # Mock experiment setup
        from app.experimentation.framework import Experiment, ExperimentVariant, ExperimentMetric
        
        variant = ExperimentVariant(
            id="experimental",
            name="Experimental",
            description="Experimental variant",
            config={
                "prompt_config": {
                    "system_prompt": "Experimental system prompt",
                    "reasoning_prompt": "Experimental reasoning",
                    "response_template": "Experimental: {response}",
                    "model_params": {"temperature": 0.8},
                    "use_chain_of_thought": True,
                    "max_tokens": 600,
                    "temperature": 0.8,
                    "examples": []
                },
                "target_intent": "complaint"
            },
            traffic_weight=0.5
        )
        
        # Mock the experiment engine
        with patch('app.experimentation.prompt_experiments.get_experiment_engine') as mock_engine:
            mock_engine_instance = AsyncMock()
            mock_engine_instance.get_variant.return_value = variant
            mock_engine.return_value = mock_engine_instance

            # A stand-in experiment. `get_prompt_config` reads `.variants` to
            # apply intent targeting, so this needs a real dict — a bare
            # AsyncMock would hand back a non-iterable mock.
            manager.active_experiments["test_exp"] = SimpleNamespace(
                id="test_exp",
                variants={"experimental": variant},
            )

            config = await manager.get_prompt_config(
                session_id="test_session",
                intent="complaint"
            )
            
            assert config is not None
            assert config.system_prompt == "Experimental system prompt"
            assert config.reasoning_prompt == "Experimental reasoning"
            assert config.temperature == 0.8
            assert config.max_tokens == 600
    
    @pytest.mark.asyncio
    async def test_get_prompt_config_no_experiment(self):
        """Test getting prompt config when no experiment is active."""
        manager = PromptExperimentManager()
        
        with patch('app.experimentation.prompt_experiments.get_experiment_engine') as mock_engine:
            mock_engine_instance = AsyncMock()
            mock_engine_instance.get_variant.return_value = None
            mock_engine.return_value = mock_engine_instance
            
            config = await manager.get_prompt_config(
                session_id="test_session",
                intent="general"
            )
            
            assert config is None  # Should return None for default behavior
    
    @pytest.mark.asyncio
    async def test_track_response_metrics(self):
        """Test tracking response metrics."""
        manager = PromptExperimentManager()
        
        with patch('app.experimentation.prompt_experiments.get_experiment_engine') as mock_engine:
            mock_engine_instance = AsyncMock()
            mock_engine.return_value = mock_engine_instance
            
            # Add mock experiment
            manager.active_experiments["exp_1"] = AsyncMock()
            
            await manager.track_response_metrics(
                session_id="test_session",
                response_quality=4.2,
                user_satisfied=True,
                escalated=False,
                response_time_ms=1500.0,
                confidence_score=0.85
            )
            
            # Should have called track_metric for each metric
            assert mock_engine_instance.track_metric.call_count >= 4
    
    def test_predefined_prompt_experiments(self):
        """Test predefined prompt experiment configurations."""
        # Test reasoning style experiments
        reasoning_experiments = PROMPT_EXPERIMENTS["reasoning_style"]
        assert "control" in reasoning_experiments
        assert "chain_of_thought" in reasoning_experiments
        
        control_config = reasoning_experiments["control"]
        assert isinstance(control_config, PromptConfig)
        assert control_config.use_chain_of_thought is False
        
        cot_config = reasoning_experiments["chain_of_thought"]
        assert cot_config.use_chain_of_thought is True
        assert "step by step" in cot_config.reasoning_prompt.lower()
    
    def test_empathy_level_experiments(self):
        """Test empathy level experiment configurations."""
        empathy_experiments = PROMPT_EXPERIMENTS["empathy_level"]
        assert "standard" in empathy_experiments
        assert "high_empathy" in empathy_experiments
        
        standard_config = empathy_experiments["standard"]
        high_empathy_config = empathy_experiments["high_empathy"]
        
        # High empathy should have more emotional language
        assert len(high_empathy_config.system_prompt) > len(standard_config.system_prompt)
        assert "caring" in high_empathy_config.system_prompt.lower()
        assert "empathetic" in high_empathy_config.system_prompt.lower()
    
    def test_response_length_experiments(self):
        """Test response length experiment configurations."""
        length_experiments = PROMPT_EXPERIMENTS["response_length"]
        assert "concise" in length_experiments
        assert "detailed" in length_experiments
        
        concise_config = length_experiments["concise"]
        detailed_config = length_experiments["detailed"]
        
        # Concise should have lower max_tokens
        assert concise_config.max_tokens < detailed_config.max_tokens
        assert "brief" in concise_config.system_prompt.lower()
        assert "comprehensive" in detailed_config.system_prompt.lower()
    
    @pytest.mark.asyncio
    async def test_prompt_manager_singleton(self):
        """Test prompt manager singleton pattern."""
        manager1 = await get_prompt_manager()
        manager2 = await get_prompt_manager()
        
        # Should be same instance
        assert manager1 is manager2
    
    @pytest.mark.asyncio
    async def test_initialize_default_experiments(self):
        """Test initializing default experiments."""
        from app.experimentation.prompt_experiments import initialize_default_experiments
        
        with patch('app.experimentation.prompt_experiments.get_prompt_manager') as mock_manager:
            mock_manager_instance = AsyncMock()
            mock_manager.return_value = mock_manager_instance
            
            await initialize_default_experiments()
            
            # Should have created multiple experiments
            assert mock_manager_instance.create_prompt_experiment.call_count >= 3
    
    @pytest.mark.asyncio
    async def test_prompt_config_target_intent_filtering(self):
        """Test that experiments can target specific intents."""
        manager = PromptExperimentManager()
        
        # Create experiment targeting specific intent
        # Two variants: `Experiment` requires at least a control and a treatment.
        prompt_variants = {
            "control": PromptConfig(
                system_prompt="Standard",
                reasoning_prompt="Standard",
                response_template="Standard: {response}",
                model_params={}
            ),
            "specialized": PromptConfig(
                system_prompt="Specialized",
                reasoning_prompt="Specialized",
                response_template="Specialized: {response}",
                model_params={}
            )
        }

        with patch('app.experimentation.prompt_experiments.get_experiment_engine') as mock_engine:
            mock_engine_instance = AsyncMock()
            mock_engine.return_value = mock_engine_instance

            await manager.create_prompt_experiment(
                name="Intent-Specific Test",
                description="Test for fraud reports only",
                prompt_variants=prompt_variants,
                target_intent="fraud_report",  # Specific intent
                traffic_split=0.3
            )
            
            # Verify experiment was created with correct target
            call_args = mock_engine_instance.register_experiment.call_args[0][0]
            
            # Check that variants have target_intent in config
            for variant in call_args.variants.values():
                assert variant.config.get("target_intent") == "fraud_report"
    
    @pytest.mark.asyncio
    async def test_error_handling_in_get_prompt_config(self):
        """Test error handling in get_prompt_config."""
        manager = PromptExperimentManager()
        
        with patch('app.experimentation.prompt_experiments.get_experiment_engine') as mock_engine:
            # Simulate engine error
            mock_engine.side_effect = Exception("Engine error")
            
            config = await manager.get_prompt_config(
                session_id="test_session", 
                intent="test"
            )
            
            # Should return None on error, not crash
            assert config is None
    
    @pytest.mark.asyncio
    async def test_error_handling_in_track_metrics(self):
        """Test error handling in track_response_metrics."""
        manager = PromptExperimentManager()
        
        with patch('app.experimentation.prompt_experiments.get_experiment_engine') as mock_engine:
            # Simulate engine error
            mock_engine.side_effect = Exception("Tracking error")
            
            # Should not raise exception
            await manager.track_response_metrics(
                session_id="test_session",
                response_quality=3.5
            )