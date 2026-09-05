"""
Policy Classification Model - Regulatory and compliance categorization.

Classifies customer messages for regulatory compliance categories,
policy violations, and legal requirements.

This matches the "Classification Model (Routing, Policy)" in Layer 4 of the architecture diagram.
"""
from typing import Dict, List, Tuple, Set
import asyncio

from app.core.logging import get_logger

logger = get_logger(__name__)


class PolicyClassificationResult:
    """Result of policy/compliance classification."""
    
    def __init__(
        self,
        policy_categories: List[str],
        compliance_requirements: List[str],
        risk_level: str,  # 'low', 'medium', 'high', 'critical'
        regulatory_flags: List[str],
        required_actions: List[str],
        escalation_required: bool,
        confidence_scores: Dict[str, float]
    ):
        self.policy_categories = policy_categories
        self.compliance_requirements = compliance_requirements  
        self.risk_level = risk_level
        self.regulatory_flags = regulatory_flags
        self.required_actions = required_actions
        self.escalation_required = escalation_required
        self.confidence_scores = confidence_scores


class RegulatoryPolicyClassifier:
    """
    Classifier for regulatory compliance and policy adherence.
    
    Policy Categories:
    - fair_lending: ECOA, Fair Housing Act compliance
    - privacy_data: CCPA, GDPR, GLB Act data protection
    - consumer_protection: CFPB, state consumer protection laws
    - anti_discrimination: Fair lending, equal treatment requirements
    - debt_collection: FDCPA, state debt collection laws
    - disclosure: Truth in Lending, TILA-RESPA requirements
    - accessibility: ADA, Section 508 compliance
    - fraud_prevention: BSA, AML, fraud detection requirements
    - dispute_resolution: Reg E, Reg Z dispute handling
    - record_retention: Document retention requirements
    
    Risk Levels:
    - low: General inquiries, standard complaints
    - medium: Policy questions, potential violations
    - high: Clear policy violations, regulatory complaints  
    - critical: Legal threats, regulatory investigations
    """
    
    # Regulatory framework keywords
    POLICY_KEYWORDS = {
        "fair_lending": {
            "keywords": ["discrimination", "denied", "rejection", "unfair treatment", "bias",
                        "protected class", "race", "gender", "age", "disability", "religion",
                        "ecoa", "fair housing", "redlining"],
            "risk_indicators": ["lawsuit", "discrimination complaint", "civil rights"],
            "required_actions": ["fair_lending_review", "discrimination_assessment"]
        },
        "privacy_data": {
            "keywords": ["privacy", "data protection", "personal information", "ssn", 
                        "gdpr", "ccpa", "data breach", "unauthorized access", "identity theft"],
            "risk_indicators": ["data breach", "stolen information", "privacy violation"],
            "required_actions": ["privacy_assessment", "data_protection_review"]
        },
        "consumer_protection": {
            "keywords": ["cfpb", "consumer complaint", "unfair practice", "deceptive",
                        "misleading", "consumer rights", "state attorney general"],
            "risk_indicators": ["cfpb complaint", "state investigation", "class action"],
            "required_actions": ["consumer_protection_review", "compliance_assessment"]
        },
        "debt_collection": {
            "keywords": ["debt collection", "harassment", "fdcpa", "cease and desist",
                        "validation", "collector", "collection agency", "abusive"],
            "risk_indicators": ["fdcpa violation", "harassment complaint", "illegal collection"],
            "required_actions": ["collection_compliance_review", "fdcpa_assessment"]
        },
        "disclosure": {
            "keywords": ["disclosure", "tila", "respa", "truth in lending", "apr",
                        "fees not disclosed", "hidden fees", "misleading terms"],
            "risk_indicators": ["disclosure violation", "tila violation", "hidden fees"],
            "required_actions": ["disclosure_review", "tila_compliance_check"]
        },
        "fraud_prevention": {
            "keywords": ["fraud", "money laundering", "suspicious activity", "bsa",
                        "kyc", "aml", "suspicious transaction", "identity verification"],
            "risk_indicators": ["money laundering", "terrorist financing", "suspicious activity"],
            "required_actions": ["fraud_investigation", "aml_review", "sar_consideration"]
        },
        "dispute_resolution": {
            "keywords": ["dispute", "error", "unauthorized transaction", "reg e", "reg z",
                        "chargeback", "billing error", "provisional credit"],
            "risk_indicators": ["dispute timeline violation", "reg e violation"],
            "required_actions": ["dispute_timeline_check", "regulation_compliance_review"]
        },
        "accessibility": {
            "keywords": ["accessibility", "ada", "disability", "screen reader", 
                        "reasonable accommodation", "assistive technology"],
            "risk_indicators": ["ada violation", "accessibility complaint"],
            "required_actions": ["accessibility_review", "accommodation_assessment"]
        }
    }
    
    # Critical regulatory keywords that trigger immediate escalation
    CRITICAL_REGULATORY_TERMS = [
        # Legal/regulatory bodies
        "cfpb complaint", "fdic complaint", "occ complaint", "fed complaint",
        "state attorney general", "class action", "lawsuit filed",
        
        # Legal actions
        "subpoena", "court order", "regulatory investigation", "consent order",
        "cease and desist", "regulatory action", "enforcement action",
        
        # Media/public exposure
        "media attention", "news story", "public complaint", "social media viral",
        
        # Safety/harm
        "harm", "injury", "medical bills", "financial hardship", "bankruptcy"
    ]
    
    # Compliance requirements by policy category
    COMPLIANCE_REQUIREMENTS = {
        "fair_lending": ["Equal treatment verification", "Protected class documentation", "Lending decision audit"],
        "privacy_data": ["Data encryption check", "Access control verification", "Breach notification protocol"],
        "consumer_protection": ["Consumer rights disclosure", "Fair practice verification", "Complaint documentation"],
        "debt_collection": ["FDCPA compliance check", "Communication log review", "Harassment assessment"],
        "disclosure": ["Required disclosure verification", "Fee transparency check", "Terms clarity assessment"],
        "fraud_prevention": ["Identity verification", "Transaction monitoring", "Suspicious activity review"],
        "dispute_resolution": ["Timeline compliance", "Documentation completeness", "Resolution verification"],
        "accessibility": ["ADA compliance check", "Accommodation availability", "Alternative access options"]
    }
    
    def __init__(self):
        self._initialized = False
    
    async def _initialize(self):
        """Initialize policy classification system."""
        if self._initialized:
            return
            
        self._initialized = True
        logger.info("Regulatory policy classifier initialized")
    
    def _calculate_policy_scores(self, text: str) -> Dict[str, float]:
        """Calculate confidence scores for each policy category."""
        text_lower = text.lower()
        scores = {}
        
        for policy_category, data in self.POLICY_KEYWORDS.items():
            score = 0.0
            
            # Regular keyword matches
            keyword_matches = sum(1 for keyword in data["keywords"] if keyword in text_lower)
            score += keyword_matches * 0.2
            
            # High-risk indicator matches (higher weight)
            risk_matches = sum(1 for indicator in data["risk_indicators"] if indicator in text_lower)
            score += risk_matches * 0.5
            
            # Normalize to 0-1 range
            scores[policy_category] = min(1.0, score)
        
        return scores
    
    def _determine_risk_level(self, text: str, policy_scores: Dict[str, float]) -> str:
        """Determine overall risk level based on content analysis."""
        text_lower = text.lower()
        
        # Critical level: regulatory terms or legal threats
        for term in self.CRITICAL_REGULATORY_TERMS:
            if term in text_lower:
                return "critical"
        
        # High level: clear policy violations or high scores
        max_score = max(policy_scores.values()) if policy_scores else 0
        if max_score >= 0.7:
            return "high"
        
        # Medium level: moderate scores or specific concern keywords
        if max_score >= 0.4:
            return "medium"
        
        # Check for medium-risk indicators
        medium_risk_terms = ["complaint", "violation", "unfair", "problem", "issue", "concern"]
        if any(term in text_lower for term in medium_risk_terms):
            return "medium"
        
        return "low"
    
    def _extract_regulatory_flags(self, text: str) -> List[str]:
        """Extract specific regulatory flags from text."""
        text_lower = text.lower()
        flags = []
        
        # Regulatory body mentions
        regulatory_bodies = {
            "cfpb": "CFPB mention",
            "fdic": "FDIC mention", 
            "occ": "OCC mention",
            "fed": "Federal Reserve mention",
            "attorney general": "State AG mention",
            "class action": "Class action reference"
        }
        
        for keyword, flag in regulatory_bodies.items():
            if keyword in text_lower:
                flags.append(flag)
        
        # Violation types
        violation_types = {
            "discrimination": "Discrimination allegation",
            "harassment": "Harassment complaint",
            "fraud": "Fraud allegation", 
            "privacy": "Privacy concern",
            "disclosure": "Disclosure issue"
        }
        
        for keyword, flag in violation_types.items():
            if keyword in text_lower:
                flags.append(flag)
        
        return flags
    
    def _determine_required_actions(self, policy_categories: List[str], risk_level: str) -> List[str]:
        """Determine required compliance actions."""
        actions = []
        
        # Add category-specific actions
        for category in policy_categories:
            if category in self.POLICY_KEYWORDS:
                actions.extend(self.POLICY_KEYWORDS[category]["required_actions"])
        
        # Add risk-level actions
        if risk_level == "critical":
            actions.extend(["immediate_escalation", "legal_review", "executive_notification"])
        elif risk_level == "high":
            actions.extend(["compliance_review", "supervisor_notification"])
        elif risk_level == "medium":
            actions.extend(["documentation_review", "policy_check"])
        
        return list(set(actions))  # Remove duplicates
    
    async def classify_policy_compliance(
        self, 
        text: str,
        threshold: float = 0.3
    ) -> PolicyClassificationResult:
        """
        Classify policy and compliance requirements for customer message.
        
        Args:
            text: Customer message to analyze
            threshold: Minimum confidence threshold for policy inclusion
            
        Returns:
            PolicyClassificationResult with compliance analysis
        """
        await self._initialize()
        
        # Calculate policy scores
        policy_scores = self._calculate_policy_scores(text)
        
        # Filter by threshold
        relevant_policies = [
            policy for policy, score in policy_scores.items()
            if score >= threshold
        ]
        
        # Determine risk level
        risk_level = self._determine_risk_level(text, policy_scores)
        
        # Extract regulatory flags
        regulatory_flags = self._extract_regulatory_flags(text)
        
        # Determine required actions
        required_actions = self._determine_required_actions(relevant_policies, risk_level)
        
        # Get compliance requirements
        compliance_requirements = []
        for policy in relevant_policies:
            compliance_requirements.extend(
                self.COMPLIANCE_REQUIREMENTS.get(policy, [])
            )
        
        # Escalation required for high/critical risk
        escalation_required = risk_level in ["high", "critical"]
        
        return PolicyClassificationResult(
            policy_categories=relevant_policies,
            compliance_requirements=list(set(compliance_requirements)),
            risk_level=risk_level,
            regulatory_flags=regulatory_flags,
            required_actions=required_actions,
            escalation_required=escalation_required,
            confidence_scores=policy_scores
        )
    
    async def requires_immediate_escalation(self, text: str) -> Tuple[bool, str]:
        """Quick check for immediate escalation requirements."""
        result = await self.classify_policy_compliance(text)
        
        if result.escalation_required:
            reason = f"Policy risk level: {result.risk_level}"
            if result.regulatory_flags:
                reason += f", Flags: {', '.join(result.regulatory_flags)}"
            return True, reason
        
        return False, ""
    
    async def get_compliance_requirements(self, text: str) -> List[str]:
        """Get list of compliance requirements for this message."""
        result = await self.classify_policy_compliance(text)
        return result.compliance_requirements


# Global singleton
_policy_classifier_instance = None

async def get_policy_classifier() -> RegulatoryPolicyClassifier:
    """Get the global policy classifier singleton."""
    global _policy_classifier_instance
    if _policy_classifier_instance is None:
        _policy_classifier_instance = RegulatoryPolicyClassifier()
        await _policy_classifier_instance._initialize()
    return _policy_classifier_instance