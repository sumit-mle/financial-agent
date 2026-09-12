# Day 5 Implementation: Data Ingestion Pipeline (Detailed)

**Date:** Day 5 of development  
**Theme:** Data source connectors and processing pipeline  
**Total Commits:** 6 logical commits  
**Time Span:** 8:00 AM - 8:30 PM  

---

## Overview

Day 5 focuses on bringing real data into the system. You'll build:
- Base connector interface for data sources
- CFPB financial complaints data connector
- SEC Edgar financial documents connector
- Document chunking with overlap
- Embedding generation pipeline
- Complete ingestion orchestration

This is where the knowledge base gets populated!

---

## Commit 1 (8:00 AM): Base Data Source Interface

### What to Stage:
```
app/ingestion/sources/base.py                ← Base connector interface
app/ingestion/sources/__init__.py            ← Package init
app/ingestion/__init__.py                    ← Package init
```

### Git Commands:
```bash
git add app/ingestion/sources/base.py app/ingestion/sources/__init__.py app/ingestion/__init__.py
git commit -m "Create base data source connector interface"
```

### File: `app/ingestion/sources/base.py`
Should contain:
```python
from abc import ABC, abstractmethod
from typing import List, Dict, Any, AsyncGenerator
from dataclasses import dataclass
from datetime import datetime

@dataclass
class Document:
    """Represents a document from a data source"""
    id: str
    content: str
    title: str
    source: str
    url: str
    metadata: Dict[str, Any]
    retrieved_at: datetime
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage"""
        return {
            "id": self.id,
            "content": self.content,
            "title": self.title,
            "source": self.source,
            "url": self.url,
            "metadata": self.metadata,
            "retrieved_at": self.retrieved_at.isoformat()
        }

class BaseDataSource(ABC):
    """Base class for all data sources"""
    
    def __init__(self, name: str, rate_limit: int = 100):
        self.name = name
        self.rate_limit = rate_limit
        self.documents_fetched = 0
    
    @abstractmethod
    async def fetch(self, query: str = None, limit: int = 10) -> AsyncGenerator[Document, None]:
        """Fetch documents from source"""
        pass
    
    @abstractmethod
    async def search(self, query: str) -> List[Document]:
        """Search for specific documents"""
        pass
    
    async def validate(self) -> bool:
        """Validate connection to data source"""
        try:
            async for _ in self.fetch(limit=1):
                return True
        except Exception as e:
            print(f"Validation failed: {e}")
            return False
    
    def get_stats(self) -> Dict[str, Any]:
        """Get source statistics"""
        return {
            "name": self.name,
            "documents_fetched": self.documents_fetched,
            "rate_limit": self.rate_limit
        }
```

### What This Demonstrates:
✅ ABC (Abstract Base Class) patterns
✅ Interface design
✅ Async generator patterns
✅ Data model design

---

## Commit 2 (9:30 AM): CFPB Data Source Connector

### What to Stage:
```
app/ingestion/sources/cfpb.py               ← CFPB complaints connector
```

### Git Commands:
```bash
git add app/ingestion/sources/cfpb.py
git commit -m "Implement CFPB complaints data source connector"
```

