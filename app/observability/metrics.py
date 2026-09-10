"""
Prometheus metrics collection for Financial AI Agent.
"""
from prometheus_client import Counter, Histogram, Gauge, Info
from prometheus_fastapi_instrumentator import Instrumentator
from functools import wraps
import time
from typing import Callable, Any

# ═══════════════════════════════════════════════════════════════════════════════
# Core Metrics
# ═══════════════════════════════════════════════════════════════════════════════

# Request metrics (handled by instrumentator)
instrumentator = Instrumentator()

# Agent-specific metrics
agent_requests_total = Counter(
    'agent_requests_total',
    'Total agent requests by intent and outcome',
    ['intent', 'outcome', 'escalated']
)

agent_response_confidence = Histogram(
    'agent_response_confidence',
    'Distribution of agent response confidence scores',
    buckets=[0.0, 0.2, 0.4, 0.6, 0.7, 0.8, 0.9, 0.95, 1.0]
)

agent_response_time_seconds = Histogram(
    'agent_response_time_seconds', 
    'Agent response time in seconds',
    ['intent', 'decision'],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0]
)

agent_escalation_total = Counter(
    'agent_escalation_total',
    'Total escalations by reason',
    ['reason', 'intent']
)

# RAG metrics
rag_retrieval_time = Histogram(
    'rag_retrieval_time_seconds',
    'Time spent on RAG retrieval',
    ['collection', 'status']
)

rag_documents_retrieved = Histogram(
    'rag_documents_retrieved',
    'Number of documents retrieved per query',
    ['collection'],
    buckets=[0, 1, 2, 5, 10, 20, 50]
)

# Model metrics
model_inference_time = Histogram(
    'model_inference_time_seconds',
    'Model inference time by model type',
    ['model_type', 'operation']
)

model_predictions_total = Counter(
    'model_predictions_total',
    'Total model predictions by type and result',
    ['model_type', 'prediction']
)

# Vector database metrics
vector_db_operations = Counter(
    'vector_db_operations_total',
    'Vector database operations',
    ['operation', 'collection', 'status']
)

vector_db_size = Gauge(
    'vector_db_collection_size',
    'Number of vectors in each collection',
    ['collection']
)

# Safety metrics
safety_violations = Counter(
    'safety_violations_total',
    'Safety violations detected',
    ['violation_type', 'severity']
)

pii_detections = Counter(
    'pii_detections_total',
    'PII detections by type',
    ['pii_type', 'action_taken']
)

# Business metrics
customer_satisfaction = Histogram(
    'customer_satisfaction_rating',
    'Customer satisfaction ratings',
    buckets=[1, 2, 3, 4, 5]
)

conversation_turns = Histogram(
    'conversation_turns_total',
    'Number of turns per conversation',
    buckets=[1, 2, 3, 5, 10, 20]
)

# ═══════════════════════════════════════════════════════════════════════════════
# Metric Decorators
# ═══════════════════════════════════════════════════════════════════════════════

def track_agent_performance(func: Callable) -> Callable:
    """Decorator to track agent request performance."""
    @wraps(func)
    async def wrapper(*args, **kwargs):
        start_time = time.time()
        
        try:
            result = await func(*args, **kwargs)
            
            # Extract metrics from result
            intent = getattr(result, 'detected_intent', 'unknown')
            confidence = getattr(result, 'confidence', 0.0)
            escalated = getattr(result, 'should_escalate', False)
            decision = getattr(result, 'agent_decision', 'unknown')
            
            # Record metrics
            duration = time.time() - start_time
            agent_response_time_seconds.labels(
                intent=intent, 
                decision=decision
            ).observe(duration)
            
            agent_response_confidence.observe(confidence)
            
            agent_requests_total.labels(
                intent=intent,
                outcome='success',
                escalated=str(escalated)
            ).inc()
            
            if escalated:
                escalation_reason = getattr(result, 'escalation_reason', 'unknown')
                agent_escalation_total.labels(
                    reason=escalation_reason,
                    intent=intent
                ).inc()
                
            return result
            
        except Exception as e:
            duration = time.time() - start_time
            agent_response_time_seconds.labels(
                intent='unknown',
                decision='error'
            ).observe(duration)
            
            agent_requests_total.labels(
                intent='unknown',
                outcome='error',
                escalated='false'
            ).inc()
            
            raise e
            
    return wrapper

def track_model_inference(model_type: str, operation: str = "predict"):
    """Decorator to track model inference time."""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            start_time = time.time()
            
            try:
                result = await func(*args, **kwargs)
                
                duration = time.time() - start_time
                model_inference_time.labels(
                    model_type=model_type,
                    operation=operation
                ).observe(duration)
                
                # Track prediction if result has prediction info
                if hasattr(result, 'prediction') or hasattr(result, 'label'):
                    prediction = getattr(result, 'prediction', 
                                      getattr(result, 'label', 'unknown'))
                    model_predictions_total.labels(
                        model_type=model_type,
                        prediction=str(prediction)
                    ).inc()
                
                return result
                
            except Exception as e:
                duration = time.time() - start_time
                model_inference_time.labels(
                    model_type=model_type,
                    operation='error'
                ).observe(duration)
                
                raise e
                
        return wrapper
    return decorator

def track_rag_performance(func: Callable) -> Callable:
    """Decorator to track RAG retrieval performance."""
    @wraps(func)
    async def wrapper(*args, **kwargs):
        start_time = time.time()
        
        try:
            result = await func(*args, **kwargs)
            
            duration = time.time() - start_time
            
            # Extract collection info
            collections = getattr(result, 'collections_used', ['unknown'])
            doc_count = len(getattr(result, 'documents', []))
            
            for collection in collections:
                rag_retrieval_time.labels(
                    collection=collection,
                    status='success'
                ).observe(duration)
                
                rag_documents_retrieved.labels(
                    collection=collection
                ).observe(doc_count)
            
            return result
            
        except Exception as e:
            duration = time.time() - start_time
            rag_retrieval_time.labels(
                collection='unknown',
                status='error'
            ).observe(duration)
            
            raise e
            
    return wrapper

# ═══════════════════════════════════════════════════════════════════════════════
# Utility Functions
# ═══════════════════════════════════════════════════════════════════════════════

def record_safety_violation(violation_type: str, severity: str = "medium"):
    """Record a safety violation."""
    safety_violations.labels(
        violation_type=violation_type,
        severity=severity
    ).inc()

def record_pii_detection(pii_type: str, action_taken: str = "masked"):
    """Record PII detection and action."""
    pii_detections.labels(
        pii_type=pii_type,
        action_taken=action_taken
    ).inc()

def record_customer_feedback(rating: int):
    """Record customer satisfaction rating."""
    customer_satisfaction.observe(rating)

def update_vector_db_size(collection: str, size: int):
    """Update vector database collection size."""
    vector_db_size.labels(collection=collection).set(size)

def record_vector_operation(operation: str, collection: str, success: bool):
    """Record vector database operation."""
    status = "success" if success else "error"
    vector_db_operations.labels(
        operation=operation,
        collection=collection,
        status=status
    ).inc()