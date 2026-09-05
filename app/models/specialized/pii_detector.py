"""
PII Detection Model - Specialized NER-based PII detection.

Replaces the regex-based PII detection in safety_checker.py with a 
production-grade Named Entity Recognition model using Presidio.

This matches the "PII Detection Model" in Layer 4 of the architecture diagram.
"""
from typing import List, Dict, Any
import asyncio
from pathlib import Path

from app.core.logging import get_logger

logger = get_logger(__name__)


class PIIDetectionResult:
    """Result of PII detection with detailed information."""
    
    def __init__(
        self, 
        has_pii: bool, 
        pii_types: List[str], 
        redacted_text: str,
        confidence_scores: Dict[str, float],
        entities: List[Dict[str, Any]]
    ):
        self.has_pii = has_pii
        self.pii_types = pii_types  # ['PERSON', 'SSN', 'CREDIT_CARD', etc.]
        self.redacted_text = redacted_text
        self.confidence_scores = confidence_scores  # {'SSN': 0.95, 'PERSON': 0.87}
        self.entities = entities  # Raw entity detection results


class AdvancedPIIDetector:
    """
    Production-grade PII detection using Microsoft Presidio.
    
    Detects:
    - SSN, Credit Card Numbers, Bank Account Numbers
    - Personal Names, Email Addresses, Phone Numbers  
    - Medical Record Numbers, Driver License Numbers
    - Custom financial PII patterns (routing numbers, etc.)
    
    Supports:
    - Confidence scoring for each detection
    - Text redaction with configurable masking
    - Custom entity patterns for financial domain
    """
    
    # High-confidence threshold for PII blocking
    BLOCKING_THRESHOLD = 0.8
    
    # Custom financial patterns not in base Presidio
    CUSTOM_PATTERNS = [
        {
            "name": "ROUTING_NUMBER",
            "regex": r"\b[0-9]{9}\b",
            "context": ["routing", "aba", "routing number"],
        },
        {
            "name": "ACCOUNT_NUMBER", 
            "regex": r"\b[0-9]{8,17}\b",
            "context": ["account", "acct", "account number"],
        },
        {
            "name": "LOAN_NUMBER",
            "regex": r"\b[A-Z]{2,4}[0-9]{6,12}\b", 
            "context": ["loan", "mortgage", "loan number"],
        }
    ]
    
    def __init__(self):
        self._analyzer = None
        self._anonymizer = None
        self._initialized = False
    
    async def _initialize(self):
        """Lazy initialization of Presidio components."""
        if self._initialized:
            return
            
        try:
            from presidio_analyzer import AnalyzerEngine, PatternRecognizer
            from presidio_anonymizer import AnonymizerEngine
            
            # Create analyzer with custom financial patterns
            self._analyzer = AnalyzerEngine()
            
            # Add custom financial recognizers
            for pattern in self.CUSTOM_PATTERNS:
                recognizer = PatternRecognizer(
                    supported_entity=pattern["name"],
                    patterns=[{
                        "name": pattern["name"].lower(),
                        "regex": pattern["regex"],
                        "score": 0.7  # Medium confidence for regex
                    }],
                    context=pattern["context"]
                )
                self._analyzer.registry.add_recognizer(recognizer)
            
            # Create anonymizer for text redaction
            self._anonymizer = AnonymizerEngine()
            
            self._initialized = True
            logger.info("Advanced PII detector initialized with custom financial patterns")
            
        except ImportError:
            logger.warning(
                "Presidio not installed. Install with: pip install presidio-analyzer presidio-anonymizer"
            )
            # Fallback to basic regex detection
            self._initialized = "fallback"
        except Exception as e:
            logger.error(f"Failed to initialize PII detector: {e}")
            self._initialized = "fallback"
    
    def _fallback_detect(self, text: str) -> PIIDetectionResult:
        """Fallback to regex-based detection if Presidio unavailable."""
        import re
        
        # Basic regex patterns (from original safety_checker.py)
        patterns = {
            "SSN": r"\b\d{3}-\d{2}-\d{4}\b",
            "CREDIT_CARD": r"\b\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}\b", 
            "PHONE_NUMBER": r"\b\d{3}[-.]\d{3}[-.]\d{4}\b",
            "EMAIL": r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"
        }
        
        found_pii = []
        redacted = text
        
        for pii_type, pattern in patterns.items():
            matches = re.finditer(pattern, text)
            for match in matches:
                found_pii.append(pii_type)
                # Redact with type-specific masking
                mask = f"[{pii_type}_REDACTED]"
                redacted = redacted.replace(match.group(), mask)
        
        return PIIDetectionResult(
            has_pii=len(found_pii) > 0,
            pii_types=list(set(found_pii)),
            redacted_text=redacted,
            confidence_scores={pii: 0.7 for pii in set(found_pii)},
            entities=[]
        )
    
    async def detect_pii(
        self, 
        text: str, 
        language: str = "en",
        return_redacted: bool = True
    ) -> PIIDetectionResult:
        """
        Detect PII in text and optionally return redacted version.
        
        Args:
            text: Input text to analyze
            language: Language code (default: 'en') 
            return_redacted: Whether to return redacted text
            
        Returns:
            PIIDetectionResult with detection results and optional redacted text
        """
        await self._initialize()
        
        # Fallback to regex if Presidio failed to load
        if self._initialized == "fallback":
            return self._fallback_detect(text)
        
        try:
            # Analyze text for PII entities
            results = self._analyzer.analyze(
                text=text,
                language=language,
                return_decision_process=False
            )
            
            # Filter by confidence threshold
            high_confidence_entities = [
                r for r in results 
                if r.score >= self.BLOCKING_THRESHOLD
            ]
            
            # Extract PII types and confidence scores
            pii_types = list(set([r.entity_type for r in high_confidence_entities]))
            confidence_scores = {
                r.entity_type: r.score 
                for r in high_confidence_entities
            }
            
            # Generate redacted text if requested
            redacted_text = text
            if return_redacted and high_confidence_entities:
                # Use Presidio anonymizer for clean redaction
                anonymized = self._anonymizer.anonymize(
                    text=text,
                    analyzer_results=high_confidence_entities,
                    operators={
                        "DEFAULT": {"type": "mask", "masking_char": "*", "chars_to_mask": 4, "from_end": True}
                    }
                )
                redacted_text = anonymized.text
            
            return PIIDetectionResult(
                has_pii=len(high_confidence_entities) > 0,
                pii_types=pii_types,
                redacted_text=redacted_text,
                confidence_scores=confidence_scores,
                entities=[{
                    "type": r.entity_type,
                    "start": r.start,
                    "end": r.end, 
                    "score": r.score,
                    "text": text[r.start:r.end]
                } for r in high_confidence_entities]
            )
            
        except Exception as e:
            logger.warning(f"PII detection failed, using fallback: {e}")
            return self._fallback_detect(text)
    
    async def is_safe_for_processing(self, text: str) -> bool:
        """
        Quick safety check - returns True if text is safe to process.
        Used by safety_checker.py as a drop-in replacement.
        """
        result = await self.detect_pii(text, return_redacted=False)
        return not result.has_pii
    
    async def get_redacted_text(self, text: str) -> str:
        """
        Return redacted version of text for safe logging.
        Used by logging middleware to sanitize logs.
        """
        result = await self.detect_pii(text, return_redacted=True)
        return result.redacted_text


# Global singleton for efficient reuse
_pii_detector_instance = None

async def get_pii_detector() -> AdvancedPIIDetector:
    """Get the global PII detector singleton."""
    global _pii_detector_instance
    if _pii_detector_instance is None:
        _pii_detector_instance = AdvancedPIIDetector()
        await _pii_detector_instance._initialize()
    return _pii_detector_instance