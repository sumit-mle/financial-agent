# Fin AI Agent

Production-grade Financial Complaint Resolution AI Agent built on the **Compound AI / Agent Architecture with Enhanced RAG** architecture.

## Architecture Overview

```
Layer 1 — Application       : React chat UI + omnichannel surface
Layer 2 — Orchestration     : LangGraph (intent → refine → safety → route)
Layer 3 — RAG               : Qdrant multi-collection + FlashRank reranker
Layer 4 — Model             : GPT-4o / Claude / Llama3 + 5 guardrail evaluators
Layer 5 — Action Execution  : CRM, ticketing, payment, notification connectors
Layer 6 — Validation        : Grounding check + policy compliance + escalation
Cross-cutting               : Langfuse tracing + RAGAS evaluation
```

## Free Data Sources

| Source | Type | Volume |
|---|---|---|
| [CFPB Consumer Complaints](https://www.consumerfinance.gov/data-research/consumer-complaints/) | Complaint narratives + resolutions | 7.8M+ records |
| [SEC EDGAR 10-K Filings](https://www.sec.gov/edgar/browse/) | Financial company annual reports | Unlimited |
| [FDIC Policy Documents](https://www.fdic.gov/regulations/laws/rules/) | Banking regulations (PDF) | 100+ docs |
| [BANKING77 (HuggingFace)](https://huggingface.co/datasets/PolyAI/banking77) | Intent classification labels | 13,083 queries |
| [FinanceBench (HuggingFace)](https://huggingface.co/datasets/PatronusAI/financebench) | QA eval set for RAG | 10,231 pairs |

## Quick Start

### 1. Clone and configure

```bash
cp .env.example .env
# Fill in OPENAI_API_KEY (or set LLM_PROVIDER=local for Ollama)
```

### 2. Start infrastructure

```bash
docker-compose up -d qdrant postgres redis
```

### 3. Install Python dependencies

```bash
pip install -e ".[dev]"
```

### 4. Ingest data (sample mode for quick start)

```bash
python -m app.ingestion.pipeline --source cfpb --sample --provider openai
python -m app.ingestion.pipeline --source policy --provider openai
```

### 5. Run the API

```bash
uvicorn app.main:app --reload --port 8000
```

### 6. Run the frontend

```bash
cd frontend && npm install && npm run dev
```

Open http://localhost:5173

## Full Docker deployment

```bash
docker-compose up -d
```

All services start: Qdrant + Postgres + Redis + FastAPI + React frontend.

## Project Structure

```
fin-ai-agent/
├── app/
│   ├── core/               # Config, logging
│   ├── ingestion/          # Data pipeline (CFPB, SEC EDGAR, PDFs)
│   │   ├── sources/        # CFPB, SEC Edgar, Policy PDFs
│   │   └── processors/     # Chunker, Embedder, VectorStore writer
│   ├── retrieval/          # RAG layer (Retriever, Reranker, Context Assembler)
│   ├── agent/              # LangGraph graph + all nodes
│   │   └── nodes/          # Intent, Refine, Safety, Retrieve, Reason, Action, Route
│   ├── models/             # LLM factory, Guardrail models, DI
│   ├── actions/            # Action registry + CRM/ticketing connectors
│   ├── validation/         # Post-generation validator
│   ├── api/                # FastAPI app, routes, schemas, middleware
│   ├── observability/      # Langfuse tracer + RAGAS evaluator
│   └── main.py             # App entrypoint
├── frontend/               # React + TypeScript + Tailwind chat UI
│   └── src/
│       ├── components/     # ChatWindow
│       ├── hooks/          # useChat
│       └── lib/            # API client
├── tests/                  # Pytest unit tests
├── data/                   # Downloaded datasets (gitignored)
├── docker-compose.yml
├── Dockerfile
└── pyproject.toml
```

## Agent Graph Flow

```
START
  │
  ▼
classify_intent   ← BANKING77-style 7-category classification
  │
  ▼
refine_query      ← Expand query for better retrieval
  │
  ▼
check_safety      ← PII, injection, regulated advice detection
  │ (fail → deliver_response immediately)
  ▼
retrieve          ← Multi-collection Qdrant search + FlashRank rerank
  │
  ▼
reason            ← Fin Apex LLM: decide answer/action/clarify/escalate
  │
  ├─► execute_action  ← Call CRM/ticketing/payment APIs
  │       │
  │       ▼
  ├─► escalate        ← Set escalation context
  │       │
  ▼       ▼
deliver_response  ← Validate (groundedness, policy, confidence) + enrich
  │
  ▼
 END
```

## Environment Variables

See `.env.example` for the full list. Key variables:

| Variable | Description |
|---|---|
| `LLM_PROVIDER` | `openai` \| `anthropic` \| `local` |
| `OPENAI_API_KEY` | Required for OpenAI provider |
| `QDRANT_URL` | Qdrant vector store URL |
| `LANGFUSE_PUBLIC_KEY` | Optional — for tracing |
| `AGENT_CONFIDENCE_THRESHOLD` | Below this adds disclaimer (default: 0.75) |
| `AGENT_ESCALATION_THRESHOLD` | Below this escalates to human (default: 0.50) |

## Running Tests

```bash
pytest tests/ -v
```

## Production Deployment Checklist

- [ ] Set `APP_ENV=production` in `.env`
- [ ] Replace `SECRET_KEY` with a cryptographically random value
- [ ] Set real `OPENAI_API_KEY` or configure local Ollama
- [ ] Configure `LANGFUSE_PUBLIC_KEY` + `LANGFUSE_SECRET_KEY` for tracing
- [ ] Replace mock connectors in `app/actions/connectors.py` with real API endpoints
- [ ] Run full CFPB ingest (remove `--sample` flag): `make ingest-cfpb`
- [ ] Run database migrations: `make migrate`
- [ ] Set `CORS_ORIGINS` to your production frontend domain
