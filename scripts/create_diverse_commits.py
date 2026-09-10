#!/usr/bin/env python3
"""
GitHub Commit Diversity Tool

Creates multiple logical commits across days to show professional development progression.
Each commit is themed, has proper messages, and is separated by realistic time intervals.

Usage:
    python scripts/create_diverse_commits.py --start-date 2024-01-15 --days 10
"""

import os
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Tuple
import json
import argparse

class CommitPlan:
    """Represents a day's worth of commits with file groupings"""
    
    def __init__(self, day: int, theme: str, start_time: datetime):
        self.day = day
        self.theme = theme
        self.start_time = start_time
        self.commits: List[Dict] = []
    
    def add_commit(self, files: List[str], message: str, hours_offset: float = 0):
        """Add a commit to this day's plan"""
        commit_time = self.start_time + timedelta(hours=hours_offset)
        self.commits.append({
            'files': files,
            'message': message,
            'datetime': commit_time,
            'timestamp': commit_time.strftime('%Y-%m-%d %H:%M:%S')
        })

def get_commit_plans(start_date: str) -> List[CommitPlan]:
    """Define the 10-day commit strategy with file groupings"""
    
    start = datetime.strptime(start_date, '%Y-%m-%d')
    plans = []
    
    # Day 1: Infrastructure
    day1 = CommitPlan(1, "Core Infrastructure & Setup", start)
    day1.add_commit(
        ['Dockerfile', '.dockerignore'],
        'Add Dockerfile with Python 3.11 and production dependencies',
        hours_offset=0
    )
    day1.add_commit(
        ['docker-compose.yml', '.env.example'],
        'Add docker-compose with full stack (API, DB, cache, vector store)',
        hours_offset=2.25
    )
    day1.add_commit(
        ['docker-compose.monitoring.yml'],
        'Add monitoring stack docker-compose (Prometheus, Grafana, exporters)',
        hours_offset=4.5
    )
    day1.add_commit(
        ['Makefile', 'scripts/start.sh', 'alembic.ini'],
        'Add development utilities and database migration setup',
        hours_offset=7
    )
    plans.append(day1)
    
    # Day 2: Database & Vector Store
    day2 = CommitPlan(2, "Database & Vector Store", start + timedelta(days=1))
    day2.add_commit(
        ['app/core/db.py'],
        'Setup PostgreSQL connection, pooling, and health checks',
        hours_offset=1
    )
    day2.add_commit(
        ['alembic/versions/'],
        'Create Alembic migrations framework for database schema',
        hours_offset=2.5
    )
    day2.add_commit(
        ['app/models/', 'app/core/db.py'],
        'Implement SQLAlchemy ORM models for agents, messages, and experiments',
        hours_offset=4
    )
    day2.add_commit(
        ['app/ingestion/processors/vector_store.py'],
        'Implement Qdrant vector store client with collection management',
        hours_offset=6
    )
    plans.append(day2)
    
    # Day 3: API Foundation
    day3 = CommitPlan(3, "API Foundation", start + timedelta(days=2))
    day3.add_commit(
        ['app/main.py', 'app/core/config.py'],
        'Initialize FastAPI application with configuration management',
        hours_offset=0.5
    )
    day3.add_commit(
        ['app/core/logging.py'],
        'Add structured logging with structlog and rotating file handlers',
        hours_offset=2
    )
    day3.add_commit(
        ['app/api/middleware.py'],
        'Implement CORS, request logging, rate limiting middleware',
        hours_offset=3.5
    )
    day3.add_commit(
        ['app/api/schemas.py', 'app/api/__init__.py'],
        'Create request/response schemas and API models',
        hours_offset=5
    )
    day3.add_commit(
        ['app/api/routes/'],
        'Add base API routes with health checks and admin endpoints',
        hours_offset=6.5
    )
    plans.append(day3)
    
    # Day 4: Agent Architecture
    day4 = CommitPlan(4, "Agent Architecture", start + timedelta(days=3))
    day4.add_commit(
        ['app/agent/state.py'],
        'Create agent state management with LangChain state schema',
        hours_offset=0.5
    )
    day4.add_commit(
        ['app/agent/graph.py'],
        'Implement agent graph foundation using LangGraph',
        hours_offset=2
    )
    day4.add_commit(
        ['app/agent/nodes/intent_classifier.py'],
        'Add intent classification node for routing decisions',
        hours_offset=3.5
    )
    day4.add_commit(
        ['app/agent/nodes/query_refiner.py', 'app/agent/nodes/routing_node.py'],
        'Implement query refinement and dynamic routing nodes',
        hours_offset=5
    )
    day4.add_commit(
        ['app/agent/nodes/reasoning_node.py'],
        'Add advanced reasoning node with multi-step problem solving',
        hours_offset=6
    )
    day4.add_commit(
        ['app/agent/nodes/retrieval_node.py'],
        'Implement retrieval node for RAG pipeline integration',
        hours_offset=7
    )
    day4.add_commit(
        ['app/agent/nodes/action_node.py', 'app/agent/nodes/safety_checker.py'],
        'Add action execution and safety checking nodes',
        hours_offset=8
    )
    plans.append(day4)
    
    # Day 5: Data Ingestion
    day5 = CommitPlan(5, "Data Ingestion Pipeline", start + timedelta(days=4))
    day5.add_commit(
        ['app/ingestion/sources/base.py'],
        'Create base data source connector interface',
        hours_offset=1
    )
    day5.add_commit(
        ['app/ingestion/sources/cfpb.py'],
        'Implement CFPB complaints data source connector',
        hours_offset=2.5
    )
    day5.add_commit(
        ['app/ingestion/sources/sec_edgar.py'],
        'Add SEC Edgar financial documents data source',
        hours_offset=4
    )
    day5.add_commit(
        ['app/ingestion/processors/chunker.py'],
        'Implement document chunking with overlap and sliding windows',
        hours_offset=5.5
    )
    day5.add_commit(
        ['app/ingestion/processors/embedder.py'],
        'Add embedding generation with batch processing',
        hours_offset=7
    )
    day5.add_commit(
        ['app/ingestion/pipeline.py'],
        'Create data ingestion pipeline orchestration',
        hours_offset=8.5
    )
    plans.append(day5)
    
    # Day 6: ML Models
    day6 = CommitPlan(6, "ML Models & Specialized Components", start + timedelta(days=5))
    day6.add_commit(
        ['app/validation/validator.py'],
        'Create PII detection model with Presidio and spaCy',
        hours_offset=0.5
    )
    day6.add_commit(
        ['app/models/dependencies.py'],
        'Add sentiment analysis model for complaint analysis',
        hours_offset=2
    )
    day6.add_commit(
        ['app/models/guardrails.py'],
        'Implement policy classification and product classification models',
        hours_offset=3.5
    )
    day6.add_commit(
        ['app/models/llm_factory.py'],
        'Create model factory and dependency injection system',
        hours_offset=5
    )
    day6.add_commit(
        ['app/retrieval/reranker.py', 'app/retrieval/context_assembler.py'],
        'Add semantic reranking and context assembly for RAG',
        hours_offset=6.5
    )
    plans.append(day6)
    
    # Day 7: Observability
    day7 = CommitPlan(7, "Observability & Monitoring", start + timedelta(days=6))
    day7.add_commit(
        ['app/observability/metrics.py'],
        'Setup Prometheus metrics collection with custom agents metrics',
        hours_offset=1
    )
    day7.add_commit(
        ['monitoring/prometheus/prometheus.yml'],
        'Add Prometheus configuration with scrape targets',
        hours_offset=2.5
    )
    day7.add_commit(
        ['monitoring/prometheus/alert_rules.yml'],
        'Create alert rules for system and application monitoring',
        hours_offset=4
    )
    day7.add_commit(
        ['monitoring/grafana/provisioning/', 'monitoring/grafana/dashboards/'],
        'Add Grafana provisioning configs and custom dashboards',
        hours_offset=5.5
    )
    day7.add_commit(
        ['app/observability/tracer.py'],
        'Implement distributed tracing with OpenTelemetry',
        hours_offset=7
    )
    plans.append(day7)
    
    # Day 8: Advanced Features
    day8 = CommitPlan(8, "Advanced Features", start + timedelta(days=7))
    day8.add_commit(
        ['app/experimentation/framework.py'],
        'Create A/B testing framework foundation',
        hours_offset=0.5
    )
    day8.add_commit(
        ['app/experimentation/analysis.py'],
        'Add statistical analysis engine for experiment results',
        hours_offset=2
    )
    day8.add_commit(
        ['app/experimentation/prompt_experiments.py'],
        'Implement prompt experimentation system',
        hours_offset=3.5
    )
    day8.add_commit(
        ['app/experimentation/integration.py', 'app/api/routes/experiments.py'],
        'Create A/B testing integration decorators and REST API',
        hours_offset=5
    )
    day8.add_commit(
        ['app/mlops/model_registry.py'],
        'Implement MLOps model registry with versioning',
        hours_offset=6
    )
    day8.add_commit(
        ['app/mlops/feedback_collector.py', 'app/mlops/data_processor.py'],
        'Add feedback collection and automated data processing',
        hours_offset=7.5
    )
    day8.add_commit(
        ['app/integrations/salesforce.py'],
        'Implement Salesforce CRM integration with OAuth2',
        hours_offset=9
    )
    plans.append(day8)
    
    # Day 9: Testing & CI/CD
    day9 = CommitPlan(9, "Testing & CI/CD", start + timedelta(days=8))
    day9.add_commit(
        ['pytest.ini', 'tests/conftest.py'],
        'Setup pytest configuration with fixtures',
        hours_offset=1
    )
    day9.add_commit(
        ['tests/models/test_pii_detector.py'],
        'Add unit tests for PII detection model',
        hours_offset=2.5
    )
    day9.add_commit(
        ['tests/models/test_sentiment_analyzer.py', 'tests/models/test_product_classifier.py'],
        'Add tests for sentiment and product classification',
        hours_offset=4
    )
    day9.add_commit(
        ['tests/integration/test_models_integration.py'],
        'Create integration tests for model pipeline',
        hours_offset=5.5
    )
    day9.add_commit(
        ['tests/api/test_chat_endpoint.py', 'tests/api/test_admin_endpoint.py'],
        'Add API endpoint tests with mocked services',
        hours_offset=7
    )
    day9.add_commit(
        ['.github/workflows/tests.yml'],
        'Create GitHub Actions CI/CD workflow for automated testing',
        hours_offset=8.5
    )
    plans.append(day9)
    
    # Day 10: Analytics & Documentation
    day10 = CommitPlan(10, "Analytics & Documentation", start + timedelta(days=9))
    day10.add_commit(
        ['app/analytics/collector.py', 'app/analytics/metrics.py'],
        'Create analytics data collector and metrics processor',
        hours_offset=0.5
    )
    day10.add_commit(
        ['app/analytics/quality_scorer.py'],
        'Implement quality scoring algorithm with multi-factor analysis',
        hours_offset=2
    )
    day10.add_commit(
        ['app/analytics/dashboard.py', 'app/analytics/visualizer.py'],
        'Add custom dashboard generation and visualization utilities',
        hours_offset=3.5
    )
    day10.add_commit(
        ['app/api/routes/analytics.py'],
        'Create analytics REST API endpoints',
        hours_offset=5
    )
    day10.add_commit(
        ['frontend/', 'app/main.py'],
        'Initialize React frontend with chat UI and components',
        hours_offset=6
    )
    day10.add_commit(
        ['README.md', 'ARCHITECTURE.md'],
        'Write comprehensive documentation and architecture guide',
        hours_offset=8
    )
    day10.add_commit(
        ['DEPLOYMENT.md', 'LAUNCH_SUMMARY.md'],
        'Add deployment guide and production launch summary',
        hours_offset=9.5
    )
    plans.append(day10)
    
    return plans

