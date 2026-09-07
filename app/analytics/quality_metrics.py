"""
Quality Metrics Engine for Financial AI Agent.

Calculates comprehensive quality metrics including accuracy, reliability,
performance, user satisfaction, and business impact metrics.
"""
import asyncio
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict
from enum import Enum
from collections import defaultdict
import statistics

from app.core.logging import get_logger
from app.core.config import settings
from app.mlops.feedback_collector import get_feedback_collector
from app.experimentation.framework import get_experiment_engine

logger = get_logger(__name__)


class MetricCategory(Enum):
    """Quality metric categories."""
    ACCURACY = "accuracy"
    PERFORMANCE = "performance"
    RELIABILITY = "reliability"
    SATISFACTION = "satisfaction"
    BUSINESS_IMPACT = "business_impact"
    SAFETY = "safety"
    EFFICIENCY = "efficiency"


class QualityTrend(Enum):
    """Quality trend directions."""
    IMPROVING = "improving"
    STABLE = "stable"
    DECLINING = "declining"
    VOLATILE = "volatile"


@dataclass
class QualityScore:
    """Individual quality score with metadata."""
    metric_name: str
    category: MetricCategory
    value: float
    max_value: float
    trend: QualityTrend
    confidence_interval: Tuple[float, float]
    sample_size: int
    last_updated: datetime
    description: str
    percentage: float = 0.0  # Will be calculated in __post_init__
    
    def __post_init__(self):
        self.percentage = (self.value / self.max_value) * 100 if self.max_value > 0 else 0.0


@dataclass
class QualityReport:
    """Comprehensive quality report."""
    overall_score: float
    category_scores: Dict[MetricCategory, float]
    individual_metrics: List[QualityScore]
    trends: Dict[str, QualityTrend]
    recommendations: List[str]
    report_period: Tuple[datetime, datetime]
    generated_at: datetime


