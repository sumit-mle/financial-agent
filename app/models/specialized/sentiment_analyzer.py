"""
Sentiment Analysis Model - Emotional state detection for escalation logic.

Analyzes customer messages for emotional intensity and frustration to
determine if immediate escalation to human agents is needed.

This matches the "Sentiment Model (Emotional)" in Layer 4 of the architecture diagram.
"""
from typing import Any, Dict, Tuple, List
import asyncio

from app.core.logging import get_logger

logger = get_logger(__name__)


class SentimentResult:
    """Result of sentiment analysis with detailed emotional breakdown."""
    
    def __init__(
        self,
        overall_sentiment: str,  # 'positive', 'negative', 'neutral'
        confidence: float,       # 0.0 to 1.0
        emotional_intensity: float,  # 0.0 to 1.0 (how strong the emotion is)
        emotions: Dict[str, float],  # {'anger': 0.8, 'frustration': 0.6, 'satisfaction': 0.1}
        escalation_recommended: bool,
        escalation_reason: str
    ):
        self.overall_sentiment = overall_sentiment
        self.confidence = confidence
        self.emotional_intensity = emotional_intensity
        self.emotions = emotions
        self.escalation_recommended = escalation_recommended
        self.escalation_reason = escalation_reason


class FinancialSentimentAnalyzer:
    """
    Specialized sentiment analyzer for financial customer service contexts.
    
    Features:
    - Multi-class emotion detection (anger, frustration, satisfaction, urgency)
    - Financial domain-specific keywords and patterns
    - Escalation triggers based on emotional intensity
    - Confidence scoring for reliable escalation decisions
    
    Escalation Triggers:
    - High anger/frustration (>0.7) 
    - Urgent financial distress keywords
    - Threats or legal language
    - Multiple complaint indicators
    """
    
    # Escalation thresholds
    ESCALATION_THRESHOLDS = {
        "anger": 0.7,
        "frustration": 0.6,
        "urgency": 0.8,
        "distress": 0.7
    }
    
    # Financial distress keywords (high priority for escalation)
    DISTRESS_KEYWORDS = [
        # Financial hardship
        "bankruptcy", "foreclosure", "eviction", "garnishment", "levy",
        "collection", "debt collector", "lawsuit", "court", "legal action",
        
        # Urgent financial needs  
        "emergency", "urgent", "immediately", "asap", "right now",
        "can't pay", "behind on payments", "overdue", "past due",
        
        # Emotional distress
        "desperate", "hopeless", "stressed", "anxiety", "panic",
        "suicidal", "harm", "depression", "overwhelmed",
        
        # Complaint escalation
        "manager", "supervisor", "complaint", "file a complaint",
        "attorney", "lawyer", "regulatory", "cfpb", "fdic"
    ]
    
    # Positive resolution keywords
    SATISFACTION_KEYWORDS = [
        "thank you", "resolved", "helpful", "satisfied", "appreciate",
        "excellent", "great service", "problem solved", "fixed"
    ]
    
    def __init__(self):
        self._model = None
        self._initialized = False
        
    async def _initialize(self):
        """Initialize sentiment models (HuggingFace transformers)."""
        if self._initialized:
            return
            
        try:
            from transformers import pipeline
            
            # Use a financial-domain fine-tuned model if available,
            # otherwise fall back to general sentiment analysis
            model_name = "cardiffnlp/twitter-roberta-base-sentiment-latest"
            
            self._model = pipeline(
                "sentiment-analysis",
                model=model_name,
                device=-1,  # CPU inference (set to 0 for GPU)
                # Ask for every label's score. `top_k=None` replaces the old
                # `return_all_scores=True`, which current transformers versions
                # no longer honour — leaving the pipeline in single-label mode
                # and returning a bare dict where a list is expected.
                top_k=None,
            )
            
            self._initialized = True
            logger.info("Financial sentiment analyzer initialized", model=model_name)
            
        except ImportError:
            logger.warning(
                "Transformers not installed. Install with: pip install transformers torch"
            )
            self._initialized = "fallback"
        except Exception as e:
            logger.error(f"Failed to initialize sentiment analyzer: {e}")
            self._initialized = "fallback"
    
    @staticmethod
    def _normalize_scores(raw: Any) -> List[Dict[str, Any]]:
        """
        Flatten a transformers classification output to ``[{label, score}, …]``.

        The pipeline's shape depends on the version and on whether ``top_k`` was
        honoured: it may hand back a bare dict, a flat list of dicts, or a
        batch-shaped list-of-lists. Normalizing here keeps ``analyze_sentiment``
        from indexing into whichever shape it happens to get — the old
        ``self._model(text)[0]`` produced a *string key* on the bare-dict shape
        and threw on every single call.

        Returns an empty list when the shape isn't recognized, so the caller
        raises rather than silently mis-scoring.
        """
        if isinstance(raw, dict):
            raw = [raw]
        if not isinstance(raw, list) or not raw:
            return []
        # Batch shape: [[{...}, {...}]] — unwrap the single input's scores.
        if isinstance(raw[0], list):
            raw = raw[0]
        return [
            item for item in raw
            if isinstance(item, dict) and "label" in item and "score" in item
        ]

    def _fallback_analyze(self, text: str) -> SentimentResult:
        """Keyword-based sentiment analysis used when the model is unavailable."""
        text_lower = text.lower()
        
        # Count positive/negative/distress keywords
        distress_count = sum(1 for keyword in self.DISTRESS_KEYWORDS if keyword in text_lower)
        satisfaction_count = sum(1 for keyword in self.SATISFACTION_KEYWORDS if keyword in text_lower)
        
        # Simple heuristic scoring
        if distress_count >= 2:
            return SentimentResult(
                overall_sentiment="negative",
                confidence=0.8,
                emotional_intensity=0.9,
                emotions={"distress": 0.9, "anger": 0.7, "frustration": 0.8},
                escalation_recommended=True,
                escalation_reason="Multiple distress indicators detected"
            )
        elif distress_count >= 1:
            return SentimentResult(
                overall_sentiment="negative", 
                confidence=0.6,
                emotional_intensity=0.7,
                emotions={"distress": 0.7, "frustration": 0.6},
                escalation_recommended=True,
                escalation_reason="Financial distress detected"
            )
        elif satisfaction_count >= 1:
            return SentimentResult(
                overall_sentiment="positive",
                confidence=0.7,
                emotional_intensity=0.3,
                emotions={"satisfaction": 0.8},
                escalation_recommended=False,
                escalation_reason=""
            )
        else:
            return SentimentResult(
                overall_sentiment="neutral",
                confidence=0.5,
                emotional_intensity=0.3,
                emotions={"neutral": 0.6},
                escalation_recommended=False,
                escalation_reason=""
            )
    
    def _calculate_emotional_intensity(self, text: str, base_sentiment_scores: List[Dict]) -> Dict[str, float]:
        """Calculate detailed emotional breakdown."""
        text_lower = text.lower()
        emotions = {"anger": 0.0, "frustration": 0.0, "urgency": 0.0, "distress": 0.0, "satisfaction": 0.0}
        
        # Keyword-based emotion detection
        anger_keywords = ["angry", "mad", "furious", "outraged", "pissed", "livid"]
        frustration_keywords = ["frustrated", "annoyed", "irritated", "fed up", "sick of"]
        urgency_keywords = ["urgent", "emergency", "immediately", "asap", "now"]
        
        # Score based on keyword presence and context
        for keyword in anger_keywords:
            if keyword in text_lower:
                emotions["anger"] = min(1.0, emotions["anger"] + 0.3)
                
        for keyword in frustration_keywords:
            if keyword in text_lower:
                emotions["frustration"] = min(1.0, emotions["frustration"] + 0.25)
                
        for keyword in urgency_keywords:
            if keyword in text_lower:
                emotions["urgency"] = min(1.0, emotions["urgency"] + 0.4)
        
        # Distress based on financial hardship keywords
        distress_score = sum(0.2 for keyword in self.DISTRESS_KEYWORDS if keyword in text_lower)
        emotions["distress"] = min(1.0, distress_score)
        
        # Satisfaction based on positive keywords
        satisfaction_score = sum(0.3 for keyword in self.SATISFACTION_KEYWORDS if keyword in text_lower)
        emotions["satisfaction"] = min(1.0, satisfaction_score)
        
        # Boost emotions based on sentiment model confidence
        if base_sentiment_scores:
            negative_score = next((s["score"] for s in base_sentiment_scores if s["label"] == "NEGATIVE"), 0)
            if negative_score > 0.7:
                emotions["anger"] = min(1.0, emotions["anger"] + 0.2)
                emotions["frustration"] = min(1.0, emotions["frustration"] + 0.2)
        
        return emotions
    
    def _should_escalate(self, emotions: Dict[str, float], text: str) -> Tuple[bool, str]:
        """Determine if emotional state warrants escalation."""
        reasons = []
        
        # Check individual emotion thresholds
        for emotion, threshold in self.ESCALATION_THRESHOLDS.items():
            if emotions.get(emotion, 0) >= threshold:
                reasons.append(f"High {emotion} detected ({emotions[emotion]:.2f})")
        
        # Special cases
        text_lower = text.lower()
        
        # Legal/regulatory threats
        legal_keywords = ["lawsuit", "lawyer", "attorney", "cfpb", "fdic", "regulatory", "legal action"]
        if any(keyword in text_lower for keyword in legal_keywords):
            reasons.append("Legal or regulatory language detected")
        
        # Multiple complaint indicators
        complaint_keywords = ["complaint", "file complaint", "manager", "supervisor"]
        complaint_count = sum(1 for keyword in complaint_keywords if keyword in text_lower)
        if complaint_count >= 2:
            reasons.append("Multiple complaint escalation indicators")
        
        # Threats or self-harm indicators
        threat_keywords = ["sue", "report", "harm", "hurt", "kill", "suicide"]
        if any(keyword in text_lower for keyword in threat_keywords):
            reasons.append("Threat or self-harm language detected")
        
        should_escalate = len(reasons) > 0
        escalation_reason = "; ".join(reasons) if reasons else ""
        
        return should_escalate, escalation_reason
    
    async def analyze_sentiment(self, text: str) -> SentimentResult:
        """
        Analyze sentiment and emotions for escalation decision.
        
        Args:
            text: Customer message to analyze
            
        Returns:
            SentimentResult with detailed emotional breakdown and escalation recommendation
        """
        await self._initialize()
        
        # Fallback to keyword analysis if model unavailable
        if self._initialized == "fallback":
            return self._fallback_analyze(text)
        
        try:
            # Get base sentiment scores from transformer model, normalized to a
            # flat [{label, score}, …] list regardless of pipeline shape.
            sentiment_scores = self._normalize_scores(self._model(text))
            if not sentiment_scores:
                raise ValueError("sentiment pipeline returned no usable scores")

            # Extract overall sentiment
            top_sentiment = max(sentiment_scores, key=lambda x: x["score"])
            overall_sentiment = top_sentiment["label"].lower()
            if overall_sentiment not in ["positive", "negative", "neutral"]:
                # Handle different label formats (LABEL_0, LABEL_1, etc.)
                if top_sentiment["score"] > 0.6:
                    overall_sentiment = "negative" if "1" in top_sentiment["label"] else "positive"
                else:
                    overall_sentiment = "neutral"
            
            # Calculate detailed emotions
            emotions = self._calculate_emotional_intensity(text, sentiment_scores)
            
            # Calculate overall emotional intensity
            emotional_intensity = max(emotions.values())
            
            # Escalation decision
            should_escalate, escalation_reason = self._should_escalate(emotions, text)
            
            return SentimentResult(
                overall_sentiment=overall_sentiment,
                confidence=top_sentiment["score"],
                emotional_intensity=emotional_intensity,
                emotions=emotions,
                escalation_recommended=should_escalate,
                escalation_reason=escalation_reason
            )
            
        except Exception as e:
            logger.warning(f"Sentiment analysis failed, using fallback: {e}")
            return self._fallback_analyze(text)
    
    async def should_escalate_immediately(self, text: str) -> Tuple[bool, str]:
        """
        Quick escalation check for use in safety_checker.py.
        Returns (should_escalate, reason).
        """
        result = await self.analyze_sentiment(text)
        return result.escalation_recommended, result.escalation_reason


# Global singleton
_sentiment_analyzer_instance = None

async def get_sentiment_analyzer() -> FinancialSentimentAnalyzer:
    """Get the global sentiment analyzer singleton."""
    global _sentiment_analyzer_instance
    if _sentiment_analyzer_instance is None:
        _sentiment_analyzer_instance = FinancialSentimentAnalyzer()
        await _sentiment_analyzer_instance._initialize()
    return _sentiment_analyzer_instance