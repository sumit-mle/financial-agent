# Pre-Launch Checklist - Fin AI Agent

## ✅ Completed

- ✅ All 6 architectural layers implemented
- ✅ Docker stack running (API, Qdrant, Postgres, Redis healthy)
- ✅ OpenAI API key configured
- ✅ CFPB data ingestion started (in progress)
- ✅ LangGraph orchestration working
- ✅ RAG pipeline with multi-collection search + reranking
- ✅ Guardrails and validation layer
- ✅ Action execution framework
- ✅ Observability (Langfuse-ready)

---

## 🔧 Pre-Launch Fixes Required (Estimated: 4-6 hours)

### 1. ⏳ Complete CFPB Data Ingestion
**Status**: In progress (downloading 1.4GB dataset)  
**ETA**: ~10-15 minutes remaining

**Action**: Wait for completion, then verify:
```bash
docker logs fin_api --tail 50
# Should see "✓ Ingestion complete" message
```

**Verification**:
```bash
docker exec fin_api python -c "
from app.ingestion.processors.vector_store import VectorStoreWriter
w = VectorStoreWriter()
print(f'Complaints indexed: {w.collection_count(\"complaints\")}')
"
# Expected output: ~5000 vectors
```

---

### 2. ⚠️ Fix Frontend Production Build (30 minutes)
**Issue**: Frontend running in dev mode (Vite on port 5173) instead of production nginx.

**Root Cause**: `docker-compose.override.yml` auto-loads and overrides to dev mode.

**Fix Option A - Quick** (for testing):
```bash
# Rename override file temporarily
mv docker-compose.override.yml docker-compose.override.yml.bak

# Rebuild frontend only
docker-compose build frontend

# Restart
docker-compose up -d frontend

# Verify: http://localhost:3000 should work (not 5173)
```

**Fix Option B - Production Deploy** (recommended):
```bash
# Use the production compose file
bash scripts/deploy-prod.sh

# Or manually:
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up --build -d
```

**Verification**:
```bash
curl http://localhost:3000
# Should return HTML (nginx serving static files)

docker logs fin_frontend
# Should show nginx access logs, not "VITE v5.4.21"
```

---

### 3. ⚠️ Test End-to-End Chat Flow (1-2 hours)
**Action**: Send test queries through the full pipeline.

**Test Cases**:

#### Test 1: Account Inquiry
```bash
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "What is the status of my complaint?",
    "session_id": "test_session_001",
    "customer_id": "test_customer_123"
  }'
```

**Expected Response**:
```json
{
  "session_id": "test_session_001",
  "response": "...",
  "response_type": "answer",
  "intent": "complaint_inquiry",
  "confidence": 0.85,
  "citations": ["CFPB Complaint #12345"],
  "should_escalate": false
}
```

#### Test 2: Unsafe Input (PII / Injection)
```bash
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "My SSN is 123-45-6789 and I need help",
    "session_id": "test_session_002"
  }'
```

**Expected Behavior**:
- Safety check should flag PII
- Response should escalate or ask for secure channel
- No SSN echoed in logs

#### Test 3: Escalation Trigger
```bash
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "This is insane, I want a manager NOW!",
    "session_id": "test_session_003"
  }'
```

**Expected Behavior**:
- Intent: escalation / complaint
- `should_escalate: true`
- Response offers human handoff

#### Test 4: Action Execution
```bash
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Can you look up my account balance?",
    "session_id": "test_session_004",
    "customer_id": "CUST_456"
  }'
```

**Expected Behavior**:
- Intent: account_inquiry
- Action: lookup_account_summary executed
- Response includes account data (mock for now)
- `actions_taken` list populated

---

### 4. ⚠️ Verify Guardrails & Validation (30 minutes)
**Action**: Check that all validation steps are working.

**Tests**:

#### Groundedness Check
```bash
# Send a query that triggers retrieval
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "What are the most common credit card complaints?",
    "session_id": "test_session_005"
  }'

# Check response metadata for guardrail scores
```

