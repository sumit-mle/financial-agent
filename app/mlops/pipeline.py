"""
MLOps Pipeline Manager.

Orchestrates automated model retraining based on performance feedback,
quality metrics, and continuous monitoring data.
"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum
import json
import pickle
from pathlib import Path

from app.core.logging import get_logger
from app.observability.metrics import Counter, Histogram
from app.core.config import settings

logger = get_logger(__name__)

# Metrics for MLOps pipeline
pipeline_executions = Counter(
    "mlops_pipeline_executions_total",
    "Total MLOps pipeline executions",
    ["pipeline_type", "status"]
)

model_training_duration = Histogram(
    "mlops_model_training_seconds",
    "Time spent training models",
    ["model_type"]
)

retraining_triggers = Counter(
    "mlops_retraining_triggers_total", 
    "Number of retraining triggers",
    ["trigger_type", "model_type"]
)


class RetrainingTrigger(Enum):
    """Types of triggers that can initiate model retraining."""
    PERFORMANCE_DEGRADATION = "performance_degradation"
    FEEDBACK_THRESHOLD = "feedback_threshold"
    SAFETY_VIOLATIONS = "safety_violations"
    SCHEDULED = "scheduled"
    MANUAL = "manual"
    A_B_TEST_WINNER = "ab_test_winner"


class ModelStatus(Enum):
    """Model lifecycle status."""
    ACTIVE = "active"
    TRAINING = "training"
    VALIDATING = "validating"
    DEPLOYING = "deploying"
    DEPRECATED = "deprecated"
    FAILED = "failed"


@dataclass
class ModelMetrics:
    """Performance metrics for a model."""
    accuracy: float
    precision: float
    recall: float
    f1_score: float
    confidence_avg: float
    response_time_avg: float
    user_satisfaction: float
    escalation_rate: float
    safety_violations: int
    sample_count: int
    last_updated: datetime = field(default_factory=datetime.utcnow)


@dataclass
class RetrainingJob:
    """Configuration for a model retraining job."""
    job_id: str
    model_type: str
    trigger: RetrainingTrigger
    trigger_data: Dict[str, Any]
    training_data_path: str
    validation_data_path: Optional[str] = None
    hyperparameters: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    status: str = "pending"
    error_message: Optional[str] = None


@dataclass
class ModelVersion:
    """Model version information."""
    version_id: str
    model_type: str
    model_path: str
    metrics: ModelMetrics
    status: ModelStatus
    created_at: datetime
    deployed_at: Optional[datetime] = None
    deprecated_at: Optional[datetime] = None


class MLOpsPipeline:
    """
    Main MLOps pipeline orchestrator.
    
    Handles:
    - Performance monitoring and degradation detection
    - Automated retraining triggers
    - Model version management
    - A/B testing integration
    - Rollback capabilities
    """
    
    def __init__(self):
        self.models: Dict[str, ModelVersion] = {}
        self.training_jobs: Dict[str, RetrainingJob] = {}
        self.performance_history: Dict[str, List[ModelMetrics]] = {}
        self.retraining_thresholds = {
            "accuracy_drop": 0.05,  # 5% accuracy drop triggers retraining
            "user_satisfaction_drop": 0.1,  # 10% satisfaction drop
            "escalation_rate_increase": 0.15,  # 15% escalation rate increase
            "safety_violations_threshold": 10,  # 10 safety violations in window
            "min_samples": 100  # Minimum samples before triggering
        }
        self._running = False
        
    async def start_monitoring(self):
        """Start continuous performance monitoring."""
        self._running = True
        logger.info("Starting MLOps pipeline monitoring")
        
        # Start background monitoring task
        asyncio.create_task(self._monitoring_loop())
        
    async def stop_monitoring(self):
        """Stop performance monitoring."""
        self._running = False
        logger.info("Stopping MLOps pipeline monitoring")
        
    async def _monitoring_loop(self):
        """Main monitoring loop that checks for retraining triggers."""
        while self._running:
            try:
                # Check each model for retraining triggers
                for model_type in self.models:
                    await self._check_retraining_triggers(model_type)
                
                # Process pending training jobs
                await self._process_training_jobs()
                
                # Sleep before next check
                await asyncio.sleep(settings.mlops_monitoring_interval_seconds)
                
            except Exception as e:
                logger.error(f"Error in MLOps monitoring loop: {e}")
                await asyncio.sleep(60)  # Wait before retrying
    
    async def _check_retraining_triggers(self, model_type: str):
        """Check if a model needs retraining based on performance metrics."""
        # Bail out before doing any work if this model is already retraining.
        # The same guard exists in `_trigger_retraining` for direct callers, but
        # checking here also stops a degraded model from re-scanning and
        # re-logging once per matched trigger on every monitoring cycle.
        if self._has_active_job(model_type):
            logger.debug(f"Retraining already in progress for {model_type}, skipping checks")
            return

        current_metrics = await self._get_current_metrics(model_type)
        if not current_metrics:
            return
            
        baseline_metrics = await self._get_baseline_metrics(model_type)
        if not baseline_metrics:
            logger.info(f"No baseline metrics for {model_type}, establishing baseline")
            await self._set_baseline_metrics(model_type, current_metrics)
            return
        
        # Check for performance degradation
        triggers = []
        
        # Accuracy degradation
        if (baseline_metrics.accuracy - current_metrics.accuracy) > self.retraining_thresholds["accuracy_drop"]:
            triggers.append((RetrainingTrigger.PERFORMANCE_DEGRADATION, {
                "metric": "accuracy",
                "baseline": baseline_metrics.accuracy,
                "current": current_metrics.accuracy,
                "drop": baseline_metrics.accuracy - current_metrics.accuracy
            }))
        
        # User satisfaction drop
        if (baseline_metrics.user_satisfaction - current_metrics.user_satisfaction) > self.retraining_thresholds["user_satisfaction_drop"]:
            triggers.append((RetrainingTrigger.FEEDBACK_THRESHOLD, {
                "metric": "user_satisfaction", 
                "baseline": baseline_metrics.user_satisfaction,
                "current": current_metrics.user_satisfaction,
                "drop": baseline_metrics.user_satisfaction - current_metrics.user_satisfaction
            }))
        
        # Escalation rate increase
        if (current_metrics.escalation_rate - baseline_metrics.escalation_rate) > self.retraining_thresholds["escalation_rate_increase"]:
            triggers.append((RetrainingTrigger.PERFORMANCE_DEGRADATION, {
                "metric": "escalation_rate",
                "baseline": baseline_metrics.escalation_rate,
                "current": current_metrics.escalation_rate,
                "increase": current_metrics.escalation_rate - baseline_metrics.escalation_rate
            }))
        
        # Safety violations threshold
        if current_metrics.safety_violations > self.retraining_thresholds["safety_violations_threshold"]:
            triggers.append((RetrainingTrigger.SAFETY_VIOLATIONS, {
                "violations": current_metrics.safety_violations,
                "threshold": self.retraining_thresholds["safety_violations_threshold"]
            }))
        
        # Trigger retraining if any conditions met and enough samples
        if triggers and current_metrics.sample_count >= self.retraining_thresholds["min_samples"]:
            for trigger_type, trigger_data in triggers:
                # Only count a trigger that actually created a job — otherwise
                # the counter climbs on every skipped cycle and overstates how
                # often retraining really fires.
                if await self._trigger_retraining(model_type, trigger_type, trigger_data):
                    retraining_triggers.labels(
                        trigger_type=trigger_type.value,
                        model_type=model_type
                    ).inc()
    
    async def _get_current_metrics(self, model_type: str) -> Optional[ModelMetrics]:
        """Get current performance metrics for a model."""
        try:
            # This would integrate with your metrics collection system
            # For now, simulate with some realistic metrics
            
            # In production, this would query your metrics database
            # Example: SELECT accuracy, precision, recall FROM model_metrics 
            #          WHERE model_type = ? AND timestamp > ?
            
            return ModelMetrics(
                accuracy=0.85,  # Would come from actual metrics
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
            
        except Exception as e:
            logger.error(f"Error getting current metrics for {model_type}: {e}")
            return None
    
    async def _get_baseline_metrics(self, model_type: str) -> Optional[ModelMetrics]:
        """Get baseline metrics for comparison."""
        history = self.performance_history.get(model_type, [])
        if not history:
            return None
        
        # Use metrics from when model was last deployed as baseline
        return history[-1] if history else None
    
    async def _set_baseline_metrics(self, model_type: str, metrics: ModelMetrics):
        """Set baseline metrics for a model."""
        if model_type not in self.performance_history:
            self.performance_history[model_type] = []
        
        self.performance_history[model_type].append(metrics)
        logger.info(f"Set baseline metrics for {model_type}: accuracy={metrics.accuracy:.3f}")
    
    def _has_active_job(self, model_type: str) -> bool:
        """True when a pending or running retraining job exists for the model."""
        return any(
            job.model_type == model_type and job.status in ("pending", "running")
            for job in self.training_jobs.values()
        )

    async def _trigger_retraining(self, model_type: str, trigger: RetrainingTrigger, trigger_data: Dict[str, Any]) -> bool:
        """
        Trigger retraining for a model.

        Returns True when a new job was created, False when one was already in
        flight, so callers can avoid counting a skipped trigger.
        """
        # Check if retraining already in progress
        if self._has_active_job(model_type):
            logger.info(f"Retraining already in progress for {model_type}, skipping trigger")
            return False
        
        # Create retraining job
        job_id = f"{model_type}_retrain_{int(datetime.utcnow().timestamp())}"
        training_data_path = await self._prepare_training_data(model_type, trigger_data)
        
        job = RetrainingJob(
            job_id=job_id,
            model_type=model_type,
            trigger=trigger,
            trigger_data=trigger_data,
            training_data_path=training_data_path,
            hyperparameters=await self._get_hyperparameters(model_type, trigger_data)
        )
        
        self.training_jobs[job_id] = job
        
        logger.info(f"Triggered retraining for {model_type}: {trigger.value} - Job ID: {job_id}")
        
        # Log metrics
        pipeline_executions.labels(
            pipeline_type="retraining",
            status="triggered"
        ).inc()
        return True
    
    async def _prepare_training_data(self, model_type: str, trigger_data: Dict[str, Any]) -> str:
        """Prepare training data for retraining."""
        # In production, this would:
        # 1. Query recent interaction data 
        # 2. Apply data quality filters
        # 3. Balance datasets
        # 4. Apply privacy/anonymization
        # 5. Save to training data path
        
        data_dir = Path(settings.mlops_data_dir) / "training" / model_type
        data_dir.mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        training_file = data_dir / f"training_data_{timestamp}.jsonl"
        
        # Simulate data preparation
        logger.info(f"Preparing training data for {model_type} at {training_file}")
        
        # In real implementation, fetch and process actual data
        # For demo, create placeholder file
        with open(training_file, 'w') as f:
            f.write('{"example": "training data would be here"}\n')
        
        return str(training_file)
    
    async def _get_hyperparameters(self, model_type: str, trigger_data: Dict[str, Any]) -> Dict[str, Any]:
        """Get hyperparameters for retraining based on trigger data."""
        # Base hyperparameters
        base_params = {
            "learning_rate": 0.001,
            "batch_size": 32,
            "epochs": 10,
            "early_stopping_patience": 3
        }
        
        # Adjust based on trigger type
        if trigger_data.get("metric") == "accuracy":
            # More aggressive training for accuracy issues
            base_params.update({
                "learning_rate": 0.0005,  # Lower learning rate
                "epochs": 15,  # More epochs
                "dropout": 0.3  # More regularization
            })
        elif trigger_data.get("metric") == "user_satisfaction":
            # Focus on response quality
            base_params.update({
                "learning_rate": 0.002,  # Slightly higher learning rate
                "temperature": 0.8,  # More creative responses
                "max_length": 512  # Longer responses allowed
            })
        
        return base_params
    
    async def _process_training_jobs(self):
        """Process pending training jobs."""
        pending_jobs = [job for job in self.training_jobs.values() if job.status == "pending"]
        
        for job in pending_jobs:
            try:
                await self._execute_training_job(job)
            except Exception as e:
                logger.error(f"Error processing training job {job.job_id}: {e}")
                job.status = "failed"
                job.error_message = str(e)
    
    async def _execute_training_job(self, job: RetrainingJob):
        """Execute a training job."""
        logger.info(f"Starting training job {job.job_id} for {job.model_type}")
        job.status = "running"
        
        start_time = datetime.utcnow()
        
        try:
            # Simulate training process
            with model_training_duration.labels(model_type=job.model_type).time():
                # In production, this would:
                # 1. Load training data
                # 2. Initialize model architecture
                # 3. Train with hyperparameters
                # 4. Validate on held-out data
                # 5. Save trained model
                
                # Simulate training time
                await asyncio.sleep(5)  # Represents training time
                
                # Create new model version
                version_id = f"{job.model_type}_v{int(datetime.utcnow().timestamp())}"
                model_path = await self._save_trained_model(job, version_id)
                
                # Validate model
                validation_metrics = await self._validate_model(job, model_path)
                
                # Create model version entry
                model_version = ModelVersion(
                    version_id=version_id,
                    model_type=job.model_type,
                    model_path=model_path,
                    metrics=validation_metrics,
                    status=ModelStatus.VALIDATING,
                    created_at=datetime.utcnow()
                )
                
                # Check if model should be deployed
                if await self._should_deploy_model(model_version):
                    await self._deploy_model(model_version)
                    job.status = "completed"
                    logger.info(f"Training job {job.job_id} completed and deployed successfully")
                else:
                    model_version.status = ModelStatus.DEPRECATED
                    job.status = "completed_not_deployed"
                    logger.info(f"Training job {job.job_id} completed but not deployed (quality check failed)")
                
                self.models[model_version.version_id] = model_version
                
        except Exception as e:
            job.status = "failed"
            job.error_message = str(e)
            logger.error(f"Training job {job.job_id} failed: {e}")
            raise
        
        finally:
            duration = (datetime.utcnow() - start_time).total_seconds()
            logger.info(f"Training job {job.job_id} finished in {duration:.1f}s with status: {job.status}")
            
            # Log metrics
            pipeline_executions.labels(
                pipeline_type="training",
                status=job.status
            ).inc()
    
    async def _save_trained_model(self, job: RetrainingJob, version_id: str) -> str:
        """Save trained model to disk."""
        model_dir = Path(settings.mlops_model_dir) / job.model_type
        model_dir.mkdir(parents=True, exist_ok=True)
        
        model_path = model_dir / f"{version_id}.pkl"
        
        # Simulate saving model
        # In production: torch.save(model.state_dict(), model_path)
        with open(model_path, 'wb') as f:
            pickle.dump({"model": "placeholder", "version": version_id}, f)
        
        logger.info(f"Saved model {version_id} to {model_path}")
        return str(model_path)
    
    async def _validate_model(self, job: RetrainingJob, model_path: str) -> ModelMetrics:
        """Validate trained model performance."""
        logger.info(f"Validating model for job {job.job_id}")
        
        # In production, this would:
        # 1. Load validation dataset
        # 2. Run model inference
        # 3. Calculate metrics
        # 4. Compare against baseline
        
        # Simulate validation metrics (slightly better than current)
        return ModelMetrics(
            accuracy=0.88,  # Improved from trigger condition
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
    
    async def _should_deploy_model(self, model_version: ModelVersion) -> bool:
        """Determine if model should be deployed based on validation metrics."""
        # Get current model metrics for comparison
        current_model = self._get_current_model(model_version.model_type)
        if not current_model:
            return True  # Deploy if no current model
        
        new_metrics = model_version.metrics
        current_metrics = current_model.metrics
        
        # Deployment criteria
        criteria = {
            "accuracy_improvement": new_metrics.accuracy > current_metrics.accuracy,
            "user_satisfaction_improvement": new_metrics.user_satisfaction > current_metrics.user_satisfaction,
            "escalation_reduction": new_metrics.escalation_rate < current_metrics.escalation_rate,
            "safety_improvement": new_metrics.safety_violations <= current_metrics.safety_violations,
            "min_accuracy": new_metrics.accuracy >= 0.80,  # Minimum quality threshold
            "min_user_satisfaction": new_metrics.user_satisfaction >= 0.75
        }
        
        # Must meet minimum thresholds and show improvement
        required_criteria = ["min_accuracy", "min_user_satisfaction"]
        improvement_criteria = ["accuracy_improvement", "user_satisfaction_improvement", "escalation_reduction"]
        
        meets_requirements = all(criteria[c] for c in required_criteria)
        shows_improvement = any(criteria[c] for c in improvement_criteria)
        
        should_deploy = meets_requirements and shows_improvement
        
        logger.info(f"Deployment decision for {model_version.version_id}: {should_deploy}")
        logger.info(f"  Criteria: {criteria}")
        
        return should_deploy
    
    def _get_current_model(self, model_type: str) -> Optional[ModelVersion]:
        """Get currently deployed model of given type."""
        active_models = [m for m in self.models.values() 
                        if m.model_type == model_type and m.status == ModelStatus.ACTIVE]
        return active_models[0] if active_models else None
    
    async def _deploy_model(self, model_version: ModelVersion):
        """Deploy model to production."""
        logger.info(f"Deploying model {model_version.version_id}")
        
        # Deprecate current model
        current_model = self._get_current_model(model_version.model_type)
        if current_model:
            current_model.status = ModelStatus.DEPRECATED
            current_model.deprecated_at = datetime.utcnow()
            logger.info(f"Deprecated previous model {current_model.version_id}")
        
        # Activate new model
        model_version.status = ModelStatus.ACTIVE
        model_version.deployed_at = datetime.utcnow()
        
        # Update baseline metrics
        await self._set_baseline_metrics(model_version.model_type, model_version.metrics)
        
        # In production, this would:
        # 1. Update model registry
        # 2. Update serving infrastructure 
        # 3. Run smoke tests
        # 4. Gradually ramp up traffic
        
        logger.info(f"Successfully deployed model {model_version.version_id}")
    
    async def register_model(self, model_type: str, model_path: str, metrics: ModelMetrics):
        """Register a new model version."""
        version_id = f"{model_type}_initial_v{int(datetime.utcnow().timestamp())}"
        
        model_version = ModelVersion(
            version_id=version_id,
            model_type=model_type,
            model_path=model_path,
            metrics=metrics,
            status=ModelStatus.ACTIVE,
            created_at=datetime.utcnow(),
            deployed_at=datetime.utcnow()
        )
        
        self.models[version_id] = model_version
        await self._set_baseline_metrics(model_type, metrics)
        
        logger.info(f"Registered initial model {version_id}")
    
    async def trigger_manual_retraining(self, model_type: str, reason: str = "Manual trigger"):
        """Manually trigger retraining for a model."""
        trigger_data = {"reason": reason, "manual": True}
        await self._trigger_retraining(model_type, RetrainingTrigger.MANUAL, trigger_data)
        
    async def get_pipeline_status(self) -> Dict[str, Any]:
        """Get current pipeline status and metrics."""
        return {
            "running": self._running,
            "models": {
                version_id: {
                    "model_type": model.model_type,
                    "status": model.status.value,
                    "created_at": model.created_at.isoformat(),
                    "deployed_at": model.deployed_at.isoformat() if model.deployed_at else None,
                    "metrics": {
                        "accuracy": model.metrics.accuracy,
                        "user_satisfaction": model.metrics.user_satisfaction,
                        "escalation_rate": model.metrics.escalation_rate
                    }
                }
                for version_id, model in self.models.items()
            },
            "training_jobs": {
                job_id: {
                    "model_type": job.model_type,
                    "status": job.status,
                    "trigger": job.trigger.value,
                    "created_at": job.created_at.isoformat(),
                    "error_message": job.error_message
                }
                for job_id, job in self.training_jobs.items()
            },
            "thresholds": self.retraining_thresholds
        }


# Global pipeline instance
_pipeline_instance = None

async def get_mlops_pipeline() -> MLOpsPipeline:
    """Get global MLOps pipeline instance."""
    global _pipeline_instance
    if _pipeline_instance is None:
        _pipeline_instance = MLOpsPipeline()
    return _pipeline_instance