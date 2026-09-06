"""
Experiment management API endpoints.

Provides REST API for managing A/B tests, viewing results,
and controlling experiment rollouts.
"""
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.api.middleware import _require_admin
from app.experimentation.framework import (
    get_experiment_engine,
    Experiment,
    ExperimentVariant,
    ExperimentMetric,
    ExperimentStatus,
    TrafficAllocation
)
from app.experimentation.prompt_experiments import (
    get_prompt_manager,
    PromptConfig,
    initialize_default_experiments
)
from app.experimentation.analysis import get_analyzer, ExperimentAnalysis
from app.core.logging import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/experiments", tags=["Experiments"])


# ── Request/Response Models ────────────────────────────────────────────────────

class CreateExperimentRequest(BaseModel):
    """Request to create a new experiment."""
    name: str = Field(..., description="Experiment name")
    description: str = Field(..., description="Experiment description")
    experiment_type: str = Field(default="prompt", description="Type of experiment")
    variants: Dict[str, Dict[str, Any]] = Field(..., description="Experiment variants")
    traffic_split: float = Field(default=0.1, ge=0.01, le=0.5, description="Traffic allocation for treatment")
    target_intent: Optional[str] = Field(None, description="Target intent for experiment")
    duration_days: int = Field(default=14, ge=1, le=90, description="Experiment duration")


class ExperimentResponse(BaseModel):
    """Experiment information response."""
    id: str
    name: str
    description: str
    status: str
    variants: List[Dict[str, Any]]
    metrics: List[Dict[str, Any]]
    traffic_allocation: str
    start_date: Optional[datetime]
    end_date: Optional[datetime]
    created_at: datetime


class ExperimentResultsResponse(BaseModel):
    """Experiment results response."""
    experiment_id: str
    metric_name: str
    variants: Dict[str, Dict[str, Any]]  # variant_id -> stats
    statistical_analysis: Dict[str, Any]
    recommendation: str
    is_significant: bool
    confidence_level: float


class ExperimentListResponse(BaseModel):
    """List of experiments response."""
    experiments: List[ExperimentResponse]
    total: int


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.post("/", response_model=Dict[str, str])
async def create_experiment(
    request: CreateExperimentRequest,
    _: None = Depends(_require_admin)
) -> Dict[str, str]:
    """Create a new A/B experiment."""
    
    try:
        if request.experiment_type == "prompt":
            # Create prompt experiment
            prompt_manager = await get_prompt_manager()
            
            # Convert variants to PromptConfig objects
            prompt_variants = {}
            for variant_id, config in request.variants.items():
                prompt_variants[variant_id] = PromptConfig(
                    system_prompt=config.get("system_prompt", ""),
                    reasoning_prompt=config.get("reasoning_prompt", ""),
                    response_template=config.get("response_template", ""),
                    model_params=config.get("model_params", {}),
                    use_chain_of_thought=config.get("use_chain_of_thought", True),
                    max_tokens=config.get("max_tokens", 1000),
                    temperature=config.get("temperature", 0.7),
                    examples=config.get("examples", [])
                )
            
            experiment_id = await prompt_manager.create_prompt_experiment(
                name=request.name,
                description=request.description,
                prompt_variants=prompt_variants,
                target_intent=request.target_intent,
                traffic_split=request.traffic_split
            )
            
            logger.info(f"Created prompt experiment: {experiment_id}")
            return {"experiment_id": experiment_id, "status": "created"}
            
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported experiment type: {request.experiment_type}"
            )
            
    except Exception as e:
        logger.error(f"Failed to create experiment: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create experiment: {str(e)}"
        )


@router.get("/", response_model=ExperimentListResponse)
async def list_experiments(
    status_filter: Optional[str] = Query(None, description="Filter by status"),
    limit: int = Query(50, ge=1, le=100, description="Maximum results"),
    offset: int = Query(0, ge=0, description="Results offset"),
    _: None = Depends(_require_admin)
) -> ExperimentListResponse:
    """List all experiments with optional filtering."""
    
    try:
        engine = await get_experiment_engine()
        experiments = []
        
        # Get experiments from engine (in production, query database)
        for exp_id, experiment in engine._experiments.items():
            if status_filter and experiment.status.value != status_filter:
                continue
                
            exp_data = ExperimentResponse(
                id=experiment.id,
                name=experiment.name,
                description=experiment.description,
                status=experiment.status.value,
                variants=[
                    {
                        "id": v.id,
                        "name": v.name,
                        "description": v.description,
                        "traffic_weight": v.traffic_weight,
                        "is_control": v.is_control
                    }
                    for v in experiment.variants.values()
                ],
                metrics=[
                    {
                        "name": m.name,
                        "type": m.type,
                        "description": m.description,
                        "higher_is_better": m.higher_is_better
                    }
                    for m in experiment.metrics.values()
                ],
                traffic_allocation=experiment.traffic_allocation.value,
                start_date=experiment.start_date,
                end_date=experiment.end_date,
                created_at=datetime.utcnow()  # Mock created_at
            )
            experiments.append(exp_data)
        
        # Apply pagination
        total = len(experiments)
        paginated = experiments[offset:offset + limit]
        
        return ExperimentListResponse(
            experiments=paginated,
            total=total
        )
        
    except Exception as e:
        logger.error(f"Failed to list experiments: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to list experiments: {str(e)}"
        )


