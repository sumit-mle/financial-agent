# Day 6 Implementation: ML Models & Analysis (Detailed)

**Date:** Day 6 of development  
**Theme:** Specialized ML models for financial analysis  
**Total Commits:** 5 logical commits  
**Time Span:** 7:30 AM - 7:00 PM  

---

## Overview

Day 6 focuses on building specialized models that analyze and understand financial complaints. You'll create:
- PII (Personally Identifiable Information) detection model
- Sentiment analysis classifier
- Complaint classification system
- Model factory for centralized access
- Reranking for retrieval optimization

This is where the system becomes "intelligent" about analyzing content!

---

## Commit 1 (7:30 AM): PII Detection Model

### What to Stage:
```
app/models/pii_detector.py                 ← PII detection logic
```

### Git Commands:
```bash
git add app/models/pii_detector.py
git commit -m "Implement PII detection model for data privacy"
```

### File: `app/models/pii_detector.py`
Should contain:
```python
import re
from typing import List, Dict, Any
from enum import Enum

class PIIType(Enum):
    """Types of PII we detect"""
    SSN = "ssn"
    CREDIT_CARD = "credit_card"
    EMAIL = "email"
    PHONE = "phone"
    ADDRESS = "address"
    NAME = "name"
    ACCOUNT_NUMBER = "account_number"

class PIIDetector:
    """Detect and redact personally identifiable information"""
    
    def __init__(self):
        self.patterns = {
            PIIType.SSN: r'\b\d{3}-\d{2}-\d{4}\b',
            PIIType.CREDIT_CARD: r'\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b',
            PIIType.EMAIL: r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
            PIIType.PHONE: r'\b(?:\+?1[-.\s]?)?\(?[0-9]{3}\)?[-.\s]?[0-9]{3}[-.\s]?[0-9]{4}\b',
            PIIType.ACCOUNT_NUMBER: r'\b(?:account|acct|acc)\s*(?:number|#|no\.?)\s*[:=]?\s*[A-Za-z0-9]{8,20}\b',
        }
        self.name_patterns = [
            r'\b[A-Z][a-z]+\s+[A-Z][a-z]+\b',  # First Last
            r'\b[A-Z]\.\s+[A-Z][a-z]+\b',       # I. Last
        ]
    
    def detect(self, text: str) -> List[Dict[str, Any]]:
        """Detect all PII in text"""
        detected_pii = []
        
        # Check all patterns
        for pii_type, pattern in self.patterns.items():
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                detected_pii.append({
                    "type": pii_type.value,
                    "value": match.group(0),
                    "start": match.start(),
                    "end": match.end(),
                    "confidence": 0.95
                })
        
        # Check names (lower confidence)
        for pattern in self.name_patterns:
            matches = re.finditer(pattern, text)
            for match in matches:
                detected_pii.append({
                    "type": PIIType.NAME.value,
                    "value": match.group(0),
                    "start": match.start(),
                    "end": match.end(),
                    "confidence": 0.7
                })
        
        return detected_pii
    
    def redact(self, text: str, mask_char: str = "*") -> str:
        """Redact PII from text"""
        pii_found = self.detect(text)
        
        # Sort by position (reverse order to avoid offset issues)
        pii_found.sort(key=lambda x: x["start"], reverse=True)
        
        # Redact each PII
        for pii in pii_found:
            start = pii["start"]
            end = pii["end"]
            original = text[start:end]
            # Keep first and last character visible
            if len(original) > 2:
                redacted = original[0] + mask_char * (len(original) - 2) + original[-1]
            else:
                redacted = mask_char * len(original)
            text = text[:start] + redacted + text[end:]
        
        return text
    
    def get_stats(self, text: str) -> Dict[str, int]:
        """Get PII statistics for text"""
        detected = self.detect(text)
        stats = {}
        
        for pii_type in PIIType:
            count = sum(1 for p in detected if p["type"] == pii_type.value)
            if count > 0:
                stats[pii_type.value] = count
        
        return stats

# Singleton instance
_detector = None

def get_pii_detector():
    global _detector
    if _detector is None:
        _detector = PIIDetector()
    return _detector
```