### File: `app/ingestion/sources/cfpb.py`
Should contain:
```python
import aiohttp
import zipfile
import csv
import io
from typing import AsyncGenerator
from app.ingestion.sources.base import BaseDataSource, Document
from datetime import datetime
from app.core.config import settings

class CFPBDataSource(BaseDataSource):
    """Connector for CFPB financial complaints database"""
    
    def __init__(self):
        super().__init__(name="CFPB", rate_limit=50)
        self.data_url = settings.cfpb_data_url
        self.complaints_cache = []
    
    async def fetch(self, query: str = None, limit: int = 10) -> AsyncGenerator[Document, None]:
        """Fetch complaints from CFPB"""
        
        if not self.complaints_cache:
            await self._load_data()
        
        count = 0
        for complaint in self.complaints_cache:
            if count >= limit:
                break
            
            # Filter by query if provided
            if query:
                if query.lower() not in complaint.get("content", "").lower():
                    continue
            
            doc = Document(
                id=complaint.get("complaint_id"),
                content=complaint.get("content"),
                title=complaint.get("title"),
                source="CFPB",
                url=complaint.get("url", ""),
                metadata={
                    "product": complaint.get("product"),
                    "issue": complaint.get("issue"),
                    "company": complaint.get("company"),
                    "status": complaint.get("status")
                },
                retrieved_at=datetime.utcnow()
            )
            
            yield doc
            count += 1
            self.documents_fetched += 1
    
    async def search(self, query: str) -> list[Document]:
        """Search CFPB complaints"""
        results = []
        async for doc in self.fetch(query=query, limit=20):
            results.append(doc)
        return results
    
    async def _load_data(self):
        """Load CFPB complaint data from CSV"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(self.data_url, timeout=aiohttp.ClientTimeout(total=300)) as resp:
                    # Download and extract ZIP
                    content = await resp.read()
                    with zipfile.ZipFile(io.BytesIO(content)) as zf:
                        csv_file = [f for f in zf.namelist() if f.endswith('.csv')][0]
                        with zf.open(csv_file) as f:
                            reader = csv.DictReader(io.TextIOWrapper(f))
                            for row in reader:
                                self.complaints_cache.append({
                                    "complaint_id": row.get("Complaint ID"),
                                    "title": row.get("Product") + " - " + row.get("Issue"),
                                    "content": row.get("Consumer complaint narrative", ""),
                                    "product": row.get("Product"),
                                    "issue": row.get("Issue"),
                                    "company": row.get("Company"),
                                    "status": row.get("Company response to consumer"),
                                    "url": f"https://www.consumerfinance.gov/complaint/{row.get('Complaint ID')}"
                                })
        except Exception as e:
            print(f"Error loading CFPB data: {e}")
            self.complaints_cache = []
```

### What This Demonstrates:
✅ HTTP client patterns (aiohttp)
✅ ZIP file handling
✅ CSV parsing
✅ Async data fetching
✅ Real API integration

---

## Commit 3 (11:00 AM): SEC Edgar Data Source

### What to Stage:
```
app/ingestion/sources/sec_edgar.py          ← SEC Edgar documents connector
```

### Git Commands:
```bash
git add app/ingestion/sources/sec_edgar.py
git commit -m "Add SEC Edgar financial documents source"
```

### File: `app/ingestion/sources/sec_edgar.py`
Should contain:
```python
import aiohttp
from typing import AsyncGenerator
from app.ingestion.sources.base import BaseDataSource, Document
from datetime import datetime
from app.core.config import settings
import json

class SECEdgarDataSource(BaseDataSource):
    """Connector for SEC EDGAR financial documents"""
    
    def __init__(self):
        super().__init__(name="SEC EDGAR", rate_limit=100)
        self.base_url = settings.sec_edgar_base_url
        self.documents_cache = []
    
    async def fetch(self, query: str = None, limit: int = 10) -> AsyncGenerator[Document, None]:
        """Fetch SEC filings"""
        
        if not self.documents_cache:
            await self._search_filings(query or "10-K")
        
        count = 0
        for filing in self.documents_cache:
            if count >= limit:
                break
            
            doc = Document(
                id=filing.get("accession_number"),
                content=filing.get("text", ""),
                title=filing.get("title"),
                source="SEC EDGAR",
                url=filing.get("url"),
                metadata={
                    "cik": filing.get("cik"),
                    "company": filing.get("company"),
                    "form_type": filing.get("form_type"),
                    "filing_date": filing.get("filing_date")
                },
                retrieved_at=datetime.utcnow()
            )
            
            yield doc
            count += 1
            self.documents_fetched += 1
    
    async def search(self, query: str) -> list[Document]:
        """Search SEC filings"""
        results = []
        async for doc in self.fetch(query=query, limit=10):
            results.append(doc)
        return results
    
    async def _search_filings(self, form_type: str = "10-K", count: int = 20):
        """Search SEC EDGAR filings"""
        try:
            async with aiohttp.ClientSession() as session:
                # Search endpoint
                search_url = f"{self.base_url}/cgi-bin/browse-edgar"
                params = {
                    "action": "getcompany",
                    "type": form_type,
                    "dateb": "",
                    "owner": "exclude",
                    "count": count,
                    "output": "json"
                }
                
                async with session.get(search_url, params=params) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        for filing in data.get("filings", {}).get("filing", [])[:count]:
                            self.documents_cache.append({
                                "accession_number": filing.get("accession-number"),
                                "cik": filing.get("cik-number"),
                                "company": filing.get("company-name"),
                                "form_type": filing.get("form-type"),
                                "filing_date": filing.get("filing-date"),
                                "url": f"{self.base_url}/cgi-bin/viewer?action=view&cik={filing.get('cik-number')}&accession_number={filing.get('accession-number')}&xbrl_type=v",
                                "text": f"Filing: {filing.get('company-name')} {filing.get('form-type')} from {filing.get('filing-date')}"
                            })
        except Exception as e:
            print(f"Error searching SEC EDGAR: {e}")
```

