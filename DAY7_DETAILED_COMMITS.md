# Day 7 Implementation: Observability & Monitoring (Detailed)

**Date:** Day 7 of development  
**Theme:** System observability, metrics, and distributed tracing  
**Total Commits:** 5 logical commits  
**Time Span:** 8:00 AM - 6:30 PM  

---

## Overview

Day 7 focuses on making the system observable and monitorable. You'll build:
- Prometheus metrics collection
- Custom business metrics
- Grafana dashboard configuration
- Distributed tracing with instrumentation
- Logging aggregation setup

This is where you can see what the system is actually doing!

---

## Commit 1 (8:00 AM): Prometheus Metrics Setup

### What to Stage:
```
app/observability/metrics.py                ← Prometheus metrics
```

### Git Commands:
```bash
git add app/observability/metrics.py
git commit -m "Setup Prometheus metrics collection"
```

### File: `app/observability/metrics.py`
Should contain:
```python
from prometheus_client import Counter, Histogram, Gauge
from functools import wraps
import time

# Request metrics
request_count = Counter(
    'financial_agent_requests_total',
    'Total API requests',
    ['method', 'endpoint', 'status']
)

request_duration = Histogram(
    'financial_agent_request_duration_seconds',
    'Request duration in seconds',
    ['method', 'endpoint'],
    buckets=(0.1, 0.5, 1.0, 2.5, 5.0, 10.0)
)

# Agent metrics
agent_executions = Counter(
    'financial_agent_executions_total',
    'Total agent executions',
    ['intent', 'status']
)

agent_duration = Histogram(
    'financial_agent_duration_seconds',
    'Agent execution time',
    ['intent'],
    buckets=(0.5, 1.0, 2.0, 5.0, 10.0, 30.0)
)

# Retrieval metrics
documents_retrieved = Counter(
    'financial_agent_documents_retrieved_total',
    'Total documents retrieved',
    ['source']
)

retrieval_quality = Histogram(
    'financial_agent_retrieval_quality_score',
    'Quality score of retrieved documents',
    buckets=(0.1, 0.3, 0.5, 0.7, 0.9)
)

# Model metrics
model_calls = Counter(
    'financial_agent_model_calls_total',
    'Total model API calls',
    ['model', 'status']
)

model_duration = Histogram(
    'financial_agent_model_duration_seconds',
    'Model call latency',
    ['model'],
    buckets=(0.1, 0.5, 1.0, 2.0, 5.0)
)

tokens_used = Counter(
    'financial_agent_tokens_used_total',
    'Total tokens used',
    ['model']
)

# Sentiment metrics
complaints_sentiment = Gauge(
    'financial_agent_complaints_sentiment',
    'Latest complaint sentiment score',
    ['sentiment_level']
)

# PII metrics
pii_detections = Counter(
    'financial_agent_pii_detections_total',
    'Total PII detected',
    ['pii_type']
)

# Queue metrics
queue_size = Gauge(
    'financial_agent_queue_size',
    'Current queue size'
)

processing_queue_duration = Histogram(
    'financial_agent_queue_wait_seconds',
    'Time spent in queue',
    buckets=(0.1, 0.5, 1.0, 5.0, 10.0)
)

def track_request(method: str, endpoint: str):
    """Decorator to track HTTP requests"""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            start = time.time()
            try:
                result = await func(*args, **kwargs)
                status = 200
            except Exception as e:
                status = 500
                raise
            finally:
                duration = time.time() - start
                request_duration.labels(method=method, endpoint=endpoint).observe(duration)
                request_count.labels(method=method, endpoint=endpoint, status=status).inc()
            return result
        return wrapper
    return decorator

def track_agent_execution(intent: str):
    """Decorator to track agent executions"""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            start = time.time()
            try:
                result = await func(*args, **kwargs)
                status = "success"
            except Exception as e:
                status = "error"
                raise
            finally:
                duration = time.time() - start
                agent_duration.labels(intent=intent).observe(duration)
                agent_executions.labels(intent=intent, status=status).inc()
            return result
        return wrapper
    return decorator

def track_model_call(model_name: str):
    """Decorator to track model API calls"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            start = time.time()
            try:
                result = func(*args, **kwargs)
                status = "success"
            except Exception as e:
                status = "error"
                raise
            finally:
                duration = time.time() - start
                model_duration.labels(model=model_name).observe(duration)
                model_calls.labels(model=model_name, status=status).inc()
            return result
        return wrapper
    return decorator
```

### What This Demonstrates:
✅ Prometheus counter and histogram metrics
✅ Custom business metrics
✅ Decorator patterns for instrumentation
✅ Performance tracking

---

## Commit 2 (10:00 AM): Tracing Configuration

### What to Stage:
```
app/observability/tracer.py                 ← Distributed tracing (UPDATE)
```