class QualityMetricsEngine:
    """
    Advanced quality metrics calculation engine.
    
    Features:
    - Multi-dimensional quality scoring
    - Trend analysis and forecasting
    - Statistical confidence calculation
    - Automated quality recommendations
    - Integration with A/B testing results
    - Business impact correlation
    - Real-time quality monitoring
    """
    
    def __init__(self):
        self.quality_thresholds = self._initialize_quality_thresholds()
        self.metric_weights = self._initialize_metric_weights()
        self.baseline_metrics = {}
        self.historical_data = defaultdict(list)
    
    def _initialize_quality_thresholds(self) -> Dict[str, Dict[str, float]]:
        """Initialize quality thresholds for different metrics."""
        return {
            "accuracy": {"excellent": 0.95, "good": 0.85, "acceptable": 0.75, "poor": 0.60},
            "response_time": {"excellent": 1.0, "good": 2.0, "acceptable": 5.0, "poor": 10.0},
            "confidence": {"excellent": 0.90, "good": 0.80, "acceptable": 0.70, "poor": 0.60},
            "satisfaction": {"excellent": 4.5, "good": 4.0, "acceptable": 3.5, "poor": 3.0},
            "escalation_rate": {"excellent": 0.05, "good": 0.10, "acceptable": 0.15, "poor": 0.25},
            "safety_violations": {"excellent": 0.001, "good": 0.005, "acceptable": 0.01, "poor": 0.02},
            "availability": {"excellent": 0.999, "good": 0.995, "acceptable": 0.99, "poor": 0.95}
        }
    
    def _initialize_metric_weights(self) -> Dict[MetricCategory, float]:
        """Initialize weights for different metric categories."""
        return {
            MetricCategory.ACCURACY: 0.25,
            MetricCategory.PERFORMANCE: 0.20,
            MetricCategory.RELIABILITY: 0.15,
            MetricCategory.SATISFACTION: 0.20,
            MetricCategory.BUSINESS_IMPACT: 0.10,
            MetricCategory.SAFETY: 0.10
        }
    
    async def calculate_quality_report(self, 
                                     period_hours: int = 24,
                                     include_trends: bool = True) -> QualityReport:
        """Calculate comprehensive quality report for specified period."""
        
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(hours=period_hours)
        
        logger.info(f"Calculating quality report for period: {start_time} to {end_time}")
        
        # Calculate individual quality metrics
        individual_metrics = await self._calculate_individual_metrics(start_time, end_time)
        
        # Calculate category scores
        category_scores = self._calculate_category_scores(individual_metrics)
        
        # Calculate overall score
        overall_score = self._calculate_overall_score(category_scores)
        
        # Calculate trends if requested
        trends = {}
        if include_trends:
            trends = await self._calculate_trends(individual_metrics, period_hours)
        
        # Generate recommendations
        recommendations = self._generate_recommendations(individual_metrics, trends)
        
        report = QualityReport(
            overall_score=overall_score,
            category_scores=category_scores,
            individual_metrics=individual_metrics,
            trends=trends,
            recommendations=recommendations,
            report_period=(start_time, end_time),
            generated_at=datetime.utcnow()
        )
        
        logger.info(f"Quality report generated - Overall score: {overall_score:.2f}%")
        
        return report
    
    async def _calculate_individual_metrics(self, 
                                          start_time: datetime, 
                                          end_time: datetime) -> List[QualityScore]:
        """Calculate individual quality metrics."""
        
        metrics = []
        
        # Get feedback data (limited to recent 24 hours by feedback collector)
        feedback_collector = await get_feedback_collector()
        feedback_summary = await feedback_collector.get_feedback_summary()
        
        # Accuracy Metrics
        accuracy_score = await self._calculate_accuracy_score(feedback_summary)
        metrics.append(accuracy_score)
        
        # Performance Metrics
        performance_metrics = await self._calculate_performance_metrics(feedback_summary)
        metrics.extend(performance_metrics)
        
        # Reliability Metrics
        reliability_metrics = await self._calculate_reliability_metrics(feedback_summary)
        metrics.extend(reliability_metrics)
        
        # Satisfaction Metrics
        satisfaction_metrics = await self._calculate_satisfaction_metrics(feedback_summary)
        metrics.extend(satisfaction_metrics)
        
        # Business Impact Metrics
        business_metrics = await self._calculate_business_impact_metrics(feedback_summary)
        metrics.extend(business_metrics)
        
        # Safety Metrics
        safety_metrics = await self._calculate_safety_metrics(feedback_summary)
        metrics.extend(safety_metrics)
        
        return metrics
    
    async def _calculate_accuracy_score(self, feedback_summary: Dict[str, Any]) -> QualityScore:
        """Calculate overall accuracy score."""
        
        # Calculate weighted accuracy from different sources
        confidence_avg = feedback_summary.get("avg_confidence", 0.85)
        escalation_rate = feedback_summary.get("escalation_rate", 0.15)
        
        # Accuracy = confidence score adjusted for escalation rate
        accuracy = confidence_avg * (1 - escalation_rate)
        
        # Calculate trend
        trend = await self._calculate_metric_trend("accuracy", accuracy)
        
        # Calculate confidence interval
        sample_size = feedback_summary.get("total_feedback", 0)
        confidence_interval = self._calculate_confidence_interval(accuracy, sample_size)
        
        return QualityScore(
            metric_name="Overall Accuracy",
            category=MetricCategory.ACCURACY,
            value=accuracy,
            max_value=1.0,
            trend=trend,
            confidence_interval=confidence_interval,
            sample_size=sample_size,
            last_updated=datetime.utcnow(),
            description="Combined accuracy score based on confidence and escalation rate"
        )
    
    async def _calculate_performance_metrics(self, feedback_summary: Dict[str, Any]) -> List[QualityScore]:
        """Calculate performance-related metrics."""
        
        metrics = []
        
        # Response Time
        avg_response_time = feedback_summary.get("avg_response_time", 2.5)
        response_time_trend = await self._calculate_metric_trend("response_time", avg_response_time)
        
        # Normalize response time (lower is better)
        response_time_score = max(0, min(1, (10 - avg_response_time) / 10))
        
        metrics.append(QualityScore(
            metric_name="Response Time",
            category=MetricCategory.PERFORMANCE,
            value=response_time_score,
            max_value=1.0,
            trend=response_time_trend,
            confidence_interval=self._calculate_confidence_interval(response_time_score, 
                                                                   feedback_summary.get("total_feedback", 0)),
            sample_size=feedback_summary.get("total_feedback", 0),
            last_updated=datetime.utcnow(),
            description=f"Response time performance (avg: {avg_response_time:.2f}s)"
        ))
        
        # Throughput (requests handled successfully)
        success_rate = 1 - feedback_summary.get("error_rate", 0.05)
        throughput_trend = await self._calculate_metric_trend("throughput", success_rate)
        
        metrics.append(QualityScore(
            metric_name="Throughput",
            category=MetricCategory.PERFORMANCE,
            value=success_rate,
            max_value=1.0,
            trend=throughput_trend,
            confidence_interval=self._calculate_confidence_interval(success_rate, 
                                                                   feedback_summary.get("total_feedback", 0)),
            sample_size=feedback_summary.get("total_feedback", 0),
            last_updated=datetime.utcnow(),
            description=f"Successful request processing rate ({success_rate:.1%})"
        ))
        
        return metrics
    
    async def _calculate_reliability_metrics(self, feedback_summary: Dict[str, Any]) -> List[QualityScore]:
        """Calculate reliability metrics."""
        
        metrics = []
        
        # System Availability
        error_rate = feedback_summary.get("error_rate", 0.05)
        availability = 1 - error_rate
        availability_trend = await self._calculate_metric_trend("availability", availability)
        
        metrics.append(QualityScore(
            metric_name="System Availability",
            category=MetricCategory.RELIABILITY,
            value=availability,
            max_value=1.0,
            trend=availability_trend,
            confidence_interval=self._calculate_confidence_interval(availability, 
                                                                   feedback_summary.get("total_feedback", 0)),
            sample_size=feedback_summary.get("total_feedback", 0),
            last_updated=datetime.utcnow(),
            description=f"System uptime and availability ({availability:.1%})"
        ))
        
        # Consistency Score
        confidence_std = feedback_summary.get("confidence_std", 0.15)
        consistency = max(0, 1 - confidence_std)  # Lower std = higher consistency
        consistency_trend = await self._calculate_metric_trend("consistency", consistency)
        
        metrics.append(QualityScore(
            metric_name="Response Consistency",
            category=MetricCategory.RELIABILITY,
            value=consistency,
            max_value=1.0,
            trend=consistency_trend,
            confidence_interval=self._calculate_confidence_interval(consistency, 
                                                                   feedback_summary.get("total_feedback", 0)),
            sample_size=feedback_summary.get("total_feedback", 0),
            last_updated=datetime.utcnow(),
            description=f"Consistency of response quality (std: {confidence_std:.3f})"
        ))
        
        return metrics
    
    async def _calculate_satisfaction_metrics(self, feedback_summary: Dict[str, Any]) -> List[QualityScore]:
        """Calculate user satisfaction metrics."""
        
        metrics = []
        
        # User Rating
        avg_rating = feedback_summary.get("avg_rating", 3.5)
        rating_trend = await self._calculate_metric_trend("user_rating", avg_rating)
        
        # Normalize rating to 0-1 scale (assuming 1-5 rating scale)
        normalized_rating = (avg_rating - 1) / 4
        
        metrics.append(QualityScore(
            metric_name="User Satisfaction",
            category=MetricCategory.SATISFACTION,
            value=normalized_rating,
            max_value=1.0,
            trend=rating_trend,
            confidence_interval=self._calculate_confidence_interval(normalized_rating, 
                                                                   feedback_summary.get("total_feedback", 0)),
            sample_size=feedback_summary.get("total_feedback", 0),
            last_updated=datetime.utcnow(),
            description=f"Average user rating ({avg_rating:.2f}/5.0)"
        ))
        
        # Resolution Rate
        escalation_rate = feedback_summary.get("escalation_rate", 0.15)
        resolution_rate = 1 - escalation_rate
        resolution_trend = await self._calculate_metric_trend("resolution_rate", resolution_rate)
        
        metrics.append(QualityScore(
            metric_name="First Contact Resolution",
            category=MetricCategory.SATISFACTION,
            value=resolution_rate,
            max_value=1.0,
            trend=resolution_trend,
            confidence_interval=self._calculate_confidence_interval(resolution_rate, 
                                                                   feedback_summary.get("total_feedback", 0)),
            sample_size=feedback_summary.get("total_feedback", 0),
            last_updated=datetime.utcnow(),
            description=f"Issues resolved without escalation ({resolution_rate:.1%})"
        ))
        
        return metrics
    
    async def _calculate_business_impact_metrics(self, feedback_summary: Dict[str, Any]) -> List[QualityScore]:
        """Calculate business impact metrics."""
        
        metrics = []
        
        # Cost Efficiency (based on automation rate)
        escalation_rate = feedback_summary.get("escalation_rate", 0.15)
        automation_rate = 1 - escalation_rate
        
        # Assume cost savings are proportional to automation
        cost_efficiency = automation_rate * 0.85  # Cap at 85% efficiency
        efficiency_trend = await self._calculate_metric_trend("cost_efficiency", cost_efficiency)
        
        metrics.append(QualityScore(
            metric_name="Cost Efficiency",
            category=MetricCategory.BUSINESS_IMPACT,
            value=cost_efficiency,
            max_value=1.0,
            trend=efficiency_trend,
            confidence_interval=self._calculate_confidence_interval(cost_efficiency, 
                                                                   feedback_summary.get("total_feedback", 0)),
            sample_size=feedback_summary.get("total_feedback", 0),
            last_updated=datetime.utcnow(),
            description=f"Cost savings through automation ({automation_rate:.1%} automated)"
        ))
        
        # Customer Retention Proxy
        avg_rating = feedback_summary.get("avg_rating", 3.5)
        retention_proxy = min(1.0, max(0, (avg_rating - 2) / 3))  # Scale 2-5 rating to 0-1
        retention_trend = await self._calculate_metric_trend("retention_proxy", retention_proxy)
        
        metrics.append(QualityScore(
            metric_name="Customer Retention Indicator",
            category=MetricCategory.BUSINESS_IMPACT,
            value=retention_proxy,
            max_value=1.0,
            trend=retention_trend,
            confidence_interval=self._calculate_confidence_interval(retention_proxy, 
                                                                   feedback_summary.get("total_feedback", 0)),
            sample_size=feedback_summary.get("total_feedback", 0),
            last_updated=datetime.utcnow(),
            description="Proxy metric for customer retention based on satisfaction"
        ))
        
        return metrics
    
    async def _calculate_safety_metrics(self, feedback_summary: Dict[str, Any]) -> List[QualityScore]:
        """Calculate safety and compliance metrics."""
        
        metrics = []
        
        # Safety Violations Rate
        safety_violations = feedback_summary.get("safety_violations", 0)
        total_interactions = max(1, feedback_summary.get("total_feedback", 1))
        safety_rate = 1 - (safety_violations / total_interactions)
        
        safety_trend = await self._calculate_metric_trend("safety_rate", safety_rate)
        
        metrics.append(QualityScore(
            metric_name="Safety Compliance",
            category=MetricCategory.SAFETY,
            value=safety_rate,
            max_value=1.0,
            trend=safety_trend,
            confidence_interval=self._calculate_confidence_interval(safety_rate, total_interactions),
            sample_size=total_interactions,
            last_updated=datetime.utcnow(),
            description=f"Safety compliance rate ({safety_violations} violations in {total_interactions} interactions)"
        ))
        
        # PII Protection Rate (assume high compliance)
        pii_protection_rate = 0.995  # Placeholder - would integrate with PII detection metrics
        pii_trend = await self._calculate_metric_trend("pii_protection", pii_protection_rate)
        
        metrics.append(QualityScore(
            metric_name="PII Protection",
            category=MetricCategory.SAFETY,
            value=pii_protection_rate,
            max_value=1.0,
            trend=pii_trend,
            confidence_interval=(0.990, 0.999),
            sample_size=total_interactions,
            last_updated=datetime.utcnow(),
            description="Personal information protection compliance"
        ))
        
        return metrics
    
    def _calculate_category_scores(self, metrics: List[QualityScore]) -> Dict[MetricCategory, float]:
        """Calculate average scores for each category."""
        
        category_scores = {}
        
        for category in MetricCategory:
            category_metrics = [m for m in metrics if m.category == category]
            if category_metrics:
                avg_score = statistics.mean([m.percentage for m in category_metrics])
                category_scores[category] = avg_score
            else:
                category_scores[category] = 0.0
        
        return category_scores
    
    def _calculate_overall_score(self, category_scores: Dict[MetricCategory, float]) -> float:
        """Calculate weighted overall quality score."""
        
        overall_score = 0.0
        total_weight = 0.0
        
        for category, score in category_scores.items():
            weight = self.metric_weights.get(category, 0.0)
            overall_score += score * weight
            total_weight += weight
        
        return overall_score / total_weight if total_weight > 0 else 0.0
    
    async def _calculate_metric_trend(self, metric_name: str, current_value: float) -> QualityTrend:
        """Calculate trend for a specific metric."""
        
        # Store current value in historical data
        self.historical_data[metric_name].append({
            "timestamp": datetime.utcnow(),
            "value": current_value
        })
        
        # Keep only last 10 data points
        if len(self.historical_data[metric_name]) > 10:
            self.historical_data[metric_name] = self.historical_data[metric_name][-10:]
        
        history = self.historical_data[metric_name]
        
        if len(history) < 3:
            return QualityTrend.STABLE
        
        # Calculate trend using linear regression
        values = [point["value"] for point in history[-5:]]  # Last 5 points
        
        if len(values) < 2:
            return QualityTrend.STABLE
        
        # Simple trend calculation
        recent_avg = statistics.mean(values[-3:])
        older_avg = statistics.mean(values[:-3]) if len(values) > 3 else values[0]
        
        change_percent = ((recent_avg - older_avg) / older_avg) if older_avg != 0 else 0
        
        # Calculate volatility
        volatility = statistics.stdev(values) if len(values) > 1 else 0
        avg_value = statistics.mean(values)
        cv = volatility / avg_value if avg_value != 0 else 0  # Coefficient of variation
        
        # Determine trend
        if cv > 0.15:  # High volatility
            return QualityTrend.VOLATILE
        elif change_percent > 0.05:  # Improving by more than 5%
            return QualityTrend.IMPROVING
        elif change_percent < -0.05:  # Declining by more than 5%
            return QualityTrend.DECLINING
        else:
            return QualityTrend.STABLE
    
    def _calculate_confidence_interval(self, value: float, sample_size: int, confidence_level: float = 0.95) -> Tuple[float, float]:
        """Calculate confidence interval for a metric value."""
        
        if sample_size == 0:
            return (value, value)
        
        # Use normal approximation for confidence interval
        z_score = 1.96  # 95% confidence level
        
        # Assume binomial distribution for proportions
        if 0 <= value <= 1:
            std_error = np.sqrt(value * (1 - value) / sample_size) if sample_size > 0 else 0
            margin_error = z_score * std_error
            
            lower = max(0, value - margin_error)
            upper = min(1, value + margin_error)
            
            return (lower, upper)
        
        # For other metrics, use a simplified approach
        margin_error = z_score * (value / np.sqrt(sample_size)) if sample_size > 0 else 0
        return (max(0, value - margin_error), value + margin_error)
    
    async def _calculate_trends(self, metrics: List[QualityScore], period_hours: int) -> Dict[str, QualityTrend]:
        """Calculate trends for all metrics."""
        
        trends = {}
        
        for metric in metrics:
            trends[metric.metric_name] = metric.trend
        
        return trends
    
    def _generate_recommendations(self, 
                                metrics: List[QualityScore], 
                                trends: Dict[str, QualityTrend]) -> List[str]:
        """Generate quality improvement recommendations."""
        
        recommendations = []
        
        # Analyze each metric for recommendations
        for metric in metrics:
            if metric.percentage < 70:  # Poor performance
                recommendations.append(
                    f"🔴 CRITICAL: {metric.metric_name} is below acceptable threshold "
                    f"({metric.percentage:.1f}%). Immediate action required."
                )
            elif metric.percentage < 85:  # Needs improvement
                recommendations.append(
                    f"🟡 ATTENTION: {metric.metric_name} needs improvement "
                    f"({metric.percentage:.1f}%). Consider optimization strategies."
                )
            
            # Trend-based recommendations
            if trends.get(metric.metric_name) == QualityTrend.DECLINING:
                recommendations.append(
                    f"📉 TREND ALERT: {metric.metric_name} is declining. "
                    f"Investigate root causes and implement corrective measures."
                )
            elif trends.get(metric.metric_name) == QualityTrend.VOLATILE:
                recommendations.append(
                    f"⚡ STABILITY: {metric.metric_name} shows high volatility. "
                    f"Focus on consistency improvements."
                )
        
        # Category-specific recommendations
        accuracy_metrics = [m for m in metrics if m.category == MetricCategory.ACCURACY]
        if accuracy_metrics:
            avg_accuracy = statistics.mean([m.percentage for m in accuracy_metrics])
            if avg_accuracy < 80:
                recommendations.append(
                    "🎯 ACCURACY: Consider model retraining, prompt optimization, "
                    "or additional training data to improve accuracy."
                )
        
        performance_metrics = [m for m in metrics if m.category == MetricCategory.PERFORMANCE]
        if performance_metrics:
            avg_performance = statistics.mean([m.percentage for m in performance_metrics])
            if avg_performance < 75:
                recommendations.append(
                    "⚡ PERFORMANCE: Optimize response times through caching, "
                    "model optimization, or infrastructure scaling."
                )
        
        safety_metrics = [m for m in metrics if m.category == MetricCategory.SAFETY]
        if safety_metrics:
            avg_safety = statistics.mean([m.percentage for m in safety_metrics])
            if avg_safety < 95:
                recommendations.append(
                    "🛡️ SAFETY: Strengthen safety measures, enhance content filtering, "
                    "and review compliance procedures."
                )
        
        # If no specific issues, provide general optimization suggestions
        if not recommendations:
            recommendations.extend([
                "✅ EXCELLENT: All metrics are performing well. Continue monitoring.",
                "📊 OPTIMIZATION: Consider A/B testing new prompts or model configurations.",
                "🔄 MAINTENANCE: Regular model retraining and performance reviews recommended."
            ])
        
        return recommendations
    
    async def get_quality_summary(self) -> Dict[str, Any]:
        """Get quick quality summary for dashboards."""
        
        report = await self.calculate_quality_report(period_hours=1)
        
        return {
            "overall_score": report.overall_score,
            "grade": self._score_to_grade(report.overall_score),
            "category_scores": {cat.value: score for cat, score in report.category_scores.items()},
            "trending_down": [
                metric.metric_name for metric in report.individual_metrics 
                if metric.trend == QualityTrend.DECLINING
            ],
            "critical_issues": [
                metric.metric_name for metric in report.individual_metrics 
                if metric.percentage < 70
            ],
            "last_updated": report.generated_at.isoformat()
        }
    
    def _score_to_grade(self, score: float) -> str:
        """Convert quality score to letter grade."""
        if score >= 95:
            return "A+"
        elif score >= 90:
            return "A"
        elif score >= 85:
            return "B+"
        elif score >= 80:
            return "B"
        elif score >= 75:
            return "C+"
        elif score >= 70:
            return "C"
        elif score >= 65:
            return "D"
        else:
            return "F"
    
    async def export_quality_data(self, 
                                 format: str = "json",
                                 period_days: int = 7) -> Dict[str, Any]:
        """Export quality data for external analysis."""
        
        report = await self.calculate_quality_report(period_hours=period_days * 24)
        
        if format == "json":
            return {
                "report": asdict(report),
                "historical_data": dict(self.historical_data),
                "thresholds": self.quality_thresholds,
                "weights": {k.value: v for k, v in self.metric_weights.items()}
            }
        
        # Could add other formats (CSV, PDF) in the future
        return asdict(report)


# Global quality metrics engine instance
_quality_engine_instance = None

async def get_quality_metrics_engine() -> QualityMetricsEngine:
    """Get global quality metrics engine instance."""
    global _quality_engine_instance
    if _quality_engine_instance is None:
        _quality_engine_instance = QualityMetricsEngine()
    return _quality_engine_instance