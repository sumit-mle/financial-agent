"""
Feedback Collection System for MLOps Pipeline.

Collects and processes user feedback, performance metrics,
and quality indicators to drive automated model retraining.
"""
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum
import json
from pathlib import Path

from app.core.logging import get_logger
from app.observability.metrics import Counter, Histogram, Gauge
from app.mlops.pipeline import get_mlops_pipeline, ModelMetrics

logger = get_logger(__name__)

# Feedback metrics
feedback_received = Counter(
    "mlops_feedback_received_total",
    "Total feedback received",
    ["feedback_type", "model_type", "rating"]
)

feedback_processing_duration = Histogram(
    "mlops_feedback_processing_seconds", 
    "Time spent processing feedback"
)

model_performance_gauge = Gauge(
    "mlops_model_performance",
    "Current model performance metrics",
    ["model_type", "metric"]
)


class FeedbackType(Enum):
    """Types of feedback that can be collected."""
    USER_RATING = "user_rating"
    ESCALATION = "escalation"
    SAFETY_VIOLATION = "safety_violation"
    RESPONSE_QUALITY = "response_quality"
    CONVERSATION_OUTCOME = "conversation_outcome"
    A_B_TEST_RESULT = "ab_test_result"


class FeedbackSentiment(Enum):
    """Sentiment classification for feedback."""
    POSITIVE = "positive"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"


@dataclass
class FeedbackEntry:
    """Individual feedback entry."""
    feedback_id: str
    session_id: str
    user_id: Optional[str]
    model_type: str
    feedback_type: FeedbackType
    rating: Optional[int]  # 1-5 scale
    sentiment: Optional[FeedbackSentiment]
    escalated: bool
    safety_violation: bool
    response_time: float
    confidence_score: float
    user_message: str
    agent_response: str
    follow_up_needed: bool
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class ModelPerformanceSnapshot:
    """Snapshot of model performance over a time period."""
    model_type: str
    time_period: str
    total_interactions: int
    avg_rating: float
    escalation_rate: float
    safety_violations: int
    avg_confidence: float
    avg_response_time: float
    user_satisfaction_rate: float
    timestamp: datetime = field(default_factory=datetime.utcnow)


