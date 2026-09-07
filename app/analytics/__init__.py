"""
Advanced Analytics Module for Financial AI Agent.

This module provides comprehensive analytics capabilities including:
- Custom dashboard generation
- Quality metrics calculation
- Business intelligence insights
- Performance trend analysis
- Anomaly detection
- Predictive analytics
"""

from .dashboard_builder import DashboardBuilder
from .quality_metrics import QualityMetricsEngine
from .business_intelligence import BusinessIntelligenceEngine
from .anomaly_detector import AnomalyDetector
from .predictive_analytics import PredictiveAnalytics
from .reports import ReportGenerator

__all__ = [
    "DashboardBuilder",
    "QualityMetricsEngine", 
    "BusinessIntelligenceEngine",
    "AnomalyDetector",
    "PredictiveAnalytics",
    "ReportGenerator"
]