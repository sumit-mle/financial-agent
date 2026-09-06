"""
MLOps API Routes.

REST API endpoints for managing MLOps pipeline:
- Model training and deployment
- Performance monitoring  
- Data processing
- Model registry management
"""
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from fastapi import APIRouter, HTTPException, BackgroundTasks, Query
from pydantic import BaseModel, Field

from app.core.logging import get_logger
from app.mlops.pipeline import get_mlops_pipeline, RetrainingTrigger
from app.mlops.feedback_collector import get_feedback_collector, FeedbackType
from app.mlops.model_registry import get_model_registry, ModelStage, DeploymentStrategy
from app.mlops.data_processor import get_data_processor, DataProcessingConfig

logger = get_logger(__name__)
router = APIRouter(prefix="/mlops", tags=["MLOps"])


# Pydantic models for API
class ModelRegistrationRequest(BaseModel):
    model_type: str = Field(..., description="Type of model (e.g., 'sentiment_classifier')")
    model_path: str = Field(..., description="Path to model artifacts")
    version: str = Field(..., description="Model version")
    description: str = Field(default="", description="Model description")
    tags: List[str] = Field(default=[], description="Model tags")
    hyperparameters: Dict[str, Any] = Field(default={}, description="Model hyperparameters")
    training_metrics: Dict[str, float] = Field(default={}, description="Training metrics")
    validation_metrics: Dict[str, float] = Field(default={}, description="Validation metrics")


class ModelDeploymentRequest(BaseModel):
    model_id: str = Field(..., description="Model ID to deploy")
    target_stage: str = Field(..., description="Target deployment stage (development/staging/production)")
    strategy: str = Field(default="blue_green", description="Deployment strategy")
    traffic_percentage: float = Field(default=100.0, description="Traffic percentage (0-100)")
    rollback_model_id: Optional[str] = Field(None, description="Fallback model for rollback")
    deployment_notes: str = Field(default="", description="Deployment notes")


class FeedbackSubmissionRequest(BaseModel):
    session_id: str = Field(..., description="Session ID")
    model_type: str = Field(..., description="Model type")
    feedback_type: str = Field(..., description="Type of feedback")
    rating: Optional[int] = Field(None, description="User rating (1-5)")
    escalated: bool = Field(default=False, description="Was conversation escalated")
    safety_violation: bool = Field(default=False, description="Safety violation occurred")
    user_message: str = Field(..., description="User message")
    agent_response: str = Field(..., description="Agent response")
    response_time: float = Field(..., description="Response time in seconds")
    confidence_score: float = Field(..., description="Model confidence score")
    metadata: Dict[str, Any] = Field(default={}, description="Additional metadata")


class DataProcessingRequest(BaseModel):
    target_model_type: str = Field(..., description="Target model type")
    source_tables: List[str] = Field(..., description="Source data tables")
    training_window_days: int = Field(default=30, description="Training data window in days")
    min_samples_per_class: int = Field(default=100, description="Minimum samples per class")
    max_samples_per_class: int = Field(default=10000, description="Maximum samples per class")
    test_split_ratio: float = Field(default=0.2, description="Test split ratio")
    validation_split_ratio: float = Field(default=0.1, description="Validation split ratio")
    quality_threshold: float = Field(default=0.8, description="Data quality threshold")
    privacy_mode: bool = Field(default=True, description="Enable privacy protection")


class RetrainingTriggerRequest(BaseModel):
    model_type: str = Field(..., description="Model type to retrain")
    reason: str = Field(default="Manual trigger", description="Reason for retraining")


@router.get("/pipeline/status")
async def get_pipeline_status():
    """Get MLOps pipeline status and metrics."""
    try:
        pipeline = await get_mlops_pipeline()
        status = await pipeline.get_pipeline_status()
        
        # Add additional system information
        status["system_info"] = {
            "timestamp": datetime.utcnow().isoformat(),
            "monitoring_active": pipeline._running
        }
        
        return status
        
    except Exception as e:
        logger.error(f"Error getting pipeline status: {e}")
        raise HTTPException(status_code=500, detail="Failed to get pipeline status")


