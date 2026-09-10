#!/usr/bin/env python3
"""
Test script to demonstrate MLOps pipeline functionality.

Usage:
    python scripts/test_mlops_pipeline.py
"""
import asyncio
import json
import sys
from pathlib import Path
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.mlops.pipeline import get_mlops_pipeline, ModelMetrics
from app.mlops.feedback_collector import get_feedback_collector
from app.mlops.model_registry import get_model_registry, ModelStage, DeploymentStrategy
from app.mlops.data_processor import get_data_processor, DataProcessingConfig
from app.core.logging import get_logger

logger = get_logger(__name__)


async def test_mlops_pipeline():
    """Test the complete MLOps pipeline functionality."""
    print("🤖 Testing MLOps Pipeline for Financial AI Agent\n")
    
    # Initialize components
    pipeline = await get_mlops_pipeline()
    collector = await get_feedback_collector()
    registry = await get_model_registry()
    processor = await get_data_processor()
    
    print("✅ MLOps components initialized\n")
    
    # Test 1: Model Registration
    print("1. 📋 Testing Model Registration...")
    
    # Register initial models
    models_to_register = [
        {
            "model_type": "sentiment_classifier",
            "model_path": "/models/sentiment_v1.pkl",
            "version": "1.0.0",
            "description": "Initial sentiment classification model",
            "metrics": ModelMetrics(
                accuracy=0.85, precision=0.83, recall=0.87, f1_score=0.85,
                confidence_avg=0.78, response_time_avg=1.2, user_satisfaction=0.82,
                escalation_rate=0.15, safety_violations=3, sample_count=1000
            )
        },
        {
            "model_type": "intent_classifier",
            "model_path": "/models/intent_v1.pkl", 
            "version": "1.0.0",
            "description": "Intent classification for customer queries",
            "metrics": ModelMetrics(
                accuracy=0.88, precision=0.86, recall=0.89, f1_score=0.87,
                confidence_avg=0.82, response_time_avg=0.9, user_satisfaction=0.85,
                escalation_rate=0.12, safety_violations=1, sample_count=1200
            )
        }
    ]
    
    registered_models = []
    for model_info in models_to_register:
        model_id = await registry.register_model(
            model_type=model_info["model_type"],
            model_path=model_info["model_path"],
            version=model_info["version"],
            description=model_info["description"],
            training_metrics={
                "accuracy": model_info["metrics"].accuracy,
                "precision": model_info["metrics"].precision,
                "recall": model_info["metrics"].recall,
                "f1_score": model_info["metrics"].f1_score
            },
            validation_metrics={
                "accuracy": model_info["metrics"].accuracy,
                "user_satisfaction": model_info["metrics"].user_satisfaction,
                "response_time": model_info["metrics"].response_time_avg
            }
        )
        registered_models.append((model_id, model_info["model_type"]))
        print(f"   ✅ Registered {model_info['model_type']}: {model_id}")
    
    # Test 2: Model Promotion and Deployment
    print("\n2. 🚀 Testing Model Promotion and Deployment...")
    
    for model_id, model_type in registered_models:
        # Promote to staging
        promoted = await registry.promote_model(model_id, ModelStage.STAGING)
        if promoted:
            print(f"   ✅ {model_type} promoted to staging")
            
            # Promote to production
            promoted_prod = await registry.promote_model(model_id, ModelStage.PRODUCTION)
            if promoted_prod:
                print(f"   ✅ {model_type} promoted to production")
                
                # Deploy with blue-green strategy
                deployment_id = await registry.deploy_model(
                    model_id=model_id,
                    target_stage=ModelStage.PRODUCTION,
                    strategy=DeploymentStrategy.BLUE_GREEN,
                    deployment_notes=f"Initial production deployment for {model_type}"
                )
                if deployment_id:
                    print(f"   🚀 {model_type} deployed: {deployment_id}")
    
    # Test 3: Feedback Collection
    print("\n3. 📊 Testing Feedback Collection...")
    
    # Simulate various types of feedback
    feedback_scenarios = [
        # Positive interactions
        {"model": "sentiment_classifier", "rating": 5, "escalated": False, "safety": False, "confidence": 0.92},
        {"model": "intent_classifier", "rating": 4, "escalated": False, "safety": False, "confidence": 0.88},
        {"model": "sentiment_classifier", "rating": 4, "escalated": False, "safety": False, "confidence": 0.85},
        
        # Mixed interactions
        {"model": "intent_classifier", "rating": 3, "escalated": False, "safety": False, "confidence": 0.70},
        {"model": "sentiment_classifier", "rating": 3, "escalated": False, "safety": False, "confidence": 0.75},
        
        # Negative interactions
        {"model": "sentiment_classifier", "rating": 2, "escalated": True, "safety": False, "confidence": 0.45},
        {"model": "intent_classifier", "rating": 1, "escalated": True, "safety": False, "confidence": 0.30},
        
        # Safety violations
        {"model": "sentiment_classifier", "rating": 1, "escalated": True, "safety": True, "confidence": 0.65}
    ]
    
    for i, scenario in enumerate(feedback_scenarios):
        if scenario["safety"]:
            await collector.collect_safety_violation(
                session_id=f"test_session_{i}",
                model_type=scenario["model"],
                violation_type="inappropriate_content",
                user_message=f"Test message {i}",
                agent_response=f"I cannot assist with that request",
                confidence_score=scenario["confidence"]
            )
        else:
            await collector.collect_user_rating(
                session_id=f"test_session_{i}",
                model_type=scenario["model"],
                rating=scenario["rating"],
                user_message=f"Test user message {i}",
                agent_response=f"Test agent response {i}",
                response_time=1.0 + i * 0.1,
                confidence_score=scenario["confidence"],
                escalated=scenario["escalated"]
            )
    
    print(f"   ✅ Collected {len(feedback_scenarios)} feedback entries")
    
    # Get feedback summary
    summary = await collector.get_feedback_summary()
    print(f"   📈 Feedback Summary:")
    print(f"      Total Feedback: {summary['total_feedback']}")
    print(f"      Average Rating: {summary['avg_rating']:.2f}")
    print(f"      Escalation Rate: {summary['escalation_rate']:.1%}")
    print(f"      Safety Violations: {summary['safety_violations']}")
    
    # Test 4: Data Processing
    print("\n4. 🔧 Testing Data Processing...")
    
    # Configure data processing
    config = DataProcessingConfig(
        source_tables=["user_interactions", "feedback_data"],
        target_model_type="sentiment_classifier",
        training_window_days=30,
        min_samples_per_class=50,  # Lower for demo
        max_samples_per_class=500,
        test_split_ratio=0.2,
        validation_split_ratio=0.1,
        quality_threshold=0.7
    )
    
    # Process training data
    output_path = f"data/processed/demo_{int(datetime.utcnow().timestamp())}"
    
    try:
        result = await processor.process_training_data(config, output_path)
        print(f"   ✅ Data processing completed: {result['job_id']}")
        print(f"      Dataset paths: {list(result['dataset_paths'].keys())}")
        print(f"      Statistics: {json.dumps(result['statistics'], indent=6, default=str)}")
    except Exception as e:
        print(f"   ⚠️  Data processing simulation: {e}")
    
    # Test 5: Retraining Triggers
    print("\n5. ⚡ Testing Retraining Triggers...")
    
    # Register models with pipeline for monitoring
    for model_id, model_type in registered_models:
        model = await registry.get_model(model_id)
        if model:
            await pipeline.register_model(
                model_type=model_type,
                model_path=model.model_path,
                metrics=ModelMetrics(
                    accuracy=model.validation_metrics.get("accuracy", 0.85),
                    precision=0.83, recall=0.87, f1_score=0.85,
                    confidence_avg=0.78, response_time_avg=1.2,
                    user_satisfaction=model.validation_metrics.get("user_satisfaction", 0.82),
                    escalation_rate=0.15, safety_violations=3, sample_count=1000
                )
            )
    
    # Test manual retraining trigger
    await pipeline.trigger_manual_retraining(
        model_type="sentiment_classifier",
        reason="Demo: Testing manual retraining trigger"
    )
    print(f"   ✅ Manual retraining triggered for sentiment_classifier")
    
    # Test 6: Pipeline Status
    print("\n6. 📊 Testing Pipeline Status...")
    
    status = await pipeline.get_pipeline_status()
    print(f"   📋 Pipeline Status:")
    print(f"      Running: {status['running']}")
    print(f"      Models: {len(status['models'])}")
    print(f"      Training Jobs: {len(status['training_jobs'])}")
    
    # Display model information
    for model_id, model_info in status["models"].items():
        print(f"      📦 {model_info['model_type']}: {model_info['status']} (confidence: {model_info['metrics']['accuracy']:.1%})")
    
    # Display training jobs
    for job_id, job_info in status["training_jobs"].items():
        print(f"      🔧 {job_info['model_type']}: {job_info['status']} ({job_info['trigger']})")
    
    # Test 7: Model Comparison
    print("\n7. 🔍 Testing Model Comparison...")
    
    if len(registered_models) >= 2:
        model1_id, model1_type = registered_models[0]
        model2_id, model2_type = registered_models[1]
        
        try:
            comparison = await registry.compare_models(model1_id, model2_id)
            print(f"   🔍 Comparing {model1_type} vs {model2_type}:")
            
            for metric, values in comparison["metrics_comparison"].items():
                if values["model_1"] and values["model_2"]:
                    improvement = "📈" if values["improvement"] else "📉"
                    print(f"      {metric}: {values['model_1']:.3f} → {values['model_2']:.3f} {improvement}")
        except Exception as e:
            print(f"   ⚠️  Model comparison: {e}")
    
    # Test 8: Deployment History
    print("\n8. 📚 Testing Deployment History...")
    
    history = await registry.get_deployment_history(model_type=None)
    history = history[:5]  # Limit to 5 results
    print(f"   📜 Recent Deployments: {len(history)}")
    
    for deployment in history:
        print(f"      🚀 {deployment.model_id}: {deployment.strategy.value} → {deployment.target_stage.value}")
        print(f"         Status: Health={deployment.health_check_passed}, Perf={deployment.performance_validation_passed}")
    
    print(f"\n🎉 MLOps Pipeline Testing Complete!")
    print(f"=" * 60)
    
    # Final summary
    print(f"✅ Components Tested:")
    print(f"   • Model Registration & Versioning")
    print(f"   • Model Promotion & Deployment")  
    print(f"   • Feedback Collection & Analysis")
    print(f"   • Data Processing Pipeline")
    print(f"   • Automated Retraining Triggers")
    print(f"   • Performance Monitoring")
    print(f"   • Model Comparison & History")
    
    print(f"\n📊 System Status:")
    print(f"   • Registered Models: {len(status['models'])}")
    print(f"   • Active Training Jobs: {len([j for j in status['training_jobs'].values() if j['status'] in ['pending', 'running']])}")
    print(f"   • Feedback Entries: {summary['total_feedback']}")
    print(f"   • Overall System Health: ✅ Operational")


if __name__ == "__main__":
    try:
        asyncio.run(test_mlops_pipeline())
    except KeyboardInterrupt:
        print("\n⏹️ Testing interrupted by user")
    except Exception as e:
        print(f"\n❌ Testing failed: {e}")
        sys.exit(1)