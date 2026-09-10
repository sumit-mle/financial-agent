"""
Tests for MLOps Pipeline.
"""
import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from app.mlops.pipeline import (
    MLOpsPipeline, RetrainingTrigger, ModelStatus, ModelMetrics, RetrainingJob
)


@pytest.mark.models
@pytest.mark.unit
class TestMLOpsPipeline:
    """Test suite for MLOps pipeline."""
    
    @pytest.fixture
    def pipeline(self):
        """Create MLOps pipeline instance."""
        return MLOpsPipeline()
    
    @pytest.fixture
    def sample_metrics(self):
        """Create sample model metrics."""
        return ModelMetrics(
            accuracy=0.85,
            precision=0.83,
            recall=0.87,
            f1_score=0.85,
            confidence_avg=0.78,
            response_time_avg=1.2,
            user_satisfaction=0.82,
            escalation_rate=0.15,
            safety_violations=3,
            sample_count=450
        )
    
    @pytest.mark.asyncio
    async def test_pipeline_startup(self, pipeline):
        """Test pipeline startup and monitoring."""
        assert not pipeline._running
        
        # Start monitoring
        await pipeline.start_monitoring()
        assert pipeline._running
        
        # Stop monitoring
        await pipeline.stop_monitoring()
        assert not pipeline._running
    
    @pytest.mark.asyncio
    async def test_model_registration(self, pipeline, sample_metrics):
        """Test model registration."""
        model_type = "sentiment_classifier"
        model_path = "/models/sentiment_v1.pkl"
        
        await pipeline.register_model(
            model_type=model_type,
            model_path=model_path,
            metrics=sample_metrics
        )
        
        # Check model was registered
        assert len(pipeline.models) == 1
        model = list(pipeline.models.values())[0]
        assert model.model_type == model_type
        assert model.model_path == model_path
        assert model.status == ModelStatus.ACTIVE
        
        # Check baseline metrics were set
        assert model_type in pipeline.performance_history
        assert len(pipeline.performance_history[model_type]) == 1
    
    @pytest.mark.asyncio
    async def test_performance_degradation_trigger(self, pipeline, sample_metrics):
        """Test retraining trigger on performance degradation."""
        model_type = "sentiment_classifier"
        
        # Register model with good baseline metrics
        await pipeline.register_model(model_type, "/model.pkl", sample_metrics)
        
        # Mock current metrics with degraded accuracy
        degraded_metrics = ModelMetrics(
            accuracy=0.75,  # 10% drop from 0.85
            precision=0.73,
            recall=0.77,
            f1_score=0.75,
            confidence_avg=0.68,
            response_time_avg=1.5,
            user_satisfaction=0.72,  # 10% drop from 0.82
            escalation_rate=0.25,    # 10% increase from 0.15
            safety_violations=5,
            sample_count=200
        )
        
        with patch.object(pipeline, '_get_current_metrics', return_value=degraded_metrics):
            with patch.object(pipeline, '_trigger_retraining') as mock_trigger:
                await pipeline._check_retraining_triggers(model_type)
                
                # Should trigger retraining for multiple reasons
                assert mock_trigger.call_count >= 1
                
                # Check trigger reasons
                call_args_list = mock_trigger.call_args_list
                trigger_types = [call[0][1] for call in call_args_list]
                assert RetrainingTrigger.PERFORMANCE_DEGRADATION in trigger_types
    
    @pytest.mark.asyncio
    async def test_safety_violation_trigger(self, pipeline, sample_metrics):
        """Test retraining trigger on safety violations."""
        model_type = "safety_classifier"
        
        await pipeline.register_model(model_type, "/model.pkl", sample_metrics)
        
        # Mock metrics with high safety violations
        unsafe_metrics = ModelMetrics(
            accuracy=0.85,
            precision=0.83,
            recall=0.87,
            f1_score=0.85,
            confidence_avg=0.78,
            response_time_avg=1.2,
            user_satisfaction=0.82,
            escalation_rate=0.15,
            safety_violations=15,  # Above threshold of 10
            sample_count=200
        )
        
        with patch.object(pipeline, '_get_current_metrics', return_value=unsafe_metrics):
            with patch.object(pipeline, '_trigger_retraining') as mock_trigger:
                await pipeline._check_retraining_triggers(model_type)
                
                mock_trigger.assert_called()
                call_args = mock_trigger.call_args[0]
                assert call_args[1] == RetrainingTrigger.SAFETY_VIOLATIONS
    
    @pytest.mark.asyncio
    async def test_insufficient_samples_no_trigger(self, pipeline, sample_metrics):
        """Test that retraining doesn't trigger with insufficient samples."""
        model_type = "test_classifier"
        
        await pipeline.register_model(model_type, "/model.pkl", sample_metrics)
        
        # Mock metrics with poor performance but insufficient samples
        poor_metrics = ModelMetrics(
            accuracy=0.70,  # Poor accuracy
            precision=0.68,
            recall=0.72,
            f1_score=0.70,
            confidence_avg=0.65,
            response_time_avg=1.8,
            user_satisfaction=0.65,
            escalation_rate=0.35,
            safety_violations=8,
            sample_count=50  # Below threshold of 100
        )
        
        with patch.object(pipeline, '_get_current_metrics', return_value=poor_metrics):
            with patch.object(pipeline, '_trigger_retraining') as mock_trigger:
                await pipeline._check_retraining_triggers(model_type)
                
                # Should not trigger due to insufficient samples
                mock_trigger.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_training_job_creation(self, pipeline):
        """Test training job creation and processing."""
        model_type = "test_model"
        trigger = RetrainingTrigger.MANUAL
        trigger_data = {"reason": "Testing"}
        
        with patch.object(pipeline, '_prepare_training_data', return_value="/data/train.jsonl"):
            with patch.object(pipeline, '_get_hyperparameters', return_value={"lr": 0.001}):
                
                await pipeline._trigger_retraining(model_type, trigger, trigger_data)
                
                # Check job was created
                assert len(pipeline.training_jobs) == 1
                job = list(pipeline.training_jobs.values())[0]
                assert job.model_type == model_type
                assert job.trigger == trigger
                assert job.status == "pending"
    
    @pytest.mark.asyncio
    async def test_training_job_execution(self, pipeline):
        """Test training job execution."""
        # Create a training job
        job = RetrainingJob(
            job_id="test_job",
            model_type="test_model",
            trigger=RetrainingTrigger.MANUAL,
            trigger_data={"reason": "Test"},
            training_data_path="/data/train.jsonl"
        )
        
        with patch.object(pipeline, '_save_trained_model', return_value="/models/new_model.pkl"):
            with patch.object(pipeline, '_validate_model') as mock_validate:
                with patch.object(pipeline, '_should_deploy_model', return_value=True):
                    with patch.object(pipeline, '_deploy_model'):
                        
                        # Mock validation metrics
                        validation_metrics = ModelMetrics(
                            accuracy=0.88,
                            precision=0.86,
                            recall=0.89,
                            f1_score=0.87,
                            confidence_avg=0.82,
                            response_time_avg=1.1,
                            user_satisfaction=0.86,
                            escalation_rate=0.12,
                            safety_violations=1,
                            sample_count=200
                        )
                        mock_validate.return_value = validation_metrics
                        
                        await pipeline._execute_training_job(job)
                        
                        # Check job completed successfully
                        assert job.status == "completed"
                        
                        # Check model was registered
                        assert len(pipeline.models) == 1
    
    @pytest.mark.asyncio
    async def test_manual_retraining_trigger(self, pipeline):
        """Test manual retraining trigger."""
        model_type = "manual_test"
        reason = "Manual testing trigger"
        
        with patch.object(pipeline, '_trigger_retraining') as mock_trigger:
            await pipeline.trigger_manual_retraining(model_type, reason)
            
            mock_trigger.assert_called_once_with(
                model_type, RetrainingTrigger.MANUAL, {"reason": reason, "manual": True}
            )
    
    @pytest.mark.asyncio
    async def test_pipeline_status(self, pipeline, sample_metrics):
        """Test getting pipeline status."""
        # Register a model
        await pipeline.register_model("test_model", "/model.pkl", sample_metrics)
        
        status = await pipeline.get_pipeline_status()
        
        assert "running" in status
        assert "models" in status
        assert "training_jobs" in status
        assert "thresholds" in status
        
        # Check model information
        assert len(status["models"]) == 1
        model_info = list(status["models"].values())[0]
        assert model_info["model_type"] == "test_model"
        assert model_info["status"] == "active"
    
    @pytest.mark.asyncio
    async def test_hyperparameter_adjustment(self, pipeline):
        """Test hyperparameter adjustment based on trigger type."""
        # Test accuracy degradation adjustments
        accuracy_trigger_data = {"metric": "accuracy", "drop": 0.1}
        accuracy_params = await pipeline._get_hyperparameters("test_model", accuracy_trigger_data)
        
        assert accuracy_params["learning_rate"] == 0.0005  # Lower learning rate
        assert accuracy_params["epochs"] == 15  # More epochs
        assert "dropout" in accuracy_params
        
        # Test user satisfaction adjustments
        satisfaction_trigger_data = {"metric": "user_satisfaction", "drop": 0.15}
        satisfaction_params = await pipeline._get_hyperparameters("test_model", satisfaction_trigger_data)
        
        assert satisfaction_params["learning_rate"] == 0.002  # Higher learning rate
        assert "temperature" in satisfaction_params
    
    def test_retraining_thresholds_configuration(self, pipeline):
        """Test retraining threshold configuration."""
        thresholds = pipeline.retraining_thresholds
        
        # Check all required thresholds are present
        required_keys = [
            "accuracy_drop", "user_satisfaction_drop", 
            "escalation_rate_increase", "safety_violations_threshold", "min_samples"
        ]
        
        for key in required_keys:
            assert key in thresholds
            assert isinstance(thresholds[key], (int, float))
            assert thresholds[key] > 0
    
    @pytest.mark.asyncio
    async def test_no_retraining_during_active_job(self, pipeline, sample_metrics):
        """Test that retraining doesn't trigger when job is already active."""
        model_type = "test_model"
        
        # Register model
        await pipeline.register_model(model_type, "/model.pkl", sample_metrics)
        
        # Create active training job
        pipeline.training_jobs["active_job"] = RetrainingJob(
            job_id="active_job",
            model_type=model_type,
            trigger=RetrainingTrigger.MANUAL,
            trigger_data={},
            training_data_path="/data/train.jsonl",
            status="running"
        )
        
        # Mock degraded performance
        degraded_metrics = ModelMetrics(
            accuracy=0.70,  # Poor performance
            precision=0.68,
            recall=0.72,
            f1_score=0.70,
            confidence_avg=0.65,
            response_time_avg=1.8,
            user_satisfaction=0.65,
            escalation_rate=0.35,
            safety_violations=8,
            sample_count=200
        )
        
        with patch.object(pipeline, '_get_current_metrics', return_value=degraded_metrics):
            with patch.object(pipeline, '_trigger_retraining') as mock_trigger:
                await pipeline._check_retraining_triggers(model_type)
                
                # Should not trigger new job
                mock_trigger.assert_not_called()


