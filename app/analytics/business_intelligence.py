"""
Business Intelligence Engine for Financial AI Agent.

Provides advanced business insights, financial analytics, customer behavior analysis,
and strategic decision support through data-driven intelligence.
"""
import asyncio
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict
from enum import Enum
from collections import defaultdict
import json
from pathlib import Path

from app.core.logging import get_logger
from app.core.config import settings
from app.mlops.feedback_collector import get_feedback_collector
from app.experimentation.framework import get_experiment_engine
from app.analytics.quality_metrics import get_quality_metrics_engine

logger = get_logger(__name__)


class BusinessMetric(Enum):
    """Business intelligence metric types."""
    CUSTOMER_ACQUISITION = "customer_acquisition"
    CUSTOMER_RETENTION = "customer_retention"
    REVENUE_IMPACT = "revenue_impact"
    OPERATIONAL_EFFICIENCY = "operational_efficiency"
    PRODUCT_ADOPTION = "product_adoption"
    RISK_MITIGATION = "risk_mitigation"
    MARKET_INSIGHTS = "market_insights"


class TimeGranularity(Enum):
    """Time granularity for analytics."""
    HOURLY = "hourly"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"


@dataclass
class BusinessInsight:
    """Individual business insight with actionable recommendations."""
    title: str
    category: BusinessMetric
    insight_text: str
    confidence_score: float
    impact_level: str  # "high", "medium", "low"
    recommended_actions: List[str]
    supporting_data: Dict[str, Any]
    generated_at: datetime
    validity_period_days: int = 30


@dataclass
class CustomerSegment:
    """Customer segment analysis."""
    segment_name: str
    characteristics: Dict[str, Any]
    size: int
    engagement_score: float
    satisfaction_score: float
    value_score: float
    churn_risk: str
    recommended_strategies: List[str]


@dataclass
class FinancialAnalysis:
    """Financial impact analysis."""
    cost_savings: float
    revenue_impact: float
    roi_percentage: float
    payback_period_months: float
    automation_rate: float
    efficiency_gains: Dict[str, float]


@dataclass
class BusinessIntelligenceReport:
    """Comprehensive business intelligence report."""
    executive_summary: str
    key_insights: List[BusinessInsight]
    customer_segments: List[CustomerSegment]
    financial_analysis: FinancialAnalysis
    market_trends: Dict[str, Any]
    competitive_analysis: Dict[str, Any]
    strategic_recommendations: List[str]
    report_period: Tuple[datetime, datetime]
    generated_at: datetime


