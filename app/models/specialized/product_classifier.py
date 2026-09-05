"""
Product Classification Model - Multi-label product assignment for banking complaints.

Automatically tags customer messages with relevant banking product categories
for proper routing to specialized teams and knowledge retrieval.

This matches the "Classification Model (Routing, Policy)" and "Multi-Label Product Assignment" 
from Layer 4 of the architecture diagram.
"""
from typing import Dict, List, Set, Tuple
import asyncio
import json

from app.core.logging import get_logger

logger = get_logger(__name__)


class ProductClassificationResult:
    """Result of product classification with confidence scores."""
    
    def __init__(
        self,
        primary_product: str,
        all_products: List[str], 
        confidence_scores: Dict[str, float],
        routing_suggestions: List[str]
    ):
        self.primary_product = primary_product  # Most likely product
        self.all_products = all_products  # All detected products (multi-label)
        self.confidence_scores = confidence_scores  # Product -> confidence score
        self.routing_suggestions = routing_suggestions  # Suggested team/department routing


class BankingProductClassifier:
    """
    Multi-label classifier for banking products and services.
    
    Product Categories (aligned with CFPB complaint categories):
    - credit_card: Credit cards, charge cards, store cards
    - checking_savings: Checking accounts, savings accounts, CDs
    - mortgage: Home loans, refinancing, home equity
    - student_loan: Federal/private student loans, servicing
    - auto_loan: Vehicle financing, auto loans, leases  
    - personal_loan: Personal loans, installment loans
    - debt_collection: Debt collection, third-party collectors
    - credit_reporting: Credit reports, credit monitoring, disputes
    - money_transfer: Wire transfers, remittances, payment services
    - prepaid_card: Prepaid cards, gift cards, stored value
    - payday_loan: Payday loans, title loans, small dollar loans
    - other: General banking, miscellaneous financial services
    
    Routing Logic:
    - Routes to appropriate specialist teams
    - Flags high-risk products (payday loans, debt collection)
    - Identifies cross-selling opportunities
    """
    
    # Product keyword mappings
    PRODUCT_KEYWORDS = {
        "credit_card": {
            "primary": ["credit card", "charge card", "mastercard", "visa", "amex", "american express"],
            "secondary": ["apr", "interest rate", "credit limit", "balance transfer", "cash advance", 
                         "minimum payment", "late fee", "overlimit", "chargeback"],
            "context": ["card", "credit", "statement", "billing"]
        },
        "checking_savings": {
            "primary": ["checking", "savings", "bank account", "deposit", "withdrawal", "cd", 
                       "certificate of deposit", "money market"],
            "secondary": ["overdraft", "nsf", "insufficient funds", "direct deposit", "ach", 
                         "debit card", "atm", "check", "balance"],
            "context": ["account", "deposit", "withdraw", "balance"]
        },
        "mortgage": {
            "primary": ["mortgage", "home loan", "refinance", "refinancing", "heloc", 
                       "home equity", "foreclosure"],
            "secondary": ["escrow", "property tax", "homeowners insurance", "pmi", "closing costs",
                         "appraisal", "loan modification", "forbearance"],
            "context": ["home", "house", "property", "real estate"]
        },
        "student_loan": {
            "primary": ["student loan", "education loan", "college loan", "university loan"],
            "secondary": ["deferment", "forbearance", "income driven", "pslf", "forgiveness",
                         "consolidation", "graduation", "school"],
            "context": ["student", "education", "school", "college", "university"]
        },
        "auto_loan": {
            "primary": ["auto loan", "car loan", "vehicle loan", "car financing", "auto financing"],
            "secondary": ["trade in", "down payment", "gap insurance", "repossession", "vehicle"],
            "context": ["car", "vehicle", "auto", "truck", "motorcycle"]
        },
        "personal_loan": {
            "primary": ["personal loan", "installment loan", "signature loan", "unsecured loan"],
            "secondary": ["fixed rate", "monthly payment", "loan amount", "approval"],
            "context": ["loan", "borrow", "financing"]
        },
        "debt_collection": {
            "primary": ["debt collection", "collector", "collection agency", "debt collector"],
            "secondary": ["validation", "cease and desist", "harassment", "fdcpa", "debt verification"],
            "context": ["collect", "debt", "owe", "pay"]
        },
        "credit_reporting": {
            "primary": ["credit report", "credit score", "credit monitoring", "credit bureau"],
            "secondary": ["dispute", "fraud alert", "freeze", "identity theft", "experian", 
                         "equifax", "transunion", "fico"],
            "context": ["credit", "report", "score", "bureau"]
        },
        "money_transfer": {
            "primary": ["wire transfer", "money transfer", "remittance", "international transfer"],
            "secondary": ["swift", "routing number", "beneficiary", "sender", "exchange rate"],
            "context": ["transfer", "send", "wire", "remit"]
        },
        "prepaid_card": {
            "primary": ["prepaid card", "gift card", "stored value", "reload"],
            "secondary": ["activation", "balance", "fees", "reload"],
            "context": ["prepaid", "gift", "card"]
        },
        "payday_loan": {
            "primary": ["payday loan", "cash advance", "title loan", "small dollar loan"],
            "secondary": ["rollover", "renewal", "high interest", "short term"],
            "context": ["payday", "cash advance", "quick cash"]
        }
    }
    
    # Team routing based on product classification
    ROUTING_MAP = {
        "credit_card": ["credit_card_team", "billing_disputes"],
        "checking_savings": ["retail_banking", "deposit_operations"],
        "mortgage": ["mortgage_team", "loan_servicing", "foreclosure_prevention"],
        "student_loan": ["student_loan_team", "loan_servicing"],
        "auto_loan": ["auto_lending", "loan_servicing"],
        "personal_loan": ["personal_lending", "loan_servicing"],
        "debt_collection": ["collections_compliance", "legal_team"],  # High priority routing
        "credit_reporting": ["credit_operations", "fraud_team"],
        "money_transfer": ["wire_operations", "compliance"],
        "prepaid_card": ["prepaid_operations", "card_services"],
        "payday_loan": ["consumer_protection", "compliance"],  # High scrutiny
        "other": ["general_support", "customer_service"]
    }
    
    # High-risk products needing special handling
    HIGH_RISK_PRODUCTS = {"debt_collection", "payday_loan", "mortgage"}
    
    def __init__(self):
        self._model = None
        self._initialized = False
    
    async def _initialize(self):
        """Initialize classification model."""
        if self._initialized:
            return
            
        try:
            # For now, use keyword-based classification
            # In production, would use a fine-tuned transformer model
            # trained on CFPB complaint data
            
            self._initialized = True
            logger.info("Banking product classifier initialized (keyword-based)")
            
        except Exception as e:
            logger.error(f"Failed to initialize product classifier: {e}")
            self._initialized = "fallback"
    
    def _calculate_product_scores(self, text: str) -> Dict[str, float]:
        """Calculate confidence scores for each product category."""
        text_lower = text.lower()
        scores = {}
        
        for product, keywords in self.PRODUCT_KEYWORDS.items():
            score = 0.0
            
            # Primary keyword matches (high weight)
            for keyword in keywords["primary"]:
                if keyword in text_lower:
                    score += 0.4
            
            # Secondary keyword matches (medium weight) 
            for keyword in keywords["secondary"]:
                if keyword in text_lower:
                    score += 0.2
                    
            # Context keyword matches (low weight)
            for keyword in keywords["context"]:
                if keyword in text_lower:
                    score += 0.1
            
            # Normalize score to 0-1 range
            scores[product] = min(1.0, score)
        
        return scores
    
    def _determine_routing(self, products: List[str]) -> List[str]:
        """Determine routing suggestions based on detected products."""
        all_routes = set()
        
        for product in products:
            routes = self.ROUTING_MAP.get(product, ["general_support"])
            all_routes.update(routes)
        
        # Prioritize high-risk product routing
        high_risk_routes = []
        for product in products:
            if product in self.HIGH_RISK_PRODUCTS:
                high_risk_routes.extend(self.ROUTING_MAP[product])
        
        if high_risk_routes:
            return high_risk_routes[:2]  # Return top 2 high-priority routes
        
        return list(all_routes)[:3]  # Return top 3 routes
    
    async def classify_products(
        self, 
        text: str, 
        threshold: float = 0.3,
        max_products: int = 3
    ) -> ProductClassificationResult:
        """
        Classify banking products mentioned in customer text.
        
        Args:
            text: Customer message to classify
            threshold: Minimum confidence threshold for product inclusion
            max_products: Maximum number of products to return
            
        Returns:
            ProductClassificationResult with detected products and routing suggestions
        """
        await self._initialize()
        
        # Calculate scores for all products
        scores = self._calculate_product_scores(text)
        
        # Filter by threshold and sort by confidence
        qualified_products = [
            (product, score) for product, score in scores.items() 
            if score >= threshold
        ]
        qualified_products.sort(key=lambda x: x[1], reverse=True)
        
        # Limit to max_products
        top_products = qualified_products[:max_products]
        
        if not top_products:
            # Default to "other" if no clear product detected
            top_products = [("other", 0.5)]
        
        # Extract product names and scores
        product_names = [product for product, _ in top_products]
        confidence_scores = dict(top_products)
        
        # Primary product is highest confidence
        primary_product = product_names[0]
        
        # Generate routing suggestions
        routing_suggestions = self._determine_routing(product_names)
        
        return ProductClassificationResult(
            primary_product=primary_product,
            all_products=product_names,
            confidence_scores=confidence_scores,
            routing_suggestions=routing_suggestions
        )
    
    async def get_primary_product(self, text: str) -> str:
        """Quick method to get just the primary product classification."""
        result = await self.classify_products(text)
        return result.primary_product
    
    async def is_high_risk_product(self, text: str) -> bool:
        """Check if message relates to high-risk products requiring special handling."""
        result = await self.classify_products(text)
        return any(product in self.HIGH_RISK_PRODUCTS for product in result.all_products)
    
    async def get_routing_team(self, text: str) -> str:
        """Get the primary routing team for this message."""
        result = await self.classify_products(text)
        return result.routing_suggestions[0] if result.routing_suggestions else "general_support"


# Global singleton
_product_classifier_instance = None

async def get_product_classifier() -> BankingProductClassifier:
    """Get the global product classifier singleton."""
    global _product_classifier_instance
    if _product_classifier_instance is None:
        _product_classifier_instance = BankingProductClassifier()
        await _product_classifier_instance._initialize()
    return _product_classifier_instance