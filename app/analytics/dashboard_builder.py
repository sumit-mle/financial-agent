"""
Dynamic Dashboard Builder for Financial AI Agent.

Creates custom Grafana dashboards based on specified metrics and requirements.
Supports automatic dashboard generation, template management, and real-time updates.
"""
import json
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Union
from pathlib import Path
from dataclasses import dataclass, asdict
from enum import Enum

from app.core.logging import get_logger
from app.core.config import settings
from app.observability.metrics import (
    agent_requests_total, agent_response_time_seconds, agent_response_confidence,
    model_inference_time, safety_violations, customer_satisfaction
)

logger = get_logger(__name__)


class PanelType(Enum):
    """Grafana panel types."""
    STAT = "stat"
    GRAPH = "graph"
    TIMESERIES = "timeseries"
    HEATMAP = "heatmap"
    TABLE = "table"
    PIECHART = "piechart"
    BARGRAPH = "bargraph"
    SINGLESTAT = "singlestat"


class TimeRange(Enum):
    """Time range options."""
    HOUR = "1h"
    DAY = "24h"
    WEEK = "7d"
    MONTH = "30d"
    QUARTER = "90d"


@dataclass
class PanelConfig:
    """Configuration for a dashboard panel."""
    title: str
    panel_type: PanelType
    query: str
    description: str = ""
    unit: str = ""
    width: int = 6
    height: int = 8
    thresholds: List[Dict[str, Any]] = None
    colors: List[str] = None
    legend: bool = True
    
    def __post_init__(self):
        if self.thresholds is None:
            self.thresholds = []
        if self.colors is None:
            self.colors = ["green", "yellow", "red"]


@dataclass 
class DashboardConfig:
    """Configuration for a complete dashboard."""
    title: str
    description: str
    tags: List[str]
    panels: List[PanelConfig]
    refresh_interval: str = "30s"
    time_range: TimeRange = TimeRange.HOUR
    auto_refresh: bool = True