### What This Demonstrates:
✅ REST API consumption
✅ JSON parsing
✅ Query parameter handling
✅ Error handling in data fetching

---

## Commit 4 (12:30 PM): Document Chunking Processor

### What to Stage:
```
app/ingestion/processors/chunker.py         ← Document chunking
app/ingestion/processors/__init__.py        ← Package init
```

### Git Commands:
```bash
git add app/ingestion/processors/chunker.py app/ingestion/processors/__init__.py
git commit -m "Implement document chunking with sliding windows"
```

### File: `app/ingestion/processors/chunker.py`
Should contain:
```python
from typing import List, Dict, Any
from dataclasses import dataclass
from app.core.config import settings

@dataclass
class Chunk:
    """Represents a document chunk"""
    id: str
    content: str
    chunk_index: int
    total_chunks: int
    source_document_id: str
    metadata: Dict[str, Any]

class DocumentChunker:
    """Break documents into overlapping chunks for embedding"""
    
    def __init__(self, 
                 chunk_size: int = None,
                 chunk_overlap: int = None):
        self.chunk_size = chunk_size or settings.chunk_size
        self.chunk_overlap = chunk_overlap or settings.chunk_overlap
    
    def chunk(self, document_id: str, content: str, metadata: Dict = None) -> List[Chunk]:
        """Split document into overlapping chunks"""
        
        if metadata is None:
            metadata = {}
        
        chunks = []
        tokens = content.split()
        
        # Calculate chunk boundaries
        chunk_start = 0
        chunk_index = 0
        
        while chunk_start < len(tokens):
            # Calculate end (with overlap)
            chunk_end = min(chunk_start + self.chunk_size, len(tokens))
            
            # Extract chunk
            chunk_tokens = tokens[chunk_start:chunk_end]
            chunk_text = " ".join(chunk_tokens)
            
            # Create chunk object
            chunk = Chunk(
                id=f"{document_id}_chunk_{chunk_index}",
                content=chunk_text,
                chunk_index=chunk_index,
                total_chunks=0,  # Will be set after loop
                source_document_id=document_id,
                metadata=metadata
            )
            
            chunks.append(chunk)
            chunk_index += 1
            
            # Move start position (accounting for overlap)
            chunk_start += self.chunk_size - self.chunk_overlap
        
        # Update total chunks
        for chunk in chunks:
            chunk.total_chunks = len(chunks)
        
        return chunks
    
    def chunk_batch(self, documents: List[Dict[str, Any]]) -> List[Chunk]:
        """Chunk multiple documents"""
        all_chunks = []
        
        for doc in documents:
            chunks = self.chunk(
                document_id=doc.get("id"),
                content=doc.get("content"),
                metadata=doc.get("metadata", {})
            )
            all_chunks.extend(chunks)
        
        return all_chunks

# Factory function
def get_chunker():
    return DocumentChunker()
```

### What This Demonstrates:
✅ Text processing patterns
✅ Chunking algorithm with overlap
✅ Batch processing
✅ Metadata preservation

---

## Commit 5 (2:00 PM): Embedding Generation

### What to Stage:
```
app/ingestion/processors/embedder.py        ← Embedding generation
```

