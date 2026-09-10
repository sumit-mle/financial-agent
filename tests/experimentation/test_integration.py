"""
Integration tests for A/B Testing Framework.

Note on patch targets: both ``prompt_experiments`` and ``reasoning_node`` bind
their collaborators (``get_experiment_engine`` / ``get_prompt_manager``) at
import time, so these tests patch the name *in the importing module*. Patching
the defining module leaves the already-bound reference alone and the real
singletons get used instead.
"""
import pytest
from unittest.mock import patch, AsyncMock, MagicMock

from app.experimentation.framework import (
    ExperimentEngine, Experiment, ExperimentVariant, ExperimentMetric, ExperimentStatus
)
from app.experimentation.prompt_experiments import PromptExperimentManager, PromptConfig
from app.experimentation.integration import experiment_prompt_override
from app.agent.nodes.reasoning_node import ReasoningNode
from app.agent.state import AgentState


@pytest.mark.models
@pytest.mark.integration
class TestABTestingIntegration:
    """Integration tests for A/B testing framework."""
    
    @pytest.fixture
    def mock_llm_client(self):
        """Mock LLM client for testing."""
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.content = '''
        {
            "decision": "answer",
            "confidence": 0.85,
            "response": "Test response from experimental prompt",
            "action_name": null,
            "action_parameters": {},
            "reasoning": "Answered based on retrieved context",
            "follow_up_suggestions": ["Any other questions?"]
        }
        '''
        mock_client.ainvoke.return_value = mock_response
        return mock_client
    
    @pytest.fixture
    def sample_agent_state(self):
        """Create sample agent state for testing."""
        state = AgentState(
            session_id="test_session_123",
            user_message="What are the fees for my checking account?",
            assembled_context="Context: Checking account fees are $5/month for basic accounts."
        )
        state.intent = "fee_inquiry"
        return state
    
    @pytest.mark.asyncio
    async def test_experiment_prompt_override_decorator(self):
        """Test the experiment_prompt_override decorator."""
        
        # Mock function to decorate
        @experiment_prompt_override
        async def mock_get_prompt(base_prompt: str, state: AgentState) -> str:
            return "Experimental prompt content"
        
        state = AgentState(session_id="test_session", user_message="Test")
        
        # Mock experiment engine to return a variant
        with patch('app.experimentation.integration.get_experiment_engine') as mock_engine:
            mock_engine_instance = AsyncMock()
            mock_variant = ExperimentVariant(
                id="experimental",
                name="Experimental",
                description="Test variant",
                config={
                    "prompt_config": {
                        "system_prompt": "Experimental system",
                        "reasoning_prompt": "Experimental reasoning", 
                        "response_template": "Experimental: {response}",
                        "model_params": {"temperature": 0.8},
                        "use_chain_of_thought": True,
                        "max_tokens": 600,
                        "temperature": 0.8,
                        "examples": []
                    }
                }
            )
            mock_engine_instance.get_variant.return_value = mock_variant
            mock_engine.return_value = mock_engine_instance
            
            result = await mock_get_prompt("Base prompt", state)
            assert result == "Experimental prompt content"
    
    @pytest.mark.asyncio
    async def test_reasoning_node_with_experiment(self, mock_llm_client, sample_agent_state):
        """Test reasoning node with active A/B experiment."""
        
        # Create reasoning node with mock LLM
        reasoning_node = ReasoningNode(llm_client=mock_llm_client)
        
        # Mock the experiment system — get_prompt_manager is awaited, so AsyncMock
        with patch('app.agent.nodes.reasoning_node.get_prompt_manager') as mock_pm:
            mock_manager = AsyncMock()
            mock_pm.return_value = mock_manager  # MagicMock is fine; _get_prompt_manager does await get_prompt_manager(), not await get_prompt_manager
            mock_pm.side_effect = None
            # Make get_prompt_manager a coroutine that returns mock_manager
            async def _fake_pm():
                return mock_manager
            mock_pm.side_effect = _fake_pm
            
            # Return experimental config
            experimental_config = PromptConfig(
                system_prompt="You are an empathetic financial AI assistant.",
                reasoning_prompt="Consider the customer's emotional state carefully.",
                response_template="I understand your concern about {topic}: {response}",
                model_params={"temperature": 0.8},
                use_chain_of_thought=True,
                max_tokens=600,
                temperature=0.8,
                examples=["I understand this might be frustrating..."]
            )
            
            mock_manager.get_prompt_config.return_value = experimental_config
            mock_pm.return_value = mock_manager
            
            # Run reasoning node
            result_state = await reasoning_node.run(sample_agent_state)
            
            # Verify experiment integration
            assert result_state.agent_decision == "answer"
            assert result_state.confidence_score == 0.85
            assert result_state.final_response == "Test response from experimental prompt"
            
            # Verify metrics were tracked
            mock_manager.track_response_metrics.assert_called_once()
            call_args = mock_manager.track_response_metrics.call_args[1]
            assert call_args["session_id"] == "test_session_123"
            assert call_args["confidence_score"] == 0.85
            assert call_args["user_satisfied"] is True
            assert call_args["escalated"] is False
    
    @pytest.mark.asyncio
    async def test_reasoning_node_without_experiment(self, mock_llm_client, sample_agent_state):
        """Test reasoning node with no active experiment (control group)."""
        
        reasoning_node = ReasoningNode(llm_client=mock_llm_client)
        
        # Mock no experimental config
        with patch('app.agent.nodes.reasoning_node.get_prompt_manager') as mock_pm:
            mock_manager = AsyncMock()
            mock_manager.get_prompt_config.return_value = None  # No experiment
            async def _fake_pm2():
                return mock_manager
            mock_pm.side_effect = _fake_pm2
            
            result_state = await reasoning_node.run(sample_agent_state)
            
            # Should still work normally
            assert result_state.agent_decision == "answer"
            assert result_state.confidence_score == 0.85
            
            # Metrics still tracked (with default prompts)
            mock_manager.track_response_metrics.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_end_to_end_experiment_flow(self):
        """Test complete A/B testing flow from experiment creation to results."""
        
        # 1. Create experiment
        engine = ExperimentEngine()
        
        variants = [
            ExperimentVariant("control", "Control", "Standard prompt", {}, 0.5, True),
            ExperimentVariant("treatment", "Treatment", "Empathy prompt", {}, 0.5, False)
        ]
        metrics = [
            ExperimentMetric("user_satisfaction", "conversion", "User satisfaction", True),
            ExperimentMetric("escalation_rate", "conversion", "Escalation rate", False)
        ]
        
        experiment = Experiment("e2e_test", "E2E Test", "End to end test", variants, metrics)
        experiment.status = ExperimentStatus.ACTIVE
        
        await engine.register_experiment(experiment)
        
        # 2. Test variant assignment consistency
        session_id = "consistent_user"
        variant1 = await engine.get_variant("e2e_test", session_id)
        variant2 = await engine.get_variant("e2e_test", session_id)
        
        assert variant1.id == variant2.id  # Consistent assignment
        
        # 3. Track metrics
        await engine.track_metric("e2e_test", session_id, "user_satisfaction", True)
        await engine.track_metric("e2e_test", session_id, "escalation_rate", False)
        
        # 4. Verify experiment data
        assert "e2e_test" in engine._experiments
        assert engine._experiments["e2e_test"].status == ExperimentStatus.ACTIVE
    
    @pytest.mark.asyncio
    async def test_prompt_experiment_manager_integration(self):
        """Test prompt experiment manager integration."""
        
        manager = PromptExperimentManager()
        
        # Create prompt experiment
        prompt_variants = {
            "control": PromptConfig(
                system_prompt="Standard AI assistant",
                reasoning_prompt="Analyze and respond",
                response_template="Response: {response}",
                model_params={"temperature": 0.7}
            ),
            "empathetic": PromptConfig(
                system_prompt="Caring and empathetic AI assistant", 
                reasoning_prompt="Consider emotional context",
                response_template="I understand your concern: {response}",
                model_params={"temperature": 0.8}
            )
        }
        
        with patch('app.experimentation.prompt_experiments.get_experiment_engine') as mock_engine:
            mock_engine_instance = AsyncMock()
            mock_engine.return_value = mock_engine_instance
            
            experiment_id = await manager.create_prompt_experiment(
                name="Empathy Test Integration",
                description="Integration test for empathy experiment",
                prompt_variants=prompt_variants,
                target_intent="complaint",
                traffic_split=0.25
            )
            
            assert experiment_id is not None
            assert experiment_id in manager.active_experiments
            
            # Verify experiment was registered with engine
            mock_engine_instance.register_experiment.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_error_handling_in_integration(self, sample_agent_state):
        """Test error handling in experiment integration."""
        
        reasoning_node = ReasoningNode(llm_client=None)  # No LLM client
        
        # Mock experiment manager that throws error
        with patch('app.agent.nodes.reasoning_node.get_prompt_manager') as mock_pm:
            mock_pm.side_effect = Exception("Experiment system down")
            
            # Should still work with fallback
            result_state = await reasoning_node.run(sample_agent_state)
            
            assert result_state.agent_decision == "escalate"  # Fallback behavior
            assert result_state.confidence_score == 0.0
    
    @pytest.mark.asyncio
    async def test_traffic_allocation_distribution(self):
        """Test that traffic allocation works correctly across many sessions."""
        
        engine = ExperimentEngine()
        
        # Create experiment with 70/30 split
        variants = [
            ExperimentVariant("control", "Control", "Control variant", {}, 0.7, True),
            ExperimentVariant("treatment", "Treatment", "Treatment variant", {}, 0.3, False)
        ]
        metrics = [ExperimentMetric("metric", "conversion", "Test metric", True)]
        
        experiment = Experiment("traffic_test", "Traffic Test", "Test traffic", variants, metrics)
        experiment.status = ExperimentStatus.ACTIVE
        await engine.register_experiment(experiment)
        
        # Assign 1000 sessions
        assignments = []
        for i in range(1000):
            variant = await engine.get_variant("traffic_test", f"session_{i}")
            assignments.append(variant.id)
        
        # Check distribution is approximately correct
        control_count = assignments.count("control")
        treatment_count = assignments.count("treatment")
        
        control_pct = control_count / len(assignments)
        treatment_pct = treatment_count / len(assignments)
        
        # Allow 5% variance
        assert 0.65 <= control_pct <= 0.75, f"Control: {control_pct:.1%}"
        assert 0.25 <= treatment_pct <= 0.35, f"Treatment: {treatment_pct:.1%}"
    
    @pytest.mark.asyncio
    async def test_experiment_targeting_by_intent(self):
        """Test that experiments can target specific user intents."""
        
        manager = PromptExperimentManager()
        
        # Create intent-specific experiment
        prompt_variants = {
            "control": PromptConfig(
                system_prompt="Standard response",
                reasoning_prompt="Standard reasoning",
                response_template="{response}",
                model_params={}
            ),
            "specialized": PromptConfig(
                system_prompt="Specialized fraud response system",
                reasoning_prompt="Focus on fraud detection and prevention",
                response_template="Fraud Alert: {response}",
                model_params={"temperature": 0.5}
            )
        }
        
        with patch('app.experimentation.prompt_experiments.get_experiment_engine') as mock_engine:
            mock_engine_instance = AsyncMock()
            mock_engine.return_value = mock_engine_instance
            
            # Create experiment targeting fraud reports
            await manager.create_prompt_experiment(
                name="Fraud Response Test",
                description="Specialized responses for fraud reports",
                prompt_variants=prompt_variants,
                target_intent="fraud_report",  # Target specific intent
                traffic_split=0.5
            )
            
            # Verify experiment configuration includes intent targeting
            call_args = mock_engine_instance.register_experiment.call_args[0][0]
            
            # Check that variants have target_intent configured
            for variant in call_args.variants.values():
                if variant.config:
                    assert variant.config.get("target_intent") == "fraud_report"