### Git Commands:
```bash
git add app/observability/tracer.py
git commit -m "Configure OpenTelemetry distributed tracing"
```

### File: `app/observability/tracer.py`
Should contain:
```python
from opentelemetry import trace
from opentelemetry.exporter.jaeger.thrift import JaegerExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from app.core.config import settings

# Configure Jaeger exporter
jaeger_exporter = JaegerExporter(
    agent_host_name=settings.jaeger_host,
    agent_port=settings.jaeger_port,
)

# Set trace provider
trace.set_tracer_provider(TracerProvider())
trace.get_tracer_provider().add_span_processor(
    BatchSpanProcessor(jaeger_exporter)
)

# Get tracer
tracer = trace.get_tracer(__name__)

def init_tracing():
    """Initialize automatic instrumentation"""
    # FastAPI
    FastAPIInstrumentor.instrument_app(app=None)  # App passed separately
    
    # HTTP requests
    RequestsInstrumentor().instrument()
    
    # Database
    SQLAlchemyInstrumentor().instrument()

def create_span(name: str, attributes: dict = None):
    """Create and return span"""
    span = tracer.start_span(name)
    if attributes:
        for key, value in attributes.items():
            span.set_attribute(key, value)
    return span

class SpanContext:
    """Context manager for spans"""
    def __init__(self, name: str, attributes: dict = None):
        self.name = name
        self.attributes = attributes or {}
        self.span = None
    
    def __enter__(self):
        self.span = create_span(self.name, self.attributes)
        return self.span
    
    def __exit__(self, *args):
        if self.span:
            self.span.end()
```

### What This Demonstrates:
✅ OpenTelemetry setup
✅ Jaeger integration
✅ Automatic instrumentation
✅ Span context management

---

## Commit 3 (12:00 PM): Logging Configuration

### What to Stage:
```
app/core/logging.py                         ← Structured logging (UPDATE)
```

### Git Commands:
```bash
git add app/core/logging.py
git commit -m "Implement structured JSON logging"
```

### File: `app/core/logging.py`
Should contain:
```python
import logging
import json
from datetime import datetime
from pythonjsonlogger import jsonlogger

class CustomJsonFormatter(jsonlogger.JsonFormatter):
    """Custom JSON formatter with extra fields"""
    
    def add_fields(self, log_record, record, message_dict):
        super(CustomJsonFormatter, self).add_fields(log_record, record, message_dict)
        log_record['timestamp'] = datetime.utcnow().isoformat()
        log_record['logger_name'] = record.name
        log_record['level'] = record.levelname

def setup_logging(name: str = "financial_agent", level=logging.INFO):
    """Setup structured logging"""
    
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    # Console handler with JSON formatting
    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    
    formatter = CustomJsonFormatter('%(message)s %(level)s %(timestamp)s')
    console_handler.setFormatter(formatter)
    
    logger.addHandler(console_handler)
    
    return logger

# Standard loggers
agent_logger = setup_logging("agent")
api_logger = setup_logging("api")
ingestion_logger = setup_logging("ingestion")
retrieval_logger = setup_logging("retrieval")
model_logger = setup_logging("model")

def log_agent_execution(intent: str, status: str, duration_ms: float, metadata: dict = None):
    """Log agent execution"""
    agent_logger.info(f"Agent execution: {intent}", extra={
        "intent": intent,
        "status": status,
        "duration_ms": duration_ms,
        "metadata": metadata or {}
    })

def log_retrieval(query: str, documents_count: int, quality_score: float):
    """Log retrieval operation"""
    retrieval_logger.info(f"Retrieved {documents_count} documents", extra={
        "query": query[:100],
        "documents_count": documents_count,
        "quality_score": quality_score
    })

def log_model_call(model: str, status: str, tokens: int = 0):
    """Log model API call"""
    model_logger.info(f"Model call: {model}", extra={
        "model": model,
        "status": status,
        "tokens": tokens
    })
```

### What This Demonstrates:
✅ Structured logging
✅ JSON log formatting
✅ Log aggregation support
✅ Correlation logging

---

## Commit 4 (2:00 PM): Grafana Dashboard Configuration

### What to Stage:
```
monitoring/grafana/dashboards/agent-dashboard.json    ← Dashboard definition
monitoring/grafana/provisioning/dashboards.yml         ← Dashboard provisioning
```

### Git Commands:
```bash
git add monitoring/grafana/dashboards/agent-dashboard.json monitoring/grafana/provisioning/dashboards.yml
git commit -m "Add Grafana dashboard for agent monitoring"
```

