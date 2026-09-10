"""
A/B Testing Framework for Prompt and Model Experimentation.

Features:
- Multi-variate experiment support
- Statistical significance testing
- Automatic traffic splitting
- Performance metric tracking
- Experiment management and rollout control
"""
import hashlib
import json
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Union
from abc import ABC, abstractmethod

import asyncio
from sqlalchemy import Column, String, Float, Integer, DateTime, Text, Boolean
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.core.logging import get_logger
from app.observability.metrics import Counter, Histogram

logger = get_logger(__name__)

# Metrics for A/B testing
experiment_assignments = Counter(
    'experiment_assignments_total',
    'Total experiment assignments',
    ['experiment_id', 'variant']
)

experiment_conversions = Counter(
    'experiment_conversions_total', 
    'Total experiment conversions',
    ['experiment_id', 'variant', 'metric']
)

experiment_duration = Histogram(
    'experiment_duration_seconds',
    'Time spent in experiments',
    ['experiment_id', 'variant']
)

Base = declarative_base()


class ExperimentStatus(Enum):
    """Experiment lifecycle status."""
    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused" 
    COMPLETED = "completed"
    ARCHIVED = "archived"


class TrafficAllocation(Enum):
    """Traffic allocation strategies."""
    EQUAL = "equal"           # Equal split across variants
    WEIGHTED = "weighted"     # Custom weights per variant
    RAMP = "ramp"            # Gradual ramp up of new variant
    CHAMPION_CHALLENGER = "champion_challenger"  # 80/20 split


@dataclass
class ExperimentVariant:
    """A single variant in an experiment."""
    id: str
    name: str
    description: str
    config: Dict[str, Any]
    traffic_weight: float = 0.5
    is_control: bool = False


@dataclass
class ExperimentMetric:
    """Metric to track for experiment evaluation."""
    name: str
    type: str  # 'conversion', 'numeric', 'duration'
    description: str
    higher_is_better: bool = True
    statistical_power: float = 0.8
    minimum_detectable_effect: float = 0.05


@dataclass
class ExperimentResult:
    """Result of an experiment evaluation."""
    variant_id: str
    metric_name: str
    sample_size: int
    mean_value: float
    std_deviation: float
    confidence_interval: tuple[float, float]
    p_value: Optional[float] = None
    is_significant: bool = False
    
    
class ExperimentModel(Base):
    """Database model for experiments."""
    __tablename__ = 'experiments'
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    description = Column(Text)
    status = Column(String(50), default=ExperimentStatus.DRAFT.value)
    
    # Configuration
    config = Column(JSONB)
    variants = Column(JSONB)  # List of variants
    metrics = Column(JSONB)   # List of metrics to track
    
    # Traffic control
    traffic_allocation = Column(String(50), default=TrafficAllocation.EQUAL.value)
    target_population = Column(String(100))  # 'all', 'new_users', 'returning_users'
    
    # Timing
    start_date = Column(DateTime)
    end_date = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Results
    results = Column(JSONB)
    winner_variant = Column(String(100))
    
    
class ExperimentEventModel(Base):
    """Database model for experiment events and metrics."""
    __tablename__ = 'experiment_events'
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    experiment_id = Column(UUID(as_uuid=True), nullable=False)
    session_id = Column(String(100), nullable=False)
    user_id = Column(String(100))
    
    # Assignment
    variant_id = Column(String(100), nullable=False)
    assigned_at = Column(DateTime, default=datetime.utcnow)
    
    # Event data
    event_type = Column(String(50))  # 'assignment', 'conversion', 'metric'
    metric_name = Column(String(100))
    metric_value = Column(Float)
    
    # Context
    event_metadata = Column(JSONB)  # Renamed from metadata to avoid SQLAlchemy conflict
    created_at = Column(DateTime, default=datetime.utcnow)


