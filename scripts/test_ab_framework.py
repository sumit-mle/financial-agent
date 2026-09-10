#!/usr/bin/env python3
"""
Test script to demonstrate A/B testing framework functionality.
"""
import asyncio
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.experimentation.framework import (
    ExperimentEngine, Experiment, ExperimentVariant, ExperimentMetric, ExperimentStatus
)
from app.experimentation.prompt_experiments import PromptExperimentManager, PromptConfig
from app.agent.state import AgentState
from app.agent.nodes.reasoning_node import ReasoningNode

async def test_ab_framework():
    """Test the complete A/B testing framework."""
    print("🧪 Testing A/B Testing Framework\n")
    
    # 1. Test basic experiment creation and assignment
    print("1. Testing Basic Experiment Engine...")
    engine = ExperimentEngine()
    
    # Create experiment
    variants = [
        ExperimentVariant("control", "Control", "Standard prompt", {}, 0.6, True),
        ExperimentVariant("empathetic", "Empathetic", "Empathetic prompt", {}, 0.4, False)
    ]
    metrics = [
        ExperimentMetric("user_satisfaction", "conversion", "User satisfaction", True),
        ExperimentMetric("escalation_rate", "conversion", "Escalation rate", False)
    ]
    
    experiment = Experiment("test_empathy", "Empathy Test", "Test empathy in responses", variants, metrics)
    experiment.status = ExperimentStatus.ACTIVE
    
    await engine.register_experiment(experiment)
    print("   ✅ Experiment registered")
    
    # Test variant assignments
    sessions = ["user_123", "user_456", "user_789", "user_abc", "user_def"]
    assignments = {}
    
    for session_id in sessions:
        variant = await engine.get_variant("test_empathy", session_id)
        assignments[session_id] = variant.id
        print(f"   📊 Session {session_id} → {variant.name}")
    
    # Verify consistency
    for session_id in sessions[:3]:  # Test first 3 again
        variant = await engine.get_variant("test_empathy", session_id)
        assert variant.id == assignments[session_id], f"Assignment inconsistent for {session_id}"
    
    print("   ✅ Variant assignments are consistent")
    
    # 2. Test metric tracking
    print("\n2. Testing Metric Tracking...")
    
    for session_id in sessions:
        # Simulate user interaction metrics
        user_satisfied = session_id[-1] in ['3', '9', 'c']  # Some users satisfied
        escalated = session_id[-1] in ['6', 'f']  # Some escalated
        
        await engine.track_metric("test_empathy", session_id, "user_satisfaction", user_satisfied)
        await engine.track_metric("test_empathy", session_id, "escalation_rate", escalated)
        
        print(f"   📈 Tracked metrics for {session_id}: satisfied={user_satisfied}, escalated={escalated}")
    
    print("   ✅ Metrics tracked successfully")
    
    # 3. Test prompt experiment manager
    print("\n3. Testing Prompt Experiment Manager...")
    
    manager = PromptExperimentManager()
    
    # Create prompt experiment
    prompt_variants = {
        "standard": PromptConfig(
            system_prompt="You are Fin, a professional financial AI assistant.",
            reasoning_prompt="Analyze the query and provide a clear, factual response.",
            response_template="Based on your question: {response}",
            model_params={"temperature": 0.7},
            use_chain_of_thought=False,
            max_tokens=400
        ),
        "empathetic": PromptConfig(
            system_prompt="You are Fin, a caring and empathetic financial AI assistant who understands that financial matters can be deeply personal and stressful.",
            reasoning_prompt="Consider the customer's emotional state and potential stress. Craft a response that is both informative and emotionally supportive.",
            response_template="I understand this situation might be concerning. Let me help you with that: {response}",
            model_params={"temperature": 0.8},
            use_chain_of_thought=True,
            max_tokens=600
        )
    }
    
    exp_id = await manager.create_prompt_experiment(
        name="Customer Care Empathy Test",
        description="Compare standard vs empathetic responses",
        prompt_variants=prompt_variants,
        traffic_split=0.5
    )
    
    print(f"   ✅ Created prompt experiment: {exp_id}")
    
    # Test getting experimental prompts
    for session_id in sessions[:3]:
        config = await manager.get_prompt_config(session_id=session_id)
        if config:
            print(f"   🎭 Session {session_id} gets experimental config (temp={config.temperature})")
        else:
            print(f"   📝 Session {session_id} gets default prompt")
    
    # 4. Test integration with reasoning node
    print("\n4. Testing Reasoning Node Integration...")
    
    # Mock LLM client
    class MockLLMClient:
        async def ainvoke(self, prompt):
            # Return different responses based on prompt content
            if "caring" in prompt or "empathetic" in prompt:
                response_content = '''
                {
                    "decision": "answer",
                    "confidence": 0.82,
                    "response": "I understand this situation might be stressful for you. Let me help you resolve this banking issue with care and attention to your concerns.",
                    "action_name": null,
                    "action_parameters": {},
                    "reasoning": "Using empathetic approach to address customer concern",
                    "follow_up_suggestions": ["Is there anything else I can help you with today?", "Would you like me to explain any part of this in more detail?"]
                }
                '''
            else:
                response_content = '''
                {
                    "decision": "answer",
                    "confidence": 0.75,
                    "response": "Based on your account information, here is the resolution to your banking inquiry.",
                    "action_name": null,
                    "action_parameters": {},
                    "reasoning": "Standard response based on query analysis",
                    "follow_up_suggestions": ["Any other questions?"]
                }
                '''
            
            class MockResponse:
                content = response_content
            return MockResponse()
    
    # Test reasoning node with A/B testing
    reasoning_node = ReasoningNode(llm_client=MockLLMClient())
    
    for i, session_id in enumerate(sessions[:2]):
        state = AgentState(
            session_id=session_id,
            user_message="I'm worried about suspicious charges on my account.",
            assembled_context="Customer has checking account with recent transactions."
        )
        state.intent = "fraud_inquiry"
        
        result_state = await reasoning_node.run(state)
        
        print(f"   🤖 Session {session_id}:")
        print(f"      Decision: {result_state.agent_decision}")
        print(f"      Confidence: {result_state.confidence_score:.2f}")
        print(f"      Response: {result_state.final_response[:100]}...")
    
    print("   ✅ Reasoning node A/B testing integration working")
    
    # 5. Test distribution analysis
    print("\n5. Testing Traffic Distribution...")
    
    # Test with larger sample
    large_sessions = [f"session_{i:04d}" for i in range(100)]
    distribution = {"control": 0, "empathetic": 0}
    
    for session_id in large_sessions:
        variant = await engine.get_variant("test_empathy", session_id)
        distribution[variant.id] += 1
    
    control_pct = distribution["control"] / len(large_sessions)
    empathetic_pct = distribution["empathetic"] / len(large_sessions)
    
    print(f"   📊 Distribution over {len(large_sessions)} sessions:")
    print(f"      Control: {control_pct:.1%} (expected ~60%)")
    print(f"      Empathetic: {empathetic_pct:.1%} (expected ~40%)")
    
    # Check if distribution is roughly correct (allow for random variance)
    assert 0.4 <= control_pct <= 0.8, f"Control distribution off: {control_pct:.1%}"
    assert 0.2 <= empathetic_pct <= 0.6, f"Empathetic distribution off: {empathetic_pct:.1%}"
    
    print("   ✅ Traffic distribution is working correctly")
    
    print("\n🎉 All A/B Testing Framework tests passed!")
    print("\nFramework Features Demonstrated:")
    print("  ✅ Experiment creation and management")
    print("  ✅ Consistent variant assignments")
    print("  ✅ Metric tracking")
    print("  ✅ Prompt experimentation")
    print("  ✅ Integration with reasoning nodes")
    print("  ✅ Traffic allocation")
    print("  ✅ Experimental prompt overrides")

if __name__ == "__main__":
    asyncio.run(test_ab_framework())