### File: `monitoring/grafana/dashboards/agent-dashboard.json`
Should contain (simplified):
```json
{
  "annotations": {
    "list": [
      {
        "builtIn": 1,
        "datasource": "-- Prometheus --",
        "enable": true,
        "hide": true,
        "iconColor": "rgba(0, 211, 255, 1)",
        "name": "Annotations & Alerts",
        "type": "dashboard"
      }
    ]
  },
  "editable": true,
  "gnetId": null,
  "graphTooltip": 0,
  "id": null,
  "links": [],
  "panels": [
    {
      "datasource": "Prometheus",
      "fieldConfig": {
        "defaults": {
          "color": {
            "mode": "palette-classic"
          },
          "custom": {
            "axisLabel": "",
            "axisPlacement": "auto"
          }
        }
      },
      "gridPos": {
        "h": 8,
        "w": 12,
        "x": 0,
        "y": 0
      },
      "id": 2,
      "options": {
        "legend": {
          "calcs": [],
          "displayMode": "list",
          "placement": "bottom"
        }
      },
      "targets": [
        {
          "expr": "rate(financial_agent_requests_total[5m])",
          "legendFormat": "{{method}} {{endpoint}}",
          "refId": "A"
        }
      ],
      "title": "Request Rate",
      "type": "timeseries"
    },
    {
      "datasource": "Prometheus",
      "fieldConfig": {
        "defaults": {
          "mappings": [],
          "thresholds": {
            "mode": "absolute",
            "steps": [
              {
                "color": "green",
                "value": null
              },
              {
                "color": "red",
                "value": 800
              }
            ]
          }
        }
      },
      "gridPos": {
        "h": 8,
        "w": 12,
        "x": 12,
        "y": 0
      },
      "id": 4,
      "targets": [
        {
          "expr": "histogram_quantile(0.95, financial_agent_request_duration_seconds)",
          "refId": "A"
        }
      ],
      "title": "p95 Request Duration",
      "type": "gauge"
    },
    {
      "datasource": "Prometheus",
      "gridPos": {
        "h": 8,
        "w": 12,
        "x": 0,
        "y": 8
      },
      "id": 6,
      "targets": [
        {
          "expr": "increase(financial_agent_documents_retrieved_total[5m])",
          "legendFormat": "{{source}}",
          "refId": "A"
        }
      ],
      "title": "Documents Retrieved",
      "type": "timeseries"
    },
    {
      "datasource": "Prometheus",
      "gridPos": {
        "h": 8,
        "w": 12,
        "x": 12,
        "y": 8
      },
      "id": 8,
      "targets": [
        {
          "expr": "financial_agent_complaints_sentiment",
          "refId": "A"
        }
      ],
      "title": "Sentiment Distribution",
      "type": "piechart"
    }
  ],
  "refresh": "30s",
  "schemaVersion": 26,
  "style": "dark",
  "tags": ["agent", "financial"],
  "templating": {
    "list": []
  },
  "time": {
    "from": "now-1h",
    "to": "now"
  },
  "timepicker": {},
  "timezone": "",
  "title": "Financial Agent Monitoring",
  "uid": "financial-agent",
  "version": 0
}
```

### File: `monitoring/grafana/provisioning/dashboards.yml`
```yaml
apiVersion: 1

providers:
  - name: 'default'
    orgId: 1
    folder: 'Agent'
    type: file
    disableDeletion: false
    updateIntervalSeconds: 10
    allowUiUpdates: true
    options:
      path: /etc/grafana/provisioning/dashboards
```

### What This Demonstrates:
✅ Grafana dashboard definition
✅ PromQL queries
✅ Visual monitoring panels
✅ Real-time metrics visualization

---

## Commit 5 (4:00 PM): Alert Rules Configuration

### What to Stage:
```
monitoring/prometheus/alert_rules.yml       ← Alert rules
monitoring/prometheus/prometheus.yml        ← Prometheus config (UPDATE)
```

### Git Commands:
```bash
git add monitoring/prometheus/alert_rules.yml monitoring/prometheus/prometheus.yml
git commit -m "Add Prometheus alerting rules for system health"
```