class ExperimentEngine:
    """Core A/B testing engine."""
    
    def __init__(self):
        self._experiments: Dict[str, 'Experiment'] = {}
        self._assignments: Dict[str, Dict[str, str]] = {}  # session_id -> {exp_id: variant_id}
        
    async def register_experiment(self, experiment: 'Experiment') -> None:
        """Register an experiment with the engine."""
        self._experiments[experiment.id] = experiment
        logger.info(f"Registered experiment: {experiment.name} ({experiment.id})")
    
    async def get_variant(self, 
                         experiment_id: str, 
                         session_id: str, 
                         user_id: Optional[str] = None,
                         context: Optional[Dict[str, Any]] = None) -> Optional[ExperimentVariant]:
        """Get the assigned variant for a user/session."""
        experiment = self._experiments.get(experiment_id)
        if not experiment or not experiment.is_active():
            return None
            
        # Check if user is eligible
        if not experiment.is_eligible(session_id, user_id, context):
            return None
            
        # Get or assign variant
        variant = await self._get_assignment(experiment, session_id, user_id, context)
        
        # Track assignment
        if variant:
            experiment_assignments.labels(
                experiment_id=experiment_id,
                variant=variant.id
            ).inc()
            
            # Record assignment event
            await self._record_event(
                experiment_id=experiment_id,
                session_id=session_id,
                user_id=user_id,
                variant_id=variant.id,
                event_type='assignment'
            )
        
        return variant
    
    async def track_metric(self,
                          experiment_id: str,
                          session_id: str, 
                          metric_name: str,
                          value: Union[float, int, bool],
                          user_id: Optional[str] = None) -> None:
        """Track a metric value for an experiment."""
        experiment = self._experiments.get(experiment_id)
        if not experiment:
            return
            
        # Get user's assigned variant
        assignment = self._assignments.get(session_id, {})
        variant_id = assignment.get(experiment_id)
        
        if not variant_id:
            return
            
        # Convert boolean to numeric
        if isinstance(value, bool):
            value = 1.0 if value else 0.0
        
        # Track metric
        experiment_conversions.labels(
            experiment_id=experiment_id,
            variant=variant_id,
            metric=metric_name
        ).inc()
        
        # Record metric event
        await self._record_event(
            experiment_id=experiment_id,
            session_id=session_id,
            user_id=user_id,
            variant_id=variant_id,
            event_type='metric',
            metric_name=metric_name,
            metric_value=float(value)
        )
    
    async def _get_assignment(self,
                            experiment: 'Experiment',
                            session_id: str,
                            user_id: Optional[str] = None,
                            context: Optional[Dict[str, Any]] = None) -> Optional[ExperimentVariant]:
        """Get or create variant assignment for user."""
        # Check existing assignment
        if session_id in self._assignments:
            variant_id = self._assignments[session_id].get(experiment.id)
            if variant_id:
                return experiment.get_variant(variant_id)
        
        # Create new assignment
        variant = experiment.assign_variant(session_id, user_id, context)
        if variant:
            if session_id not in self._assignments:
                self._assignments[session_id] = {}
            self._assignments[session_id][experiment.id] = variant.id
            
        return variant
    
    async def _record_event(self,
                          experiment_id: str,
                          session_id: str,
                          variant_id: str,
                          event_type: str,
                          user_id: Optional[str] = None,
                          metric_name: Optional[str] = None,
                          metric_value: Optional[float] = None) -> None:
        """Record experiment event to database."""
        # In production, save to database
        # For now, just log
        logger.info(
            "Experiment event recorded",
            experiment_id=experiment_id,
            session_id=session_id,
            variant_id=variant_id,
            event_type=event_type,
            metric_name=metric_name,
            metric_value=metric_value
        )


class Experiment:
    """Individual A/B experiment."""
    
    def __init__(self,
                 id: str,
                 name: str,
                 description: str,
                 variants: List[ExperimentVariant],
                 metrics: List[ExperimentMetric],
                 traffic_allocation: TrafficAllocation = TrafficAllocation.EQUAL,
                 target_population: str = "all",
                 start_date: Optional[datetime] = None,
                 end_date: Optional[datetime] = None):
        
        self.id = id
        self.name = name
        self.description = description
        self.variants = {v.id: v for v in variants}
        self.metrics = {m.name: m for m in metrics}
        self.traffic_allocation = traffic_allocation
        self.target_population = target_population
        self.start_date = start_date
        self.end_date = end_date
        self.status = ExperimentStatus.DRAFT
        
        # Validate configuration
        self._validate()
    
    def _validate(self) -> None:
        """Validate experiment configuration."""
        if len(self.variants) < 2:
            raise ValueError("Experiment must have at least 2 variants")
            
        if not self.metrics:
            raise ValueError("Experiment must have at least 1 metric")
            
        total_weight = sum(v.traffic_weight for v in self.variants.values())
        if abs(total_weight - 1.0) > 0.001:
            raise ValueError(f"Variant weights must sum to 1.0, got {total_weight}")
            
        control_variants = [v for v in self.variants.values() if v.is_control]
        if len(control_variants) != 1:
            raise ValueError("Experiment must have exactly 1 control variant")
    
    def is_active(self) -> bool:
        """Check if experiment is currently active."""
        if self.status != ExperimentStatus.ACTIVE:
            return False
            
        now = datetime.utcnow()
        if self.start_date and now < self.start_date:
            return False
            
        if self.end_date and now > self.end_date:
            return False
            
        return True
    
    def is_eligible(self,
                   session_id: str,
                   user_id: Optional[str] = None,
                   context: Optional[Dict[str, Any]] = None) -> bool:
        """Check if user is eligible for this experiment."""
        # Basic eligibility check
        if not self.is_active():
            return False
            
        # Target population filtering
        if self.target_population == "new_users" and context and context.get("is_returning_user"):
            return False
            
        if self.target_population == "returning_users" and context and not context.get("is_returning_user"):
            return False
            
        # Add more sophisticated targeting logic here
        return True
    
    def assign_variant(self,
                      session_id: str,
                      user_id: Optional[str] = None,
                      context: Optional[Dict[str, Any]] = None) -> Optional[ExperimentVariant]:
        """Assign a variant to the user based on traffic allocation."""
        # Use consistent hashing for deterministic assignment
        hash_key = f"{self.id}:{session_id}"
        if user_id:
            hash_key += f":{user_id}"
            
        hash_value = int(hashlib.md5(hash_key.encode()).hexdigest(), 16)
        bucket = (hash_value % 10000) / 10000.0  # 0.0 to 1.0
        
        # Assign based on traffic weights
        cumulative_weight = 0.0
        for variant in self.variants.values():
            cumulative_weight += variant.traffic_weight
            if bucket <= cumulative_weight:
                return variant
                
        # Fallback to control variant
        control_variants = [v for v in self.variants.values() if v.is_control]
        return control_variants[0] if control_variants else None
    
    def get_variant(self, variant_id: str) -> Optional[ExperimentVariant]:
        """Get variant by ID."""
        return self.variants.get(variant_id)


# Global experiment engine instance
_experiment_engine: Optional[ExperimentEngine] = None

async def get_experiment_engine() -> ExperimentEngine:
    """Get singleton experiment engine."""
    global _experiment_engine
    if _experiment_engine is None:
        _experiment_engine = ExperimentEngine()
    return _experiment_engine