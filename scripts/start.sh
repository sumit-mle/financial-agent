#!/bin/bash
# =============================================================================
# Fin AI Agent — Container startup script
# =============================================================================
set -euo pipefail

echo "═══════════════════════════════════════════════════"
echo "  Fin AI Agent — startup"
echo "═══════════════════════════════════════════════════"

QDRANT="${QDRANT_URL:-http://qdrant:6333}"

# ── 1. Wait for Qdrant ────────────────────────────────────────────────────────
echo "▶ Waiting for Qdrant at $QDRANT ..."
for i in $(seq 1 40); do
    if curl -sf "$QDRANT/readyz" > /dev/null 2>&1; then
        echo "  ✓ Qdrant ready"
        break
    fi
    secs=$((i * 2))
    echo "  … $secs s"
    sleep 2
done

# ── 2. Wait for Postgres ──────────────────────────────────────────────────────
echo "▶ Waiting for Postgres..."
for i in $(seq 1 30); do
    if python -c "
import asyncio, asyncpg, os
async def check():
    url = os.environ.get('DATABASE_URL','').replace('+asyncpg','')
    conn = await asyncpg.connect(url)
    await conn.close()
asyncio.run(check())
" 2>/dev/null; then
        echo "  ✓ Postgres ready"
        break
    fi
    sleep 2
done

# ── 3. Run DB migrations ──────────────────────────────────────────────────────
echo "▶ Running Alembic migrations..."
if ! alembic upgrade head; then
    echo "  ✗ Alembic migrations failed — refusing to start with an unknown schema." >&2
    exit 1
fi
echo "  ✓ Database schema up to date"

# ── 4. Seed vector store if empty ────────────────────────────────────────────
echo "▶ Checking vector store..."
COMPLAINT_COUNT=$(python -c "
from app.ingestion.processors.vector_store import VectorStoreWriter
from app.core.config import settings
try:
    w = VectorStoreWriter()
    print(w.collection_count(settings.qdrant_collection_complaints))
except Exception:
    print(0)
" 2>/dev/null || echo "0")

echo "  complaints collection: ${COMPLAINT_COUNT} vectors"

if [ "${COMPLAINT_COUNT}" = "0" ] && [ "${SKIP_INGEST:-false}" != "true" ]; then
    if [ -z "${OPENAI_API_KEY:-}" ] || [ "${OPENAI_API_KEY}" = "sk-...your-key-here..." ]; then
        echo "  ⚠ OPENAI_API_KEY not set — skipping ingestion. Set it in .env to enable."
    else
        echo "▶ Running sample ingestion (CFPB 5K + policy PDFs)..."
        python -m app.ingestion.pipeline --source cfpb --sample --provider openai 2>&1 \
            || echo "  ⚠ CFPB ingest failed"
        python -m app.ingestion.pipeline --source policy --provider openai 2>&1 \
            || echo "  ⚠ Policy ingest failed"
        echo "  ✓ Ingestion complete"
    fi
else
    echo "  ✓ Skipping ingest (${COMPLAINT_COUNT} vectors already loaded or SKIP_INGEST=true)"
fi

# ── 5. Start server ───────────────────────────────────────────────────────────
echo "▶ Starting API..."
echo "  http://localhost:8000/docs"
echo "═══════════════════════════════════════════════════"

# Normalize LOG_LEVEL to lowercase (uvicorn requires lowercase)
LOG_LEVEL_LOWER=$(echo "${LOG_LEVEL:-info}" | tr '[:upper:]' '[:lower:]')

exec uvicorn app.main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --workers 1 \
    --log-level "$LOG_LEVEL_LOWER"