@router.post("/pipeline/start")
async def start_pipeline():
    """Start MLOps pipeline monitoring."""
    try:
        pipeline = await get_mlops_pipeline()
        collector = await get_feedback_collector()
        
        if not pipeline._running:
            await pipeline.start_monitoring()
            
        if not collector._running:
            await collector.start_collection()
            
        return {"message": "MLOps pipeline started successfully"}
        
    except Exception as e:
        logger.error(f"Error starting pipeline: {e}")
        raise HTTPException(status_code=500, detail="Failed to start pipeline")


@router.post("/pipeline/stop")
async def stop_pipeline():
    """Stop MLOps pipeline monitoring."""
    try:
        pipeline = await get_mlops_pipeline()
        collector = await get_feedback_collector()
        
        await pipeline.stop_monitoring()
        await collector.stop_collection()
        
        return {"message": "MLOps pipeline stopped successfully"}
        
    except Exception as e:
        logger.error(f"Error stopping pipeline: {e}")
        raise HTTPException(status_code=500, detail="Failed to stop pipeline")


@router.post("/models/register")
async def register_model(request: ModelRegistrationRequest):
    """Register a new model version."""
    try:
        registry = await get_model_registry()
        
        # Convert stage string to enum
        stage = ModelStage.DEVELOPMENT  # Default stage for new models
        
        model_id = await registry.register_model(
            model_type=request.model_type,
            model_path=request.model_path,
            version=request.version,
            stage=stage,
            description=request.description,
            tags=set(request.tags),
            hyperparameters=request.hyperparameters,
            training_metrics=request.training_metrics,
            validation_metrics=request.validation_metrics
        )
        
        return {
            "model_id": model_id,
            "message": f"Model {model_id} registered successfully"
        }
        
    except Exception as e:
        logger.error(f"Error registering model: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to register model: {str(e)}")