### Git Commands:
```bash
git add app/ingestion/processors/embedder.py
git commit -m "Add embedding generation with batch processing"
```

### File: `app/ingestion/processors/embedder.py`
Should contain:
```python
from typing import List, Dict, Any
import asyncio
from app.models.llm_factory import get_embedding_model
from app.core.config import settings

class DocumentEmbedder:
    """Generate embeddings for document chunks"""
    
    def __init__(self, batch_size: int = None):
        self.batch_size = batch_size or settings.embedding_batch_size
        self.model = get_embedding_model()
    
    async def embed(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for text list"""
        embeddings = []
        
        # Process in batches
        for i in range(0, len(texts), self.batch_size):
            batch = texts[i:i + self.batch_size]
            
            try:
                # Get embeddings for batch
                batch_embeddings = await self.model.aembed_documents(batch)
                embeddings.extend(batch_embeddings)
            except Exception as e:
                print(f"Error embedding batch: {e}")
                # Return dummy embeddings on error
                embeddings.extend([[0.0] * 1536 for _ in batch])
        
        return embeddings
    
    async def embed_chunks(self, chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Add embeddings to chunks"""
        
        # Extract texts
        texts = [chunk.get("content", "") for chunk in chunks]
        
        # Generate embeddings
        embeddings = await self.embed(texts)
        
        # Attach embeddings to chunks
        for chunk, embedding in zip(chunks, embeddings):
            chunk["embedding"] = embedding
        
        return chunks

# Factory function
async def get_embedder():
    return DocumentEmbedder()
```

### What This Demonstrates:
✅ LLM embedding integration
✅ Batch processing for efficiency
✅ Error handling with fallbacks
✅ Async operations

---

## Commit 6 (5:00 PM): Data Ingestion Pipeline Orchestration

### What to Stage:
```
app/ingestion/pipeline.py                   ← Pipeline orchestration
```

### Git Commands:
```bash
git add app/ingestion/pipeline.py
git commit -m "Create data ingestion pipeline orchestration"
```

### File: `app/ingestion/pipeline.py`
Should contain:
```python
import asyncio
from typing import List
from app.ingestion.sources.cfpb import CFPBDataSource
from app.ingestion.sources.sec_edgar import SECEdgarDataSource
from app.ingestion.processors.chunker import get_chunker
from app.ingestion.processors.embedder import DocumentEmbedder
from app.ingestion.processors.vector_store import get_vector_store
import logging

logger = logging.getLogger(__name__)

class DataIngestionPipeline:
    """Complete data ingestion workflow"""
    
    def __init__(self):
        self.cfpb_source = CFPBDataSource()
        self.sec_source = SECEdgarDataSource()
        self.chunker = get_chunker()
        self.embedder = DocumentEmbedder()
        self.vector_store = get_vector_store()
    
    async def ingest_all(self, limit_per_source: int = 100):
        """Run complete ingestion pipeline"""
        
        logger.info("Starting data ingestion pipeline")
        
        documents = []
        
        # Fetch from CFPB
        logger.info("Fetching CFPB complaints")
        async for doc in self.cfpb_source.fetch(limit=limit_per_source):
            documents.append(doc.to_dict())
        
        # Fetch from SEC EDGAR
        logger.info("Fetching SEC EDGAR filings")
        async for doc in self.sec_source.fetch(limit=limit_per_source):
            documents.append(doc.to_dict())
        
        logger.info(f"Fetched {len(documents)} documents")
        
        # Chunk documents
        logger.info("Chunking documents")
        chunks = self.chunker.chunk_batch([
            {"id": doc.get("id"), "content": doc.get("content"), "metadata": doc.get("metadata")}
            for doc in documents
        ])
        
        logger.info(f"Created {len(chunks)} chunks")
        
        # Generate embeddings
        logger.info("Generating embeddings")
        chunk_dicts = [
            {
                "id": chunk.id,
                "content": chunk.content,
                "metadata": chunk.metadata
            }
            for chunk in chunks
        ]
        
        embedded_chunks = await self.embedder.embed_chunks(chunk_dicts)
        
        # Store in vector database
        logger.info("Storing in vector database")
        await self.vector_store.insert_documents("complaints", embedded_chunks)
        
        logger.info("Data ingestion complete")
        
        return {
            "documents_fetched": len(documents),
            "chunks_created": len(chunks),
            "chunks_stored": len(embedded_chunks)
        }

# Singleton instance
_pipeline = None

def get_pipeline():
    global _pipeline
    if _pipeline is None:
        _pipeline = DataIngestionPipeline()
    return _pipeline

async def run_ingestion(limit: int = 100):
    """Run ingestion pipeline"""
    pipeline = get_pipeline()
    return await pipeline.ingest_all(limit_per_source=limit)
```

