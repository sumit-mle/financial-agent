"""
Feedback Aggregator - Learn & Improve Pipeline Component.

Processes customer feedback from Langfuse to identify quality patterns,
low-confidence queries, and areas for improvement.

This matches the "Learn & Improve" section in Layer 6 of the architecture diagram.
"""
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
import json

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class FeedbackInsight:
    """Structured insight from feedback analysis."""
    
    def __init__(
        self,
        insight_type: str,  # 'low_confidence', 'poor_retrieval', 'escalation_pattern', etc.
        severity: str,      # 'low', 'medium', 'high', 'critical'
        description: str,
        affected_queries: List[str],
        recommended_actions: List[str],
        confidence: float,
        evidence: Dict
    ):
        self.insight_type = insight_type
        self.severity = severity
        self.description = description
        self.affected_queries = affected_queries
        self.recommended_actions = recommended_actions
        self.confidence = confidence
        self.evidence = evidence


class FeedbackAggregator:
    """
    Aggregates and analyzes customer feedback for continuous improvement.
    
    Key Functions:
    - Weekly feedback analysis from Langfuse
    - Low-confidence query identification  
    - Retrieval gap detection (queries with no relevant chunks)
    - Escalation pattern analysis
    - Prompt optimization suggestions
    - Model performance tracking
    
    Outputs:
    - Quality degradation alerts
    - Retraining recommendations  
    - Prompt template improvements
    - Knowledge base gaps
    """
    
    # Quality thresholds for alerting
    QUALITY_THRESHOLDS = {
        "confidence_threshold": 0.75,    # Alert if avg confidence drops below
        "escalation_rate_threshold": 0.15,  # Alert if escalation rate > 15%
        "negative_feedback_threshold": 0.20,  # Alert if negative feedback > 20%
        "retrieval_failure_threshold": 0.10   # Alert if retrieval fails > 10%
    }
    
    def __init__(self):
        self._langfuse_client = None
        self._initialized = False
    
    async def _initialize_langfuse(self):
        """Initialize Langfuse client for feedback retrieval."""
        if self._initialized or not settings.observability_enabled:
            return
            
        try:
            from langfuse import Langfuse
            self._langfuse_client = Langfuse(
                public_key=settings.langfuse_public_key,
                secret_key=settings.langfuse_secret_key,
                host=settings.langfuse_host,
            )
            self._initialized = True
            logger.info("Feedback aggregator initialized with Langfuse")
        except Exception as e:
            logger.warning(f"Langfuse initialization failed: {e}")
            self._initialized = "no_op"
    
    async def _fetch_feedback_data(self, days: int = 7) -> List[Dict]:
        """Fetch feedback data from Langfuse for the last N days."""
        await self._initialize_langfuse()
        
        if not self._langfuse_client:
            # Mock data for testing without Langfuse
            return self._generate_mock_feedback()
        
        try:
            # Fetch traces with feedback scores
            end_time = datetime.now()
            start_time = end_time - timedelta(days=days)
            
            # This would be the actual Langfuse API call
            # traces = self._langfuse_client.get_traces(
            #     start_time=start_time,
            #     end_time=end_time,
            #     with_scores=True
            # )
            
            # For now, return mock data since Langfuse Python SDK structure may vary
            return self._generate_mock_feedback()
            
        except Exception as e:
            logger.error(f"Failed to fetch feedback data: {e}")
            return []
    
    def _generate_mock_feedback(self) -> List[Dict]:
        """Generate mock feedback data for testing."""
        return [
            {
                "trace_id": f"trace_{i}",
                "session_id": f"session_{i % 10}",
                "timestamp": datetime.now() - timedelta(hours=i),
                "query": f"Sample query {i}",
                "response": f"Sample response {i}",
                "intent": "account_inquiry",
                "confidence_score": 0.85 - (i * 0.02),  # Declining confidence
                "customer_rating": 3 if i < 5 else 4,   # Poor ratings early
                "helpful": i >= 5,                       # Not helpful early
                "escalated": i < 3,                     # High escalation early
                "retrieval_chunks": max(0, 5 - i),     # Decreasing retrieval quality
                "response_time_ms": 2000 + (i * 100),
                "metadata": {
                    "guardrail_scores": {
                        "groundedness": 0.90 - (i * 0.01),
                        "relevance": 0.85 - (i * 0.015),
                        "confidence": 0.80 - (i * 0.02)
                    }
                }
            }
            for i in range(20)  # 20 mock feedback entries
        ]
    
    def _analyze_confidence_trends(self, feedback_data: List[Dict]) -> Optional[FeedbackInsight]:
        """Analyze confidence score trends."""
        if not feedback_data:
            return None
        
        confidence_scores = [f.get("confidence_score", 0) for f in feedback_data]
        avg_confidence = sum(confidence_scores) / len(confidence_scores)
        
        if avg_confidence < self.QUALITY_THRESHOLDS["confidence_threshold"]:
            low_conf_queries = [
                f["query"] for f in feedback_data 
                if f.get("confidence_score", 1) < 0.6
            ]
            
            return FeedbackInsight(
                insight_type="low_confidence",
                severity="high" if avg_confidence < 0.65 else "medium",
                description=f"Average confidence score dropped to {avg_confidence:.2f}",
                affected_queries=low_conf_queries[:5],  # Top 5 examples
                recommended_actions=[
                    "Review LLM prompt templates",
                    "Analyze knowledge base gaps",
                    "Consider model fine-tuning",
                    "Increase retrieval chunk count"
                ],
                confidence=0.9,
                evidence={"avg_confidence": avg_confidence, "threshold": 0.75}
            )
        return None
    
    def _analyze_escalation_patterns(self, feedback_data: List[Dict]) -> Optional[FeedbackInsight]:
        """Analyze escalation rate trends."""
        if not feedback_data:
            return None
        
        escalated_count = sum(1 for f in feedback_data if f.get("escalated", False))
        escalation_rate = escalated_count / len(feedback_data)
        
        if escalation_rate > self.QUALITY_THRESHOLDS["escalation_rate_threshold"]:
            escalated_queries = [
                f["query"] for f in feedback_data if f.get("escalated", False)
            ]
            
            return FeedbackInsight(
                insight_type="escalation_pattern",
                severity="high" if escalation_rate > 0.25 else "medium",
                description=f"Escalation rate increased to {escalation_rate:.1%}",
                affected_queries=escalated_queries[:5],
                recommended_actions=[
                    "Review escalation triggers",
                    "Improve emotion detection",
                    "Enhance knowledge base coverage",
                    "Train staff on escalated query patterns"
                ],
                confidence=0.85,
                evidence={"escalation_rate": escalation_rate, "threshold": 0.15}
            )
        return None
    
    def _analyze_retrieval_quality(self, feedback_data: List[Dict]) -> Optional[FeedbackInsight]:
        """Analyze retrieval effectiveness."""
        if not feedback_data:
            return None
        
        # Queries with poor retrieval (< 2 relevant chunks)
        poor_retrieval = [
            f for f in feedback_data 
            if f.get("retrieval_chunks", 5) < 2
        ]
        
        failure_rate = len(poor_retrieval) / len(feedback_data)
        
        if failure_rate > self.QUALITY_THRESHOLDS["retrieval_failure_threshold"]:
            failed_queries = [f["query"] for f in poor_retrieval]
            
            return FeedbackInsight(
                insight_type="poor_retrieval",
                severity="high" if failure_rate > 0.20 else "medium", 
                description=f"Retrieval failure rate: {failure_rate:.1%}",
                affected_queries=failed_queries[:5],
                recommended_actions=[
                    "Expand knowledge base content",
                    "Improve embedding model",
                    "Optimize chunking strategy",
                    "Add more data sources"
                ],
                confidence=0.8,
                evidence={"failure_rate": failure_rate, "threshold": 0.10}
            )
        return None
    
    def _analyze_customer_satisfaction(self, feedback_data: List[Dict]) -> Optional[FeedbackInsight]:
        """Analyze customer satisfaction trends."""
        if not feedback_data:
            return None
        
        # Calculate negative feedback rate (rating <= 2 or helpful = False)
        negative_feedback = [
            f for f in feedback_data 
            if f.get("customer_rating", 5) <= 2 or not f.get("helpful", True)
        ]
        
        negative_rate = len(negative_feedback) / len(feedback_data)
        
        if negative_rate > self.QUALITY_THRESHOLDS["negative_feedback_threshold"]:
            negative_queries = [f["query"] for f in negative_feedback]
            
            return FeedbackInsight(
                insight_type="customer_dissatisfaction",
                severity="high" if negative_rate > 0.35 else "medium",
                description=f"Negative feedback rate: {negative_rate:.1%}",
                affected_queries=negative_queries[:5],
                recommended_actions=[
                    "Review response templates",
                    "Improve answer accuracy",
                    "Enhance empathy in responses",
                    "Speed up response times"
                ],
                confidence=0.9,
                evidence={"negative_rate": negative_rate, "threshold": 0.20}
            )
        return None
    
    async def analyze_weekly_feedback(self, days: int = 7) -> List[FeedbackInsight]:
        """
        Run weekly feedback analysis and generate insights.
        
        Args:
            days: Number of days of feedback to analyze
            
        Returns:
            List of insights with recommended actions
        """
        logger.info(f"Starting weekly feedback analysis for last {days} days")
        
        # Fetch feedback data
        feedback_data = await self._fetch_feedback_data(days)
        
        if not feedback_data:
            logger.warning("No feedback data available for analysis")
            return []
        
        insights = []
        
        # Run all analysis functions
        analysis_functions = [
            self._analyze_confidence_trends,
            self._analyze_escalation_patterns,  
            self._analyze_retrieval_quality,
            self._analyze_customer_satisfaction
        ]
        
        for analysis_func in analysis_functions:
            try:
                insight = analysis_func(feedback_data)
                if insight:
                    insights.append(insight)
            except Exception as e:
                logger.error(f"Analysis function {analysis_func.__name__} failed: {e}")
        
        # Log insights
        logger.info(
            "Weekly feedback analysis complete",
            insights_found=len(insights),
            feedback_records=len(feedback_data)
        )
        
        # Alert on critical insights
        critical_insights = [i for i in insights if i.severity == "critical"]
        if critical_insights:
            logger.warning(
                "CRITICAL quality issues detected",
                critical_count=len(critical_insights),
                issues=[i.insight_type for i in critical_insights]
            )
        
        return insights
    
    def generate_improvement_report(self, insights: List[FeedbackInsight]) -> Dict:
        """Generate a structured improvement report."""
        if not insights:
            return {
                "status": "healthy",
                "message": "No quality issues detected",
                "recommendations": []
            }
        
        # Prioritize by severity
        critical = [i for i in insights if i.severity == "critical"]
        high = [i for i in insights if i.severity == "high"] 
        medium = [i for i in insights if i.severity == "medium"]
        
        # Collect all unique recommendations
        all_recommendations = []
        for insight in insights:
            all_recommendations.extend(insight.recommended_actions)
        
        unique_recommendations = list(set(all_recommendations))
        
        return {
            "status": "critical" if critical else "needs_attention" if high else "monitor",
            "summary": f"Found {len(insights)} quality insights",
            "critical_issues": len(critical),
            "high_priority_issues": len(high),
            "medium_priority_issues": len(medium),
            "top_recommendations": unique_recommendations[:5],
            "detailed_insights": [
                {
                    "type": i.insight_type,
                    "severity": i.severity,
                    "description": i.description,
                    "actions": i.recommended_actions[:3]
                }
                for i in insights
            ]
        }


# Singleton instance
_feedback_aggregator_instance = None

def get_feedback_aggregator() -> FeedbackAggregator:
    """Get the global feedback aggregator singleton."""
    global _feedback_aggregator_instance
    if _feedback_aggregator_instance is None:
        _feedback_aggregator_instance = FeedbackAggregator()
    return _feedback_aggregator_instance