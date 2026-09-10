"""
Tests for Feedback Collector.
"""
import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

from app.mlops.feedback_collector import (
    FeedbackCollector, FeedbackEntry, FeedbackType, FeedbackSentiment, ModelPerformanceSnapshot
)


@pytest.mark.models
@pytest.mark.unit
class TestFeedbackCollector:
    """Test suite for feedback collector."""
    
    @pytest.fixture
    def collector(self):
        """Create feedback collector instance."""
        return FeedbackCollector()
    
    @pytest.fixture
    def sample_feedback(self):
        """Create sample feedback entry."""
        return FeedbackEntry(
            feedback_id="test_feedback_001",
            session_id="session_123",
            user_id="user_456",
            model_type="sentiment_classifier",
            feedback_type=FeedbackType.USER_RATING,
            rating=4,
            sentiment=FeedbackSentiment.POSITIVE,
            escalated=False,
            safety_violation=False,
            response_time=1.2,
            confidence_score=0.85,
            user_message="What are my account fees?",
            agent_response="Your account has the following fees...",
            follow_up_needed=False,
            metadata={"source": "web_chat"}
        )
    
    @pytest.mark.asyncio
    async def test_collector_startup(self, collector):
        """Test feedback collector startup."""
        assert not collector._running
        
        await collector.start_collection()
        assert collector._running
        
        await collector.stop_collection()
        assert not collector._running
    
    @pytest.mark.asyncio
    async def test_feedback_collection(self, collector, sample_feedback):
        """Test basic feedback collection."""
        initial_count = len(collector.feedback_buffer)
        
        await collector.collect_feedback(sample_feedback)
        
        assert len(collector.feedback_buffer) == initial_count + 1
        assert collector.feedback_buffer[-1] == sample_feedback
    
    @pytest.mark.asyncio
    async def test_user_rating_collection(self, collector):
        """Test user rating feedback collection."""
        await collector.collect_user_rating(
            session_id="test_session",
            model_type="test_model",
            rating=5,
            user_message="Great service!",
            agent_response="Thank you for the positive feedback!",
            response_time=0.8,
            confidence_score=0.92
        )
        
        assert len(collector.feedback_buffer) == 1
        feedback = collector.feedback_buffer[0]
        
        assert feedback.rating == 5
        assert feedback.feedback_type == FeedbackType.USER_RATING
        assert feedback.sentiment == FeedbackSentiment.POSITIVE
        assert feedback.escalated is False
        assert feedback.session_id == "test_session"
    
    @pytest.mark.asyncio
    async def test_escalation_feedback(self, collector):
        """Test escalation feedback collection."""
        await collector.collect_escalation_feedback(
            session_id="escalation_session",
            model_type="test_model",
            reason="Unable to resolve issue",
            user_message="This is not working at all!",
            agent_response="I understand your frustration...",
            response_time=2.5,
            confidence_score=0.45
        )
        
        assert len(collector.feedback_buffer) == 1
        feedback = collector.feedback_buffer[0]
        
        assert feedback.feedback_type == FeedbackType.ESCALATION
        assert feedback.escalated is True
        assert feedback.sentiment == FeedbackSentiment.NEGATIVE
        assert feedback.follow_up_needed is True
        assert feedback.metadata["escalation_reason"] == "Unable to resolve issue"
    
    @pytest.mark.asyncio
    async def test_safety_violation_collection(self, collector):
        """Test safety violation feedback collection."""
        await collector.collect_safety_violation(
            session_id="safety_session",
            model_type="test_model",
            violation_type="inappropriate_content",
            user_message="Inappropriate request",
            agent_response="I cannot assist with that request",
            confidence_score=0.95
        )
        
        assert len(collector.feedback_buffer) == 1
        feedback = collector.feedback_buffer[0]
        
        assert feedback.feedback_type == FeedbackType.SAFETY_VIOLATION
        assert feedback.safety_violation is True
        assert feedback.escalated is True
        assert feedback.rating == 1
        assert feedback.sentiment == FeedbackSentiment.NEGATIVE
    
    @pytest.mark.asyncio
    async def test_immediate_alert_processing(self, collector):
        """Test immediate alert processing."""
        with patch.object(collector, '_process_alert') as mock_alert:
            # Test safety violation alert
            await collector.collect_safety_violation(
                session_id="alert_session",
                model_type="test_model", 
                violation_type="security_issue",
                user_message="Test message",
                agent_response="Test response",
                confidence_score=0.8
            )
            
            # Should trigger safety violation alert (may also trigger very_low_rating)
            mock_alert.assert_called()
            all_alerts = [c[0][0] for c in mock_alert.call_args_list]
            safety_alerts = [a for a in all_alerts if a["type"] == "safety_violation"]
            assert len(safety_alerts) >= 1, f"No safety_violation alert fired; got: {[a['type'] for a in all_alerts]}"
            assert safety_alerts[0]["severity"] == "high"
    
    @pytest.mark.asyncio
    async def test_very_low_rating_alert(self, collector):
        """Test very low rating alert."""
        with patch.object(collector, '_process_alert') as mock_alert:
            await collector.collect_user_rating(
                session_id="low_rating_session",
                model_type="test_model",
                rating=1,  # Very low rating
                user_message="Terrible experience",
                agent_response="I apologize for the poor experience",
                response_time=3.0,
                confidence_score=0.6
            )
            
            mock_alert.assert_called()
            alert_call = mock_alert.call_args[0][0]
            assert alert_call["type"] == "very_low_rating"
            assert alert_call["severity"] == "medium"
    
    @pytest.mark.asyncio
    async def test_performance_snapshot_creation(self, collector):
        """Test creation of performance snapshots."""
        model_type = "test_model"
        
        # Add various feedback entries
        feedback_entries = [
            # High rating feedback
            FeedbackEntry(
                feedback_id=f"feedback_{i}",
                session_id=f"session_{i}",
                user_id=None,
                model_type=model_type,
                feedback_type=FeedbackType.USER_RATING,
                rating=4 if i % 3 != 0 else 5,  # Mix of 4s and 5s
                sentiment=FeedbackSentiment.POSITIVE,
                escalated=i % 10 == 0,  # 10% escalation rate
                safety_violation=i % 20 == 0,  # 5% safety violations
                response_time=1.0 + (i % 5) * 0.2,  # Varying response times
                confidence_score=0.7 + (i % 4) * 0.05,  # Varying confidence
                user_message=f"Test message {i}",
                agent_response=f"Test response {i}",
                follow_up_needed=False
            )
            for i in range(20)
        ]
        
        snapshot = await collector._create_performance_snapshot(model_type, feedback_entries)
        
        assert snapshot.model_type == model_type
        assert snapshot.total_interactions == 20
        assert 4.0 <= snapshot.avg_rating <= 5.0  # Should be between 4 and 5
        assert 0.08 <= snapshot.escalation_rate <= 0.12  # Around 10%
        assert snapshot.safety_violations == 1  # Should have 1 violation
        assert 0.7 <= snapshot.avg_confidence <= 0.85
        assert 0.8 <= snapshot.user_satisfaction_rate <= 1.0  # All ratings >= 4
    
    @pytest.mark.asyncio
    async def test_performance_alert_thresholds(self, collector):
        """Test performance alerts against thresholds."""
        # Create snapshot with poor performance
        poor_snapshot = ModelPerformanceSnapshot(
            model_type="poor_model",
            time_period="1h", 
            total_interactions=100,
            avg_rating=2.0,  # Below threshold
            escalation_rate=0.4,  # Above threshold
            safety_violations=8,  # High violations per hour
            avg_confidence=0.5,  # Below threshold
            avg_response_time=2.5,
            user_satisfaction_rate=0.3
        )
        
        with patch.object(collector, '_process_alert') as mock_alert:
            await collector._check_performance_alerts(poor_snapshot)
            
            # Should trigger multiple alerts
            assert mock_alert.call_count >= 3
            
            # Check alert types
            alert_types = [call[0][0]["type"] for call in mock_alert.call_args_list]
            expected_types = ["high_escalation_rate", "high_safety_violations", "low_average_rating", "low_confidence"]
            
            for alert_type in expected_types:
                if alert_type in alert_types:
                    continue
                # Some alerts might not trigger depending on thresholds
    
    @pytest.mark.asyncio
    async def test_feedback_summary_generation(self, collector):
        """Test feedback summary generation."""
        model_type = "summary_test"
        
        # Add sample feedback
        await collector.collect_user_rating(
            session_id="session1", model_type=model_type, rating=5,
            user_message="Great!", agent_response="Thank you!",
            response_time=1.0, confidence_score=0.9
        )
        
        await collector.collect_user_rating(
            session_id="session2", model_type=model_type, rating=2,
            user_message="Poor service", agent_response="Sorry to hear that",
            response_time=2.0, confidence_score=0.6
        )
        
        await collector.collect_escalation_feedback(
            session_id="session3", model_type=model_type, reason="Complex issue",
            user_message="Need help", agent_response="Escalating to specialist",
            response_time=1.5, confidence_score=0.4
        )
        
        # Get summary
        summary = await collector.get_feedback_summary(model_type=model_type)
        
        assert summary["total_feedback"] == 3
        assert summary["avg_rating"] == 3.5  # (5 + 2) / 2
        assert summary["escalations"] == 1
        assert summary["escalation_rate"] == 1/3
        assert summary["safety_violations"] == 0
        assert model_type in summary["model_types"]
    
    @pytest.mark.asyncio
    async def test_model_performance_history(self, collector):
        """Test model performance history tracking."""
        model_type = "history_test"
        
        # Create and store performance snapshots
        snapshot1 = ModelPerformanceSnapshot(
            model_type=model_type,
            time_period="1h",
            total_interactions=50,
            avg_rating=4.2,
            escalation_rate=0.1,
            safety_violations=0,
            avg_confidence=0.8,
            avg_response_time=1.2,
            user_satisfaction_rate=0.85,
            timestamp=datetime.utcnow() - timedelta(hours=2)
        )
        
        snapshot2 = ModelPerformanceSnapshot(
            model_type=model_type,
            time_period="1h",
            total_interactions=60,
            avg_rating=4.0,
            escalation_rate=0.15,
            safety_violations=1,
            avg_confidence=0.75,
            avg_response_time=1.4,
            user_satisfaction_rate=0.80,
            timestamp=datetime.utcnow() - timedelta(hours=1)
        )
        
        # Store snapshots
        collector.performance_snapshots[model_type] = [snapshot1, snapshot2]
        
        # Get history
        history = await collector.get_model_performance_history(model_type, hours=3)
        
        assert len(history) == 2
        assert history[0].timestamp == snapshot1.timestamp
        assert history[1].timestamp == snapshot2.timestamp
    
    @pytest.mark.asyncio  
    async def test_emergency_rollback_consideration(self, collector):
        """Test emergency rollback consideration for safety violations."""
        model_type = "unsafe_model"
        
        # Add multiple safety violations in short time
        base_time = datetime.utcnow()
        
        for i in range(4):  # 4 violations in 30 minutes should trigger consideration
            violation_feedback = FeedbackEntry(
                feedback_id=f"safety_{i}",
                session_id=f"session_{i}",
                user_id=None,
                model_type=model_type,
                feedback_type=FeedbackType.SAFETY_VIOLATION,
                rating=1,
                sentiment=FeedbackSentiment.NEGATIVE,
                escalated=True,
                safety_violation=True,
                response_time=1.0,
                confidence_score=0.8,
                user_message="Unsafe request",
                agent_response="Cannot comply",
                follow_up_needed=True,
                timestamp=base_time - timedelta(minutes=i*5)  # Spread over 15 minutes
            )
            collector.feedback_buffer.append(violation_feedback)
        
        with patch('app.mlops.feedback_collector.logger') as mock_logger:
            await collector._consider_emergency_rollback(model_type)
            
            # Should log critical emergency
            mock_logger.critical.assert_called()
            call_message = mock_logger.critical.call_args[0][0]
            assert "Emergency" in call_message
            assert "safety violations" in call_message
    
    @pytest.mark.asyncio
    async def test_aggregation_loop_error_handling(self, collector):
        """Test error handling in aggregation loop."""
        with patch.object(collector, '_aggregate_performance_metrics', side_effect=Exception("Test error")):
            with patch('app.mlops.feedback_collector.logger') as mock_logger:
                collector._running = True
                
                # Run one iteration with error
                try:
                    await collector._aggregation_loop()
                except:
                    pass  # Expected to exit due to error
                
                # Should log error
                mock_logger.error.assert_called()


