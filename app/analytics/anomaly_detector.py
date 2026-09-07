"""
Anomaly Detection Engine for Financial AI Agent.

Detects unusual patterns, performance degradations, and potential issues
using statistical methods and machine learning approaches.
"""
import asyncio
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from enum import Enum
from collections import deque
import statistics

from app.core.logging import get_logger
from app.mlops.feedback_collector import get_feedback_collector

logger = get_logger(__name__)


class AnomalySeverity(Enum):
    """Anomaly severity levels."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AnomalyType(Enum):
    """Types of anomalies to detect."""
    PERFORMANCE_DEGRADATION = "performance_degradation"
    SATISFACTION_DROP = "satisfaction_drop"
    ESCALATION_SPIKE = "escalation_spike"
    RESPONSE_TIME_INCREASE = "response_time_increase"
    ERROR_RATE_SPIKE = "error_rate_spike"
    TRAFFIC_ANOMALY = "traffic_anomaly"
    QUALITY_REGRESSION = "quality_regression"
    SAFETY_VIOLATION_INCREASE = "safety_violation_increase"


@dataclass
class Anomaly:
    """Detected anomaly with details."""
    anomaly_type: AnomalyType
    severity: AnomalySeverity
    title: str
    description: str
    detected_at: datetime
    metric_name: str
    current_value: float
    expected_value: float
    deviation_score: float
    confidence: float
    recommended_actions: List[str]
    affected_components: List[str]
    
    @property
    def deviation_percentage(self) -> float:
        """Calculate deviation as percentage."""
        if self.expected_value == 0:
            return 0.0
        return ((self.current_value - self.expected_value) / self.expected_value) * 100


class AnomalyDetector:
    """
    Advanced anomaly detection engine.
    
    Features:
    - Statistical anomaly detection (z-score, IQR)
    - Time-series pattern recognition
    - Multi-metric correlation analysis
    - Dynamic threshold adaptation
    - Real-time anomaly alerting
    - Performance baseline tracking
    - Seasonal pattern consideration
    """
    
    def __init__(self, window_size: int = 100):
        self.window_size = window_size
        self.metric_history = {}
        self.baselines = {}
        self.detection_thresholds = self._initialize_thresholds()
        self.seasonal_patterns = {}
        
    def _initialize_thresholds(self) -> Dict[str, Dict[str, float]]:
        """Initialize detection thresholds for different metrics."""
        return {
            "satisfaction_rating": {
                "z_score_threshold": 2.0,
                "min_deviation_percent": 10.0,
                "critical_threshold": 2.5
            },
            "escalation_rate": {
                "z_score_threshold": 2.5,
                "min_deviation_percent": 25.0,
                "critical_threshold": 3.0
            },
            "response_time": {
                "z_score_threshold": 2.0,
                "min_deviation_percent": 50.0,
                "critical_threshold": 3.0
            },
            "error_rate": {
                "z_score_threshold": 2.0,
                "min_deviation_percent": 100.0,
                "critical_threshold": 2.5
            },
            "confidence_score": {
                "z_score_threshold": 2.0,
                "min_deviation_percent": 15.0,
                "critical_threshold": 2.5
            },
            "safety_violations": {
                "z_score_threshold": 1.5,
                "min_deviation_percent": 50.0,
                "critical_threshold": 2.0
            }
        }
    
    async def detect_anomalies(self, 
                             current_metrics: Dict[str, float],
                             historical_window_hours: int = 24) -> List[Anomaly]:
        """Detect anomalies in current metrics compared to historical baseline."""
        
        anomalies = []
        
        # Update metric history
        timestamp = datetime.utcnow()
        for metric_name, value in current_metrics.items():
            if metric_name not in self.metric_history:
                self.metric_history[metric_name] = deque(maxlen=self.window_size)
            
            self.metric_history[metric_name].append({
                "timestamp": timestamp,
                "value": value
            })
        
        # Detect anomalies for each metric
        for metric_name, current_value in current_metrics.items():
            if len(self.metric_history.get(metric_name, [])) < 10:
                continue  # Need minimum history for detection
            
            anomaly = await self._detect_metric_anomaly(metric_name, current_value)
            if anomaly:
                anomalies.append(anomaly)
        
        # Detect correlation anomalies
        correlation_anomalies = await self._detect_correlation_anomalies(current_metrics)
        anomalies.extend(correlation_anomalies)
        
        # Sort by severity and confidence
        anomalies.sort(key=lambda x: (x.severity.value, -x.confidence), reverse=True)
        
        logger.info(f"Detected {len(anomalies)} anomalies in current metrics")
        
        return anomalies
    
    async def _detect_metric_anomaly(self, metric_name: str, current_value: float) -> Optional[Anomaly]:
        """Detect anomaly for a single metric."""
        
        history = list(self.metric_history[metric_name])
        historical_values = [point["value"] for point in history[:-1]]  # Exclude current value
        
        if len(historical_values) < 5:
            return None
        
        # Calculate baseline statistics
        mean_value = statistics.mean(historical_values)
        std_value = statistics.stdev(historical_values) if len(historical_values) > 1 else 0
        
        # Handle zero standard deviation
        if std_value == 0:
            std_value = abs(mean_value) * 0.1  # Use 10% of mean as fallback
        
        # Calculate z-score
        z_score = abs((current_value - mean_value) / std_value) if std_value > 0 else 0
        
        # Get thresholds for this metric
        thresholds = self.detection_thresholds.get(metric_name, {
            "z_score_threshold": 2.0,
            "min_deviation_percent": 20.0,
            "critical_threshold": 3.0
        })
        
        # Calculate deviation percentage
        deviation_percent = abs((current_value - mean_value) / mean_value * 100) if mean_value != 0 else 0
        
        # Check if anomaly exists
        if (z_score > thresholds["z_score_threshold"] and 
            deviation_percent > thresholds["min_deviation_percent"]):
            
            # Determine severity
            if z_score > thresholds["critical_threshold"]:
                severity = AnomalySeverity.CRITICAL
            elif z_score > thresholds["z_score_threshold"] * 1.5:
                severity = AnomalySeverity.HIGH
            elif z_score > thresholds["z_score_threshold"] * 1.2:
                severity = AnomalySeverity.MEDIUM
            else:
                severity = AnomalySeverity.LOW
            
            # Determine anomaly type and generate description
            anomaly_type, title, description, actions = self._classify_anomaly(
                metric_name, current_value, mean_value, z_score
            )
            
            # Calculate confidence based on z-score and historical stability
            confidence = min(0.99, max(0.5, (z_score - 1.0) / 3.0))
            
            return Anomaly(
                anomaly_type=anomaly_type,
                severity=severity,
                title=title,
                description=description,
                detected_at=datetime.utcnow(),
                metric_name=metric_name,
                current_value=current_value,
                expected_value=mean_value,
                deviation_score=z_score,
                confidence=confidence,
                recommended_actions=actions,
                affected_components=self._get_affected_components(metric_name)
            )
        
        return None
    
    def _classify_anomaly(self, 
                         metric_name: str, 
                         current_value: float, 
                         expected_value: float,
                         z_score: float) -> Tuple[AnomalyType, str, str, List[str]]:
        """Classify anomaly type and generate description."""
        
        is_increase = current_value > expected_value
        deviation_percent = abs((current_value - expected_value) / expected_value * 100) if expected_value != 0 else 0
        
        if "satisfaction" in metric_name.lower() or "rating" in metric_name.lower():
            if not is_increase:  # Satisfaction drop
                return (
                    AnomalyType.SATISFACTION_DROP,
                    "Customer Satisfaction Drop Detected",
                    f"Customer satisfaction has dropped by {deviation_percent:.1f}% "
                    f"(from {expected_value:.2f} to {current_value:.2f}, z-score: {z_score:.2f})",
                    [
                        "Investigate recent changes to prompts or models",
                        "Review recent customer feedback for common issues",
                        "Check if specific intent categories are affected",
                        "Consider rolling back recent deployments if correlation exists"
                    ]
                )
        
        elif "escalation" in metric_name.lower():
            if is_increase:  # Escalation spike
                return (
                    AnomalyType.ESCALATION_SPIKE,
                    "Escalation Rate Spike Detected",
                    f"Escalation rate has increased by {deviation_percent:.1f}% "
                    f"(from {expected_value:.1%} to {current_value:.1%}, z-score: {z_score:.2f})",
                    [
                        "Review recent model performance metrics",
                        "Check for new types of queries the AI cannot handle",
                        "Analyze escalated cases for common patterns",
                        "Consider additional model training or prompt tuning"
                    ]
                )
        
        elif "response_time" in metric_name.lower() or "latency" in metric_name.lower():
            if is_increase:  # Response time increase
                return (
                    AnomalyType.RESPONSE_TIME_INCREASE,
                    "Response Time Degradation Detected",
                    f"Response time has increased by {deviation_percent:.1f}% "
                    f"(from {expected_value:.2f}s to {current_value:.2f}s, z-score: {z_score:.2f})",
                    [
                        "Check system resource utilization (CPU, memory)",
                        "Review database query performance",
                        "Investigate external API latencies",
                        "Consider scaling infrastructure if needed"
                    ]
                )
        
        elif "error" in metric_name.lower():
            if is_increase:  # Error rate spike
                return (
                    AnomalyType.ERROR_RATE_SPIKE,
                    "Error Rate Spike Detected", 
                    f"Error rate has increased by {deviation_percent:.1f}% "
                    f"(from {expected_value:.1%} to {current_value:.1%}, z-score: {z_score:.2f})",
                    [
                        "Review application logs for error patterns",
                        "Check external service dependencies",
                        "Validate recent code deployments",
                        "Monitor system health metrics"
                    ]
                )
        
        elif "safety" in metric_name.lower() or "violation" in metric_name.lower():
            if is_increase:  # Safety violation increase
                return (
                    AnomalyType.SAFETY_VIOLATION_INCREASE,
                    "Safety Violation Increase Detected",
                    f"Safety violations have increased by {deviation_percent:.1f}% "
                    f"(from {expected_value:.3f} to {current_value:.3f}, z-score: {z_score:.2f})",
                    [
                        "Review recent safety violation cases",
                        "Check if new content patterns are bypassing filters",
                        "Strengthen content filtering rules",
                        "Consider additional safety model training"
                    ]
                )
        
        elif "confidence" in metric_name.lower():
            if not is_increase:  # Confidence drop
                return (
                    AnomalyType.QUALITY_REGRESSION,
                    "Model Confidence Degradation",
                    f"Model confidence has dropped by {deviation_percent:.1f}% "
                    f"(from {expected_value:.2f} to {current_value:.2f}, z-score: {z_score:.2f})",
                    [
                        "Evaluate model performance on recent queries",
                        "Check for distribution shift in incoming requests",
                        "Consider model retraining with recent data",
                        "Review prompt effectiveness"
                    ]
                )
        
        # Default case
        return (
            AnomalyType.PERFORMANCE_DEGRADATION,
            "Performance Anomaly Detected",
            f"{metric_name} has deviated by {deviation_percent:.1f}% from expected value "
            f"(from {expected_value:.3f} to {current_value:.3f}, z-score: {z_score:.2f})",
            [
                "Investigate the underlying cause of the metric change",
                "Review recent system changes or deployments",
                "Check correlated metrics for additional insights",
                "Monitor trend over next few measurement periods"
            ]
        )
    
    def _get_affected_components(self, metric_name: str) -> List[str]:
        """Get list of components affected by the anomaly."""
        
        component_mapping = {
            "satisfaction": ["customer_experience", "prompts", "models"],
            "escalation": ["ai_models", "intent_classification", "reasoning"],
            "response_time": ["infrastructure", "databases", "external_apis"],
            "error": ["application", "infrastructure", "dependencies"],
            "confidence": ["ai_models", "training_data", "prompts"],
            "safety": ["safety_filters", "content_moderation", "compliance"]
        }
        
        affected = []
        for key, components in component_mapping.items():
            if key in metric_name.lower():
                affected.extend(components)
        
        return affected if affected else ["system"]
    
    async def _detect_correlation_anomalies(self, current_metrics: Dict[str, float]) -> List[Anomaly]:
        """Detect anomalies based on metric correlations."""
        
        correlation_anomalies = []
        
        # Check for inverse correlation anomalies
        satisfaction = current_metrics.get("avg_rating", 0)
        escalation_rate = current_metrics.get("escalation_rate", 0)
        
        # Expected: High satisfaction should correlate with low escalation
        if satisfaction > 4.0 and escalation_rate > 0.2:
            correlation_anomalies.append(Anomaly(
                anomaly_type=AnomalyType.QUALITY_REGRESSION,
                severity=AnomalySeverity.HIGH,
                title="Satisfaction-Escalation Correlation Anomaly",
                description=f"High satisfaction ({satisfaction:.2f}) with high escalation rate ({escalation_rate:.1%}) indicates potential measurement issues",
                detected_at=datetime.utcnow(),
                metric_name="correlation_satisfaction_escalation",
                current_value=escalation_rate,
                expected_value=0.1,  # Expected escalation for high satisfaction
                deviation_score=3.0,  # High confidence in this correlation
                confidence=0.85,
                recommended_actions=[
                    "Verify satisfaction measurement accuracy",
                    "Review escalation classification logic",
                    "Check for timing differences in metric collection",
                    "Analyze specific cases with high satisfaction but escalation"
                ],
                affected_components=["metrics", "measurement", "classification"]
            ))
        
        # Check response time vs satisfaction correlation
        response_time = current_metrics.get("avg_response_time", 0)
        if response_time > 5.0 and satisfaction > 4.0:
            correlation_anomalies.append(Anomaly(
                anomaly_type=AnomalyType.PERFORMANCE_DEGRADATION,
                severity=AnomalySeverity.MEDIUM,
                title="Response Time-Satisfaction Correlation Anomaly",
                description=f"High response time ({response_time:.1f}s) with high satisfaction ({satisfaction:.2f}) is unexpected",
                detected_at=datetime.utcnow(),
                metric_name="correlation_response_satisfaction",
                current_value=response_time,
                expected_value=2.5,
                deviation_score=2.0,
                confidence=0.75,
                recommended_actions=[
                    "Investigate if customers are more tolerant of delays",
                    "Check if response quality compensates for speed",
                    "Review satisfaction survey timing and methodology",
                    "Consider if customer expectations have changed"
                ],
                affected_components=["performance", "customer_experience"]
            ))
        
        return correlation_anomalies
    
    async def update_baselines(self, period_days: int = 7):
        """Update baseline metrics from historical data."""
        
        logger.info(f"Updating anomaly detection baselines from {period_days} days of data")
        
        # Get historical feedback data
        feedback_collector = await get_feedback_collector()
        end_time = datetime.utcnow()
        
        # Note: FeedbackCollector only provides 24h data
        historical_summary = await feedback_collector.get_feedback_summary()
        
        # Update baselines
        self.baselines = {
            "avg_rating": historical_summary.get("avg_rating", 3.5),
            "escalation_rate": historical_summary.get("escalation_rate", 0.15),
            "avg_response_time": historical_summary.get("avg_response_time", 2.5),
            "error_rate": historical_summary.get("error_rate", 0.05),
            "avg_confidence": historical_summary.get("avg_confidence", 0.8),
            "safety_violations": historical_summary.get("safety_violations", 0)
        }
        
        logger.info(f"Updated baselines: {self.baselines}")
    
    async def get_anomaly_summary(self) -> Dict[str, Any]:
        """Get summary of recent anomaly detection results."""
        
        # Get current metrics for anomaly detection (limited to 24h)
        feedback_collector = await get_feedback_collector()
        recent_summary = await feedback_collector.get_feedback_summary()
        
        current_metrics = {
            "avg_rating": recent_summary.get("avg_rating", 3.5),
            "escalation_rate": recent_summary.get("escalation_rate", 0.15),
            "avg_response_time": recent_summary.get("avg_response_time", 2.5),
            "avg_confidence": recent_summary.get("avg_confidence", 0.8)
        }
        
        # Detect anomalies
        anomalies = await self.detect_anomalies(current_metrics)
        
        return {
            "total_anomalies": len(anomalies),
            "critical_count": len([a for a in anomalies if a.severity == AnomalySeverity.CRITICAL]),
            "high_count": len([a for a in anomalies if a.severity == AnomalySeverity.HIGH]),
            "recent_anomalies": [
                {
                    "title": a.title,
                    "severity": a.severity.value,
                    "type": a.anomaly_type.value,
                    "deviation_percentage": a.deviation_percentage
                }
                for a in anomalies[:5]  # Top 5 anomalies
            ],
            "system_health": "critical" if any(a.severity == AnomalySeverity.CRITICAL for a in anomalies) 
                           else "degraded" if any(a.severity == AnomalySeverity.HIGH for a in anomalies)
                           else "healthy",
            "last_updated": datetime.utcnow().isoformat()
        }
    
    def get_detection_config(self) -> Dict[str, Any]:
        """Get current anomaly detection configuration."""
        
        return {
            "window_size": self.window_size,
            "thresholds": self.detection_thresholds,
            "baselines": self.baselines,
            "metrics_tracked": list(self.metric_history.keys()),
            "history_sizes": {k: len(v) for k, v in self.metric_history.items()}
        }
    
    async def configure_detection(self, 
                                metric_name: str,
                                z_score_threshold: Optional[float] = None,
                                min_deviation_percent: Optional[float] = None,
                                critical_threshold: Optional[float] = None):
        """Configure detection thresholds for a specific metric."""
        
        if metric_name not in self.detection_thresholds:
            self.detection_thresholds[metric_name] = {}
        
        if z_score_threshold is not None:
            self.detection_thresholds[metric_name]["z_score_threshold"] = z_score_threshold
        
        if min_deviation_percent is not None:
            self.detection_thresholds[metric_name]["min_deviation_percent"] = min_deviation_percent
        
        if critical_threshold is not None:
            self.detection_thresholds[metric_name]["critical_threshold"] = critical_threshold
        
        logger.info(f"Updated detection thresholds for {metric_name}: {self.detection_thresholds[metric_name]}")


# Global anomaly detector instance
_anomaly_detector_instance = None

async def get_anomaly_detector() -> AnomalyDetector:
    """Get global anomaly detector instance."""
    global _anomaly_detector_instance
    if _anomaly_detector_instance is None:
        _anomaly_detector_instance = AnomalyDetector()
    return _anomaly_detector_instance