@router.get("/models")
async def list_models(
    model_type: Optional[str] = Query(None, description="Filter by model type"),
    stage: Optional[str] = Query(None, description="Filter by stage"),
    limit: int = Query(100, description="Maximum number of models to return")
):
    """List registered models with optional filters."""
    try:
        registry = await get_model_registry()
        
        # Convert stage string to enum if provided
        stage_enum = None
        if stage:
            try:
                stage_enum = ModelStage(stage)
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Invalid stage: {stage}")
        
        models = await registry.list_models(
            model_type=model_type,
            stage=stage_enum
        )
        
        # Limit results
        models = models[:limit]
        
        # Convert to API response format
        models_data = []
        for model in models:
            model_data = {
                "model_id": model.model_id,
                "model_type": model.model_type,
                "version": model.version,
                "stage": model.stage.value,
                "created_at": model.created_at.isoformat(),
                "deployed_at": model.deployed_at.isoformat() if model.deployed_at else None,
                "traffic_percentage": model.traffic_percentage,
                "description": model.description,
                "tags": list(model.tags),
                "training_metrics": model.training_metrics,
                "validation_metrics": model.validation_metrics
            }
            models_data.append(model_data)
        
        return {
            "models": models_data,
            "total_count": len(models_data)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing models: {e}")
        raise HTTPException(status_code=500, detail="Failed to list models")


@router.get("/models/{model_id}")
async def get_model_details(model_id: str):
    """Get detailed information about a specific model."""
    try:
        registry = await get_model_registry()
        model = await registry.get_model(model_id)
        
        if not model:
            raise HTTPException(status_code=404, detail=f"Model {model_id} not found")
        
        model_data = {
            "model_id": model.model_id,
            "model_type": model.model_type,
            "version": model.version,
            "stage": model.stage.value,
            "created_by": model.created_by,
            "created_at": model.created_at.isoformat(),
            "deployed_at": model.deployed_at.isoformat() if model.deployed_at else None,
            "model_path": model.model_path,
            "description": model.description,
            "tags": list(model.tags),
            "hyperparameters": model.hyperparameters,
            "training_metrics": model.training_metrics,
            "validation_metrics": model.validation_metrics,
            "production_metrics": model.production_metrics,
            "traffic_percentage": model.traffic_percentage,
            "deployment_strategy": model.deployment_strategy.value if model.deployment_strategy else None,
            "parent_model_id": model.parent_model_id,
            "derived_models": model.derived_models
        }
        
        return model_data
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting model details: {e}")
        raise HTTPException(status_code=500, detail="Failed to get model details")


@router.post("/models/{model_id}/promote")
async def promote_model(
    model_id: str,
    target_stage: str = Query(..., description="Target stage (staging/production)"),
    validation_metrics: Optional[Dict[str, float]] = None
):
    """Promote model to next stage."""
    try:
        registry = await get_model_registry()
        
        # Convert stage string to enum
        try:
            stage_enum = ModelStage(target_stage)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid stage: {target_stage}")
        
        success = await registry.promote_model(
            model_id=model_id,
            target_stage=stage_enum,
            validation_metrics=validation_metrics
        )
        
        if success:
            return {"message": f"Model {model_id} promoted to {target_stage} successfully"}
        else:
            raise HTTPException(status_code=400, detail="Model promotion failed validation requirements")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error promoting model: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to promote model: {str(e)}")


@router.post("/models/deploy")
async def deploy_model(request: ModelDeploymentRequest, background_tasks: BackgroundTasks):
    """Deploy model to target environment."""
    try:
        registry = await get_model_registry()
        
        # Convert enums
        try:
            target_stage = ModelStage(request.target_stage)
            strategy = DeploymentStrategy(request.strategy)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"Invalid parameter: {str(e)}")
        
        # Execute deployment in background
        background_tasks.add_task(
            _execute_deployment,
            registry,
            request.model_id,
            target_stage,
            strategy,
            request.traffic_percentage,
            request.rollback_model_id,
            request.deployment_notes
        )
        
        return {
            "message": f"Deployment initiated for model {request.model_id}",
            "model_id": request.model_id,
            "target_stage": request.target_stage,
            "strategy": request.strategy
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error initiating deployment: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to initiate deployment: {str(e)}")


async def _execute_deployment(registry, model_id: str, target_stage: ModelStage, 
                             strategy: DeploymentStrategy, traffic_percentage: float,
                             rollback_model_id: Optional[str], deployment_notes: str):
    """Execute model deployment in background."""
    try:
        deployment_id = await registry.deploy_model(
            model_id=model_id,
            target_stage=target_stage,
            strategy=strategy,
            traffic_percentage=traffic_percentage,
            rollback_model_id=rollback_model_id,
            deployment_notes=deployment_notes
        )
        
        logger.info(f"Deployment completed: {deployment_id}")
        
    except Exception as e:
        logger.error(f"Background deployment failed: {e}")


@router.post("/models/rollback/{deployment_id}")
async def rollback_deployment(
    deployment_id: str,
    reason: str = Query("Manual rollback", description="Reason for rollback"),
    rollback_to_model_id: Optional[str] = Query(None, description="Specific model to rollback to")
):
    """Rollback a model deployment."""
    try:
        registry = await get_model_registry()
        
        success = await registry.rollback_deployment(
            deployment_id=deployment_id,
            reason=reason,
            rollback_to_model_id=rollback_to_model_id
        )
        
        if success:
            return {"message": f"Deployment {deployment_id} rolled back successfully"}
        else:
            raise HTTPException(status_code=400, detail="Rollback failed")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error rolling back deployment: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to rollback deployment: {str(e)}")


@router.post("/feedback/submit")
async def submit_feedback(request: FeedbackSubmissionRequest):
    """Submit user feedback for model performance tracking."""
    try:
        collector = await get_feedback_collector()
        
        # Determine feedback type
        if request.feedback_type == "user_rating" and request.rating:
            await collector.collect_user_rating(
                session_id=request.session_id,
                model_type=request.model_type,
                rating=request.rating,
                user_message=request.user_message,
                agent_response=request.agent_response,
                response_time=request.response_time,
                confidence_score=request.confidence_score,
                escalated=request.escalated,
                metadata=request.metadata
            )
            
        elif request.feedback_type == "escalation" and request.escalated:
            await collector.collect_escalation_feedback(
                session_id=request.session_id,
                model_type=request.model_type,
                reason=request.metadata.get("escalation_reason", "Unknown"),
                user_message=request.user_message,
                agent_response=request.agent_response,
                response_time=request.response_time,
                confidence_score=request.confidence_score,
                metadata=request.metadata
            )
            
        elif request.feedback_type == "safety_violation" and request.safety_violation:
            await collector.collect_safety_violation(
                session_id=request.session_id,
                model_type=request.model_type,
                violation_type=request.metadata.get("violation_type", "Unknown"),
                user_message=request.user_message,
                agent_response=request.agent_response,
                confidence_score=request.confidence_score,
                metadata=request.metadata
            )
        
        return {"message": "Feedback submitted successfully"}
        
    except Exception as e:
        logger.error(f"Error submitting feedback: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to submit feedback: {str(e)}")


@router.get("/feedback/summary")
async def get_feedback_summary(
    model_type: Optional[str] = Query(None, description="Filter by model type"),
    hours: int = Query(24, description="Time window in hours")
):
    """Get feedback summary and performance metrics."""
    try:
        collector = await get_feedback_collector()
        summary = await collector.get_feedback_summary(model_type=model_type)
        
        return {
            "summary": summary,
            "time_window_hours": hours,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error getting feedback summary: {e}")
        raise HTTPException(status_code=500, detail="Failed to get feedback summary")


@router.post("/data/process")
async def process_training_data(request: DataProcessingRequest, background_tasks: BackgroundTasks):
    """Process data for model training."""
    try:
        processor = await get_data_processor()
        
        # Create processing config
        config = DataProcessingConfig(
            source_tables=request.source_tables,
            target_model_type=request.target_model_type,
            training_window_days=request.training_window_days,
            min_samples_per_class=request.min_samples_per_class,
            max_samples_per_class=request.max_samples_per_class,
            test_split_ratio=request.test_split_ratio,
            validation_split_ratio=request.validation_split_ratio,
            quality_threshold=request.quality_threshold,
            privacy_mode=request.privacy_mode
        )
        
        # Generate output path
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        output_path = f"data/processed/{request.target_model_type}/{timestamp}"
        
        # Execute processing in background
        background_tasks.add_task(
            _process_data_background,
            processor,
            config,
            output_path
        )
        
        return {
            "message": "Data processing initiated",
            "target_model_type": request.target_model_type,
            "output_path": output_path,
            "config": request.dict()
        }
        
    except Exception as e:
        logger.error(f"Error initiating data processing: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to initiate data processing: {str(e)}")


async def _process_data_background(processor, config: DataProcessingConfig, output_path: str):
    """Execute data processing in background."""
    try:
        result = await processor.process_training_data(config, output_path)
        logger.info(f"Data processing completed: {result['job_id']}")
        
    except Exception as e:
        logger.error(f"Background data processing failed: {e}")


@router.post("/retrain/trigger")
async def trigger_retraining(request: RetrainingTriggerRequest):
    """Manually trigger model retraining."""
    try:
        pipeline = await get_mlops_pipeline()
        
        await pipeline.trigger_manual_retraining(
            model_type=request.model_type,
            reason=request.reason
        )
        
        return {
            "message": f"Retraining triggered for {request.model_type}",
            "reason": request.reason,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error triggering retraining: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to trigger retraining: {str(e)}")


@router.get("/deployments/history")
async def get_deployment_history(
    model_type: Optional[str] = Query(None, description="Filter by model type"),
    limit: int = Query(50, description="Maximum number of deployments to return")
):
    """Get deployment history."""
    try:
        registry = await get_model_registry()
        deployments = await registry.get_deployment_history(model_type=model_type)
        
        # Limit results
        deployments = deployments[:limit]
        
        # Convert to API response format
        deployments_data = []
        for deployment in deployments:
            deployment_data = {
                "deployment_id": deployment.deployment_id,
                "model_id": deployment.model_id,
                "model_version": deployment.model_version,
                "strategy": deployment.strategy.value,
                "target_stage": deployment.target_stage.value,
                "traffic_percentage": deployment.traffic_percentage,
                "deployed_at": deployment.deployed_at.isoformat(),
                "deployed_by": deployment.deployed_by,
                "health_check_passed": deployment.health_check_passed,
                "performance_validation_passed": deployment.performance_validation_passed,
                "rolled_back_at": deployment.rolled_back_at.isoformat() if deployment.rolled_back_at else None,
                "rollback_reason": deployment.rollback_reason,
                "deployment_notes": deployment.deployment_notes
            }
            deployments_data.append(deployment_data)
        
        return {
            "deployments": deployments_data,
            "total_count": len(deployments_data)
        }
        
    except Exception as e:
        logger.error(f"Error getting deployment history: {e}")
        raise HTTPException(status_code=500, detail="Failed to get deployment history")