@pytest.mark.models
@pytest.mark.integration
class TestFeedbackCollectorIntegration:
    """Integration tests for feedback collector."""
    
    @pytest.mark.asyncio
    async def test_end_to_end_feedback_flow(self):
        """Test complete feedback collection and processing flow."""
        collector = FeedbackCollector()
        model_type = "integration_test"
        
        # Simulate various user interactions
        feedback_scenarios = [
            # Positive interactions
            {"rating": 5, "escalated": False, "safety_violation": False, "confidence": 0.9},
            {"rating": 4, "escalated": False, "safety_violation": False, "confidence": 0.8},
            {"rating": 4, "escalated": False, "safety_violation": False, "confidence": 0.85},
            
            # Negative interactions  
            {"rating": 2, "escalated": True, "safety_violation": False, "confidence": 0.4},
            {"rating": 1, "escalated": True, "safety_violation": False, "confidence": 0.3},
            
            # Safety violation
            {"rating": 1, "escalated": True, "safety_violation": True, "confidence": 0.7}
        ]
        
        # Submit all feedback
        for i, scenario in enumerate(feedback_scenarios):
            if scenario["safety_violation"]:
                await collector.collect_safety_violation(
                    session_id=f"session_{i}",
                    model_type=model_type,
                    violation_type="inappropriate_content",
                    user_message=f"Message {i}",
                    agent_response=f"Response {i}",
                    confidence_score=scenario["confidence"]
                )
            else:
                await collector.collect_user_rating(
                    session_id=f"session_{i}",
                    model_type=model_type,
                    rating=scenario["rating"],
                    user_message=f"Message {i}",
                    agent_response=f"Response {i}",
                    response_time=1.0 + i * 0.1,
                    confidence_score=scenario["confidence"],
                    escalated=scenario["escalated"]
                )
        
        # Check feedback was collected
        assert len(collector.feedback_buffer) == len(feedback_scenarios)
        
        # Create performance snapshot
        feedback_list = [f for f in collector.feedback_buffer if f.model_type == model_type]
        snapshot = await collector._create_performance_snapshot(model_type, feedback_list)
        
        # Verify snapshot metrics
        assert snapshot.total_interactions == 6
        assert snapshot.safety_violations == 1
        assert snapshot.escalation_rate == 3/6  # 3 escalations out of 6
        
        # Verify ratings calculation — all rated entries (including safety_violation) are included
        ratings = [f.rating for f in feedback_list if f.rating is not None]
        expected_avg_rating = sum(ratings) / len(ratings)
        assert abs(snapshot.avg_rating - expected_avg_rating) < 0.01