### What This Demonstrates:
✅ Regex pattern matching
✅ PII detection patterns
✅ Data privacy practices
✅ Text redaction techniques

---

## Commit 2 (9:00 AM): Sentiment Analysis Model

### What to Stage:
```
app/models/sentiment_analyzer.py            ← Sentiment analysis
```

### Git Commands:
```bash
git add app/models/sentiment_analyzer.py
git commit -m "Add sentiment analysis for complaint understanding"
```

### File: `app/models/sentiment_analyzer.py`
Should contain:
```python
from typing import Dict, Any
from enum import Enum
from app.models.llm_factory import get_llm
import json

class SentimentLabel(Enum):
    """Sentiment classifications"""
    VERY_NEGATIVE = "very_negative"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"
    POSITIVE = "positive"
    VERY_POSITIVE = "very_positive"

class SentimentAnalyzer:
    """Analyze sentiment of financial complaints"""
    
    def __init__(self):
        self.llm = get_llm()
        self.emotion_keywords = {
            "anger": ["angry", "furious", "outraged", "furious"],
            "frustration": ["frustrated", "annoyed", "exasperated"],
            "sadness": ["sad", "disappointed", "depressed"],
            "fear": ["scared", "worried", "anxious", "concerned"],
            "trust": ["trust", "confident", "assured"],
        }
    
    async def analyze(self, text: str) -> Dict[str, Any]:
        """Analyze sentiment of text"""
        
        prompt = f"""Analyze the sentiment of this financial complaint.
        
Text: {text}

Provide:
1. Overall sentiment: very_negative, negative, neutral, positive, very_positive
2. Emotions detected: list of emotions (anger, frustration, sadness, fear, trust)
3. Intensity (0-1): How intense is the sentiment?
4. Key sentiment phrases: Quoted phrases that indicate sentiment
5. Urgency (low, medium, high): How urgent is the issue?

Respond in JSON format:
{{
    "sentiment": "negative",
    "emotions": ["anger", "frustration"],
    "intensity": 0.85,
    "sentiment_phrases": ["furious about", "terrible service"],
    "urgency": "high"
}}"""
        
        response = await self.llm.ainvoke(prompt)
        
        try:
            result = json.loads(response.content)
            return {
                "sentiment": result.get("sentiment", "neutral"),
                "emotions": result.get("emotions", []),
                "intensity": result.get("intensity", 0.5),
                "sentiment_phrases": result.get("sentiment_phrases", []),
                "urgency": result.get("urgency", "medium"),
                "confidence": 0.8
            }
        except:
            return {
                "sentiment": "neutral",
                "emotions": [],
                "intensity": 0.5,
                "sentiment_phrases": [],
                "urgency": "medium",
                "confidence": 0.3
            }
    
    def classify_urgency(self, sentiment_data: Dict[str, Any]) -> str:
        """Determine urgency from sentiment"""
        intensity = sentiment_data.get("intensity", 0.5)
        sentiment = sentiment_data.get("sentiment")
        emotions = sentiment_data.get("emotions", [])
        
        # High urgency indicators
        if intensity > 0.8 or "anger" in emotions:
            return "high"
        elif intensity > 0.5 or sentiment in ["negative", "very_negative"]:
            return "medium"
        else:
            return "low"

# Singleton
_analyzer = None

async def get_sentiment_analyzer():
    global _analyzer
    if _analyzer is None:
        _analyzer = SentimentAnalyzer()
    return _analyzer
```

### What This Demonstrates:
✅ LLM-based NLP analysis
✅ Emotion detection
✅ Structured output parsing
✅ Urgency classification

---

## Commit 3 (10:30 AM): Complaint Classification Model

### What to Stage:
```
app/models/complaint_classifier.py          ← Classification logic
```

