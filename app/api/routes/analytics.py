"""
Analytics API Routes for Financial AI Agent.

Provides REST endpoints for advanced analytics, quality metrics,
business intelligence, anomaly detection, and reporting.
"""
from fastapi import APIRouter, HTTPException, Query, BackgroundTasks, Depends
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from pydantic import BaseModel

from app.api.middleware import require_admin
from app.analytics.quality_metrics import get_quality_metrics_engine
from app.analytics.business_intelligence import get_business_intelligence_engine
from app.analytics.anomaly_detector import get_anomaly_detector
from app.analytics.predictive_analytics import get_predictive_analytics
from app.analytics.dashboard_builder import get_dashboard_builder
from app.analytics.reports import get_report_generator, ReportConfig, ReportType, ReportFormat
from app.core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(
    prefix="/analytics",
    tags=["analytics"],
    dependencies=[Depends(require_admin)],
)


# Pydantic models for API requests
class QualityReportRequest(BaseModel):
    period_hours: int = 24
    include_trends: bool = True


class DashboardCreationRequest(BaseModel):
    template_name: str
    customizations: Optional[Dict[str, Any]] = None


class ReportGenerationRequest(BaseModel):
    report_type: str
    format: str = "json"
    period_days: int = 7
    include_charts: bool = True
    include_recommendations: bool = True


class AnomalyConfigRequest(BaseModel):
    metric_name: str
    z_score_threshold: Optional[float] = None
    min_deviation_percent: Optional[float] = None
    critical_threshold: Optional[float] = None


