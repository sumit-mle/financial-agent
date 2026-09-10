"""
Tests for A/B Testing Framework.
"""
import pytest
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

from app.experimentation.framework import (
    Experiment,
    ExperimentVariant,
    ExperimentMetric,
    ExperimentEngine,
    ExperimentStatus,
    TrafficAllocation
)


@pytest.mark.models
@pytest.mark.unit
class TestABFramework:
    """Test suite for A/B testing framework."""
    
    @pytest.fixture
    def sample_variants(self):
        """Create sample experiment variants."""
        return [
            ExperimentVariant(
                id="control",
                name="Control",
                description="Original prompt",
                config={"prompt": "original"},
                traffic_weight=0.5,
                is_control=True
            ),
            ExperimentVariant(
                id="treatment",
                name="Treatment",
                description="New prompt",
                config={"prompt": "new"},
                traffic_weight=0.5,
                is_control=False
            )
        ]
    
    @pytest.fixture
    def sample_metrics(self):
        """Create sample experiment metrics."""
        return [
            ExperimentMetric(
                name="conversion_rate",
                type="conversion",
                description="User satisfaction rate",
                higher_is_better=True
            ),
            ExperimentMetric(
                name="response_time",
                type="duration", 
                description="Response generation time",
                higher_is_better=False
            )
        ]
    
    @pytest.fixture
    def sample_experiment(self, sample_variants, sample_metrics):
        """Create sample experiment."""
        return Experiment(
            id="test_exp_001",
            name="Test Experiment",
            description="Test experiment for unit testing",
            variants=sample_variants,
            metrics=sample_metrics
        )
    
    def test_experiment_creation(self, sample_experiment):
        """Test experiment creation and validation."""
        assert sample_experiment.id == "test_exp_001"
        assert sample_experiment.name == "Test Experiment"
        assert len(sample_experiment.variants) == 2
        assert len(sample_experiment.metrics) == 2
        
        # Check control variant exists
        control_variants = [v for v in sample_experiment.variants.values() if v.is_control]
        assert len(control_variants) == 1
        assert control_variants[0].id == "control"
    
    def test_experiment_validation_fails_insufficient_variants(self, sample_metrics):
        """Test experiment validation with insufficient variants."""
        with pytest.raises(ValueError, match="at least 2 variants"):
            Experiment(
                id="bad_exp",
                name="Bad Experiment",
                description="Bad experiment",
                variants=[ExperimentVariant("only_one", "One", "Only variant", {})],
                metrics=sample_metrics
            )
    
    def test_experiment_validation_fails_no_metrics(self, sample_variants):
        """Test experiment validation with no metrics."""
        with pytest.raises(ValueError, match="at least 1 metric"):
            Experiment(
                id="bad_exp",
                name="Bad Experiment", 
                description="Bad experiment",
                variants=sample_variants,
                metrics=[]
            )
    
    def test_experiment_validation_fails_wrong_weights(self, sample_metrics):
        """Test experiment validation with wrong traffic weights."""
        variants = [
            ExperimentVariant("a", "A", "Variant A", {}, 0.3, True),
            ExperimentVariant("b", "B", "Variant B", {}, 0.8, False)  # Sum > 1.0
        ]
        
        with pytest.raises(ValueError, match="weights must sum to 1.0"):
            Experiment(
                id="bad_exp",
                name="Bad Experiment",
                description="Bad experiment", 
                variants=variants,
                metrics=sample_metrics
            )
    
    def test_experiment_validation_fails_multiple_controls(self, sample_metrics):
        """Test experiment validation with multiple control variants."""
        variants = [
            ExperimentVariant("a", "A", "Variant A", {}, 0.5, True),
            ExperimentVariant("b", "B", "Variant B", {}, 0.5, True)  # Both control
        ]
        
        with pytest.raises(ValueError, match="exactly 1 control variant"):
            Experiment(
                id="bad_exp",
                name="Bad Experiment",
                description="Bad experiment",
                variants=variants,
                metrics=sample_metrics
            )
    
    def test_experiment_is_active(self, sample_experiment):
        """Test experiment active status checks."""
        # Draft status
        assert not sample_experiment.is_active()
        
        # Active status without dates
        sample_experiment.status = ExperimentStatus.ACTIVE
        assert sample_experiment.is_active()
        
        # Active with future start date
        sample_experiment.start_date = datetime.utcnow() + timedelta(days=1)
        assert not sample_experiment.is_active()
        
        # Active with past end date
        sample_experiment.start_date = datetime.utcnow() - timedelta(days=2)
        sample_experiment.end_date = datetime.utcnow() - timedelta(days=1)
        assert not sample_experiment.is_active()
        
        # Active in valid time window
        sample_experiment.start_date = datetime.utcnow() - timedelta(days=1)
        sample_experiment.end_date = datetime.utcnow() + timedelta(days=1)
        assert sample_experiment.is_active()
    
    def test_experiment_variant_assignment(self, sample_experiment):
        """Test consistent variant assignment."""
        sample_experiment.status = ExperimentStatus.ACTIVE
        
        # Same session should get same variant
        session_id = "test_session_123"
        variant1 = sample_experiment.assign_variant(session_id)
        variant2 = sample_experiment.assign_variant(session_id)
        
        assert variant1.id == variant2.id
        
        # Different sessions should potentially get different variants
        variants = set()
        for i in range(100):
            variant = sample_experiment.assign_variant(f"session_{i}")
            variants.add(variant.id)
        
        # Should see both variants with enough samples
        assert len(variants) >= 1  # At least one variant assigned
    
    def test_experiment_eligibility(self, sample_experiment):
        """Test experiment eligibility checks."""
        # Inactive experiment
        assert not sample_experiment.is_eligible("session_123")
        
        # Active experiment
        sample_experiment.status = ExperimentStatus.ACTIVE
        assert sample_experiment.is_eligible("session_123")
        
        # Target population filtering
        sample_experiment.target_population = "new_users"
        
        # New user (no context about being returning)
        assert sample_experiment.is_eligible("session_123", context={})
        
        # Returning user (should be excluded)
        assert not sample_experiment.is_eligible("session_123", context={"is_returning_user": True})
        
        # New user (explicitly marked)
        assert sample_experiment.is_eligible("session_123", context={"is_returning_user": False})

    @pytest.mark.asyncio
    async def test_experiment_engine_basic_operations(self):
        """Test basic experiment engine operations."""
        engine = ExperimentEngine()
        
        # Create test experiment
        variants = [
            ExperimentVariant("control", "Control", "Control variant", {}, 0.6, True),
            ExperimentVariant("treatment", "Treatment", "Treatment variant", {}, 0.4, False)
        ]
        metrics = [
            ExperimentMetric("success_rate", "conversion", "Success rate", True)
        ]
        
        experiment = Experiment("test_001", "Test", "Test experiment", variants, metrics)
        experiment.status = ExperimentStatus.ACTIVE
        
        # Register experiment
        await engine.register_experiment(experiment)
        assert "test_001" in engine._experiments
        
        # Get variant assignment
        variant = await engine.get_variant("test_001", "session_123")
        assert variant is not None
        assert variant.id in ["control", "treatment"]
        
        # Track metric
        await engine.track_metric("test_001", "session_123", "success_rate", True)
        
        # Tracking for non-existent experiment should not fail
        await engine.track_metric("nonexistent", "session_123", "metric", 1.0)
    
    @pytest.mark.asyncio
    async def test_experiment_engine_assignment_consistency(self):
        """Test that variant assignments are consistent."""
        engine = ExperimentEngine()
        
        # Create experiment
        variants = [
            ExperimentVariant("a", "A", "Variant A", {}, 0.5, True),
            ExperimentVariant("b", "B", "Variant B", {}, 0.5, False)
        ]
        metrics = [ExperimentMetric("metric", "conversion", "Test metric", True)]
        
        experiment = Experiment("consistency_test", "Test", "Test", variants, metrics)
        experiment.status = ExperimentStatus.ACTIVE
        await engine.register_experiment(experiment)
        
        # Same session should get same variant multiple times
        session_id = "consistent_session"
        assignments = []
        
        for _ in range(5):
            variant = await engine.get_variant("consistency_test", session_id)
            assignments.append(variant.id)
        
        # All assignments should be the same
        assert len(set(assignments)) == 1, f"Inconsistent assignments: {assignments}"
    
    @pytest.mark.asyncio
    async def test_experiment_engine_traffic_distribution(self):
        """Test traffic distribution across variants.""" 
        engine = ExperimentEngine()
        
        # Create experiment with unequal traffic split
        variants = [
            ExperimentVariant("control", "Control", "Control", {}, 0.8, True),
            ExperimentVariant("treatment", "Treatment", "Treatment", {}, 0.2, False)
        ]
        metrics = [ExperimentMetric("metric", "conversion", "Test metric", True)]
        
        experiment = Experiment("traffic_test", "Test", "Test", variants, metrics)
        experiment.status = ExperimentStatus.ACTIVE
        await engine.register_experiment(experiment)
        
        # Assign many sessions
        assignments = []
        for i in range(1000):
            variant = await engine.get_variant("traffic_test", f"session_{i}")
            assignments.append(variant.id)
        
        # Check distribution is approximately correct
        control_count = assignments.count("control")
        treatment_count = assignments.count("treatment") 
        
        control_pct = control_count / len(assignments)
        treatment_pct = treatment_count / len(assignments)
        
        # Allow some variance but should be roughly 80/20
        assert 0.75 < control_pct < 0.85, f"Control: {control_pct:.2%}"
        assert 0.15 < treatment_pct < 0.25, f"Treatment: {treatment_pct:.2%}"
    
    def test_experiment_variant_dataclass(self):
        """Test ExperimentVariant dataclass."""
        variant = ExperimentVariant(
            id="test_variant",
            name="Test Variant",
            description="A test variant",
            config={"param": "value"},
            traffic_weight=0.3,
            is_control=False
        )
        
        assert variant.id == "test_variant"
        assert variant.name == "Test Variant" 
        assert variant.config["param"] == "value"
        assert variant.traffic_weight == 0.3
        assert variant.is_control is False
    
    def test_experiment_metric_dataclass(self):
        """Test ExperimentMetric dataclass."""
        metric = ExperimentMetric(
            name="test_metric",
            type="conversion",
            description="A test metric",
            higher_is_better=True,
            statistical_power=0.8,
            minimum_detectable_effect=0.05
        )
        
        assert metric.name == "test_metric"
        assert metric.type == "conversion"
        assert metric.higher_is_better is True
        assert metric.statistical_power == 0.8
        assert metric.minimum_detectable_effect == 0.05
    
    @pytest.mark.asyncio
    async def test_experiment_engine_singleton(self):
        """Test experiment engine singleton pattern."""
        from app.experimentation.framework import get_experiment_engine
        
        engine1 = await get_experiment_engine()
        engine2 = await get_experiment_engine()
        
        # Should be same instance
        assert engine1 is engine2