### Git Commands:
```bash
git add app/models/complaint_classifier.py
git commit -m "Implement complaint classification with category mapping"
```

### File: `app/models/complaint_classifier.py`
Should contain:
```python
from typing import Dict, List, Any
from enum import Enum
from app.models.llm_factory import get_llm
import json

class ComplaintCategory(Enum):
    """Financial complaint categories"""
    MORTGAGE = "mortgage"
    CREDIT_CARD = "credit_card"
    DEBT_COLLECTION = "debt_collection"
    CHECKING_SAVINGS = "checking_savings"
    CREDIT_REPORTING = "credit_reporting"
    PAYDAY_LOAN = "payday_loan"
    MONEY_TRANSFER = "money_transfer"
    STUDENT_LOAN = "student_loan"
    VEHICLE_LOAN = "vehicle_loan"
    AUTO_INSURANCE = "auto_insurance"
    OTHER = "other"

class ComplaintIssueType(Enum):
    """Common issue types"""
    INCORRECT_INFORMATION = "incorrect_information"
    UNAUTHORIZED_TRANSACTION = "unauthorized_transaction"
    BILLING_ERROR = "billing_error"
    SERVICE_FAILURE = "service_failure"
    FRAUD = "fraud"
    FEES = "fees"
    ACCOUNT_CLOSURE = "account_closure"

class ComplaintClassifier:
    """Classify complaints into categories and issue types"""
    
    def __init__(self):
        self.llm = get_llm()
        self.categories = [e.value for e in ComplaintCategory]
        self.issues = [e.value for e in ComplaintIssueType]
    
    async def classify(self, text: str) -> Dict[str, Any]:
        """Classify complaint into categories"""
        
        categories_str = ", ".join(self.categories)
        issues_str = ", ".join(self.issues)
        
        prompt = f"""Classify this financial complaint.

Text: {text}

Available categories: {categories_str}
Available issues: {issues_str}

Provide:
1. Primary category with confidence (0-1)
2. Secondary category with confidence (if applicable)
3. Primary issue type
4. Problem description (1 sentence)
5. Recommended action

Respond in JSON:
{{
    "primary_category": "credit_card",
    "primary_confidence": 0.92,
    "secondary_category": "billing",
    "secondary_confidence": 0.65,
    "issue_type": "billing_error",
    "problem_description": "Charged twice for single transaction",
    "recommended_action": "Review transaction logs and issue refund"
}}"""
        
        response = await self.llm.ainvoke(prompt)
        
        try:
            result = json.loads(response.content)
            return {
                "primary_category": result.get("primary_category", "other"),
                "primary_confidence": result.get("primary_confidence", 0.5),
                "secondary_category": result.get("secondary_category"),
                "secondary_confidence": result.get("secondary_confidence"),
                "issue_type": result.get("issue_type", "other"),
                "problem_description": result.get("problem_description"),
                "recommended_action": result.get("recommended_action")
            }
        except:
            return {
                "primary_category": "other",
                "primary_confidence": 0.3,
                "secondary_category": None,
                "secondary_confidence": None,
                "issue_type": "other",
                "problem_description": "Unable to classify",
                "recommended_action": "Manual review required"
            }

# Singleton
_classifier = None

async def get_complaint_classifier():
    global _classifier
    if _classifier is None:
        _classifier = ComplaintClassifier()
    return _classifier
```

### What This Demonstrates:
✅ Multi-label classification
✅ Enum-based category management
✅ Confidence scoring
✅ Secondary classification support

---

## Commit 4 (12:00 PM): Model Factory

### What to Stage:
```
app/models/model_factory.py                 ← Centralized model access (UPDATE)
```

### Git Commands:
```bash
git add app/models/model_factory.py
git commit -m "Update model factory with PII, sentiment, and classification models"
```