@pytest.mark.models
@pytest.mark.integration
class TestMLOpsPipelineIntegration:
    """Integration tests for MLOps pipeline."""
    
    @pytest.mark.asyncio
    async def test_end_to_end_retraining_flow(self):
        """Test complete retraining flow from trigger to deployment."""
        pipeline = MLOpsPipeline()
        
        # Initial model registration
        initial_metrics = ModelMetrics(
            accuracy=0.85, precision=0.83, recall=0.87, f1_score=0.85,
            confidence_avg=0.78, response_time_avg=1.2, user_satisfaction=0.82,
            escalation_rate=0.15, safety_violations=3, sample_count=450
        )
        
        await pipeline.register_model("e2e_test", "/model.pkl", initial_metrics)
        
        # Simulate performance degradation and retraining
        with patch.object(pipeline, '_get_current_metrics') as mock_current:
            with patch.object(pipeline, '_prepare_training_data', return_value="/data/train.jsonl"):
                with patch.object(pipeline, '_save_trained_model', return_value="/models/new.pkl"):
                    with patch.object(pipeline, '_validate_model') as mock_validate:
                        with patch.object(pipeline, '_should_deploy_model', return_value=True):
                            with patch.object(pipeline, '_deploy_model'):
                                
                                # Mock degraded performance
                                degraded_metrics = ModelMetrics(
                                    accuracy=0.75, precision=0.73, recall=0.77, f1_score=0.75,
                                    confidence_avg=0.68, response_time_avg=1.5, user_satisfaction=0.70,
                                    escalation_rate=0.25, safety_violations=5, sample_count=200
                                )
                                mock_current.return_value = degraded_metrics
                                
                                # Mock improved validation metrics
                                improved_metrics = ModelMetrics(
                                    accuracy=0.88, precision=0.86, recall=0.89, f1_score=0.87,
                                    confidence_avg=0.82, response_time_avg=1.1, user_satisfaction=0.86,
                                    escalation_rate=0.12, safety_violations=1, sample_count=200
                                )
                                mock_validate.return_value = improved_metrics
                                
                                # Check retraining triggers
                                await pipeline._check_retraining_triggers("e2e_test")
                                
                                # Process training jobs
                                await pipeline._process_training_jobs()
                                
                                # Verify completion
                                assert len(pipeline.training_jobs) == 1
                                job = list(pipeline.training_jobs.values())[0]
                                assert job.status == "completed"
                                
                                # Verify new model was registered
                                assert len(pipeline.models) == 2  # Original + new model