class DashboardBuilder:
    """
    Dynamic dashboard builder for creating custom Grafana dashboards.
    
    Features:
    - Template-based dashboard generation
    - Custom panel configurations
    - Automatic layout optimization
    - Real-time dashboard updates
    - Business-specific dashboard presets
    - A/B testing dashboard integration
    - MLOps pipeline dashboards
    """
    
    def __init__(self):
        self.dashboards_path = Path("monitoring/grafana/dashboards")
        self.dashboards_path.mkdir(parents=True, exist_ok=True)
        
        # Predefined dashboard templates
        self.templates = {
            "business_overview": self._create_business_overview_template(),
            "model_performance": self._create_model_performance_template(),
            "customer_experience": self._create_customer_experience_template(),
            "operational_health": self._create_operational_health_template(),
            "ab_testing": self._create_ab_testing_template(),
            "mlops": self._create_mlops_template(),
            "security_compliance": self._create_security_template(),
            "financial_insights": self._create_financial_insights_template()
        }
    
    async def create_dashboard(self, 
                             config: DashboardConfig,
                             filename: Optional[str] = None) -> str:
        """Create a custom dashboard from configuration."""
        
        if filename is None:
            filename = f"{config.title.lower().replace(' ', '_')}_dashboard.json"
        
        dashboard = self._build_dashboard_json(config)
        
        dashboard_file = self.dashboards_path / filename
        
        with open(dashboard_file, 'w') as f:
            json.dump(dashboard, f, indent=2)
        
        logger.info(f"Created dashboard: {filename}")
        
        return str(dashboard_file)
    
    async def create_from_template(self, 
                                 template_name: str,
                                 customizations: Optional[Dict[str, Any]] = None) -> str:
        """Create dashboard from predefined template."""
        
        if template_name not in self.templates:
            raise ValueError(f"Template {template_name} not found")
        
        config = self.templates[template_name]
        
        # Apply customizations
        if customizations:
            config = self._apply_customizations(config, customizations)
        
        filename = f"{template_name}_dashboard.json"
        return await self.create_dashboard(config, filename)
    
    async def update_dashboard(self, 
                              filename: str, 
                              updates: Dict[str, Any]) -> bool:
        """Update existing dashboard with new configuration."""
        
        dashboard_file = self.dashboards_path / filename
        
        if not dashboard_file.exists():
            logger.error(f"Dashboard file not found: {filename}")
            return False
        
        try:
            with open(dashboard_file, 'r') as f:
                dashboard = json.load(f)
            
            # Apply updates
            dashboard = self._apply_dashboard_updates(dashboard, updates)
            
            with open(dashboard_file, 'w') as f:
                json.dump(dashboard, f, indent=2)
            
            logger.info(f"Updated dashboard: {filename}")
            return True
            
        except Exception as e:
            logger.error(f"Error updating dashboard {filename}: {e}")
            return False
    
    def _build_dashboard_json(self, config: DashboardConfig) -> Dict[str, Any]:
        """Build complete Grafana dashboard JSON."""
        
        dashboard = {
            "dashboard": {
                "id": None,
                "title": config.title,
                "description": config.description,
                "tags": config.tags,
                "timezone": "browser",
                "refresh": config.refresh_interval,
                "time": {
                    "from": f"now-{config.time_range.value}",
                    "to": "now"
                },
                "panels": [],
                "schemaVersion": 30,
                "version": 1
            }
        }
        
        # Add panels with automatic positioning
        x_pos = 0
        y_pos = 0
        row_height = 0
        
        for i, panel_config in enumerate(config.panels):
            panel = self._build_panel_json(panel_config, i + 1)
            
            # Auto-position panels
            panel["gridPos"] = {
                "h": panel_config.height,
                "w": panel_config.width,
                "x": x_pos,
                "y": y_pos
            }
            
            # Update position for next panel
            x_pos += panel_config.width
            row_height = max(row_height, panel_config.height)
            
            # Move to next row if needed
            if x_pos >= 24:  # Grafana uses 24-unit grid
                x_pos = 0
                y_pos += row_height
                row_height = 0
            
            dashboard["dashboard"]["panels"].append(panel)
        
        return dashboard
    
    def _build_panel_json(self, config: PanelConfig, panel_id: int) -> Dict[str, Any]:
        """Build individual panel JSON."""
        
        panel = {
            "id": panel_id,
            "title": config.title,
            "type": config.panel_type.value,
            "description": config.description,
            "targets": [{
                "expr": config.query,
                "refId": "A"
            }],
            "fieldConfig": {
                "defaults": {
                    "color": {"mode": "palette-classic"},
                    "custom": {"drawStyle": "line"},
                    "thresholds": {"steps": config.thresholds}
                }
            }
        }
        
        # Add unit if specified
        if config.unit:
            panel["fieldConfig"]["defaults"]["unit"] = config.unit
        
        # Panel-specific configurations
        if config.panel_type == PanelType.STAT:
            panel["fieldConfig"]["defaults"]["mappings"] = []
            
        elif config.panel_type == PanelType.TIMESERIES:
            panel["fieldConfig"]["defaults"]["custom"] = {
                "drawStyle": "line",
                "lineInterpolation": "linear",
                "barAlignment": 0,
                "lineWidth": 1,
                "fillOpacity": 0.1,
                "gradientMode": "none",
                "spanNulls": False,
                "insertNulls": False,
                "showPoints": "auto",
                "pointSize": 5
            }
            
        elif config.panel_type == PanelType.PIECHART:
            panel["options"] = {
                "pieType": "pie",
                "reduceOptions": {
                    "values": False,
                    "calcs": ["lastNotNull"],
                    "fields": ""
                },
                "legend": {"displayMode": "visible" if config.legend else "hidden"}
            }
        
        return panel
    
    def _create_business_overview_template(self) -> DashboardConfig:
        """Create business overview dashboard template."""
        
        panels = [
            PanelConfig(
                title="Total Requests",
                panel_type=PanelType.STAT,
                query="sum(rate(agent_requests_total[5m]))",
                description="Requests per second across all agents",
                unit="reqps",
                thresholds=[
                    {"color": "green", "value": None},
                    {"color": "yellow", "value": 10},
                    {"color": "red", "value": 50}
                ]
            ),
            PanelConfig(
                title="Success Rate",
                panel_type=PanelType.STAT,
                query='sum(rate(agent_requests_total{outcome="success"}[5m])) / sum(rate(agent_requests_total[5m])) * 100',
                description="Percentage of successful requests",
                unit="percent",
                thresholds=[
                    {"color": "red", "value": None},
                    {"color": "yellow", "value": 95},
                    {"color": "green", "value": 99}
                ]
            ),
            PanelConfig(
                title="Customer Satisfaction",
                panel_type=PanelType.STAT,
                query="avg(customer_satisfaction_rating)",
                description="Average customer satisfaction rating",
                unit="short",
                thresholds=[
                    {"color": "red", "value": None},
                    {"color": "yellow", "value": 3.5},
                    {"color": "green", "value": 4.0}
                ]
            ),
            PanelConfig(
                title="Escalation Rate",
                panel_type=PanelType.STAT,
                query='sum(rate(agent_requests_total{escalated="true"}[5m])) / sum(rate(agent_requests_total[5m])) * 100',
                description="Percentage of requests escalated to humans",
                unit="percent",
                thresholds=[
                    {"color": "green", "value": None},
                    {"color": "yellow", "value": 5},
                    {"color": "red", "value": 15}
                ]
            ),
            PanelConfig(
                title="Request Volume by Intent",
                panel_type=PanelType.TIMESERIES,
                query="sum(rate(agent_requests_total[5m])) by (intent)",
                description="Request volume over time by detected intent",
                width=12,
                height=10
            ),
            PanelConfig(
                title="Response Time Distribution",
                panel_type=PanelType.HEATMAP,
                query="rate(agent_response_time_seconds_bucket[5m])",
                description="Distribution of response times",
                unit="s",
                width=12,
                height=10
            )
        ]
        
        return DashboardConfig(
            title="Business Overview",
            description="High-level business metrics for Financial AI Agent",
            tags=["business", "overview", "kpi"],
            panels=panels,
            time_range=TimeRange.DAY
        )
    
    def _create_model_performance_template(self) -> DashboardConfig:
        """Create model performance dashboard template."""
        
        panels = [
            PanelConfig(
                title="Model Inference Time",
                panel_type=PanelType.TIMESERIES,
                query="histogram_quantile(0.95, rate(model_inference_time_seconds_bucket[5m])) by (model_type)",
                description="95th percentile inference time by model type",
                unit="s",
                width=12
            ),
            PanelConfig(
                title="Model Accuracy Trend",
                panel_type=PanelType.TIMESERIES,
                query="avg(agent_response_confidence) by (intent)",
                description="Average confidence scores by intent",
                unit="percent",
                width=12
            ),
            PanelConfig(
                title="Model Predictions by Type",
                panel_type=PanelType.PIECHART,
                query="sum(rate(model_predictions_total[5m])) by (model_type)",
                description="Distribution of predictions by model type",
                width=6
            ),
            PanelConfig(
                title="Safety Violations",
                panel_type=PanelType.STAT,
                query="sum(rate(safety_violations_total[5m]))",
                description="Safety violations per second",
                unit="vps",
                width=6,
                thresholds=[
                    {"color": "green", "value": None},
                    {"color": "yellow", "value": 0.1},
                    {"color": "red", "value": 1.0}
                ]
            )
        ]
        
        return DashboardConfig(
            title="Model Performance",
            description="AI model performance and quality metrics",
            tags=["models", "performance", "ai"],
            panels=panels
        )
    
    def _create_customer_experience_template(self) -> DashboardConfig:
        """Create customer experience dashboard template."""
        
        panels = [
            PanelConfig(
                title="Satisfaction Distribution",
                panel_type=PanelType.BARGRAPH,
                query="sum(rate(customer_satisfaction_rating_bucket[5m])) by (le)",
                description="Distribution of customer satisfaction ratings",
                width=8
            ),
            PanelConfig(
                title="Average Session Length", 
                panel_type=PanelType.STAT,
                query="avg(conversation_turns_total)",
                description="Average number of turns per conversation",
                unit="turns",
                width=4
            ),
            PanelConfig(
                title="Resolution Rate by Intent",
                panel_type=PanelType.TABLE,
                query='sum(rate(agent_requests_total{escalated="false"}[5m])) by (intent) / sum(rate(agent_requests_total[5m])) by (intent)',
                description="Percentage of requests resolved without escalation",
                width=12
            )
        ]
        
        return DashboardConfig(
            title="Customer Experience",
            description="Customer satisfaction and experience metrics",
            tags=["customer", "experience", "satisfaction"],
            panels=panels
        )
    
    def _create_operational_health_template(self) -> DashboardConfig:
        """Create operational health dashboard template."""
        
        panels = [
            PanelConfig(
                title="System Health Score",
                panel_type=PanelType.STAT,
                query="(avg(up) + (1 - avg(rate(agent_requests_total{outcome=\"error\"}[5m])) / avg(rate(agent_requests_total[5m])))) / 2 * 100",
                description="Overall system health percentage",
                unit="percent",
                width=6,
                thresholds=[
                    {"color": "red", "value": None},
                    {"color": "yellow", "value": 95},
                    {"color": "green", "value": 99}
                ]
            ),
            PanelConfig(
                title="Error Rate",
                panel_type=PanelType.TIMESERIES,
                query='sum(rate(agent_requests_total{outcome="error"}[5m])) / sum(rate(agent_requests_total[5m])) * 100',
                description="Error rate over time",
                unit="percent",
                width=6
            ),
            PanelConfig(
                title="Vector DB Operations",
                panel_type=PanelType.TIMESERIES,
                query="sum(rate(vector_db_operations_total[5m])) by (operation, status)",
                description="Vector database operation rates",
                width=12
            )
        ]
        
        return DashboardConfig(
            title="Operational Health",
            description="System health and operational metrics",
            tags=["operations", "health", "system"],
            panels=panels
        )
    
    def _create_ab_testing_template(self) -> DashboardConfig:
        """Create A/B testing dashboard template."""
        
        panels = [
            PanelConfig(
                title="Experiment Traffic Distribution",
                panel_type=PanelType.PIECHART,
                query="sum(rate(experiment_assignments_total[5m])) by (variant)",
                description="Traffic distribution across experiment variants",
                width=6
            ),
            PanelConfig(
                title="Conversion Rate by Variant",
                panel_type=PanelType.BARGRAPH,
                query="sum(rate(experiment_conversions_total[5m])) by (variant) / sum(rate(experiment_assignments_total[5m])) by (variant) * 100",
                description="Conversion rates for each experiment variant",
                unit="percent",
                width=6
            ),
            PanelConfig(
                title="Statistical Significance",
                panel_type=PanelType.TABLE,
                query="experiment_statistical_significance",
                description="P-values and confidence intervals for experiments",
                width=12
            )
        ]
        
        return DashboardConfig(
            title="A/B Testing Analytics",
            description="Experiment performance and statistical analysis",
            tags=["experiments", "ab-testing", "analytics"],
            panels=panels
        )
    
    def _create_mlops_template(self) -> DashboardConfig:
        """Create MLOps pipeline dashboard template."""
        
        panels = [
            PanelConfig(
                title="Model Deployments",
                panel_type=PanelType.TIMESERIES,
                query="sum(rate(mlops_model_deployments_total[5m])) by (model_type, deployment_type)",
                description="Model deployment frequency",
                width=8
            ),
            PanelConfig(
                title="Active Model Versions",
                panel_type=PanelType.STAT,
                query="sum(mlops_active_model_versions)",
                description="Number of active model versions",
                width=4
            ),
            PanelConfig(
                title="Training Job Status",
                panel_type=PanelType.TABLE,
                query="mlops_training_jobs_status",
                description="Current status of training jobs",
                width=6
            ),
            PanelConfig(
                title="Model Rollbacks",
                panel_type=PanelType.TIMESERIES,
                query="sum(rate(mlops_model_rollbacks_total[5m])) by (reason)",
                description="Model rollback frequency by reason",
                width=6
            )
        ]
        
        return DashboardConfig(
            title="MLOps Pipeline",
            description="Model lifecycle and deployment metrics",
            tags=["mlops", "models", "deployment"],
            panels=panels
        )
    
    def _create_security_template(self) -> DashboardConfig:
        """Create security and compliance dashboard template."""
        
        panels = [
            PanelConfig(
                title="PII Detections",
                panel_type=PanelType.TIMESERIES,
                query="sum(rate(pii_detections_total[5m])) by (pii_type)",
                description="PII detection frequency by type",
                width=8
            ),
            PanelConfig(
                title="Safety Violations",
                panel_type=PanelType.STAT,
                query="sum(rate(safety_violations_total[1h]))",
                description="Safety violations in the last hour",
                width=4,
                thresholds=[
                    {"color": "green", "value": None},
                    {"color": "yellow", "value": 5},
                    {"color": "red", "value": 20}
                ]
            ),
            PanelConfig(
                title="Compliance Score",
                panel_type=PanelType.STAT,
                query="(1 - sum(rate(safety_violations_total[1h])) / sum(rate(agent_requests_total[1h]))) * 100",
                description="Compliance percentage",
                unit="percent",
                width=6
            ),
            PanelConfig(
                title="Security Event Timeline",
                panel_type=PanelType.TABLE,
                query="increase(safety_violations_total[1h])",
                description="Recent security events",
                width=6
            )
        ]
        
        return DashboardConfig(
            title="Security & Compliance",
            description="Security violations and compliance metrics",
            tags=["security", "compliance", "safety"],
            panels=panels
        )
    
    def _create_financial_insights_template(self) -> DashboardConfig:
        """Create financial insights dashboard template."""
        
        panels = [
            PanelConfig(
                title="Request Volume by Financial Product",
                panel_type=PanelType.PIECHART,
                query='sum(rate(agent_requests_total[5m])) by (intent) and on() (label_replace({__name__=~".*"}, "intent", "$1", "intent", ".*(loan|credit|mortgage|investment|insurance).*"))',
                description="Distribution of requests by financial product",
                width=6
            ),
            PanelConfig(
                title="High-Value Customer Interactions",
                panel_type=PanelType.STAT,
                query='sum(rate(agent_requests_total{intent=~".*investment.*|.*loan.*"}[5m]))',
                description="Interactions related to high-value products",
                unit="reqps",
                width=6
            ),
            PanelConfig(
                title="Fraud Detection Rate",
                panel_type=PanelType.TIMESERIES,
                query='sum(rate(model_predictions_total{model_type="fraud_detection", prediction="fraud"}[5m])) / sum(rate(model_predictions_total{model_type="fraud_detection"}[5m])) * 100',
                description="Percentage of interactions flagged as potential fraud",
                unit="percent",
                width=12
            )
        ]
        
        return DashboardConfig(
            title="Financial Insights",
            description="Financial sector specific metrics and insights",
            tags=["financial", "business", "insights"],
            panels=panels
        )
    
    def _apply_customizations(self, 
                            config: DashboardConfig, 
                            customizations: Dict[str, Any]) -> DashboardConfig:
        """Apply customizations to dashboard configuration."""
        
        # Create a copy to avoid modifying the original
        custom_config = DashboardConfig(
            title=customizations.get("title", config.title),
            description=customizations.get("description", config.description),
            tags=customizations.get("tags", config.tags),
            panels=config.panels.copy(),
            refresh_interval=customizations.get("refresh_interval", config.refresh_interval),
            time_range=TimeRange(customizations.get("time_range", config.time_range.value)),
            auto_refresh=customizations.get("auto_refresh", config.auto_refresh)
        )
        
        # Apply panel customizations
        if "panels" in customizations:
            panel_updates = customizations["panels"]
            for i, panel_update in enumerate(panel_updates):
                if i < len(custom_config.panels):
                    panel = custom_config.panels[i]
                    for key, value in panel_update.items():
                        if hasattr(panel, key):
                            setattr(panel, key, value)
        
        return custom_config
    
    def _apply_dashboard_updates(self, 
                               dashboard: Dict[str, Any], 
                               updates: Dict[str, Any]) -> Dict[str, Any]:
        """Apply updates to existing dashboard JSON."""
        
        # Update dashboard-level properties
        for key in ["title", "description", "refresh", "tags"]:
            if key in updates:
                dashboard["dashboard"][key] = updates[key]
        
        # Update time range
        if "time_range" in updates:
            dashboard["dashboard"]["time"] = {
                "from": f"now-{updates['time_range']}",
                "to": "now"
            }
        
        # Update panels if specified
        if "panels" in updates:
            panel_updates = updates["panels"]
            for panel_id, panel_update in panel_updates.items():
                for panel in dashboard["dashboard"]["panels"]:
                    if panel["id"] == int(panel_id):
                        panel.update(panel_update)
                        break
        
        return dashboard
    
    async def get_dashboard_list(self) -> List[Dict[str, str]]:
        """Get list of available dashboards."""
        
        dashboards = []
        
        for file_path in self.dashboards_path.glob("*.json"):
            try:
                with open(file_path, 'r') as f:
                    dashboard_data = json.load(f)
                
                dashboards.append({
                    "filename": file_path.name,
                    "title": dashboard_data.get("dashboard", {}).get("title", "Unknown"),
                    "description": dashboard_data.get("dashboard", {}).get("description", ""),
                    "tags": dashboard_data.get("dashboard", {}).get("tags", [])
                })
                
            except Exception as e:
                logger.warning(f"Error reading dashboard {file_path}: {e}")
        
        return dashboards
    
    async def export_dashboard_config(self, filename: str) -> Optional[Dict[str, Any]]:
        """Export dashboard configuration for backup or sharing."""
        
        dashboard_file = self.dashboards_path / filename
        
        if not dashboard_file.exists():
            return None
        
        try:
            with open(dashboard_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error exporting dashboard {filename}: {e}")
            return None


# Global dashboard builder instance
_builder_instance = None

async def get_dashboard_builder() -> DashboardBuilder:
    """Get global dashboard builder instance."""
    global _builder_instance
    if _builder_instance is None:
        _builder_instance = DashboardBuilder()
    return _builder_instance