### File: `app/models/model_factory.py` (Update existing)
Should contain:
```python
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from app.core.config import settings
from app.models.pii_detector import get_pii_detector
from app.models.sentiment_analyzer import get_sentiment_analyzer
from app.models.complaint_classifier import get_complaint_classifier

# Cached instances
_llm = None
_embeddings = None
_pii_detector = None
_sentiment_analyzer = None
_classifier = None

def get_llm():
    """Get LLM instance"""
    global _llm
    if _llm is None:
        _llm = ChatOpenAI(
            model=settings.llm_model,
            temperature=settings.llm_temperature,
            api_key=settings.openai_api_key,
            max_tokens=2000
        )
    return _llm

def get_embedding_model():
    """Get embedding model"""
    global _embeddings
    if _embeddings is None:
        _embeddings = OpenAIEmbeddings(
            model=settings.embedding_model,
            api_key=settings.openai_api_key
        )
    return _embeddings

def get_pii_detector():
    """Get PII detector"""
    global _pii_detector
    if _pii_detector is None:
        from app.models.pii_detector import PIIDetector
        _pii_detector = PIIDetector()
    return _pii_detector

async def get_sentiment_analyzer():
    """Get sentiment analyzer"""
    global _sentiment_analyzer
    if _sentiment_analyzer is None:
        from app.models.sentiment_analyzer import SentimentAnalyzer
        _sentiment_analyzer = SentimentAnalyzer()
    return _sentiment_analyzer

async def get_complaint_classifier():
    """Get complaint classifier"""
    global _classifier
    if _classifier is None:
        from app.models.complaint_classifier import ComplaintClassifier
        _classifier = ComplaintClassifier()
    return _classifier

def get_all_models():
    """Get reference to all available models"""
    return {
        "llm": get_llm(),
        "embeddings": get_embedding_model(),
        "pii_detector": get_pii_detector(),
        "sentiment_analyzer": get_sentiment_analyzer(),
        "classifier": get_complaint_classifier()
    }
```

### What This Demonstrates:
✅ Factory pattern
✅ Singleton management
✅ Centralized model access
✅ Lazy initialization

---

## Commit 5 (2:30 PM): Retrieval Reranker

### What to Stage:
```
app/retrieval/reranker.py                   ← Reranking logic
```

### Git Commands:
```bash
git add app/retrieval/reranker.py
git commit -m "Add retrieval reranker for semantic relevance"
```

### File: `app/retrieval/reranker.py`
Should contain:
```python
from typing import List, Dict, Any
from app.models.llm_factory import get_llm
import json

class RetrievalReranker:
    """Rerank retrieved documents for relevance"""
    
    def __init__(self, top_k: int = 5):
        self.llm = get_llm()
        self.top_k = top_k
    
    async def rerank(self, query: str, documents: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Rerank documents by relevance to query"""
        
        if not documents or len(documents) <= 1:
            return documents
        
        # Create reranking prompt
        doc_text = "\n".join([
            f"{i+1}. {doc.get('title', doc.get('content', '')[:100])}"
            for i, doc in enumerate(documents)
        ])
        
        prompt = f"""Given this query and documents, rank them by relevance.

Query: {query}

Documents:
{doc_text}

Rank from most relevant (1) to least relevant ({len(documents)}).
Consider:
- Direct answer to query
- Related concepts
- Applicability to user's situation

Respond with JSON:
{{
    "ranking": [2, 1, 3, 4],
    "relevance_scores": [0.95, 0.88, 0.72, 0.65]
}}"""
        
        response = await self.llm.ainvoke(prompt)
        
        try:
            result = json.loads(response.content)
            ranking = result.get("ranking", list(range(1, len(documents) + 1)))
            scores = result.get("relevance_scores", [1.0] * len(documents))
            
            # Apply ranking
            reranked = []
            for rank, score in zip(ranking, scores):
                doc = documents[rank - 1].copy()
                doc["rerank_score"] = score
                doc["rerank_position"] = len(reranked) + 1
                reranked.append(doc)
            
            return reranked[:self.top_k]
        except:
            return documents[:self.top_k]
    
    async def score_relevance(self, query: str, text: str) -> float:
        """Score relevance of single document (0-1)"""
        
        prompt = f"""Rate how relevant this document is to the query (0-1).

Query: {query}

Document: {text[:500]}

Consider semantic relevance, topical match, and usefulness.
Respond with JSON:
{{"score": 0.85}}"""
        
        response = await self.llm.ainvoke(prompt)
        
        try:
            result = json.loads(response.content)
            return result.get("score", 0.5)
        except:
            return 0.5

# Singleton
_reranker = None

def get_reranker(top_k: int = 5):
    global _reranker
    if _reranker is None:
        _reranker = RetrievalReranker(top_k=top_k)
    return _reranker
```

