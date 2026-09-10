"""
Model Registry for MLOps Pipeline.

Manages model versions, metadata, and deployment lifecycle.
Provides versioning, rollback capabilities, and model performance tracking.
"""
import asyncio
import json
import shutil
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Set
from dataclasses import dataclass, asdict
from pathlib import Path
from enum import Enum

from app.core.logging import get_logger
from app.core.config import settings
from app.observability.metrics import Counter, Histogram, Gauge

logger = get_logger(__name__)

# Registry metrics
model_deployments = Counter(
    "mlops_model_deployments_total",
    "Total model deployments",
    ["model_type", "deployment_type"]
)

model_rollbacks = Counter(
    "mlops_model_rollbacks_total", 
    "Total model rollbacks",
    ["model_type", "reason"]
)

active_model_versions = Gauge(
    "mlops_active_model_versions",
    "Number of active model versions",
    ["model_type"]
)


class DeploymentStrategy(Enum):
    """Model deployment strategies."""
    BLUE_GREEN = "blue_green"
    CANARY = "canary"
    ROLLING = "rolling"
    IMMEDIATE = "immediate"


class ModelStage(Enum):
    """Model lifecycle stages."""
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"
    ARCHIVED = "archived"


@dataclass
class ModelMetadata:
    """Comprehensive model metadata."""
    model_id: str
    model_type: str
    version: str
    stage: ModelStage
    created_by: str
    created_at: datetime
    
    # Model artifacts
    model_path: str
    config_path: Optional[str] = None
    requirements_path: Optional[str] = None
    
    # Performance metrics
    training_metrics: Dict[str, float] = None
    validation_metrics: Dict[str, float] = None
    production_metrics: Dict[str, float] = None
    
    # Deployment info
    deployment_strategy: Optional[DeploymentStrategy] = None
    deployment_config: Dict[str, Any] = None
    deployed_at: Optional[datetime] = None
    traffic_percentage: float = 0.0
    
    # Metadata
    description: str = ""
    tags: Set[str] = None
    hyperparameters: Dict[str, Any] = None
    training_dataset: Optional[str] = None
    validation_dataset: Optional[str] = None
    
    # Lineage
    parent_model_id: Optional[str] = None
    derived_models: List[str] = None
    
    def __post_init__(self):
        if self.tags is None:
            self.tags = set()
        if self.derived_models is None:
            self.derived_models = []
        if self.training_metrics is None:
            self.training_metrics = {}
        if self.validation_metrics is None:
            self.validation_metrics = {}
        if self.production_metrics is None:
            self.production_metrics = {}
        if self.deployment_config is None:
            self.deployment_config = {}
        if self.hyperparameters is None:
            self.hyperparameters = {}


@dataclass
class DeploymentRecord:
    """Record of a model deployment."""
    deployment_id: str
    model_id: str
    model_version: str
    strategy: DeploymentStrategy
    target_stage: ModelStage
    traffic_percentage: float
    deployed_at: datetime
    deployed_by: str
    rollback_model_id: Optional[str] = None
    deployment_notes: str = ""
    health_check_passed: bool = False
    performance_validation_passed: bool = False
    rolled_back_at: Optional[datetime] = None
    rollback_reason: Optional[str] = None


