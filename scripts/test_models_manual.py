#!/usr/bin/env python3
"""
Manual testing script for specialized models.
Allows interactive testing of models with real examples.
"""
import asyncio
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.models.specialized import (
    get_pii_detector,
    get_sentiment_analyzer,
    get_product_classifier,
    get_policy_classifier
)

async def test_pii_detection():
    """Test PII detection with sample texts."""
    print("\n🔍 PII Detection Tests")
    print("=" * 50)
    
    pii_detector = await get_pii_detector()
    
    test_cases = [
        "My name is John Smith and my SSN is 123-45-6789.",
        "Please call me at (555) 123-4567 or email john@example.com.",
        "My credit card number is 4532-1234-5678-9012.",
        "I live at 123 Main Street, Anytown, CA 90210.",
        "I would like to check my account balance please."  # No PII
    ]
    
    for i, text in enumerate(test_cases, 1):
        print(f"\nTest {i}: {text}")
        try:
            result = await pii_detector.detect_pii(text)
            print(f"  Has PII: {result.has_pii}")
            print(f"  Risk Level: {result.risk_level}")
            print(f"  Entities: {result.detected_entities}")
            print(f"  Masked: {result.masked_text}")
        except Exception as e:
            print(f"  ❌ Error: {e}")

async def test_sentiment_analysis():
    """Test sentiment analysis with sample texts."""
    print("\n😊 Sentiment Analysis Tests")
    print("=" * 50)
    
    sentiment_analyzer = await get_sentiment_analyzer()
    
    test_cases = [
        "Thank you so much! Excellent customer service!",
        "I am extremely frustrated with these unauthorized charges!",
        "Can you help me understand my statement?",
        "This is the worst bank ever! I'm closing my account!",
        "I need to report fraud on my credit card immediately."
    ]
    
    for i, text in enumerate(test_cases, 1):
        print(f"\nTest {i}: {text}")
        try:
            result = await sentiment_analyzer.analyze_sentiment(text)
            print(f"  Sentiment: {result.sentiment}")
            print(f"  Confidence: {result.confidence:.2f}")
            print(f"  Escalate: {result.escalation_recommended}")
            print(f"  Emotions: {result.emotions}")
            if result.escalation_reason:
                print(f"  Reason: {result.escalation_reason}")
        except Exception as e:
            print(f"  ❌ Error: {e}")

async def test_product_classification():
    """Test product classification with sample texts."""
    print("\n🏦 Product Classification Tests") 
    print("=" * 50)
    
    product_classifier = await get_product_classifier()
    
    test_cases = [
        "I have a problem with my credit card billing",
        "My checking account was charged an overdraft fee", 
        "I need help with my mortgage payment",
        "Issues with both my savings account and credit card",
        "A debt collector is calling about an old account",
        "What are your current interest rates?"
    ]
    
    for i, text in enumerate(test_cases, 1):
        print(f"\nTest {i}: {text}")
        try:
            result = await product_classifier.classify_products(text)
            print(f"  Primary: {result.primary_product}")
            print(f"  All Products: {result.all_products}")
            print(f"  Confidence: {result.confidence_scores}")
            print(f"  Routing: {result.routing_suggestions[:3]}...")
        except Exception as e:
            print(f"  ❌ Error: {e}")

async def test_policy_classification():
    """Test policy classification with sample texts."""
    print("\n📋 Policy Classification Tests")
    print("=" * 50)
    
    policy_classifier = await get_policy_classifier()
    
    test_cases = [
        "What are my rights under the Fair Credit Reporting Act?",
        "What fees can banks charge for overdrafts?",
        "How do I dispute an error on my credit report?",
        "Can banks share my personal information with third parties?",
        "Are there federal laws about predatory lending?",
        "What is the CFPB and how can they help me?"
    ]
    
    for i, text in enumerate(test_cases, 1):
        print(f"\nTest {i}: {text}")
        try:
            result = await policy_classifier.classify_policy(text)
            print(f"  Primary: {result.primary_category}")
            print(f"  All Categories: {result.all_categories}")
            print(f"  Confidence: {result.confidence_scores}")
            print(f"  Regulatory: {result.regulatory_areas}")
            print(f"  Risk: {result.compliance_risk}")
        except Exception as e:
            print(f"  ❌ Error: {e}")

async def test_integration_scenario():
    """Test a complete scenario with all models."""
    print("\n🔗 Integration Scenario Test")
    print("=" * 50)
    
    scenario_text = (
        "I am furious! Someone used my credit card 4532-1234-5678-9012 "
        "for unauthorized purchases. My name is John Smith and this is fraud! "
        "I want to file a complaint with the CFPB immediately!"
    )
    
    print(f"Scenario: {scenario_text}")
    print()
    
    try:
        # Run all models
        pii_detector = await get_pii_detector()
        sentiment_analyzer = await get_sentiment_analyzer()
        product_classifier = await get_product_classifier()
        policy_classifier = await get_policy_classifier()
        
        pii_result = await pii_detector.detect_pii(scenario_text)
        sentiment_result = await sentiment_analyzer.analyze_sentiment(scenario_text)
        product_result = await product_classifier.classify_products(scenario_text)
        
        policy_text = "What are my rights when reporting credit card fraud?"
        policy_result = await policy_classifier.classify_policy(policy_text)
        
        # Summary
        print("📊 Integration Results:")
        print(f"  PII Risk: {pii_result.risk_level} ({len(pii_result.detected_entities)} entities)")
        print(f"  Sentiment: {sentiment_result.sentiment} (escalate: {sentiment_result.escalation_recommended})")
        print(f"  Product: {product_result.primary_product}")
        print(f"  Policy: {policy_result.primary_category}")
        
        # Decision logic
        should_escalate = (
            pii_result.risk_level == "high" or
            sentiment_result.escalation_recommended or
            policy_result.compliance_risk == "high"
        )
        
        print(f"\n🚨 ESCALATION DECISION: {'YES' if should_escalate else 'NO'}")
        
        if should_escalate:
            reasons = []
            if pii_result.risk_level == "high":
                reasons.append("High PII risk")
            if sentiment_result.escalation_recommended:
                reasons.append("Negative sentiment")
            if policy_result.compliance_risk == "high":
                reasons.append("Compliance risk")
            print(f"   Reasons: {', '.join(reasons)}")
        
    except Exception as e:
        print(f"❌ Integration test failed: {e}")

async def main():
    """Run all manual tests."""
    print("🧪 Financial AI Agent - Manual Model Testing")
    print("=" * 60)
    
    try:
        await test_pii_detection()
        await test_sentiment_analysis()
        await test_product_classification()
        await test_policy_classification()
        await test_integration_scenario()
        
        print("\n✅ Manual testing completed successfully!")
        
    except KeyboardInterrupt:
        print("\n\n⏹️ Testing interrupted by user")
    except Exception as e:
        print(f"\n❌ Testing failed: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(asyncio.run(main()))