@router.get("/{experiment_id}", response_model=ExperimentResponse)
async def get_experiment(
    experiment_id: str,
    _: None = Depends(_require_admin)
) -> ExperimentResponse:
    """Get detailed experiment information."""
    
    try:
        engine = await get_experiment_engine()
        experiment = engine._experiments.get(experiment_id)
        
        if not experiment:
            raise HTTPException(
                status_code=404,
                detail=f"Experiment not found: {experiment_id}"
            )
        
        return ExperimentResponse(
            id=experiment.id,
            name=experiment.name,
            description=experiment.description,
            status=experiment.status.value,
            variants=[
                {
                    "id": v.id,
                    "name": v.name,
                    "description": v.description,
                    "traffic_weight": v.traffic_weight,
                    "is_control": v.is_control,
                    "config": v.config
                }
                for v in experiment.variants.values()
            ],
            metrics=[
                {
                    "name": m.name,
                    "type": m.type,
                    "description": m.description,
                    "higher_is_better": m.higher_is_better,
                    "statistical_power": m.statistical_power,
                    "minimum_detectable_effect": m.minimum_detectable_effect
                }
                for m in experiment.metrics.values()
            ],
            traffic_allocation=experiment.traffic_allocation.value,
            start_date=experiment.start_date,
            end_date=experiment.end_date,
            created_at=datetime.utcnow()
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get experiment {experiment_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get experiment: {str(e)}"
        )


@router.post("/{experiment_id}/start")
async def start_experiment(
    experiment_id: str,
    _: None = Depends(_require_admin)
) -> Dict[str, str]:
    """Start an experiment."""
    
    try:
        engine = await get_experiment_engine()
        experiment = engine._experiments.get(experiment_id)
        
        if not experiment:
            raise HTTPException(
                status_code=404,
                detail=f"Experiment not found: {experiment_id}"
            )
        
        if experiment.status != ExperimentStatus.DRAFT:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot start experiment in {experiment.status.value} status"
            )
        
        # Start experiment
        experiment.status = ExperimentStatus.ACTIVE
        experiment.start_date = datetime.utcnow()
        
        logger.info(f"Started experiment: {experiment_id}")
        return {"status": "started", "experiment_id": experiment_id}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to start experiment {experiment_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to start experiment: {str(e)}"
        )


@router.post("/{experiment_id}/stop")
async def stop_experiment(
    experiment_id: str,
    _: None = Depends(_require_admin)
) -> Dict[str, str]:
    """Stop an experiment."""
    
    try:
        engine = await get_experiment_engine()
        experiment = engine._experiments.get(experiment_id)
        
        if not experiment:
            raise HTTPException(
                status_code=404,
                detail=f"Experiment not found: {experiment_id}"
            )
        
        if experiment.status != ExperimentStatus.ACTIVE:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot stop experiment in {experiment.status.value} status"
            )
        
        # Stop experiment
        experiment.status = ExperimentStatus.COMPLETED
        experiment.end_date = datetime.utcnow()
        
        logger.info(f"Stopped experiment: {experiment_id}")
        return {"status": "stopped", "experiment_id": experiment_id}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to stop experiment {experiment_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to stop experiment: {str(e)}"
        )