class ModelRegistry:
    """
    Central registry for managing model versions and deployments.
    
    Features:
    - Version management and lineage tracking
    - Multi-stage deployments (dev/staging/prod)
    - Blue-green and canary deployment strategies
    - Automated rollback on performance degradation
    - Model artifact management
    - Performance comparison across versions
    """
    
    def __init__(self):
        self.models: Dict[str, ModelMetadata] = {}
        self.deployments: Dict[str, DeploymentRecord] = {}
        self.registry_path = Path(settings.mlops_model_dir) / "registry"
        self.registry_path.mkdir(parents=True, exist_ok=True)
        self._initialize_registry()
    
    def _initialize_registry(self):
        """Initialize registry from persistent storage."""
        registry_file = self.registry_path / "models.json"
        
        if registry_file.exists():
            try:
                with open(registry_file, 'r') as f:
                    data = json.load(f)
                
                # Load models
                for model_data in data.get("models", []):
                    # Convert datetime strings back to datetime objects
                    model_data["created_at"] = datetime.fromisoformat(model_data["created_at"])
                    if model_data.get("deployed_at"):
                        model_data["deployed_at"] = datetime.fromisoformat(model_data["deployed_at"])
                    
                    # Convert enums
                    model_data["stage"] = ModelStage(model_data["stage"])
                    if model_data.get("deployment_strategy"):
                        model_data["deployment_strategy"] = DeploymentStrategy(model_data["deployment_strategy"])
                    
                    # Convert sets
                    model_data["tags"] = set(model_data.get("tags", []))
                    
                    model = ModelMetadata(**model_data)
                    self.models[model.model_id] = model
                
                # Load deployments
                for deployment_data in data.get("deployments", []):
                    deployment_data["deployed_at"] = datetime.fromisoformat(deployment_data["deployed_at"])
                    deployment_data["strategy"] = DeploymentStrategy(deployment_data["strategy"])
                    deployment_data["target_stage"] = ModelStage(deployment_data["target_stage"])
                    
                    if deployment_data.get("rolled_back_at"):
                        deployment_data["rolled_back_at"] = datetime.fromisoformat(deployment_data["rolled_back_at"])
                    
                    deployment = DeploymentRecord(**deployment_data)
                    self.deployments[deployment.deployment_id] = deployment
                    
                logger.info(f"Loaded {len(self.models)} models and {len(self.deployments)} deployments from registry")
                
            except Exception as e:
                logger.error(f"Error loading model registry: {e}")
    
    def _persist_registry(self):
        """Persist registry to storage."""
        registry_file = self.registry_path / "models.json"
        
        try:
            # Prepare data for serialization
            models_data = []
            for model in self.models.values():
                model_dict = asdict(model)
                model_dict["created_at"] = model.created_at.isoformat()
                if model.deployed_at:
                    model_dict["deployed_at"] = model.deployed_at.isoformat()
                model_dict["stage"] = model.stage.value
                if model.deployment_strategy:
                    model_dict["deployment_strategy"] = model.deployment_strategy.value
                model_dict["tags"] = list(model.tags)
                models_data.append(model_dict)
            
            deployments_data = []
            for deployment in self.deployments.values():
                deployment_dict = asdict(deployment)
                deployment_dict["deployed_at"] = deployment.deployed_at.isoformat()
                deployment_dict["strategy"] = deployment.strategy.value
                deployment_dict["target_stage"] = deployment.target_stage.value
                if deployment.rolled_back_at:
                    deployment_dict["rolled_back_at"] = deployment.rolled_back_at.isoformat()
                deployments_data.append(deployment_dict)
            
            registry_data = {
                "models": models_data,
                "deployments": deployments_data,
                "last_updated": datetime.utcnow().isoformat()
            }
            
            # Write to temporary file first, then rename (atomic operation)
            temp_file = registry_file.with_suffix('.tmp')
            with open(temp_file, 'w') as f:
                json.dump(registry_data, f, indent=2)
            
            # On Windows, need to remove target file before rename
            if registry_file.exists():
                registry_file.unlink()
            
            temp_file.rename(registry_file)
            
        except Exception as e:
            logger.error(f"Error persisting model registry: {e}")
    
    async def register_model(self,
                           model_type: str,
                           model_path: str,
                           version: str,
                           stage: ModelStage = ModelStage.DEVELOPMENT,
                           created_by: str = "mlops_pipeline",
                           description: str = "",
                           tags: Optional[Set[str]] = None,
                           hyperparameters: Optional[Dict[str, Any]] = None,
                           training_metrics: Optional[Dict[str, float]] = None,
                           validation_metrics: Optional[Dict[str, float]] = None,
                           training_dataset: Optional[str] = None,
                           parent_model_id: Optional[str] = None) -> str:
        """Register a new model version."""
        
        model_id = f"{model_type}_{version}_{int(datetime.utcnow().timestamp())}"
        
        model = ModelMetadata(
            model_id=model_id,
            model_type=model_type,
            version=version,
            stage=stage,
            created_by=created_by,
            created_at=datetime.utcnow(),
            model_path=model_path,
            description=description,
            tags=tags or set(),
            hyperparameters=hyperparameters,
            training_metrics=training_metrics,
            validation_metrics=validation_metrics,
            training_dataset=training_dataset,
            parent_model_id=parent_model_id
        )
        
        # Update parent model lineage
        if parent_model_id and parent_model_id in self.models:
            self.models[parent_model_id].derived_models.append(model_id)
        
        self.models[model_id] = model
        self._persist_registry()
        
        logger.info(f"Registered model {model_id} (type: {model_type}, version: {version}, stage: {stage.value})")
        
        return model_id
    
    async def promote_model(self,
                          model_id: str,
                          target_stage: ModelStage,
                          validation_metrics: Optional[Dict[str, float]] = None) -> bool:
        """Promote model to next stage."""
        
        if model_id not in self.models:
            raise ValueError(f"Model {model_id} not found")
        
        model = self.models[model_id]
        current_stage = model.stage
        
        # Validation rules for stage promotion
        if not await self._can_promote_to_stage(model, target_stage):
            return False
        
        # Update model stage
        model.stage = target_stage
        
        if validation_metrics:
            model.validation_metrics.update(validation_metrics)
        
        self._persist_registry()
        
        logger.info(f"Promoted model {model_id} from {current_stage.value} to {target_stage.value}")
        
        return True
    
    async def _can_promote_to_stage(self, model: ModelMetadata, target_stage: ModelStage) -> bool:
        """Check if model can be promoted to target stage."""
        
        # Stage promotion rules
        stage_order = [ModelStage.DEVELOPMENT, ModelStage.STAGING, ModelStage.PRODUCTION]
        current_index = stage_order.index(model.stage)
        target_index = stage_order.index(target_stage)
        
        # Can only promote to next stage or same stage
        if target_index > current_index + 1:
            logger.warning(f"Cannot skip stages: {model.stage.value} -> {target_stage.value}")
            return False
        
        # Validation requirements for each stage
        if target_stage == ModelStage.STAGING:
            # Require training metrics
            required_metrics = ["accuracy", "precision", "recall"]
            if not all(metric in model.training_metrics for metric in required_metrics):
                logger.warning(f"Missing required training metrics for staging: {required_metrics}")
                return False
        
        elif target_stage == ModelStage.PRODUCTION:
            # Require validation metrics and minimum thresholds
            required_metrics = ["accuracy", "user_satisfaction"]
            if not all(metric in model.validation_metrics for metric in required_metrics):
                logger.warning(f"Missing required validation metrics for production: {required_metrics}")
                return False
            
            # Minimum quality thresholds
            min_accuracy = 0.80
            min_satisfaction = 0.75
            
            if (model.validation_metrics.get("accuracy", 0) < min_accuracy or
                model.validation_metrics.get("user_satisfaction", 0) < min_satisfaction):
                logger.warning(f"Model quality below production thresholds")
                return False
        
        return True
    
    async def deploy_model(self,
                         model_id: str,
                         target_stage: ModelStage,
                         strategy: DeploymentStrategy = DeploymentStrategy.BLUE_GREEN,
                         traffic_percentage: float = 100.0,
                         deployed_by: str = "mlops_pipeline",
                         rollback_model_id: Optional[str] = None,
                         deployment_notes: str = "") -> str:
        """Deploy model to target stage."""
        
        if model_id not in self.models:
            raise ValueError(f"Model {model_id} not found")
        
        model = self.models[model_id]
        
        # Ensure model is promoted to target stage
        if model.stage != target_stage:
            promoted = await self.promote_model(model_id, target_stage)
            if not promoted:
                raise ValueError(f"Cannot promote model {model_id} to {target_stage.value}")
        
        # Create deployment record
        deployment_id = f"deploy_{model_id}_{int(datetime.utcnow().timestamp())}"
        
        deployment = DeploymentRecord(
            deployment_id=deployment_id,
            model_id=model_id,
            model_version=model.version,
            strategy=strategy,
            target_stage=target_stage,
            traffic_percentage=traffic_percentage,
            deployed_at=datetime.utcnow(),
            deployed_by=deployed_by,
            rollback_model_id=rollback_model_id,
            deployment_notes=deployment_notes
        )
        
        # Execute deployment strategy
        success = await self._execute_deployment(model, deployment)
        
        if success:
            # Update model deployment info
            model.deployed_at = datetime.utcnow()
            model.traffic_percentage = traffic_percentage
            model.deployment_strategy = strategy
            
            # Store deployment record
            self.deployments[deployment_id] = deployment
            self._persist_registry()
            
            # Update metrics
            model_deployments.labels(
                model_type=model.model_type,
                deployment_type=strategy.value
            ).inc()
            
            self._update_active_model_metrics()
            
            logger.info(f"Successfully deployed model {model_id} using {strategy.value} strategy")
            
        return deployment_id if success else None
    
    async def _execute_deployment(self, model: ModelMetadata, deployment: DeploymentRecord) -> bool:
        """Execute the actual deployment based on strategy."""
        
        try:
            if deployment.strategy == DeploymentStrategy.IMMEDIATE:
                # Immediate replacement
                await self._immediate_deployment(model, deployment)
                
            elif deployment.strategy == DeploymentStrategy.BLUE_GREEN:
                # Blue-green deployment
                await self._blue_green_deployment(model, deployment)
                
            elif deployment.strategy == DeploymentStrategy.CANARY:
                # Canary deployment
                await self._canary_deployment(model, deployment)
                
            elif deployment.strategy == DeploymentStrategy.ROLLING:
                # Rolling deployment
                await self._rolling_deployment(model, deployment)
            
            # Run health checks
            health_check_passed = await self._run_health_check(model)
            deployment.health_check_passed = health_check_passed
            
            # Run performance validation
            perf_validation_passed = await self._run_performance_validation(model)
            deployment.performance_validation_passed = perf_validation_passed
            
            return health_check_passed and perf_validation_passed
            
        except Exception as e:
            logger.error(f"Deployment failed for {model.model_id}: {e}")
            return False
    
    async def _immediate_deployment(self, model: ModelMetadata, deployment: DeploymentRecord):
        """Execute immediate deployment."""
        logger.info(f"Executing immediate deployment for {model.model_id}")
        
        # In production, this would:
        # 1. Stop current model instances
        # 2. Load new model
        # 3. Start serving new model
        # 4. Update load balancer configuration
        
        # Simulate deployment
        await asyncio.sleep(1)
    
    async def _blue_green_deployment(self, model: ModelMetadata, deployment: DeploymentRecord):
        """Execute blue-green deployment."""
        logger.info(f"Executing blue-green deployment for {model.model_id}")
        
        # In production, this would:
        # 1. Set up parallel "green" environment with new model
        # 2. Run smoke tests on green environment
        # 3. Switch traffic from blue to green
        # 4. Keep blue environment for quick rollback
        
        # Simulate deployment phases
        await asyncio.sleep(2)  # Environment setup
        await asyncio.sleep(1)  # Traffic switch
    
    async def _canary_deployment(self, model: ModelMetadata, deployment: DeploymentRecord):
        """Execute canary deployment."""
        logger.info(f"Executing canary deployment for {model.model_id} with {deployment.traffic_percentage}% traffic")
        
        # In production, this would:
        # 1. Deploy new model to small subset of instances
        # 2. Route percentage of traffic to new model
        # 3. Monitor performance metrics
        # 4. Gradually increase traffic if metrics are good
        # 5. Complete rollout or rollback based on results
        
        # Simulate gradual rollout
        await asyncio.sleep(3)
    
    async def _rolling_deployment(self, model: ModelMetadata, deployment: DeploymentRecord):
        """Execute rolling deployment."""
        logger.info(f"Executing rolling deployment for {model.model_id}")
        
        # In production, this would:
        # 1. Replace instances one by one
        # 2. Wait for health checks between replacements
        # 3. Continue until all instances updated
        
        # Simulate rolling update
        await asyncio.sleep(2)
    
    async def _run_health_check(self, model: ModelMetadata) -> bool:
        """Run health check on deployed model."""
        logger.info(f"Running health check for {model.model_id}")
        
        # In production, this would:
        # 1. Send test requests to model endpoints
        # 2. Verify response times are acceptable
        # 3. Check error rates
        # 4. Validate model is loading correctly
        
        # Simulate health check
        await asyncio.sleep(1)
        return True  # Assume health check passes
    
    async def _run_performance_validation(self, model: ModelMetadata) -> bool:
        """Run performance validation on deployed model."""
        logger.info(f"Running performance validation for {model.model_id}")
        
        # In production, this would:
        # 1. Run model on validation dataset
        # 2. Compare metrics against previous version
        # 3. Check for performance regression
        # 4. Validate latency requirements
        
        # Simulate performance validation
        await asyncio.sleep(2)
        
        # Check if metrics meet minimum thresholds
        min_accuracy = 0.75
        current_accuracy = model.validation_metrics.get("accuracy", 0.8)
        
        return current_accuracy >= min_accuracy
    
    async def rollback_deployment(self,
                                deployment_id: str,
                                reason: str = "Performance degradation",
                                rollback_to_model_id: Optional[str] = None) -> bool:
        """Rollback a deployment."""
        
        if deployment_id not in self.deployments:
            raise ValueError(f"Deployment {deployment_id} not found")
        
        deployment = self.deployments[deployment_id]
        
        # Determine rollback target
        target_model_id = rollback_to_model_id or deployment.rollback_model_id
        if not target_model_id:
            # Find previous production model
            target_model_id = await self._find_previous_production_model(deployment.model_id)
        
        if not target_model_id:
            logger.error(f"No rollback target found for deployment {deployment_id}")
            return False
        
        try:
            # Execute rollback
            success = await self._execute_rollback(deployment, target_model_id)
            
            if success:
                # Update deployment record
                deployment.rolled_back_at = datetime.utcnow()
                deployment.rollback_reason = reason
                
                # Update current model status
                current_model = self.models[deployment.model_id]
                current_model.traffic_percentage = 0.0
                
                # Update rollback target
                rollback_model = self.models[target_model_id]
                rollback_model.traffic_percentage = 100.0
                rollback_model.deployed_at = datetime.utcnow()
                
                self._persist_registry()
                
                # Update metrics
                model_rollbacks.labels(
                    model_type=current_model.model_type,
                    reason=reason
                ).inc()
                
                logger.info(f"Successfully rolled back deployment {deployment_id} to model {target_model_id}")
                
            return success
            
        except Exception as e:
            logger.error(f"Rollback failed for deployment {deployment_id}: {e}")
            return False
    
    async def _execute_rollback(self, deployment: DeploymentRecord, target_model_id: str) -> bool:
        """Execute the actual rollback."""
        logger.info(f"Rolling back to model {target_model_id}")
        
        # In production, this would:
        # 1. Switch traffic back to previous model
        # 2. Update load balancer configuration
        # 3. Verify rollback is working
        # 4. Clean up failed deployment
        
        # Simulate rollback
        await asyncio.sleep(1)
        return True
    
    async def _find_previous_production_model(self, current_model_id: str) -> Optional[str]:
        """Find the previous production model for rollback."""
        current_model = self.models[current_model_id]
        
        # Find models of same type in production stage
        production_models = [
            model for model in self.models.values()
            if (model.model_type == current_model.model_type and
                model.stage == ModelStage.PRODUCTION and
                model.model_id != current_model_id and
                model.deployed_at is not None)
        ]
        
        if not production_models:
            return None
        
        # Return most recently deployed
        production_models.sort(key=lambda m: m.deployed_at, reverse=True)
        return production_models[0].model_id
    
    def _update_active_model_metrics(self):
        """Update Prometheus metrics for active models."""
        # Count active models by type
        active_counts = {}
        for model in self.models.values():
            if model.stage == ModelStage.PRODUCTION and model.traffic_percentage > 0:
                active_counts[model.model_type] = active_counts.get(model.model_type, 0) + 1
        
        # Update metrics
        for model_type, count in active_counts.items():
            active_model_versions.labels(model_type=model_type).set(count)
    
    async def get_model(self, model_id: str) -> Optional[ModelMetadata]:
        """Get model metadata by ID."""
        return self.models.get(model_id)
    
    async def list_models(self,
                         model_type: Optional[str] = None,
                         stage: Optional[ModelStage] = None,
                         tags: Optional[Set[str]] = None) -> List[ModelMetadata]:
        """List models with optional filters."""
        models = list(self.models.values())
        
        if model_type:
            models = [m for m in models if m.model_type == model_type]
        
        if stage:
            models = [m for m in models if m.stage == stage]
        
        if tags:
            models = [m for m in models if tags.issubset(m.tags)]
        
        return models
    
    async def get_active_model(self, model_type: str) -> Optional[ModelMetadata]:
        """Get currently active model for a type."""
        production_models = [
            model for model in self.models.values()
            if (model.model_type == model_type and
                model.stage == ModelStage.PRODUCTION and
                model.traffic_percentage > 0)
        ]
        
        if not production_models:
            return None
        
        # Return model with highest traffic percentage
        return max(production_models, key=lambda m: m.traffic_percentage)
    
    async def compare_models(self, model_id_1: str, model_id_2: str) -> Dict[str, Any]:
        """Compare two models."""
        model1 = self.models.get(model_id_1)
        model2 = self.models.get(model_id_2)
        
        if not model1 or not model2:
            raise ValueError("One or both models not found")
        
        comparison = {
            "models": {
                "model_1": {
                    "id": model1.model_id,
                    "version": model1.version,
                    "stage": model1.stage.value,
                    "created_at": model1.created_at.isoformat()
                },
                "model_2": {
                    "id": model2.model_id,
                    "version": model2.version,
                    "stage": model2.stage.value,
                    "created_at": model2.created_at.isoformat()
                }
            },
            "metrics_comparison": {}
        }
        
        # Compare validation metrics
        all_metrics = set(model1.validation_metrics.keys()) | set(model2.validation_metrics.keys())
        
        for metric in all_metrics:
            val1 = model1.validation_metrics.get(metric)
            val2 = model2.validation_metrics.get(metric)
            
            comparison["metrics_comparison"][metric] = {
                "model_1": val1,
                "model_2": val2,
                "difference": (val2 - val1) if val1 and val2 else None,
                "improvement": (val2 > val1) if val1 and val2 else None
            }
        
        return comparison
    
    async def get_deployment_history(self, model_type: Optional[str] = None) -> List[DeploymentRecord]:
        """Get deployment history."""
        deployments = list(self.deployments.values())
        
        if model_type:
            model_ids = [m.model_id for m in self.models.values() if m.model_type == model_type]
            deployments = [d for d in deployments if d.model_id in model_ids]
        
        # Sort by deployment time
        deployments.sort(key=lambda d: d.deployed_at, reverse=True)
        
        return deployments


# Global registry instance
_registry_instance = None

async def get_model_registry() -> ModelRegistry:
    """Get global model registry instance."""
    global _registry_instance
    if _registry_instance is None:
        _registry_instance = ModelRegistry()
    return _registry_instance