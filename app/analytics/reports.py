"""
Report Generator for Financial AI Agent Analytics.

Generates comprehensive reports in multiple formats (PDF, HTML, JSON)
with executive summaries, detailed analytics, and actionable insights.
"""
import asyncio
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass, asdict
from enum import Enum
from pathlib import Path
import base64
from io import BytesIO

from app.core.logging import get_logger
from app.core.config import settings
from app.analytics.quality_metrics import get_quality_metrics_engine
from app.analytics.business_intelligence import get_business_intelligence_engine
from app.analytics.anomaly_detector import get_anomaly_detector
from app.analytics.predictive_analytics import get_predictive_analytics

logger = get_logger(__name__)


class ReportType(Enum):
    """Types of reports that can be generated."""
    EXECUTIVE_SUMMARY = "executive_summary"
    QUALITY_METRICS = "quality_metrics"
    BUSINESS_INTELLIGENCE = "business_intelligence"
    ANOMALY_DETECTION = "anomaly_detection"
    PREDICTIVE_ANALYTICS = "predictive_analytics"
    COMPREHENSIVE = "comprehensive"


class ReportFormat(Enum):
    """Report output formats."""
    JSON = "json"
    HTML = "html"
    PDF = "pdf"
    CSV = "csv"


@dataclass
class ReportConfig:
    """Configuration for report generation."""
    report_type: ReportType
    format: ReportFormat
    period_days: int
    include_charts: bool = True
    include_recommendations: bool = True
    include_raw_data: bool = False
    custom_metrics: Optional[List[str]] = None
    
    def __post_init__(self):
        if self.custom_metrics is None:
            self.custom_metrics = []


@dataclass
class GeneratedReport:
    """Generated report with metadata."""
    report_id: str
    report_type: ReportType
    format: ReportFormat
    generated_at: datetime
    period_start: datetime
    period_end: datetime
    content: Union[str, bytes, Dict[str, Any]]
    metadata: Dict[str, Any]
    file_path: Optional[str] = None
    
    @property
    def content_size(self) -> int:
        """Get content size in bytes."""
        if isinstance(self.content, str):
            return len(self.content.encode('utf-8'))
        elif isinstance(self.content, bytes):
            return len(self.content)
        elif isinstance(self.content, dict):
            return len(json.dumps(self.content).encode('utf-8'))
        return 0