# ═══════════════════════════════════════════════════════════════════════════════
# Quality Metrics Endpoints
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/quality/report")
async def get_quality_report(
    period_hours: int = Query(24, description="Analysis period in hours"),
    include_trends: bool = Query(True, description="Include trend analysis")
):
    """Get comprehensive quality metrics report."""
    try:
        quality_engine = await get_quality_metrics_engine()
        report = await quality_engine.calculate_quality_report(
            period_hours=period_hours,
            include_trends=include_trends
        )
        
        return {
            "overall_score": report.overall_score,
            "category_scores": {cat.value: score for cat, score in report.category_scores.items()},
            "individual_metrics": [
                {
                    "metric_name": metric.metric_name,
                    "category": metric.category.value,  # Convert enum to string
                    "value": metric.value,
                    "percentage": metric.percentage,
                    "trend": metric.trend.value,  # Convert enum to string
                    "confidence_interval": metric.confidence_interval,
                    "description": metric.description,
                    "sample_size": metric.sample_size,
                    "last_updated": metric.last_updated.isoformat()
                }
                for metric in report.individual_metrics
            ],
            "trends": {k: v.value for k, v in report.trends.items()},
            "recommendations": report.recommendations,
            "report_period": [
                report.report_period[0].isoformat(),
                report.report_period[1].isoformat()
            ],
            "generated_at": report.generated_at.isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error generating quality report: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate quality report")


@router.get("/quality/summary")
async def get_quality_summary():
    """Get quick quality summary for dashboards."""
    try:
        quality_engine = await get_quality_metrics_engine()
        summary = await quality_engine.get_quality_summary()
        return summary
        
    except Exception as e:
        logger.error(f"Error getting quality summary: {e}")
        raise HTTPException(status_code=500, detail="Failed to get quality summary")


@router.get("/quality/export")
async def export_quality_data(
    format: str = Query("json", description="Export format (json)"),
    period_days: int = Query(7, description="Data period in days")
):
    """Export quality data for external analysis."""
    try:
        quality_engine = await get_quality_metrics_engine()
        data = await quality_engine.export_quality_data(format=format, period_days=period_days)
        return data
        
    except Exception as e:
        logger.error(f"Error exporting quality data: {e}")
        raise HTTPException(status_code=500, detail="Failed to export quality data")


# ═══════════════════════════════════════════════════════════════════════════════
# Business Intelligence Endpoints  
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/business-intelligence/report")
async def get_business_intelligence_report(
    period_days: int = Query(30, description="Analysis period in days")
):
    """Get comprehensive business intelligence report."""
    try:
        bi_engine = await get_business_intelligence_engine()
        report = await bi_engine.generate_business_intelligence_report(period_days=period_days)
        
        return {
            "executive_summary": report.executive_summary,
            "key_insights": [
                {
                    "title": insight.title,
                    "category": insight.category.value,
                    "insight_text": insight.insight_text,
                    "confidence_score": insight.confidence_score,
                    "impact_level": insight.impact_level,
                    "recommended_actions": insight.recommended_actions,
                    "supporting_data": insight.supporting_data,
                    "generated_at": insight.generated_at.isoformat()
                }
                for insight in report.key_insights
            ],
            "customer_segments": [
                {
                    "segment_name": segment.segment_name,
                    "characteristics": segment.characteristics,
                    "size": segment.size,
                    "engagement_score": segment.engagement_score,
                    "satisfaction_score": segment.satisfaction_score,
                    "value_score": segment.value_score,
                    "churn_risk": segment.churn_risk,
                    "recommended_strategies": segment.recommended_strategies
                }
                for segment in report.customer_segments
            ],
            "financial_analysis": {
                "cost_savings": report.financial_analysis.cost_savings,
                "revenue_impact": report.financial_analysis.revenue_impact,
                "roi_percentage": report.financial_analysis.roi_percentage,
                "payback_period_months": report.financial_analysis.payback_period_months,
                "automation_rate": report.financial_analysis.automation_rate,
                "efficiency_gains": report.financial_analysis.efficiency_gains
            },
            "market_trends": report.market_trends,
            "competitive_analysis": report.competitive_analysis,
            "strategic_recommendations": report.strategic_recommendations,
            "report_period": [
                report.report_period[0].isoformat(),
                report.report_period[1].isoformat()
            ],
            "generated_at": report.generated_at.isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error generating BI report: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate business intelligence report")


@router.get("/business-intelligence/insights")
async def get_real_time_insights():
    """Get real-time business insights for dashboards."""
    try:
        bi_engine = await get_business_intelligence_engine()
        insights = await bi_engine.get_real_time_insights()
        return {"insights": insights}
        
    except Exception as e:
        logger.error(f"Error getting real-time insights: {e}")
        raise HTTPException(status_code=500, detail="Failed to get real-time insights")


@router.get("/business-intelligence/export")
async def export_business_data(
    format: str = Query("json", description="Export format (json)"),
    include_predictions: bool = Query(False, description="Include predictive data")
):
    """Export business intelligence data for external systems."""
    try:
        bi_engine = await get_business_intelligence_engine()
        data = await bi_engine.export_business_data(format=format, include_predictions=include_predictions)
        return data
        
    except Exception as e:
        logger.error(f"Error exporting business data: {e}")
        raise HTTPException(status_code=500, detail="Failed to export business data")


# ═══════════════════════════════════════════════════════════════════════════════
# Anomaly Detection Endpoints
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/anomalies/summary")
async def get_anomaly_summary():
    """Get summary of recent anomaly detection results."""
    try:
        anomaly_detector = await get_anomaly_detector()
        summary = await anomaly_detector.get_anomaly_summary()
        return summary
        
    except Exception as e:
        logger.error(f"Error getting anomaly summary: {e}")
        raise HTTPException(status_code=500, detail="Failed to get anomaly summary")


@router.post("/anomalies/detect")
async def detect_anomalies(
    current_metrics: Dict[str, float],
    historical_window_hours: int = Query(24, description="Historical baseline window")
):
    """Detect anomalies in provided metrics."""
    try:
        anomaly_detector = await get_anomaly_detector()
        anomalies = await anomaly_detector.detect_anomalies(
            current_metrics=current_metrics,
            historical_window_hours=historical_window_hours
        )
        
        return {
            "anomalies": [
                {
                    "anomaly_type": anomaly.anomaly_type.value,
                    "severity": anomaly.severity.value,
                    "title": anomaly.title,
                    "description": anomaly.description,
                    "detected_at": anomaly.detected_at.isoformat(),
                    "metric_name": anomaly.metric_name,
                    "current_value": anomaly.current_value,
                    "expected_value": anomaly.expected_value,
                    "deviation_score": anomaly.deviation_score,
                    "deviation_percentage": anomaly.deviation_percentage,
                    "confidence": anomaly.confidence,
                    "recommended_actions": anomaly.recommended_actions,
                    "affected_components": anomaly.affected_components
                }
                for anomaly in anomalies
            ],
            "total_anomalies": len(anomalies),
            "critical_count": len([a for a in anomalies if a.severity.value == "critical"]),
            "high_count": len([a for a in anomalies if a.severity.value == "high"])
        }
        
    except Exception as e:
        logger.error(f"Error detecting anomalies: {e}")
        raise HTTPException(status_code=500, detail="Failed to detect anomalies")


@router.get("/anomalies/config")
async def get_anomaly_detection_config():
    """Get current anomaly detection configuration."""
    try:
        anomaly_detector = await get_anomaly_detector()
        config = anomaly_detector.get_detection_config()
        return config
        
    except Exception as e:
        logger.error(f"Error getting anomaly config: {e}")
        raise HTTPException(status_code=500, detail="Failed to get anomaly detection config")


@router.post("/anomalies/config")
async def configure_anomaly_detection(config: AnomalyConfigRequest):
    """Configure anomaly detection thresholds."""
    try:
        anomaly_detector = await get_anomaly_detector()
        await anomaly_detector.configure_detection(
            metric_name=config.metric_name,
            z_score_threshold=config.z_score_threshold,
            min_deviation_percent=config.min_deviation_percent,
            critical_threshold=config.critical_threshold
        )
        
        return {"message": f"Anomaly detection configured for {config.metric_name}"}
        
    except Exception as e:
        logger.error(f"Error configuring anomaly detection: {e}")
        raise HTTPException(status_code=500, detail="Failed to configure anomaly detection")


@router.post("/anomalies/update-baselines")
async def update_anomaly_baselines(
    background_tasks: BackgroundTasks,
    period_days: int = Query(7, description="Historical period for baseline calculation")
):
    """Update anomaly detection baselines from historical data."""
    try:
        anomaly_detector = await get_anomaly_detector()
        background_tasks.add_task(anomaly_detector.update_baselines, period_days)
        
        return {"message": f"Baseline update scheduled for {period_days} days of data"}
        
    except Exception as e:
        logger.error(f"Error updating baselines: {e}")
        raise HTTPException(status_code=500, detail="Failed to schedule baseline update")


# ═══════════════════════════════════════════════════════════════════════════════
# Predictive Analytics Endpoints
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/predictions/forecasts")
async def get_forecasts(
    metrics: List[str] = Query(None, description="Metrics to forecast"),
    horizon: str = Query("1_month", description="Forecast horizon (1_week, 1_month, 3_months)")
):
    """Generate forecasts for specified metrics."""
    try:
        predictive_engine = await get_predictive_analytics()
        
        # Default metrics if none specified
        if not metrics:
            metrics = ["avg_rating", "escalation_rate", "avg_response_time", "total_interactions"]
        
        # Convert horizon string to enum
        horizon_map = {
            "1_week": predictive_engine.ForecastHorizon.SHORT_TERM,
            "1_month": predictive_engine.ForecastHorizon.MEDIUM_TERM,
            "3_months": predictive_engine.ForecastHorizon.LONG_TERM
        }
        
        horizon_enum = horizon_map.get(horizon, predictive_engine.ForecastHorizon.MEDIUM_TERM)
        
        forecasts = await predictive_engine.generate_forecasts(metrics, horizon_enum)
        
        return {
            "forecasts": [
                {
                    "metric_name": forecast.metric_name,
                    "horizon": forecast.horizon.value,
                    "predicted_value": forecast.predicted_value,
                    "confidence_interval_lower": forecast.confidence_interval_lower,
                    "confidence_interval_upper": forecast.confidence_interval_upper,
                    "prediction_range": forecast.prediction_range,
                    "confidence_level": forecast.confidence_level,
                    "trend_direction": forecast.trend_direction.value,
                    "trend_strength": forecast.trend_strength,
                    "seasonality_detected": forecast.seasonality_detected,
                    "forecast_date": forecast.forecast_date.isoformat(),
                    "model_accuracy": forecast.model_accuracy
                }
                for forecast in forecasts
            ],
            "total_forecasts": len(forecasts)
        }
        
    except Exception as e:
        logger.error(f"Error generating forecasts: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate forecasts")


@router.get("/predictions/insights")
async def get_predictive_insights():
    """Get predictive insights with actionable recommendations."""
    try:
        predictive_engine = await get_predictive_analytics()
        insights = await predictive_engine.generate_predictive_insights()
        
        return {
            "insights": [
                {
                    "title": insight.title,
                    "description": insight.description,
                    "probability": insight.probability,
                    "impact_level": insight.impact_level,
                    "time_to_occurrence_days": insight.time_to_occurrence.days,
                    "confidence_score": insight.confidence_score,
                    "recommended_actions": insight.recommended_actions,
                    "generated_at": insight.generated_at.isoformat()
                }
                for insight in insights
            ],
            "total_insights": len(insights)
        }
        
    except Exception as e:
        logger.error(f"Error generating predictive insights: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate predictive insights")


@router.get("/predictions/summary")
async def get_predictive_summary():
    """Get predictive analytics summary for dashboards."""
    try:
        predictive_engine = await get_predictive_analytics()
        summary = await predictive_engine.get_predictive_summary()
        return summary
        
    except Exception as e:
        logger.error(f"Error getting predictive summary: {e}")
        raise HTTPException(status_code=500, detail="Failed to get predictive summary")


# ═══════════════════════════════════════════════════════════════════════════════
# Dashboard Builder Endpoints
# ═══════════════════════════════════════════════════════════════════════════════

@router.post("/dashboards/create")
async def create_dashboard(request: DashboardCreationRequest):
    """Create dashboard from template."""
    try:
        dashboard_builder = await get_dashboard_builder()
        dashboard_path = await dashboard_builder.create_from_template(
            template_name=request.template_name,
            customizations=request.customizations
        )
        
        return {
            "message": "Dashboard created successfully",
            "dashboard_path": dashboard_path,
            "template_used": request.template_name
        }
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating dashboard: {e}")
        raise HTTPException(status_code=500, detail="Failed to create dashboard")


@router.get("/dashboards/list")
async def list_dashboards():
    """Get list of available dashboards."""
    try:
        dashboard_builder = await get_dashboard_builder()
        dashboards = await dashboard_builder.get_dashboard_list()
        return {"dashboards": dashboards}
        
    except Exception as e:
        logger.error(f"Error listing dashboards: {e}")
        raise HTTPException(status_code=500, detail="Failed to list dashboards")


@router.get("/dashboards/{filename}")
async def get_dashboard(filename: str):
    """Get dashboard configuration."""
    try:
        dashboard_builder = await get_dashboard_builder()
        config = await dashboard_builder.export_dashboard_config(filename)
        
        if config is None:
            raise HTTPException(status_code=404, detail="Dashboard not found")
        
        return config
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting dashboard: {e}")
        raise HTTPException(status_code=500, detail="Failed to get dashboard")


# ═══════════════════════════════════════════════════════════════════════════════
# Report Generation Endpoints
# ═══════════════════════════════════════════════════════════════════════════════

@router.post("/reports/generate")
async def generate_report(
    background_tasks: BackgroundTasks,
    request: ReportGenerationRequest
):
    """Generate analytics report."""
    try:
        # Validate report type and format
        try:
            report_type = ReportType(request.report_type)
            report_format = ReportFormat(request.format)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"Invalid report type or format: {e}")
        
        report_generator = await get_report_generator()
        
        config = ReportConfig(
            report_type=report_type,
            format=report_format,
            period_days=request.period_days,
            include_charts=request.include_charts,
            include_recommendations=request.include_recommendations
        )
        
        # Generate report in background for large reports
        if request.period_days > 30 or report_type == ReportType.COMPREHENSIVE:
            background_tasks.add_task(report_generator.generate_report, config)
            return {
                "message": "Report generation started in background",
                "estimated_completion": "2-5 minutes"
            }
        
        # Generate report synchronously for small reports
        report = await report_generator.generate_report(config)
        
        return {
            "report_id": report.report_id,
            "report_type": report.report_type.value,
            "format": report.format.value,
            "generated_at": report.generated_at.isoformat(),
            "content_size": report.content_size,
            "file_path": report.file_path,
            "content": report.content if report.format == ReportFormat.JSON else None
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating report: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate report")


@router.get("/reports/list")
async def list_reports():
    """Get list of generated reports."""
    try:
        report_generator = await get_report_generator()
        reports = await report_generator.get_report_list()
        return {"reports": reports}
        
    except Exception as e:
        logger.error(f"Error listing reports: {e}")
        raise HTTPException(status_code=500, detail="Failed to list reports")


@router.get("/reports/{report_id}")
async def get_report(report_id: str):
    """Get specific report by ID."""
    try:
        report_generator = await get_report_generator()
        report = await report_generator.get_report(report_id)
        
        if report is None:
            raise HTTPException(status_code=404, detail="Report not found")
        
        return {
            "report_id": report.report_id,
            "report_type": report.report_type.value,
            "format": report.format.value,
            "generated_at": report.generated_at.isoformat(),
            "period_start": report.period_start.isoformat(),
            "period_end": report.period_end.isoformat(),
            "content_size": report.content_size,
            "metadata": report.metadata,
            "file_path": report.file_path,
            "content": report.content if report.format == ReportFormat.JSON else None
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting report: {e}")
        raise HTTPException(status_code=500, detail="Failed to get report")


@router.delete("/reports/{report_id}")
async def delete_report(report_id: str):
    """Delete a report."""
    try:
        report_generator = await get_report_generator()
        success = await report_generator.delete_report(report_id)
        
        if not success:
            raise HTTPException(status_code=404, detail="Report not found")
        
        return {"message": f"Report {report_id} deleted successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting report: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete report")


# ═══════════════════════════════════════════════════════════════════════════════
# Overview Endpoint
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/overview")
async def get_analytics_overview():
    """Get comprehensive analytics overview for main dashboard."""
    try:
        # Collect summaries from all analytics engines
        quality_engine = await get_quality_metrics_engine()
        bi_engine = await get_business_intelligence_engine()
        anomaly_detector = await get_anomaly_detector()
        predictive_engine = await get_predictive_analytics()
        
        # Get all summaries concurrently
        quality_summary = await quality_engine.get_quality_summary()
        bi_insights = await bi_engine.get_real_time_insights()
        anomaly_summary = await anomaly_detector.get_anomaly_summary()
        predictive_summary = await predictive_engine.get_predictive_summary()
        
        return {
            "overview": {
                "quality": quality_summary,
                "business_insights": {"insights": bi_insights},
                "anomalies": anomaly_summary,
                "predictions": predictive_summary
            },
            "system_health": anomaly_summary.get("system_health", "healthy"),
            "last_updated": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error getting analytics overview: {e}")
        raise HTTPException(status_code=500, detail="Failed to get analytics overview")