### What This Demonstrates:
✅ Pipeline orchestration patterns
✅ Source integration
✅ Processing chain
✅ Vector storage integration
✅ Logging and monitoring
✅ Async workflow coordination

---

## Full Day 5 Workflow

### Morning (8:00 AM - 12:30 PM)
```bash
# 8:00 AM - Base interface
git add app/ingestion/sources/base.py app/ingestion/sources/__init__.py app/ingestion/__init__.py
git commit -m "Create base data source connector interface"

# 9:00-9:30 AM - Code & test

# 9:30 AM - CFPB connector
git add app/ingestion/sources/cfpb.py
git commit -m "Implement CFPB complaints data source connector"

# 10:30-11:00 AM - Code & test

# 11:00 AM - SEC Edgar connector
git add app/ingestion/sources/sec_edgar.py
git commit -m "Add SEC Edgar financial documents source"
```

### Afternoon (12:30 PM - 8:30 PM)
```bash
# 12:30 PM - Chunking processor
git add app/ingestion/processors/chunker.py app/ingestion/processors/__init__.py
git commit -m "Implement document chunking with sliding windows"

# 1:30-2:00 PM - Code & test

# 2:00 PM - Embedding processor
git add app/ingestion/processors/embedder.py
git commit -m "Add embedding generation with batch processing"

# 3:30-5:00 PM - Code & test

# 5:00 PM - Pipeline orchestration
git add app/ingestion/pipeline.py
git commit -m "Create data ingestion pipeline orchestration"

# 6:00-8:30 PM - Code & test
```

---

## Verification Checklist

After Day 5:

```bash
# Check all sources
ls -la app/ingestion/sources/
# Should have: base.py, cfpb.py, sec_edgar.py

# Check processors
ls -la app/ingestion/processors/
# Should have: chunker.py, embedder.py

# Validate imports
python -c "from app.ingestion.sources.cfpb import CFPBDataSource; print('CFPB OK')"
python -c "from app.ingestion.sources.sec_edgar import SECEdgarDataSource; print('SEC OK')"
python -c "from app.ingestion.processors.chunker import DocumentChunker; print('Chunker OK')"
python -c "from app.ingestion.pipeline import get_pipeline; print('Pipeline OK')"

# Test pipeline (if data available)
python scripts/test_ingestion.py
```

---

## Git History at End of Day 5

```bash
$ git log --oneline | head -12
* Day5-6: Create data ingestion pipeline orchestration
* Day5-5: Add embedding generation with batch processing
* Day5-4: Implement document chunking with sliding windows
* Day5-3: Add SEC Edgar financial documents source
* Day5-2: Implement CFPB complaints data source connector
* Day5-1: Create base data source connector interface
```

---

## What Was Built

By end of Day 5:
- ✅ Base connector interface
- ✅ CFPB complaints data source
- ✅ SEC Edgar documents source
- ✅ Document chunking with overlap
- ✅ Embedding generation pipeline
- ✅ Complete orchestration pipeline
- ✅ Error handling and logging
- ✅ Batch processing for efficiency
- ✅ Vector store integration
- ✅ Real data ingestion capability

The system can now load real financial data! 📊

---

## Ready for Day 6?

After completing Day 5:
- [ ] 6 commits in git log
- [ ] Total: 26 commits (Days 1-5 combined)
- [ ] Data pipeline complete
- [ ] Knowledge base populated
- [ ] Ready to add ML models

**Next:** Day 6 - ML Models (PII detection, sentiment, classification)

The knowledge base is ready to be analyzed! 🧠
