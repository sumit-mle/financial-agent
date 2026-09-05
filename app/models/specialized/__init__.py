"""
Specialized Models Package - Task-specific models for Layer 4.

This package contains all the specialized models referenced in the 
Fin AI Architecture diagram Layer 4 "System of Specialized Models":

- PII Detection Model (Presidio-based NER)
- Sentiment Model (Emotional analysis for escalation)  
- Product Classification Model (Multi-label banking products)
- Policy Classification Model (Regulatory compliance)

These models work together to provide specialized intelligence beyond
the core LLM, enabling more accurate routing, compliance checking,
and customer experience optimization.
"""

from .pii_detector import AdvancedPIIDetector, get_pii_detector
from .sentiment_analyzer import FinancialSentimentAnalyzer, get_sentiment_analyzer  
from .product_classifier import BankingProductClassifier, get_product_classifier
from .policy_classifier import RegulatoryPolicyClassifier, get_policy_classifier

__all__ = [
    "AdvancedPIIDetector",
    "FinancialSentimentAnalyzer", 
    "BankingProductClassifier",
    "RegulatoryPolicyClassifier",
    "get_pii_detector",
    "get_sentiment_analyzer",
    "get_product_classifier", 
    "get_policy_classifier",
]