class BusinessIntelligenceEngine:
    """
    Advanced Business Intelligence Engine.
    
    Features:
    - Customer behavior analytics
    - Financial impact assessment
    - Market trend analysis
    - Predictive business insights
    - Revenue optimization recommendations
    - Risk assessment and mitigation
    - Competitive intelligence
    - Strategic planning support
    """
    
    def __init__(self):
        self.financial_models = self._initialize_financial_models()
        self.customer_segments = {}
        self.market_baselines = self._initialize_market_baselines()
        self.insights_cache = {}
        
    def _initialize_financial_models(self) -> Dict[str, Any]:
        """Initialize financial calculation models."""
        return {
            "automation_savings": {
                "human_agent_cost_per_hour": 25.0,
                "ai_agent_cost_per_1000_requests": 0.50,
                "average_resolution_time_minutes": 8.0
            },
            "customer_lifetime_value": {
                "average_account_value": 15000.0,
                "annual_revenue_per_customer": 1200.0,
                "customer_lifespan_years": 5.2
            },
            "operational_metrics": {
                "peak_hour_multiplier": 1.8,
                "weekend_factor": 0.6,
                "seasonal_variance": 0.25
            }
        }
    
    def _initialize_market_baselines(self) -> Dict[str, float]:
        """Initialize market baseline metrics for comparison."""
        return {
            "industry_satisfaction_score": 3.8,
            "industry_resolution_rate": 0.78,
            "industry_response_time_seconds": 45.0,
            "industry_automation_rate": 0.35,
            "industry_escalation_rate": 0.22
        }
    
    async def generate_business_intelligence_report(self, 
                                                   period_days: int = 30) -> BusinessIntelligenceReport:
        """Generate comprehensive business intelligence report."""
        
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(days=period_days)
        
        logger.info(f"Generating business intelligence report for {period_days} days")
        
        # Gather data from various sources
        feedback_collector = await get_feedback_collector()
        quality_engine = await get_quality_metrics_engine()
        ab_framework = await get_experiment_engine()
        
        # Get feedback data (limited to recent 24 hours by feedback collector)
        feedback_summary = await feedback_collector.get_feedback_summary()
        
        # Get quality metrics
        quality_report = await quality_engine.calculate_quality_report(
            period_hours=period_days * 24
        )
        
        # Generate insights
        key_insights = await self._generate_business_insights(feedback_summary, quality_report)
        
        # Analyze customer segments
        customer_segments = await self._analyze_customer_segments(feedback_summary)
        
        # Calculate financial impact
        financial_analysis = await self._calculate_financial_impact(feedback_summary, period_days)
        
        # Analyze market trends
        market_trends = await self._analyze_market_trends(feedback_summary)
        
        # Generate competitive analysis
        competitive_analysis = await self._generate_competitive_analysis(feedback_summary)
        
        # Generate strategic recommendations
        strategic_recommendations = await self._generate_strategic_recommendations(
            key_insights, financial_analysis, market_trends
        )
        
        # Create executive summary
        executive_summary = self._create_executive_summary(
            key_insights, financial_analysis, quality_report.overall_score
        )
        
        report = BusinessIntelligenceReport(
            executive_summary=executive_summary,
            key_insights=key_insights,
            customer_segments=customer_segments,
            financial_analysis=financial_analysis,
            market_trends=market_trends,
            competitive_analysis=competitive_analysis,
            strategic_recommendations=strategic_recommendations,
            report_period=(start_time, end_time),
            generated_at=datetime.utcnow()
        )
        
        logger.info(f"Business intelligence report generated with {len(key_insights)} insights")
        
        return report
    
    async def _generate_business_insights(self, 
                                        feedback_summary: Dict[str, Any],
                                        quality_report: Any) -> List[BusinessInsight]:
        """Generate actionable business insights."""
        
        insights = []
        
        # Customer Satisfaction Impact
        avg_rating = feedback_summary.get("avg_rating", 3.5)
        industry_baseline = self.market_baselines["industry_satisfaction_score"]
        
        if avg_rating > industry_baseline + 0.5:
            insights.append(BusinessInsight(
                title="Exceptional Customer Satisfaction Performance",
                category=BusinessMetric.CUSTOMER_RETENTION,
                insight_text=f"Customer satisfaction ({avg_rating:.2f}/5.0) significantly exceeds industry average ({industry_baseline:.2f}), indicating strong competitive advantage and customer loyalty potential.",
                confidence_score=0.92,
                impact_level="high",
                recommended_actions=[
                    "Leverage high satisfaction in marketing materials",
                    "Identify and replicate satisfaction drivers across all touchpoints",
                    "Consider premium service tier based on quality differentiation"
                ],
                supporting_data={
                    "current_satisfaction": avg_rating,
                    "industry_baseline": industry_baseline,
                    "competitive_advantage": avg_rating - industry_baseline
                },
                generated_at=datetime.utcnow()
            ))
        
        # Operational Efficiency Insight
        escalation_rate = feedback_summary.get("escalation_rate", 0.15)
        industry_escalation = self.market_baselines["industry_escalation_rate"]
        automation_rate = 1 - escalation_rate
        
        if automation_rate > self.market_baselines["industry_automation_rate"] + 0.1:
            cost_savings = self._calculate_automation_savings(automation_rate, feedback_summary)
            insights.append(BusinessInsight(
                title="Superior Automation Efficiency",
                category=BusinessMetric.OPERATIONAL_EFFICIENCY,
                insight_text=f"AI automation rate ({automation_rate:.1%}) significantly exceeds industry standard, generating estimated monthly savings of ${cost_savings:,.0f}.",
                confidence_score=0.88,
                impact_level="high",
                recommended_actions=[
                    "Scale AI capabilities to handle increased volume",
                    "Invest in advanced model training for edge cases",
                    "Market automation capabilities to enterprise clients"
                ],
                supporting_data={
                    "automation_rate": automation_rate,
                    "industry_rate": self.market_baselines["industry_automation_rate"],
                    "monthly_savings": cost_savings,
                    "escalation_reduction": industry_escalation - escalation_rate
                },
                generated_at=datetime.utcnow()
            ))
        
        # Response Time Competitive Advantage
        avg_response_time = feedback_summary.get("avg_response_time", 2.5)
        industry_response_time = self.market_baselines["industry_response_time_seconds"]
        
        if avg_response_time < industry_response_time * 0.5:
            insights.append(BusinessInsight(
                title="Response Time Competitive Edge",
                category=BusinessMetric.CUSTOMER_ACQUISITION,
                insight_text=f"Average response time ({avg_response_time:.1f}s) is {industry_response_time/avg_response_time:.1f}x faster than industry average, creating significant competitive moat.",
                confidence_score=0.85,
                impact_level="medium",
                recommended_actions=[
                    "Highlight speed advantage in sales materials",
                    "Create 'instant response' marketing campaigns",
                    "Monitor competitors' response time improvements"
                ],
                supporting_data={
                    "current_response_time": avg_response_time,
                    "industry_baseline": industry_response_time,
                    "speed_multiplier": industry_response_time / avg_response_time
                },
                generated_at=datetime.utcnow()
            ))
        
        # Quality Trend Analysis
        quality_score = quality_report.overall_score
        if quality_score > 90:
            insights.append(BusinessInsight(
                title="Premium Quality Positioning Opportunity",
                category=BusinessMetric.REVENUE_IMPACT,
                insight_text=f"Exceptional quality score ({quality_score:.1f}%) enables premium pricing strategy and high-value market positioning.",
                confidence_score=0.87,
                impact_level="high",
                recommended_actions=[
                    "Develop premium service tiers with quality guarantees",
                    "Target enterprise clients requiring high-quality AI",
                    "Create case studies demonstrating quality outcomes"
                ],
                supporting_data={
                    "quality_score": quality_score,
                    "quality_grade": quality_report.category_scores
                },
                generated_at=datetime.utcnow()
            ))
        
        # Safety and Compliance Excellence
        safety_violations = feedback_summary.get("safety_violations", 0)
        total_interactions = feedback_summary.get("total_feedback", 1)
        safety_rate = 1 - (safety_violations / total_interactions)
        
        if safety_rate > 0.999:
            insights.append(BusinessInsight(
                title="Regulatory Compliance Advantage",
                category=BusinessMetric.RISK_MITIGATION,
                insight_text=f"Exceptional safety compliance ({safety_rate:.1%}) positions for regulated industry expansion and reduces liability risks.",
                confidence_score=0.90,
                impact_level="medium",
                recommended_actions=[
                    "Pursue financial services regulatory certifications",
                    "Target healthcare and legal industry clients",
                    "Develop compliance-focused product offerings"
                ],
                supporting_data={
                    "safety_rate": safety_rate,
                    "violations_per_1000": (safety_violations / total_interactions) * 1000,
                    "compliance_score": safety_rate * 100
                },
                generated_at=datetime.utcnow()
            ))
        
        return insights
    
    async def _analyze_customer_segments(self, feedback_summary: Dict[str, Any]) -> List[CustomerSegment]:
        """Analyze and create customer segments."""
        
        segments = []
        
        # High-Value Segment
        segments.append(CustomerSegment(
            segment_name="Premium Engaged Users",
            characteristics={
                "avg_rating": 4.5,
                "interaction_frequency": "high",
                "resolution_preference": "self_service",
                "product_interest": ["investment", "premium_banking"]
            },
            size=int(feedback_summary.get("total_feedback", 100) * 0.15),
            engagement_score=0.92,
            satisfaction_score=0.89,
            value_score=0.95,
            churn_risk="low",
            recommended_strategies=[
                "Offer exclusive premium features",
                "Provide dedicated support channels", 
                "Cross-sell investment products"
            ]
        ))
        
        # Growth Opportunity Segment  
        segments.append(CustomerSegment(
            segment_name="Growth Potential Users",
            characteristics={
                "avg_rating": 3.8,
                "interaction_frequency": "medium",
                "resolution_preference": "guided_assistance",
                "product_interest": ["loans", "savings"]
            },
            size=int(feedback_summary.get("total_feedback", 100) * 0.45),
            engagement_score=0.74,
            satisfaction_score=0.76,
            value_score=0.68,
            churn_risk="medium",
            recommended_strategies=[
                "Improve onboarding experience",
                "Provide educational content",
                "Implement targeted upselling"
            ]
        ))
        
        # At-Risk Segment
        segments.append(CustomerSegment(
            segment_name="At-Risk Users", 
            characteristics={
                "avg_rating": 2.8,
                "interaction_frequency": "low",
                "resolution_preference": "human_support",
                "product_interest": ["basic_banking"]
            },
            size=int(feedback_summary.get("total_feedback", 100) * 0.25),
            engagement_score=0.45,
            satisfaction_score=0.52,
            value_score=0.38,
            churn_risk="high",
            recommended_strategies=[
                "Implement retention campaigns",
                "Provide personalized support",
                "Address pain points quickly"
            ]
        ))
        
        # New/Trial Users
        segments.append(CustomerSegment(
            segment_name="New Adopters",
            characteristics={
                "avg_rating": 3.5,
                "interaction_frequency": "variable",
                "resolution_preference": "mixed",
                "product_interest": ["exploring"]
            },
            size=int(feedback_summary.get("total_feedback", 100) * 0.15),
            engagement_score=0.65,
            satisfaction_score=0.70,
            value_score=0.45,
            churn_risk="medium",
            recommended_strategies=[
                "Optimize first-time experience",
                "Provide clear value demonstrations",
                "Implement progressive onboarding"
            ]
        ))
        
        return segments
    
    async def _calculate_financial_impact(self, 
                                        feedback_summary: Dict[str, Any],
                                        period_days: int) -> FinancialAnalysis:
        """Calculate comprehensive financial impact analysis."""
        
        total_interactions = feedback_summary.get("total_feedback", 1000)
        escalation_rate = feedback_summary.get("escalation_rate", 0.15)
        automation_rate = 1 - escalation_rate
        avg_response_time = feedback_summary.get("avg_response_time", 2.5)
        
        # Calculate cost savings from automation
        monthly_interactions = (total_interactions / period_days) * 30
        monthly_savings = self._calculate_automation_savings(automation_rate, {
            "total_interactions": monthly_interactions,
            "avg_response_time": avg_response_time
        })
        
        # Calculate revenue impact from improved satisfaction
        avg_rating = feedback_summary.get("avg_rating", 3.5)
        satisfaction_premium = max(0, (avg_rating - 3.5) / 1.5)  # Scale 3.5-5 to 0-1
        revenue_uplift = satisfaction_premium * 0.15  # Up to 15% revenue uplift
        
        monthly_revenue_base = monthly_interactions * 10  # Assume $10 per interaction value
        revenue_impact = monthly_revenue_base * revenue_uplift
        
        # Calculate ROI
        total_monthly_benefit = monthly_savings + revenue_impact
        estimated_ai_investment = 50000  # Estimated monthly AI infrastructure cost
        roi_percentage = (total_monthly_benefit - estimated_ai_investment) / estimated_ai_investment * 100
        
        # Payback period
        payback_period_months = estimated_ai_investment / total_monthly_benefit if total_monthly_benefit > 0 else float('inf')
        
        # Efficiency gains
        efficiency_gains = {
            "response_time_improvement": max(0, (45 - avg_response_time) / 45),  # vs 45s industry standard
            "automation_efficiency": automation_rate,
            "quality_premium": (avg_rating - 3.0) / 2.0,  # Quality above baseline
            "cost_per_interaction_reduction": 0.75  # 75% cost reduction vs human agents
        }
        
        return FinancialAnalysis(
            cost_savings=monthly_savings,
            revenue_impact=revenue_impact,
            roi_percentage=roi_percentage,
            payback_period_months=payback_period_months,
            automation_rate=automation_rate,
            efficiency_gains=efficiency_gains
        )
    
    def _calculate_automation_savings(self, automation_rate: float, data: Dict[str, Any]) -> float:
        """Calculate monthly cost savings from automation."""
        
        monthly_interactions = data.get("total_interactions", 1000)
        avg_response_time_minutes = data.get("avg_response_time", 2.5) / 60
        
        # Cost calculation
        automated_interactions = monthly_interactions * automation_rate
        human_interactions = monthly_interactions * (1 - automation_rate)
        
        # Human agent costs
        human_agent_hourly_cost = self.financial_models["automation_savings"]["human_agent_cost_per_hour"]
        human_cost = human_interactions * (avg_response_time_minutes / 60) * human_agent_hourly_cost
        
        # AI costs
        ai_cost_per_1000 = self.financial_models["automation_savings"]["ai_agent_cost_per_1000_requests"]
        ai_cost = (automated_interactions / 1000) * ai_cost_per_1000
        
        # Savings = what human agents would cost - actual AI cost
        potential_human_cost = monthly_interactions * (avg_response_time_minutes / 60) * human_agent_hourly_cost
        actual_cost = human_cost + ai_cost
        
        return max(0, potential_human_cost - actual_cost)
    
    async def _analyze_market_trends(self, feedback_summary: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze market trends and competitive positioning."""
        
        return {
            "industry_benchmarks": {
                "satisfaction_vs_industry": feedback_summary.get("avg_rating", 3.5) - self.market_baselines["industry_satisfaction_score"],
                "automation_vs_industry": (1 - feedback_summary.get("escalation_rate", 0.15)) - self.market_baselines["industry_automation_rate"],
                "response_time_advantage": self.market_baselines["industry_response_time_seconds"] / feedback_summary.get("avg_response_time", 2.5)
            },
            "market_opportunities": [
                "Enterprise AI adoption accelerating 40% YoY",
                "Regulatory compliance requirements increasing",
                "Customer expectation for instant responses rising",
                "Financial services digitization expanding"
            ],
            "competitive_threats": [
                "Large tech companies entering financial AI space", 
                "Traditional vendors improving automation capabilities",
                "Open-source AI solutions becoming more capable",
                "Price pressure from new market entrants"
            ],
            "growth_vectors": [
                "Expand into adjacent financial verticals",
                "Develop industry-specific compliance features",
                "Create white-label solutions for banks",
                "Build integration marketplace"
            ]
        }
    
    async def _generate_competitive_analysis(self, feedback_summary: Dict[str, Any]) -> Dict[str, Any]:
        """Generate competitive analysis insights."""
        
        our_metrics = {
            "satisfaction": feedback_summary.get("avg_rating", 3.5),
            "automation_rate": 1 - feedback_summary.get("escalation_rate", 0.15),
            "response_time": feedback_summary.get("avg_response_time", 2.5),
            "safety_rate": 1 - (feedback_summary.get("safety_violations", 0) / max(1, feedback_summary.get("total_feedback", 1)))
        }
        
        return {
            "competitive_positioning": {
                "satisfaction_ranking": "Top 10%" if our_metrics["satisfaction"] > 4.2 else "Above Average",
                "automation_leadership": "Market Leader" if our_metrics["automation_rate"] > 0.8 else "Competitive",
                "speed_advantage": "Significant" if our_metrics["response_time"] < 3.0 else "Moderate",
                "safety_score": "Excellent" if our_metrics["safety_rate"] > 0.999 else "Good"
            },
            "competitive_advantages": [
                "Superior response speed and accuracy",
                "High automation rate with quality maintenance", 
                "Strong safety and compliance record",
                "Consistent customer satisfaction scores"
            ],
            "areas_for_improvement": [
                "Expand multi-language capabilities",
                "Enhance complex query handling",
                "Develop more specialized financial products",
                "Improve integration ecosystem"
            ],
            "market_differentiation": {
                "unique_value_propositions": [
                    "Industry-leading response times",
                    "High-quality automated resolution",
                    "Comprehensive compliance framework",
                    "Transparent AI decision making"
                ],
                "competitive_moats": [
                    "Proprietary financial training data",
                    "Advanced safety and compliance systems", 
                    "Proven enterprise deployment experience",
                    "Strong customer satisfaction track record"
                ]
            }
        }
    
    async def _generate_strategic_recommendations(self,
                                               insights: List[BusinessInsight],
                                               financial_analysis: FinancialAnalysis,
                                               market_trends: Dict[str, Any]) -> List[str]:
        """Generate strategic business recommendations."""
        
        recommendations = []
        
        # Revenue optimization recommendations
        if financial_analysis.roi_percentage > 100:
            recommendations.append(
                f"💰 SCALE INVESTMENT: Current ROI of {financial_analysis.roi_percentage:.0f}% "
                f"justifies increased AI infrastructure investment for market expansion."
            )
        
        # Market positioning recommendations
        high_impact_insights = [i for i in insights if i.impact_level == "high"]
        if len(high_impact_insights) >= 2:
            recommendations.append(
                "🎯 PREMIUM POSITIONING: Multiple high-impact advantages support "
                "premium market positioning and pricing strategy."
            )
        
        # Automation efficiency recommendations  
        if financial_analysis.automation_rate > 0.85:
            recommendations.append(
                f"🤖 AUTOMATION LEADERSHIP: {financial_analysis.automation_rate:.1%} automation rate "
                f"creates competitive moat - consider licensing technology to partners."
            )
        
        # Financial growth recommendations
        monthly_benefit = financial_analysis.cost_savings + financial_analysis.revenue_impact
        if monthly_benefit > 100000:
            recommendations.append(
                f"📈 RAPID SCALING: Monthly benefits of ${monthly_benefit:,.0f} support "
                f"aggressive market expansion and product development."
            )
        
        # Market expansion recommendations
        growth_opportunities = market_trends.get("growth_vectors", [])
        if growth_opportunities:
            recommendations.append(
                f"🌐 MARKET EXPANSION: Pursue {len(growth_opportunities)} identified "
                f"growth vectors, starting with highest-synergy opportunities."
            )
        
        # Risk mitigation recommendations
        safety_insights = [i for i in insights if i.category == BusinessMetric.RISK_MITIGATION]
        if safety_insights:
            recommendations.append(
                "🛡️ COMPLIANCE ADVANTAGE: Leverage superior safety record "
                "for regulated industry expansion and enterprise sales."
            )
        
        # Technology investment recommendations
        if financial_analysis.payback_period_months < 12:
            recommendations.append(
                f"⚡ ACCELERATE R&D: {financial_analysis.payback_period_months:.1f}-month "
                f"payback period supports increased AI research and development investment."
            )
        
        # Customer experience recommendations
        customer_insights = [i for i in insights if i.category == BusinessMetric.CUSTOMER_RETENTION]
        if customer_insights:
            recommendations.append(
                "🎁 CUSTOMER SUCCESS: High satisfaction scores enable customer "
                "success program development and referral marketing initiatives."
            )
        
        return recommendations
    
    def _create_executive_summary(self,
                                insights: List[BusinessInsight],
                                financial_analysis: FinancialAnalysis,
                                quality_score: float) -> str:
        """Create executive summary for the business intelligence report."""
        
        high_impact_count = len([i for i in insights if i.impact_level == "high"])
        monthly_benefit = financial_analysis.cost_savings + financial_analysis.revenue_impact
        
        summary = f"""
EXECUTIVE SUMMARY - Financial AI Agent Performance

🎯 OVERALL PERFORMANCE: Exceptional quality score of {quality_score:.1f}% with {high_impact_count} high-impact business opportunities identified.

💰 FINANCIAL IMPACT: 
• Monthly Benefits: ${monthly_benefit:,.0f} (${financial_analysis.cost_savings:,.0f} cost savings + ${financial_analysis.revenue_impact:,.0f} revenue uplift)
• ROI: {financial_analysis.roi_percentage:.0f}%
• Payback Period: {financial_analysis.payback_period_months:.1f} months
• Automation Rate: {financial_analysis.automation_rate:.1%}

🚀 KEY OPPORTUNITIES:
{chr(10).join([f"• {insight.title}" for insight in insights[:3]])}

📊 COMPETITIVE POSITION: Market-leading performance across satisfaction, automation, and response time metrics creates significant competitive advantages and premium positioning opportunities.

🎪 STRATEGIC FOCUS: Scale existing advantages, expand market presence, and leverage technology leadership for accelerated growth and market share capture.
        """
        
        return summary.strip()
    
    async def get_real_time_insights(self) -> List[Dict[str, Any]]:
        """Get real-time business insights for dashboards."""
        
        # Get recent data (limited to last 24 hours)
        feedback_collector = await get_feedback_collector()
        recent_summary = await feedback_collector.get_feedback_summary()
        
        insights = []
        
        # Real-time satisfaction alert
        current_rating = recent_summary.get("avg_rating", 3.5)
        if current_rating > 4.5:
            insights.append({
                "type": "positive_trend",
                "title": "Exceptional Hour Performance",
                "message": f"Current satisfaction: {current_rating:.2f}/5.0",
                "priority": "medium"
            })
        elif current_rating < 3.0:
            insights.append({
                "type": "alert", 
                "title": "Satisfaction Below Threshold",
                "message": f"Current satisfaction: {current_rating:.2f}/5.0 - Investigate immediately",
                "priority": "high"
            })
        
        # Real-time escalation alert
        current_escalation = recent_summary.get("escalation_rate", 0.15)
        if current_escalation > 0.25:
            insights.append({
                "type": "alert",
                "title": "High Escalation Rate",
                "message": f"Current escalations: {current_escalation:.1%} - Check system health",
                "priority": "high"
            })
        
        # Real-time volume insights
        current_volume = recent_summary.get("total_feedback", 0)
        if current_volume > 0:
            insights.append({
                "type": "info",
                "title": "Current Activity",
                "message": f"{current_volume} interactions in last hour",
                "priority": "low"
            })
        
        return insights
    
    async def export_business_data(self, 
                                  format: str = "json",
                                  include_predictions: bool = False) -> Dict[str, Any]:
        """Export business intelligence data for external systems."""
        
        report = await self.generate_business_intelligence_report()
        
        export_data = {
            "report": asdict(report),
            "financial_models": self.financial_models,
            "market_baselines": self.market_baselines,
            "export_timestamp": datetime.utcnow().isoformat()
        }
        
        if include_predictions:
            # Add predictive analytics (placeholder for future implementation)
            export_data["predictions"] = {
                "satisfaction_trend_30d": "stable_improvement",
                "automation_rate_forecast": financial_analysis.automation_rate * 1.05,
                "revenue_growth_prediction": "15-20% quarterly growth potential"
            }
        
        return export_data


# Global business intelligence engine instance
_bi_engine_instance = None

async def get_business_intelligence_engine() -> BusinessIntelligenceEngine:
    """Get global business intelligence engine instance."""
    global _bi_engine_instance
    if _bi_engine_instance is None:
        _bi_engine_instance = BusinessIntelligenceEngine()
    return _bi_engine_instance