class FeedbackCollector:
    """
    Collects and aggregates feedback for MLOps pipeline.
    
    Features:
    - Real-time feedback collection
    - Performance metric aggregation
    - Automated quality alerts
    - Integration with retraining triggers
    """
    
    def __init__(self):
        self.feedback_buffer: List[FeedbackEntry] = []
        self.performance_snapshots: Dict[str, List[ModelPerformanceSnapshot]] = {}
        self.aggregation_window = timedelta(hours=1)  # Aggregate metrics every hour
        self.alert_thresholds = {
            "escalation_rate": 0.25,  # Alert if >25% escalations
            "safety_violations_per_hour": 5,  # Alert if >5 violations per hour
            "avg_rating_threshold": 2.5,  # Alert if avg rating <2.5
            "confidence_threshold": 0.6  # Alert if avg confidence <0.6
        }
        self._running = False
        
    async def start_collection(self):
        """Start feedback collection and processing."""
        self._running = True
        logger.info("Starting feedback collection")
        
        # Start background aggregation task
        asyncio.create_task(self._aggregation_loop())
        
    async def stop_collection(self):
        """Stop feedback collection."""
        self._running = False
        logger.info("Stopping feedback collection")
        
    async def collect_feedback(self, feedback: FeedbackEntry):
        """Collect a feedback entry."""
        self.feedback_buffer.append(feedback)
        
        # Log feedback metrics
        feedback_received.labels(
            feedback_type=feedback.feedback_type.value,
            model_type=feedback.model_type,
            rating=str(feedback.rating) if feedback.rating else "none"
        ).inc()
        
        # Check for immediate alerts
        await self._check_immediate_alerts(feedback)
        
        logger.debug(f"Collected feedback: {feedback.feedback_id} (type: {feedback.feedback_type.value})")
    
    async def collect_user_rating(self, 
                                 session_id: str,
                                 model_type: str,
                                 rating: int,
                                 user_message: str,
                                 agent_response: str,
                                 response_time: float,
                                 confidence_score: float,
                                 escalated: bool = False,
                                 metadata: Optional[Dict[str, Any]] = None):
        """Convenience method to collect user rating feedback."""
        
        sentiment = FeedbackSentiment.POSITIVE if rating >= 4 else (
            FeedbackSentiment.NEGATIVE if rating <= 2 else FeedbackSentiment.NEUTRAL
        )
        
        feedback = FeedbackEntry(
            feedback_id=f"rating_{session_id}_{int(datetime.utcnow().timestamp())}",
            session_id=session_id,
            user_id=None,  # Would be extracted from session
            model_type=model_type,
            feedback_type=FeedbackType.USER_RATING,
            rating=rating,
            sentiment=sentiment,
            escalated=escalated,
            safety_violation=False,
            response_time=response_time,
            confidence_score=confidence_score,
            user_message=user_message,
            agent_response=agent_response,
            follow_up_needed=escalated,
            metadata=metadata or {}
        )
        
        await self.collect_feedback(feedback)
    
    async def collect_escalation_feedback(self,
                                        session_id: str,
                                        model_type: str,
                                        reason: str,
                                        user_message: str,
                                        agent_response: str,
                                        response_time: float,
                                        confidence_score: float,
                                        metadata: Optional[Dict[str, Any]] = None):
        """Collect feedback when conversation is escalated."""
        
        feedback = FeedbackEntry(
            feedback_id=f"escalation_{session_id}_{int(datetime.utcnow().timestamp())}",
            session_id=session_id,
            user_id=None,
            model_type=model_type,
            feedback_type=FeedbackType.ESCALATION,
            rating=None,
            sentiment=FeedbackSentiment.NEGATIVE,  # Escalations typically indicate dissatisfaction
            escalated=True,
            safety_violation=False,
            response_time=response_time,
            confidence_score=confidence_score,
            user_message=user_message,
            agent_response=agent_response,
            follow_up_needed=True,
            metadata={**(metadata or {}), "escalation_reason": reason}
        )
        
        await self.collect_feedback(feedback)
    
    async def collect_safety_violation(self,
                                     session_id: str,
                                     model_type: str,
                                     violation_type: str,
                                     user_message: str,
                                     agent_response: str,
                                     confidence_score: float,
                                     metadata: Optional[Dict[str, Any]] = None):
        """Collect feedback for safety violations."""
        
        feedback = FeedbackEntry(
            feedback_id=f"safety_{session_id}_{int(datetime.utcnow().timestamp())}",
            session_id=session_id,
            user_id=None,
            model_type=model_type,
            feedback_type=FeedbackType.SAFETY_VIOLATION,
            rating=1,  # Safety violations are always poor
            sentiment=FeedbackSentiment.NEGATIVE,
            escalated=True,  # Safety violations should always escalate
            safety_violation=True,
            response_time=0.0,
            confidence_score=confidence_score,
            user_message=user_message,
            agent_response=agent_response,
            follow_up_needed=True,
            metadata={**(metadata or {}), "violation_type": violation_type}
        )
        
        await self.collect_feedback(feedback)
    
    async def _check_immediate_alerts(self, feedback: FeedbackEntry):
        """Check for immediate alerts that need attention."""
        alerts = []
        
        # Safety violation alert
        if feedback.safety_violation:
            alerts.append({
                "type": "safety_violation",
                "severity": "high",
                "model_type": feedback.model_type,
                "message": f"Safety violation detected in session {feedback.session_id}",
                "metadata": feedback.metadata
            })
        
        # Very low rating alert
        if feedback.rating and feedback.rating <= 1:
            alerts.append({
                "type": "very_low_rating",
                "severity": "medium", 
                "model_type": feedback.model_type,
                "message": f"Very low rating ({feedback.rating}) in session {feedback.session_id}",
                "metadata": {"rating": feedback.rating}
            })
        
        # Low confidence + escalation alert
        if feedback.escalated and feedback.confidence_score < 0.3:
            alerts.append({
                "type": "low_confidence_escalation",
                "severity": "medium",
                "model_type": feedback.model_type,
                "message": f"Low confidence escalation in session {feedback.session_id}",
                "metadata": {"confidence": feedback.confidence_score}
            })
        
        # Process alerts
        for alert in alerts:
            await self._process_alert(alert)
    
    async def _process_alert(self, alert: Dict[str, Any]):
        """Process an immediate alert."""
        logger.warning(f"MLOps Alert [{alert['severity']}]: {alert['message']}")
        
        # In production, this would:
        # 1. Send to monitoring system (PagerDuty, Slack, etc.)
        # 2. Log to alert database
        # 3. Trigger immediate investigation workflows
        
        # For high-severity alerts, consider immediate model rollback
        if alert["severity"] == "high" and alert["type"] == "safety_violation":
            await self._consider_emergency_rollback(alert["model_type"])
    
    async def _consider_emergency_rollback(self, model_type: str):
        """Consider emergency rollback for critical issues."""
        # Check recent safety violations
        recent_violations = [
            f for f in self.feedback_buffer[-100:]  # Last 100 feedback entries
            if (f.model_type == model_type and 
                f.safety_violation and 
                f.timestamp > datetime.utcnow() - timedelta(minutes=30))
        ]
        
        if len(recent_violations) >= 3:  # 3+ violations in 30 minutes
            logger.critical(f"Emergency: {len(recent_violations)} safety violations in 30 min for {model_type}")
            # In production: trigger emergency rollback to previous model version
            
    async def _aggregation_loop(self):
        """Main loop for aggregating feedback into performance metrics."""
        while self._running:
            try:
                await self._aggregate_performance_metrics()
                await asyncio.sleep(self.aggregation_window.total_seconds())
                
            except Exception as e:
                logger.error(f"Error in feedback aggregation loop: {e}")
                await asyncio.sleep(60)
    
    async def _aggregate_performance_metrics(self):
        """Aggregate recent feedback into performance snapshots."""
        with feedback_processing_duration.time():
            # Get recent feedback (last aggregation window)
            cutoff_time = datetime.utcnow() - self.aggregation_window
            recent_feedback = [
                f for f in self.feedback_buffer 
                if f.timestamp > cutoff_time
            ]
            
            if not recent_feedback:
                return
            
            # Group by model type
            by_model = {}
            for feedback in recent_feedback:
                if feedback.model_type not in by_model:
                    by_model[feedback.model_type] = []
                by_model[feedback.model_type].append(feedback)
            
            # Create performance snapshots
            for model_type, feedback_list in by_model.items():
                snapshot = await self._create_performance_snapshot(model_type, feedback_list)
                
                # Store snapshot
                if model_type not in self.performance_snapshots:
                    self.performance_snapshots[model_type] = []
                self.performance_snapshots[model_type].append(snapshot)
                
                # Update Prometheus metrics
                await self._update_performance_metrics(snapshot)
                
                # Check for alerts
                await self._check_performance_alerts(snapshot)
                
                # Send to MLOps pipeline
                await self._send_to_mlops_pipeline(snapshot)
        
        # Clean up old feedback (keep last 24 hours)
        cutoff = datetime.utcnow() - timedelta(hours=24)
        self.feedback_buffer = [f for f in self.feedback_buffer if f.timestamp > cutoff]
    
    async def _create_performance_snapshot(self, 
                                         model_type: str, 
                                         feedback_list: List[FeedbackEntry]) -> ModelPerformanceSnapshot:
        """Create performance snapshot from feedback list."""
        
        total_interactions = len(feedback_list)
        
        # Calculate metrics
        ratings = [f.rating for f in feedback_list if f.rating is not None]
        avg_rating = sum(ratings) / len(ratings) if ratings else 0.0
        
        escalations = [f for f in feedback_list if f.escalated]
        escalation_rate = len(escalations) / total_interactions if total_interactions > 0 else 0.0
        
        safety_violations = len([f for f in feedback_list if f.safety_violation])
        
        confidence_scores = [f.confidence_score for f in feedback_list if f.confidence_score is not None]
        avg_confidence = sum(confidence_scores) / len(confidence_scores) if confidence_scores else 0.0
        
        response_times = [f.response_time for f in feedback_list if f.response_time is not None]
        avg_response_time = sum(response_times) / len(response_times) if response_times else 0.0
        
        # User satisfaction (ratings 4-5 considered satisfied)
        satisfied = [f for f in feedback_list if f.rating and f.rating >= 4]
        user_satisfaction_rate = len(satisfied) / len(ratings) if ratings else 0.0
        
        return ModelPerformanceSnapshot(
            model_type=model_type,
            time_period=f"{self.aggregation_window.total_seconds()//3600}h",
            total_interactions=total_interactions,
            avg_rating=avg_rating,
            escalation_rate=escalation_rate,
            safety_violations=safety_violations,
            avg_confidence=avg_confidence,
            avg_response_time=avg_response_time,
            user_satisfaction_rate=user_satisfaction_rate
        )
    
    async def _update_performance_metrics(self, snapshot: ModelPerformanceSnapshot):
        """Update Prometheus metrics with performance data."""
        
        model_performance_gauge.labels(
            model_type=snapshot.model_type,
            metric="avg_rating"
        ).set(snapshot.avg_rating)
        
        model_performance_gauge.labels(
            model_type=snapshot.model_type,
            metric="escalation_rate"
        ).set(snapshot.escalation_rate)
        
        model_performance_gauge.labels(
            model_type=snapshot.model_type,
            metric="user_satisfaction_rate"
        ).set(snapshot.user_satisfaction_rate)
        
        model_performance_gauge.labels(
            model_type=snapshot.model_type,
            metric="avg_confidence"
        ).set(snapshot.avg_confidence)
    
    async def _check_performance_alerts(self, snapshot: ModelPerformanceSnapshot):
        """Check performance snapshot against alert thresholds."""
        alerts = []
        
        # Escalation rate alert
        if snapshot.escalation_rate > self.alert_thresholds["escalation_rate"]:
            alerts.append({
                "type": "high_escalation_rate",
                "severity": "medium",
                "model_type": snapshot.model_type,
                "message": f"High escalation rate: {snapshot.escalation_rate:.1%} (threshold: {self.alert_thresholds['escalation_rate']:.1%})",
                "metric_value": snapshot.escalation_rate
            })
        
        # Safety violations alert
        violations_per_hour = snapshot.safety_violations / (float(snapshot.time_period.rstrip('h')) or 1)
        if violations_per_hour > self.alert_thresholds["safety_violations_per_hour"]:
            alerts.append({
                "type": "high_safety_violations",
                "severity": "high",
                "model_type": snapshot.model_type,
                "message": f"High safety violations: {violations_per_hour:.1f}/hour (threshold: {self.alert_thresholds['safety_violations_per_hour']})",
                "metric_value": violations_per_hour
            })
        
        # Low rating alert
        if snapshot.avg_rating < self.alert_thresholds["avg_rating_threshold"]:
            alerts.append({
                "type": "low_average_rating",
                "severity": "medium",
                "model_type": snapshot.model_type,
                "message": f"Low average rating: {snapshot.avg_rating:.2f} (threshold: {self.alert_thresholds['avg_rating_threshold']})",
                "metric_value": snapshot.avg_rating
            })
        
        # Low confidence alert
        if snapshot.avg_confidence < self.alert_thresholds["confidence_threshold"]:
            alerts.append({
                "type": "low_confidence",
                "severity": "medium",
                "model_type": snapshot.model_type,
                "message": f"Low confidence: {snapshot.avg_confidence:.2f} (threshold: {self.alert_thresholds['confidence_threshold']})",
                "metric_value": snapshot.avg_confidence
            })
        
        # Process alerts
        for alert in alerts:
            await self._process_alert(alert)
    
    async def _send_to_mlops_pipeline(self, snapshot: ModelPerformanceSnapshot):
        """Send performance data to MLOps pipeline for retraining consideration."""
        
        # Convert snapshot to ModelMetrics format
        metrics = ModelMetrics(
            accuracy=0.85,  # Would be calculated from actual model evaluation
            precision=0.83,  # Would be calculated from actual model evaluation  
            recall=0.87,    # Would be calculated from actual model evaluation
            f1_score=0.85,  # Would be calculated from actual model evaluation
            confidence_avg=snapshot.avg_confidence,
            response_time_avg=snapshot.avg_response_time,
            user_satisfaction=snapshot.user_satisfaction_rate,
            escalation_rate=snapshot.escalation_rate,
            safety_violations=snapshot.safety_violations,
            sample_count=snapshot.total_interactions
        )
        
        # This would integrate with the MLOps pipeline's metric collection
        # For now, we'll log the data
        logger.info(f"Performance snapshot for {snapshot.model_type}: "
                   f"satisfaction={snapshot.user_satisfaction_rate:.1%}, "
                   f"escalation={snapshot.escalation_rate:.1%}, "
                   f"violations={snapshot.safety_violations}")
    
    async def get_model_performance_history(self, 
                                          model_type: str, 
                                          hours: int = 24) -> List[ModelPerformanceSnapshot]:
        """Get performance history for a model."""
        cutoff = datetime.utcnow() - timedelta(hours=hours)
        
        history = self.performance_snapshots.get(model_type, [])
        return [s for s in history if s.timestamp > cutoff]
    
    async def get_feedback_summary(self, model_type: Optional[str] = None) -> Dict[str, Any]:
        """Get summary of recent feedback."""
        recent_feedback = [
            f for f in self.feedback_buffer
            if f.timestamp > datetime.utcnow() - timedelta(hours=24)
        ]
        
        if model_type:
            recent_feedback = [f for f in recent_feedback if f.model_type == model_type]
        
        if not recent_feedback:
            return {"message": "No recent feedback"}
        
        # Calculate summary metrics
        total_feedback = len(recent_feedback)
        ratings = [f.rating for f in recent_feedback if f.rating is not None]
        avg_rating = sum(ratings) / len(ratings) if ratings else None
        
        escalations = len([f for f in recent_feedback if f.escalated])
        safety_violations = len([f for f in recent_feedback if f.safety_violation])
        
        sentiment_counts = {}
        for sentiment in FeedbackSentiment:
            sentiment_counts[sentiment.value] = len([
                f for f in recent_feedback if f.sentiment == sentiment
            ])
        
        return {
            "total_feedback": total_feedback,
            "avg_rating": avg_rating,
            "escalations": escalations,
            "escalation_rate": escalations / total_feedback if total_feedback > 0 else 0,
            "safety_violations": safety_violations,
            "sentiment_distribution": sentiment_counts,
            "model_types": list(set(f.model_type for f in recent_feedback))
        }


# Global collector instance
_collector_instance = None

async def get_feedback_collector() -> FeedbackCollector:
    """Get global feedback collector instance."""
    global _collector_instance
    if _collector_instance is None:
        _collector_instance = FeedbackCollector()
    return _collector_instance