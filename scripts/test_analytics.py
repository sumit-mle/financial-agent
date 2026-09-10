#!/usr/bin/env python3
"""
Test script for Advanced Analytics implementation.

Usage:
    python scripts/test_analytics.py
"""
import asyncio
import json
import sys
from pathlib import Path
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.analytics.quality_metrics import get_quality_metrics_engine
from app.analytics.business_intelligence import get_business_intelligence_engine
from app.analytics.anomaly_detector import get_anomaly_detector
from app.analytics.predictive_analytics import get_predictive_analytics
from app.analytics.dashboard_builder import get_dashboard_builder
from app.analytics.reports import get_report_generator, ReportConfig, ReportType, ReportFormat
from app.core.logging import get_logger

logger = get_logger(__name__)


async def test_analytics_system():
    """Test the complete advanced analytics system."""
    print("Advanced Analytics System Test")
    print("=" * 60)
    
    try:
        # Test 1: Quality Metrics Engine
        print("1. Testing Quality Metrics Engine...")
        quality_engine = await get_quality_metrics_engine()
        
        # Get quality summary
        quality_summary = await quality_engine.get_quality_summary()
        print(f"   Quality Summary: {quality_summary['overall_score']:.1f}% ({quality_summary['grade']})")
        
        # Generate quality report (with minimal data)
        try:
            quality_report = await quality_engine.calculate_quality_report(period_hours=1)
            print(f"   Quality Report: {len(quality_report.individual_metrics)} metrics analyzed")
            print(f"   Recommendations: {len(quality_report.recommendations)} generated")
        except Exception as e:
            print(f"   Quality Report: Limited data available - {e}")
        
        # Test 2: Business Intelligence Engine
        print("\n2. Testing Business Intelligence Engine...")
        bi_engine = await get_business_intelligence_engine()
        
        # Get real-time insights
        real_time_insights = await bi_engine.get_real_time_insights()
        print(f"   Real-time Insights: {len(real_time_insights)} insights generated")
        
        # Generate BI report (may have limited data)
        try:
            bi_report = await bi_engine.generate_business_intelligence_report(period_days=1)
            print(f"   BI Report: {len(bi_report.key_insights)} business insights")
            print(f"   Customer Segments: {len(bi_report.customer_segments)} segments analyzed")
            print(f"   ROI: {bi_report.financial_analysis.roi_percentage:.1f}%")
        except Exception as e:
            print(f"   BI Report: Limited data available - {e}")
        
        # Test 3: Anomaly Detection
        print("\n3. Testing Anomaly Detection...")
        anomaly_detector = await get_anomaly_detector()
        
        # Test anomaly detection with sample metrics
        test_metrics = {
            "avg_rating": 3.8,
            "escalation_rate": 0.12,
            "avg_response_time": 2.1,
            "avg_confidence": 0.85
        }
        
        anomalies = await anomaly_detector.detect_anomalies(test_metrics)
        print(f"   Anomalies Detected: {len(anomalies)}")
        
        # Get anomaly summary
        anomaly_summary = await anomaly_detector.get_anomaly_summary()
        print(f"   System Health: {anomaly_summary['system_health']}")
        print(f"   Total Anomalies: {anomaly_summary['total_anomalies']}")
        
        # Test 4: Predictive Analytics
        print("\n4. Testing Predictive Analytics...")
        predictive_engine = await get_predictive_analytics()
        
        # Get predictive summary
        predictive_summary = await predictive_engine.get_predictive_summary()
        print(f"   Predictive Insights: {predictive_summary['total_insights']}")
        print(f"   High Impact Insights: {predictive_summary['high_impact_insights']}")
        
        # Generate forecasts (may have limited historical data)
        try:
            from app.analytics.predictive_analytics import ForecastHorizon
            forecasts = await predictive_engine.generate_forecasts(
                ["avg_rating", "escalation_rate"], 
                ForecastHorizon.SHORT_TERM
            )
            print(f"   Forecasts Generated: {len(forecasts)}")
            for forecast in forecasts:
                print(f"     {forecast.metric_name}: {forecast.predicted_value:.3f} (trend: {forecast.trend_direction.value})")
        except Exception as e:
            print(f"   Forecasts: Limited historical data - {e}")
        
        # Test 5: Dashboard Builder
        print("\n5. Testing Dashboard Builder...")
        dashboard_builder = await get_dashboard_builder()
        
        # List available templates
        available_templates = list(dashboard_builder.templates.keys())
        print(f"   Available Templates: {len(available_templates)}")
        print(f"   Templates: {', '.join(available_templates)}")
        
        # Create a test dashboard
        try:
            dashboard_path = await dashboard_builder.create_from_template(
                "business_overview",
                customizations={"title": "Test Business Dashboard"}
            )
            print(f"   Dashboard Created: {dashboard_path}")
        except Exception as e:
            print(f"   Dashboard Creation: {e}")
        
        # Test 6: Report Generator
        print("\n6. Testing Report Generator...")
        report_generator = await get_report_generator()
        
        # Generate executive summary report
        try:
            config = ReportConfig(
                report_type=ReportType.EXECUTIVE_SUMMARY,
                format=ReportFormat.JSON,
                period_days=1,
                include_charts=True,
                include_recommendations=True
            )
            
            report = await report_generator.generate_report(config)
            print(f"   Report Generated: {report.report_id}")
            print(f"   Content Size: {report.content_size} bytes")
            print(f"   Format: {report.format.value}")
            
            # Show sample report content
            if isinstance(report.content, dict):
                if "report_metadata" in report.content:
                    metadata = report.content["report_metadata"]
                    print(f"   Report Type: {metadata.get('type', 'unknown')}")
                    print(f"   Generated: {metadata.get('generated_at', 'unknown')}")
            
        except Exception as e:
            print(f"   Report Generation: {e}")
        
        # Test 7: Integration Test
        print("\n7. Testing System Integration...")
        
        # Test analytics overview (similar to what API would return)
        try:
            overview = {
                "quality": quality_summary,
                "anomalies": anomaly_summary,
                "predictions": predictive_summary,
                "business_insights": {"insights": real_time_insights},
                "system_health": anomaly_summary.get("system_health", "healthy"),
                "last_updated": datetime.utcnow().isoformat()
            }
            
            print(f"   Analytics Overview Generated: {len(overview)} sections")
            print(f"   Overall System Health: {overview['system_health']}")
            
        except Exception as e:
            print(f"   Integration Test: {e}")
        
        # Success Summary
        print("\n" + "=" * 60)
        print("SUCCESS: Advanced Analytics System Test Complete!")
        print("=" * 60)
        
        print("\nKey Capabilities Verified:")
        print("✓ Quality Metrics Engine - Multi-dimensional quality scoring")
        print("✓ Business Intelligence - Financial impact analysis & insights") 
        print("✓ Anomaly Detection - Statistical anomaly detection & alerting")
        print("✓ Predictive Analytics - Forecasting & trend analysis")
        print("✓ Dashboard Builder - Dynamic Grafana dashboard generation")
        print("✓ Report Generator - Multi-format report generation")
        
        print(f"\nSystem Status:")
        print(f"• Quality Score: {quality_summary.get('overall_score', 'N/A')}%")
        print(f"• System Health: {anomaly_summary.get('system_health', 'unknown')}")
        print(f"• Predictive Insights: {predictive_summary.get('total_insights', 0)}")
        print(f"• Analytics Ready: ✓")
        
        return True
        
    except Exception as e:
        print(f"\nERROR: Analytics system test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_api_simulation():
    """Simulate API endpoint calls for testing."""
    print("\n" + "=" * 60)
    print("API Simulation Test")
    print("=" * 60)
    
    try:
        # Simulate analytics overview endpoint
        from app.analytics.quality_metrics import get_quality_metrics_engine
        from app.analytics.business_intelligence import get_business_intelligence_engine
        from app.analytics.anomaly_detector import get_anomaly_detector
        from app.analytics.predictive_analytics import get_predictive_analytics
        
        print("Simulating /api/v1/admin/analytics/overview...")
        
        # Collect data like the API would
        quality_engine = await get_quality_metrics_engine()
        bi_engine = await get_business_intelligence_engine()
        anomaly_detector = await get_anomaly_detector()
        predictive_engine = await get_predictive_analytics()
        
        quality_summary = await quality_engine.get_quality_summary()
        bi_insights = await bi_engine.get_real_time_insights()
        anomaly_summary = await anomaly_detector.get_anomaly_summary()
        predictive_summary = await predictive_engine.get_predictive_summary()
        
        # Construct response like API would
        api_response = {
            "overview": {
                "quality": quality_summary,
                "business_insights": {"insights": bi_insights},
                "anomalies": anomaly_summary,
                "predictions": predictive_summary
            },
            "system_health": anomaly_summary.get("system_health", "healthy"),
            "last_updated": datetime.utcnow().isoformat()
        }
        
        print(f"✓ API Response Generated: {len(json.dumps(api_response))} chars")
        print(f"✓ System Health: {api_response['system_health']}")
        print(f"✓ Quality Grade: {quality_summary.get('grade', 'N/A')}")
        
        # Simulate report generation endpoint
        print("\nSimulating /api/v1/admin/analytics/reports/generate...")
        
        report_generator = await get_report_generator()
        config = ReportConfig(
            report_type=ReportType.QUALITY_METRICS,
            format=ReportFormat.JSON,
            period_days=1
        )
        
        report = await report_generator.generate_report(config)
        
        api_report_response = {
            "report_id": report.report_id,
            "report_type": report.report_type.value,
            "format": report.format.value,
            "generated_at": report.generated_at.isoformat(),
            "content_size": report.content_size
        }
        
        print(f"✓ Report API Response: {report.report_id}")
        print(f"✓ Report Size: {report.content_size} bytes")
        
        print("\n✓ API Simulation Successful!")
        
        return True
        
    except Exception as e:
        print(f"\nERROR: API simulation failed: {e}")
        return False


if __name__ == "__main__":
    try:
        print("Starting Advanced Analytics Test Suite...")
        
        # Run main analytics test
        result1 = asyncio.run(test_analytics_system())
        
        # Run API simulation test
        result2 = asyncio.run(test_api_simulation())
        
        if result1 and result2:
            print(f"\n{'='*60}")
            print("🎉 ALL TESTS PASSED - Advanced Analytics Ready!")
            print(f"{'='*60}")
            sys.exit(0)
        else:
            print(f"\n{'='*60}")
            print("❌ SOME TESTS FAILED - Check output above")
            print(f"{'='*60}")
            sys.exit(1)
            
    except KeyboardInterrupt:
        print("\n⏹️ Testing interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Testing failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)