### File: `monitoring/prometheus/alert_rules.yml`
Should contain:
```yaml
groups:
  - name: financial_agent
    interval: 30s
    rules:
      # Request metrics alerts
      - alert: HighRequestLatency
        expr: histogram_quantile(0.95, financial_agent_request_duration_seconds) > 5
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High request latency detected"
          description: "p95 request duration is {{ $value }}s"

      - alert: HighErrorRate
        expr: rate(financial_agent_requests_total{status="500"}[5m]) > 0.05
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "High error rate"
          description: "Error rate is {{ $value | humanizePercentage }}"

      # Agent execution alerts
      - alert: SlowAgentExecution
        expr: histogram_quantile(0.95, financial_agent_duration_seconds) > 30
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Agent execution is slow"
          description: "p95 execution time is {{ $value }}s"

      - alert: AgentFailures
        expr: rate(financial_agent_executions_total{status="error"}[5m]) > 0.1
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Agent failures detected"
          description: "Failure rate is {{ $value | humanizePercentage }}"

      # Retrieval quality alerts
      - alert: PoorRetrievalQuality
        expr: histogram_quantile(0.5, financial_agent_retrieval_quality_score) < 0.5
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "Retrieval quality is low"
          description: "Median quality score is {{ $value }}"

      # Model call alerts
      - alert: ModelAPIErrors
        expr: rate(financial_agent_model_calls_total{status="error"}[5m]) > 0.1
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Model API errors"
          description: "Error rate is {{ $value | humanizePercentage }}"

      # PII detection alerts
      - alert: HighPIIDetection
        expr: rate(financial_agent_pii_detections_total[1h]) > 10
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High PII detection rate"
          description: "{{ $value | humanize }} PII instances detected per hour"
```

### File: `monitoring/prometheus/prometheus.yml`
```yaml
global:
  scrape_interval: 15s
  evaluation_interval: 15s
  external_labels:
    monitor: 'financial-agent'

# Alertmanager config
alerting:
  alertmanagers:
    - static_configs:
        - targets:
            - localhost:9093

# Load rules
rule_files:
  - "alert_rules.yml"

scrape_configs:
  - job_name: 'financial-agent'
    static_configs:
      - targets: ['localhost:8000']
    metrics_path: '/metrics'

  - job_name: 'postgres'
    static_configs:
      - targets: ['localhost:5432']

  - job_name: 'qdrant'
    static_configs:
      - targets: ['localhost:6333']
```

### What This Demonstrates:
✅ Alert rule definition
✅ Threshold-based alerting
✅ Multi-service monitoring
✅ Prometheus scrape configuration

---

## Full Day 7 Workflow

### Morning (8:00 AM - 12:00 PM)
```bash
# 8:00 AM - Prometheus Metrics
git add app/observability/metrics.py
git commit -m "Setup Prometheus metrics collection"

# 9:00-10:00 AM - Code & test

# 10:00 AM - Tracing Configuration
git add app/observability/tracer.py
git commit -m "Configure OpenTelemetry distributed tracing"

# 11:00-12:00 PM - Code & test
```

### Afternoon (12:00 PM - 6:30 PM)
```bash
# 12:00 PM - Logging Configuration
git add app/core/logging.py
git commit -m "Implement structured JSON logging"

# 1:00-2:00 PM - Code & test

# 2:00 PM - Grafana Dashboard
git add monitoring/grafana/dashboards/agent-dashboard.json monitoring/grafana/provisioning/dashboards.yml
git commit -m "Add Grafana dashboard for agent monitoring"

# 3:00-4:00 PM - Code & test

# 4:00 PM - Alert Rules
git add monitoring/prometheus/alert_rules.yml monitoring/prometheus/prometheus.yml
git commit -m "Add Prometheus alerting rules for system health"

# 5:00-6:30 PM - Code & test
```

---

## Verification Checklist

After Day 7:

```bash
# Check monitoring setup
ls -la app/observability/
# Should have: metrics.py, tracer.py

# Check monitoring config
ls -la monitoring/prometheus/
ls -la monitoring/grafana/dashboards/

# Test metrics endpoint
curl http://localhost:8000/metrics

# Verify Prometheus targets
curl http://localhost:9090/api/v1/targets

# Check Grafana dashboards
curl http://localhost:3000/api/dashboards/db/financial-agent

# View commits
git log --oneline -5
```

---

## Git History at End of Day 7

```bash
$ git log --oneline | head -8
* Day7-5: Add Prometheus alerting rules for system health
* Day7-4: Add Grafana dashboard for agent monitoring
* Day7-3: Implement structured JSON logging
* Day7-2: Configure OpenTelemetry distributed tracing
* Day7-1: Setup Prometheus metrics collection
```

---

## What Was Built

By end of Day 7:
- ✅ Prometheus metrics collection
- ✅ Custom business metrics
- ✅ OpenTelemetry tracing
- ✅ Jaeger integration
- ✅ Structured JSON logging
- ✅ Grafana dashboards
- ✅ Alert rules
- ✅ System health monitoring
- ✅ Performance tracking
- ✅ Real-time visualization

The system is now fully observable! 👀

---

## Ready for Day 8?

After completing Day 7:
- [ ] 5 commits in git log
- [ ] Total: 36 commits (Days 1-7 combined)
- [ ] Observability complete
- [ ] Monitoring dashboards live
- [ ] Ready to add advanced features

**Next:** Day 8 - Advanced Features (A/B testing, MLOps, Salesforce integration)

Time to add advanced capabilities! 🚀