**Expected**:
```json
{
  "metadata": {
    "guardrail_scores": {
      "groundedness": 0.92,
      "relevance": 0.88,
      "confidence": 0.85
    }
  }
}
```

#### Policy Compliance
Monitor logs for any policy violations:
```bash
docker logs fin_api -f | grep "Policy violation"
```

---

### 5. ⚠️ Configure Langfuse (Optional, 15 minutes)
**Action**: If using Langfuse for observability.

**Steps**:
1. Sign up at https://cloud.langfuse.com (free tier)
2. Get API keys
3. Update `.env`:
```bash
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_HOST=https://cloud.langfuse.com
```
4. Restart API container:
```bash
docker-compose restart api
```
5. Verify traces at Langfuse dashboard

**If skipping**: Leave keys blank, app works with no-op tracer.

---

## 🧪 Acceptance Criteria

Before declaring production-ready:

- [ ] CFPB ingestion completed (5000+ vectors in Qdrant)
- [ ] Frontend serving on port 3000 (nginx, not Vite dev server)
- [ ] At least 3 test queries return valid responses
- [ ] Safety checks block PII/injection attempts
- [ ] Escalation logic triggers for high-emotion queries
- [ ] Action execution works (even if mocked)
- [ ] Guardrail scores appear in response metadata
- [ ] No errors in `docker-compose ps` (all containers "Up" and healthy)
- [ ] API health check returns 200: `curl http://localhost:8000/health`
- [ ] Frontend loads without errors: `curl http://localhost:3000`

---

## 🚀 Launch Commands

### Development Mode (current setup)
```bash
docker-compose up -d
# Frontend: http://localhost:5173 (Vite HMR)
# API: http://localhost:8000/docs
```

### Production Mode
```bash
# Option 1: Use deployment script
bash scripts/deploy-prod.sh

# Option 2: Manual
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up --build -d

# Frontend: http://localhost:3000 (nginx)
# API: http://localhost:8000/docs (disabled in prod, set docs_url=None in main.py)
```

---

## 📊 Monitoring After Launch

### Health Checks
```bash
# API
curl http://localhost:8000/health

# Database
docker exec fin_postgres pg_isready -U postgres

# Qdrant
curl http://localhost:6333/readyz

# Redis
docker exec fin_redis redis-cli ping
```

### Logs
```bash
# All services
docker-compose logs -f

# API only
docker logs -f fin_api

# Filter for errors
docker logs fin_api 2>&1 | grep ERROR
```

### Metrics to Track
- **Response time**: P95 should be <3s
- **Escalation rate**: Target <15% of queries
- **Confidence scores**: Median should be >0.75
- **Guardrail failures**: Should be <5% of responses

---

## 🛠️ Troubleshooting

### Issue: Frontend returns 502 / connection refused
**Fix**:
```bash
# Check if api is healthy
docker-compose ps
docker logs fin_api --tail 50

# Restart if unhealthy
docker-compose restart api
```

### Issue: "No vectors found" in responses
**Fix**:
```bash
# Check Qdrant collection counts
docker exec fin_api python -c "
from app.ingestion.processors.vector_store import VectorStoreWriter
w = VectorStoreWriter()
for col in ['complaints', 'policies', 'faq']:
    print(f'{col}: {w.collection_count(col)} vectors')
"

# If zero, re-run ingestion
docker exec fin_api python -m app.ingestion.pipeline --source cfpb --sample --provider openai
```

### Issue: Rate limiting too aggressive
**Fix**: Increase limit in `.env`:
```bash
# In app/api/middleware.py, default is 60 req/min
# To disable temporarily:
docker exec -it fin_api bash
# Comment out rate limit middleware in main.py
```

---

## ✅ Sign-Off

Once all checklist items pass, the system is ready for:
- **Internal beta testing** (5-10 users)
- **Pilot deployment** (low-stakes customer segment)
- **Production rollout** (full traffic)

**Estimated Time to Production-Ready**: 4-6 hours from current state.