class ReportGenerator:
    """
    Comprehensive report generator for analytics data.
    
    Features:
    - Multiple report types and formats
    - Executive dashboard reports
    - Detailed technical reports
    - Custom report templates
    - Automated report scheduling
    - Export capabilities
    - Chart and visualization generation
    """
    
    def __init__(self):
        self.reports_dir = Path("reports")
        self.reports_dir.mkdir(exist_ok=True)
        
        self.templates = self._load_report_templates()
        self.generated_reports = {}
        
    def _load_report_templates(self) -> Dict[str, str]:
        """Load report templates for different formats."""
        
        # HTML template for executive summary
        html_executive_template = """
        <!DOCTYPE html>
        <html>
        <head>
            <title>Financial AI Agent - Executive Summary</title>
            <style>
                body { font-family: Arial, sans-serif; margin: 20px; }
                .header { background-color: #2c3e50; color: white; padding: 20px; border-radius: 5px; }
                .metric { background-color: #ecf0f1; padding: 15px; margin: 10px 0; border-radius: 5px; }
                .metric-value { font-size: 24px; font-weight: bold; color: #3498db; }
                .recommendation { background-color: #e8f5e8; padding: 15px; margin: 10px 0; border-left: 4px solid #27ae60; }
                .alert { background-color: #fdf2e9; padding: 15px; margin: 10px 0; border-left: 4px solid #f39c12; }
                .critical { background-color: #fadbd8; padding: 15px; margin: 10px 0; border-left: 4px solid #e74c3c; }
                table { width: 100%; border-collapse: collapse; margin: 20px 0; }
                th, td { border: 1px solid #ddd; padding: 12px; text-align: left; }
                th { background-color: #34495e; color: white; }
            </style>
        </head>
        <body>
            <div class="header">
                <h1>Financial AI Agent - Executive Summary</h1>
                <p>Report Period: {period_start} to {period_end}</p>
                <p>Generated: {generated_at}</p>
            </div>
            
            <h2>Key Performance Indicators</h2>
            {kpi_section}
            
            <h2>Quality Overview</h2>
            {quality_section}
            
            <h2>Business Impact</h2>
            {business_section}
            
            <h2>Recommendations</h2>
            {recommendations_section}
            
            <h2>Alerts & Anomalies</h2>
            {alerts_section}
        </body>
        </html>
        """
        
        return {
            "html_executive": html_executive_template,
            "html_detailed": html_executive_template  # Can be expanded later
        }
    
    async def generate_report(self, config: ReportConfig) -> GeneratedReport:
        """Generate a report based on configuration."""
        
        logger.info(f"Generating {config.report_type.value} report in {config.format.value} format")
        
        # Calculate report period
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(days=config.period_days)
        
        # Generate report ID
        report_id = f"{config.report_type.value}_{int(datetime.utcnow().timestamp())}"
        
        # Collect data based on report type
        report_data = await self._collect_report_data(config, start_time, end_time)
        
        # Generate content in requested format
        content = await self._generate_content(config, report_data)
        
        # Create report object
        report = GeneratedReport(
            report_id=report_id,
            report_type=config.report_type,
            format=config.format,
            generated_at=datetime.utcnow(),
            period_start=start_time,
            period_end=end_time,
            content=content,
            metadata={
                "period_days": config.period_days,
                "data_points": len(report_data.get("raw_metrics", [])),
                "includes_charts": config.include_charts,
                "includes_recommendations": config.include_recommendations
            }
        )
        
        # Save report to file if not JSON
        if config.format != ReportFormat.JSON:
            file_path = await self._save_report_to_file(report)
            report.file_path = file_path
        
        # Store in cache
        self.generated_reports[report_id] = report
        
        logger.info(f"Generated report {report_id} with {report.content_size} bytes")
        
        return report
    
    async def _collect_report_data(self, 
                                 config: ReportConfig, 
                                 start_time: datetime, 
                                 end_time: datetime) -> Dict[str, Any]:
        """Collect data needed for the report."""
        
        data = {}
        
        # Always collect quality metrics
        quality_engine = await get_quality_metrics_engine()
        quality_report = await quality_engine.calculate_quality_report(
            period_hours=config.period_days * 24
        )
        data["quality"] = quality_report
        
        # Collect data based on report type
        if config.report_type in [ReportType.BUSINESS_INTELLIGENCE, ReportType.COMPREHENSIVE]:
            bi_engine = await get_business_intelligence_engine()
            bi_report = await bi_engine.generate_business_intelligence_report(config.period_days)
            data["business_intelligence"] = bi_report
        
        if config.report_type in [ReportType.ANOMALY_DETECTION, ReportType.COMPREHENSIVE]:
            anomaly_detector = await get_anomaly_detector()
            anomaly_summary = await anomaly_detector.get_anomaly_summary()
            data["anomalies"] = anomaly_summary
        
        if config.report_type in [ReportType.PREDICTIVE_ANALYTICS, ReportType.COMPREHENSIVE]:
            predictive_engine = await get_predictive_analytics()
            predictive_insights = await predictive_engine.generate_predictive_insights()
            predictive_summary = await predictive_engine.get_predictive_summary()
            data["predictions"] = {
                "insights": predictive_insights,
                "summary": predictive_summary
            }
        
        return data
    
    async def _generate_content(self, 
                              config: ReportConfig, 
                              report_data: Dict[str, Any]) -> Union[str, bytes, Dict[str, Any]]:
        """Generate report content in the specified format."""
        
        if config.format == ReportFormat.JSON:
            return await self._generate_json_content(config, report_data)
        elif config.format == ReportFormat.HTML:
            return await self._generate_html_content(config, report_data)
        elif config.format == ReportFormat.PDF:
            return await self._generate_pdf_content(config, report_data)
        elif config.format == ReportFormat.CSV:
            return await self._generate_csv_content(config, report_data)
        else:
            raise ValueError(f"Unsupported format: {config.format}")
    
    async def _generate_json_content(self, 
                                   config: ReportConfig, 
                                   report_data: Dict[str, Any]) -> Dict[str, Any]:
        """Generate JSON format report content."""
        
        content = {
            "report_metadata": {
                "type": config.report_type.value,
                "generated_at": datetime.utcnow().isoformat(),
                "period_days": config.period_days,
                "version": "1.0"
            }
        }
        
        # Add data based on report type
        if config.report_type == ReportType.EXECUTIVE_SUMMARY:
            content.update(self._create_executive_summary_data(report_data))
            
        elif config.report_type == ReportType.QUALITY_METRICS:
            # Convert enums to strings for JSON serialization
            quality_report = report_data["quality"]
            quality_data = {
                "overall_score": quality_report.overall_score,
                "category_scores": {
                    cat.value: score for cat, score in quality_report.category_scores.items()
                },
                "individual_metrics": [
                    {
                        "metric_name": metric.metric_name,
                        "category": metric.category.value,
                        "value": metric.value,
                        "percentage": metric.percentage,
                        "trend": metric.trend.value,
                        "confidence_interval": metric.confidence_interval,
                        "sample_size": metric.sample_size,
                        "last_updated": metric.last_updated.isoformat(),
                        "description": metric.description
                    }
                    for metric in quality_report.individual_metrics
                ],
                "trends": {k: v.value if hasattr(v, 'value') else str(v) for k, v in quality_report.trends.items()},
                "recommendations": quality_report.recommendations,
                "report_period": [
                    quality_report.report_period[0].isoformat(),
                    quality_report.report_period[1].isoformat()
                ],
                "generated_at": quality_report.generated_at.isoformat()
            }
            content["quality_metrics"] = quality_data
            
        elif config.report_type == ReportType.BUSINESS_INTELLIGENCE:
            content["business_intelligence"] = asdict(report_data["business_intelligence"])
            
        elif config.report_type == ReportType.ANOMALY_DETECTION:
            content["anomaly_detection"] = report_data["anomalies"]
            
        elif config.report_type == ReportType.PREDICTIVE_ANALYTICS:
            content["predictive_analytics"] = {
                "insights": [asdict(insight) for insight in report_data["predictions"]["insights"]],
                "summary": report_data["predictions"]["summary"]
            }
            
        elif config.report_type == ReportType.COMPREHENSIVE:
            # Handle quality metrics with enum conversion
            quality_data = asdict(report_data["quality"])
            if "category_scores" in quality_data:
                quality_data["category_scores"] = {
                    cat.value if hasattr(cat, 'value') else str(cat): score 
                    for cat, score in report_data["quality"].category_scores.items()
                }
            content["quality_metrics"] = quality_data
            
            if "business_intelligence" in report_data:
                content["business_intelligence"] = asdict(report_data["business_intelligence"])
            if "anomalies" in report_data:
                content["anomaly_detection"] = report_data["anomalies"]
            if "predictions" in report_data:
                content["predictive_analytics"] = {
                    "insights": [asdict(insight) for insight in report_data["predictions"]["insights"]],
                    "summary": report_data["predictions"]["summary"]
                }
        
        return content
    
    async def _generate_html_content(self, 
                                   config: ReportConfig, 
                                   report_data: Dict[str, Any]) -> str:
        """Generate HTML format report content."""
        
        if config.report_type == ReportType.EXECUTIVE_SUMMARY:
            return await self._generate_executive_html(report_data)
        
        # For other types, generate a basic HTML structure
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Financial AI Agent - {config.report_type.value.title()}</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; }}
                .header {{ background-color: #2c3e50; color: white; padding: 20px; }}
                .section {{ margin: 20px 0; padding: 15px; border: 1px solid #ddd; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>Financial AI Agent - {config.report_type.value.title()}</h1>
                <p>Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}</p>
            </div>
            
            <div class="section">
                <h2>Report Data</h2>
                <pre>{json.dumps(report_data, indent=2, default=str)}</pre>
            </div>
        </body>
        </html>
        """
        
        return html_content
    
    async def _generate_executive_html(self, report_data: Dict[str, Any]) -> str:
        """Generate executive summary HTML report."""
        
        quality_report = report_data["quality"]
        
        # Generate KPI section
        kpi_html = f"""
        <div class="metric">
            <h3>Overall Quality Score</h3>
            <div class="metric-value">{quality_report.overall_score:.1f}%</div>
            <p>Current system quality assessment</p>
        </div>
        """
        
        # Add category scores
        for category, score in quality_report.category_scores.items():
            kpi_html += f"""
            <div class="metric">
                <h4>{category.value.title()}</h4>
                <div class="metric-value">{score:.1f}%</div>
            </div>
            """
        
        # Generate quality section
        quality_html = ""
        for metric in quality_report.individual_metrics[:5]:  # Top 5 metrics
            quality_html += f"""
            <div class="metric">
                <h4>{metric.metric_name}</h4>
                <div class="metric-value">{metric.percentage:.1f}%</div>
                <p>{metric.description}</p>
                <small>Trend: {metric.trend.value} | Confidence: {metric.confidence_interval}</small>
            </div>
            """
        
        # Generate business section
        business_html = ""
        if "business_intelligence" in report_data:
            bi_report = report_data["business_intelligence"]
            business_html = f"""
            <div class="metric">
                <h3>Financial Impact</h3>
                <div class="metric-value">${bi_report.financial_analysis.cost_savings + bi_report.financial_analysis.revenue_impact:,.0f}</div>
                <p>Monthly financial benefit (cost savings + revenue impact)</p>
            </div>
            <div class="metric">
                <h3>ROI</h3>
                <div class="metric-value">{bi_report.financial_analysis.roi_percentage:.0f}%</div>
                <p>Return on investment</p>
            </div>
            """
        
        # Generate recommendations
        recommendations_html = ""
        for i, rec in enumerate(quality_report.recommendations[:5]):
            recommendations_html += f"""
            <div class="recommendation">
                <strong>Recommendation {i+1}:</strong> {rec}
            </div>
            """
        
        # Generate alerts
        alerts_html = ""
        if "anomalies" in report_data:
            anomaly_data = report_data["anomalies"]
            for anomaly in anomaly_data.get("recent_anomalies", [])[:3]:
                severity_class = "critical" if anomaly["severity"] == "critical" else "alert"
                alerts_html += f"""
                <div class="{severity_class}">
                    <strong>{anomaly["title"]}</strong> (Severity: {anomaly["severity"]})
                    <p>Deviation: {anomaly["deviation_percentage"]:.1f}%</p>
                </div>
                """
        
        if not alerts_html:
            alerts_html = '<div class="metric">No critical alerts detected</div>'
        
        # Fill template
        template = self.templates["html_executive"]
        return template.format(
            period_start=quality_report.report_period[0].strftime('%Y-%m-%d'),
            period_end=quality_report.report_period[1].strftime('%Y-%m-%d'),
            generated_at=datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'),
            kpi_section=kpi_html,
            quality_section=quality_html,
            business_section=business_html,
            recommendations_section=recommendations_html,
            alerts_section=alerts_html
        )
    
    async def _generate_pdf_content(self, 
                                  config: ReportConfig, 
                                  report_data: Dict[str, Any]) -> bytes:
        """Generate PDF format report content."""
        
        # For now, generate HTML and indicate PDF conversion needed
        html_content = await self._generate_html_content(config, report_data)
        
        # In production, you would use a library like weasyprint or reportlab
        # For this demo, we'll return the HTML as bytes with a note
        pdf_placeholder = f"""
        PDF REPORT PLACEHOLDER
        
        This would contain the full PDF report generated from:
        {html_content[:500]}...
        
        To implement PDF generation, integrate a library like:
        - weasyprint (HTML/CSS to PDF)
        - reportlab (programmatic PDF creation)
        - puppeteer (headless browser PDF generation)
        """
        
        return pdf_placeholder.encode('utf-8')
    
    async def _generate_csv_content(self, 
                                  config: ReportConfig, 
                                  report_data: Dict[str, Any]) -> str:
        """Generate CSV format report content."""
        
        csv_lines = []
        
        # CSV header
        csv_lines.append("Metric,Value,Category,Trend,Confidence,Description")
        
        # Add quality metrics
        quality_report = report_data["quality"]
        for metric in quality_report.individual_metrics:
            csv_lines.append(f'"{metric.metric_name}",{metric.percentage},{metric.category.value},{metric.trend.value},{metric.confidence_interval[0]:.3f}-{metric.confidence_interval[1]:.3f},"{metric.description}"')
        
        return "\n".join(csv_lines)
    
    def _create_executive_summary_data(self, report_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create executive summary data structure."""
        
        quality_report = report_data["quality"]
        
        summary = {
            "executive_summary": {
                "overall_score": quality_report.overall_score,
                "key_metrics": [
                    {
                        "name": metric.metric_name,
                        "value": metric.percentage,
                        "trend": metric.trend.value
                    }
                    for metric in quality_report.individual_metrics[:5]
                ],
                "recommendations": quality_report.recommendations[:3],
                "generated_at": quality_report.generated_at.isoformat()
            }
        }
        
        # Add business data if available
        if "business_intelligence" in report_data:
            bi_report = report_data["business_intelligence"]
            summary["business_impact"] = {
                "monthly_savings": bi_report.financial_analysis.cost_savings,
                "revenue_impact": bi_report.financial_analysis.revenue_impact,
                "roi_percentage": bi_report.financial_analysis.roi_percentage,
                "key_insights": [
                    {
                        "title": insight.title,
                        "impact_level": insight.impact_level,
                        "confidence": insight.confidence_score
                    }
                    for insight in bi_report.key_insights[:3]
                ]
            }
        
        return summary
    
    async def _save_report_to_file(self, report: GeneratedReport) -> str:
        """Save report content to file."""
        
        # Determine file extension
        extension_map = {
            ReportFormat.HTML: ".html",
            ReportFormat.PDF: ".pdf", 
            ReportFormat.CSV: ".csv",
            ReportFormat.JSON: ".json"
        }
        
        extension = extension_map.get(report.format, ".txt")
        filename = f"{report.report_id}{extension}"
        file_path = self.reports_dir / filename
        
        # Write content to file
        if isinstance(report.content, bytes):
            with open(file_path, 'wb') as f:
                f.write(report.content)
        else:
            with open(file_path, 'w', encoding='utf-8') as f:
                if isinstance(report.content, dict):
                    json.dump(report.content, f, indent=2, default=str)
                else:
                    f.write(str(report.content))
        
        logger.info(f"Saved report to {file_path}")
        return str(file_path)
    
    async def get_report_list(self) -> List[Dict[str, Any]]:
        """Get list of generated reports."""
        
        reports = []
        
        for report_id, report in self.generated_reports.items():
            reports.append({
                "report_id": report_id,
                "type": report.report_type.value,
                "format": report.format.value,
                "generated_at": report.generated_at.isoformat(),
                "period_start": report.period_start.isoformat(),
                "period_end": report.period_end.isoformat(),
                "content_size": report.content_size,
                "file_path": report.file_path
            })
        
        # Sort by generation time, newest first
        reports.sort(key=lambda x: x["generated_at"], reverse=True)
        
        return reports
    
    async def get_report(self, report_id: str) -> Optional[GeneratedReport]:
        """Get a specific report by ID."""
        return self.generated_reports.get(report_id)
    
    async def delete_report(self, report_id: str) -> bool:
        """Delete a report from cache and filesystem."""
        
        if report_id not in self.generated_reports:
            return False
        
        report = self.generated_reports[report_id]
        
        # Delete file if exists
        if report.file_path and Path(report.file_path).exists():
            try:
                Path(report.file_path).unlink()
                logger.info(f"Deleted report file {report.file_path}")
            except Exception as e:
                logger.warning(f"Error deleting report file: {e}")
        
        # Remove from cache
        del self.generated_reports[report_id]
        
        logger.info(f"Deleted report {report_id}")
        return True
    
    async def schedule_report(self, 
                            config: ReportConfig, 
                            schedule_cron: str,
                            recipients: List[str]) -> str:
        """Schedule automatic report generation (placeholder for future implementation)."""
        
        # This would integrate with a task scheduler like Celery or APScheduler
        schedule_id = f"schedule_{int(datetime.utcnow().timestamp())}"
        
        logger.info(f"Report scheduling requested - ID: {schedule_id}")
        logger.info(f"Schedule: {schedule_cron}, Recipients: {recipients}")
        
        # Placeholder implementation
        return schedule_id
    
    async def export_report_data(self, 
                               report_id: str, 
                               target_format: ReportFormat) -> Optional[bytes]:
        """Export existing report to different format."""
        
        report = self.generated_reports.get(report_id)
        if not report:
            return None
        
        # Create new config with target format
        config = ReportConfig(
            report_type=report.report_type,
            format=target_format,
            period_days=1,  # Will be overridden by existing data
            include_charts=True,
            include_recommendations=True
        )
        
        # Convert content
        if isinstance(report.content, dict):
            new_content = await self._generate_content(config, {"quality": report.content})
        else:
            # For non-dict content, return as-is or convert appropriately
            new_content = report.content
        
        if isinstance(new_content, str):
            return new_content.encode('utf-8')
        elif isinstance(new_content, bytes):
            return new_content
        else:
            return json.dumps(new_content, default=str).encode('utf-8')


# Global report generator instance  
_report_generator_instance = None

async def get_report_generator() -> ReportGenerator:
    """Get global report generator instance."""
    global _report_generator_instance
    if _report_generator_instance is None:
        _report_generator_instance = ReportGenerator()
    return _report_generator_instance