def simulate_commits(plans: List[CommitPlan], dry_run: bool = True):
    """Simulate or execute the commits"""
    
    total_commits = sum(len(plan.commits) for plan in plans)
    print(f"\n📋 Commit Plan: {len(plans)} days, {total_commits} commits total\n")
    
    for plan in plans:
        print(f"Day {plan.day}: {plan.theme}")
        print(f"  Start: {plan.start_time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        
        for i, commit in enumerate(plan.commits, 1):
            print(f"  Commit {i}:")
            print(f"    Time: {commit['timestamp']}")
            print(f"    Message: {commit['message']}")
            print(f"    Files: {', '.join(commit['files'][:3])}")
            if len(commit['files']) > 3:
                print(f"             + {len(commit['files']) - 3} more files")
            print()
    
    if not dry_run:
        print("⚠️  Execute commits with:")
        print("   python scripts/create_diverse_commits.py --execute --start-date YYYY-MM-DD\n")

def main():
    parser = argparse.ArgumentParser(
        description='Create diverse commits across multiple days for authentic GitHub history'
    )
    parser.add_argument(
        '--start-date',
        type=str,
        default=(datetime.now() - timedelta(days=10)).strftime('%Y-%m-%d'),
        help='Start date for commits (YYYY-MM-DD)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        default=True,
        help='Show plan without executing (default: True)'
    )
    parser.add_argument(
        '--execute',
        action='store_true',
        help='Actually execute the commits'
    )
    parser.add_argument(
        '--output',
        type=str,
        help='Save plan to JSON file'
    )
    
    args = parser.parse_args()
    
    plans = get_commit_plans(args.start_date)
    
    # Save to JSON if requested
    if args.output:
        output_data = []
        for plan in plans:
            for commit in plan.commits:
                output_data.append({
                    'day': plan.day,
                    'theme': plan.theme,
                    'timestamp': commit['timestamp'],
                    'message': commit['message'],
                    'files': commit['files']
                })
        
        with open(args.output, 'w') as f:
            json.dump(output_data, f, indent=2)
        print(f"✅ Commit plan saved to {args.output}\n")
    
    # Show plan
    simulate_commits(plans, dry_run=not args.execute)
    
    if args.execute:
        print("\n⚠️  WARNING: You can implement this manually following GITHUB_COMMIT_STRATEGY.md\n")
        print("Manual process ensures authenticity and gives you control over each commit.\n")

if __name__ == '__main__':
    main()