@router.get("/{experiment_id}/results")
async def get_experiment_results(
    experiment_id: str,
    metric_name: Optional[str] = Query(None, description="Specific metric to analyze"),
    _: None = Depends(_require_admin)
) -> ExperimentResultsResponse:
    """Get experiment results and statistical analysis."""
    
    try:
        engine = await get_experiment_engine()
        experiment = engine._experiments.get(experiment_id)
        
        if not experiment:
            raise HTTPException(
                status_code=404,
                detail=f"Experiment not found: {experiment_id}"
            )
        
        # In production, query actual experiment data from database
        # For demo, generate mock results
        import random
        import numpy as np
        
        # Mock data generation
        results = {}
        for variant in experiment.variants.values():
            sample_size = random.randint(100, 1000)
            if metric_name:
                metrics_to_analyze = [metric_name]
            else:
                metrics_to_analyze = list(experiment.metrics.keys())[:1]  # First metric
            
            variant_results = {}
            for m_name in metrics_to_analyze:
                metric = experiment.metrics.get(m_name)
                if not metric:
                    continue
                    
                # Generate mock data based on metric type
                if metric.type == "conversion":
                    # Generate conversion data (0s and 1s)
                    conversion_rate = 0.15 if variant.is_control else 0.18  # Mock improvement
                    data = [1 if random.random() < conversion_rate else 0 for _ in range(sample_size)]
                elif metric.type == "numeric":
                    # Generate numeric data (e.g., response quality scores)
                    mean_val = 3.2 if variant.is_control else 3.5  # Mock improvement
                    data = np.random.normal(mean_val, 0.8, sample_size).tolist()
                else:
                    # Duration data (e.g., response times)
                    mean_time = 2.1 if variant.is_control else 1.9  # Mock improvement
                    data = np.random.exponential(mean_time, sample_size).tolist()
                
                variant_results[m_name] = {
                    "sample_size": sample_size,
                    "mean_value": np.mean(data),
                    "std_deviation": np.std(data),
                    "data": data  # For analysis
                }
            
            results[variant.id] = variant_results
        
        # Perform statistical analysis
        analyzer = get_analyzer()
        metric_to_analyze = metric_name or list(experiment.metrics.keys())[0]
        
        # Get control and treatment data
        control_variant = next(v for v in experiment.variants.values() if v.is_control)
        treatment_variants = [v for v in experiment.variants.values() if not v.is_control]
        
        if treatment_variants and metric_to_analyze in results[control_variant.id]:
            treatment_variant = treatment_variants[0]  # Analyze first treatment
            
            control_data = results[control_variant.id][metric_to_analyze]["data"]
            treatment_data = results[treatment_variant.id][metric_to_analyze]["data"]
            
            metric = experiment.metrics[metric_to_analyze]
            analysis = analyzer.analyze_experiment(
                experiment_id=experiment_id,
                metric_name=metric_to_analyze,
                control_data=control_data,
                treatment_data=treatment_data,
                metric_type=metric.type
            )
            
            # Clean up data from results (don't return raw data)
            clean_results = {}
            for variant_id, variant_data in results.items():
                clean_results[variant_id] = {}
                for m_name, stats in variant_data.items():
                    clean_results[variant_id][m_name] = {
                        "sample_size": stats["sample_size"],
                        "mean_value": stats["mean_value"],
                        "std_deviation": stats["std_deviation"]
                    }
            
            return ExperimentResultsResponse(
                experiment_id=experiment_id,
                metric_name=metric_to_analyze,
                variants=clean_results,
                statistical_analysis={
                    "test_type": analysis.statistical_test.test_type.value,
                    "p_value": analysis.statistical_test.p_value,
                    "effect_size": analysis.statistical_test.effect_size,
                    "confidence_interval": analysis.statistical_test.confidence_interval,
                    "sample_size": analysis.statistical_test.sample_size
                },
                recommendation=analysis.recommendation,
                is_significant=analysis.statistical_test.is_significant,
                confidence_level=analysis.confidence_level
            )
        else:
            raise HTTPException(
                status_code=400,
                detail="Insufficient data for analysis"
            )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get experiment results {experiment_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get experiment results: {str(e)}"
        )


@router.post("/initialize-defaults")
async def initialize_default_experiments_endpoint(
    _: None = Depends(_require_admin)
) -> Dict[str, str]:
    """Initialize default prompt experiments."""
    
    try:
        await initialize_default_experiments()
        
        logger.info("Initialized default experiments")
        return {"status": "initialized", "message": "Default experiments created"}
        
    except Exception as e:
        logger.error(f"Failed to initialize default experiments: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to initialize experiments: {str(e)}"
        )


@router.get("/{experiment_id}/assignments")
async def get_experiment_assignments(
    experiment_id: str,
    limit: int = Query(100, ge=1, le=1000),
    _: None = Depends(_require_admin)
) -> Dict[str, Any]:
    """Get experiment assignments for debugging."""
    
    try:
        engine = await get_experiment_engine()
        experiment = engine._experiments.get(experiment_id)
        
        if not experiment:
            raise HTTPException(
                status_code=404,
                detail=f"Experiment not found: {experiment_id}"
            )
        
        # In production, query assignment database
        # For demo, return mock assignments
        assignments = []
        for i in range(min(limit, 50)):  # Mock data
            variant_id = list(experiment.variants.keys())[i % len(experiment.variants)]
            assignments.append({
                "session_id": f"session_{i:04d}",
                "variant_id": variant_id,
                "assigned_at": datetime.utcnow(),
                "user_id": f"user_{i:04d}" if i % 3 == 0 else None
            })
        
        return {
            "experiment_id": experiment_id,
            "assignments": assignments,
            "total_assignments": len(assignments)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get assignments for {experiment_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get assignments: {str(e)}"
        )