### What This Demonstrates:
✅ Relevance scoring
✅ Document ranking
✅ LLM-based semantic reranking
✅ Retrieval optimization

---

## Full Day 6 Workflow

### Morning (7:30 AM - 12:00 PM)
```bash
# 7:30 AM - PII Detection
git add app/models/pii_detector.py
git commit -m "Implement PII detection model for data privacy"

# 8:30-9:00 AM - Code & test

# 9:00 AM - Sentiment Analysis
git add app/models/sentiment_analyzer.py
git commit -m "Add sentiment analysis for complaint understanding"

# 10:00-10:30 AM - Code & test

# 10:30 AM - Classification
git add app/models/complaint_classifier.py
git commit -m "Implement complaint classification with category mapping"

# 11:30 AM-12:00 PM - Code & test
```

### Afternoon (12:00 PM - 7:00 PM)
```bash
# 12:00 PM - Model Factory
git add app/models/model_factory.py
git commit -m "Update model factory with PII, sentiment, and classification models"

# 1:00-2:30 PM - Code & test

# 2:30 PM - Reranker
git add app/retrieval/reranker.py
git commit -m "Add retrieval reranker for semantic relevance"

# 3:30-7:00 PM - Code & test
```

---

## Verification Checklist

After Day 6:

```bash
# Check all models
ls -la app/models/
# Should have: pii_detector.py, sentiment_analyzer.py, complaint_classifier.py, model_factory.py

# Test PII detection
python -c "from app.models.pii_detector import get_pii_detector; detector = get_pii_detector(); print(detector.redact('My SSN is 123-45-6789'))"

# Test imports
python -c "from app.models.sentiment_analyzer import SentimentAnalyzer; print('Sentiment OK')"
python -c "from app.models.complaint_classifier import ComplaintClassifier; print('Classifier OK')"
python -c "from app.retrieval.reranker import RetrievalReranker; print('Reranker OK')"

# View commits
git log --oneline -5
```

---

## Git History at End of Day 6

```bash
$ git log --oneline | head -8
* Day6-5: Add retrieval reranker for semantic relevance
* Day6-4: Update model factory with PII, sentiment, and classification
* Day6-3: Implement complaint classification with category mapping
* Day6-2: Add sentiment analysis for complaint understanding
* Day6-1: Implement PII detection model for data privacy
```

---

## What Was Built

By end of Day 6:
- ✅ PII detection and redaction
- ✅ Regex-based pattern matching
- ✅ Sentiment analysis engine
- ✅ Emotion detection
- ✅ Complaint classification
- ✅ Multi-category support
- ✅ Centralized model factory
- ✅ Retrieval reranking
- ✅ Relevance scoring
- ✅ LLM-powered analysis

The system can now understand and analyze complaints intelligently! 🧠

---

## Ready for Day 7?

After completing Day 6:
- [ ] 5 commits in git log
- [ ] Total: 31 commits (Days 1-6 combined)
- [ ] ML models complete
- [ ] Analysis capabilities ready
- [ ] Ready to add observability

**Next:** Day 7 - Observability (Prometheus metrics, Grafana dashboards, tracing)

Time to make the system visible! 📊
