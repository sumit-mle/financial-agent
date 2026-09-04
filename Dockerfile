# =============================================================================
# Fin AI Agent — Backend Dockerfile
# Base: python:3.11-slim  (langgraph + langchain require 3.11, not 3.12+)
# Install: from requirements.txt directly — no build tool needed
# =============================================================================

FROM python:3.11-slim

WORKDIR /app

# ── System deps ───────────────────────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
        build-essential \
        libgomp1 \
        git \
    && rm -rf /var/lib/apt/lists/*

# ── Python deps ───────────────────────────────────────────────────────────────
# Copy requirements first — Docker cache skips this layer when only app/ changes
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt \
    # Install reranker separately (pulls onnxruntime — cached after first build)
    && pip install --no-cache-dir "flashrank==0.2.9"

# ── App source ────────────────────────────────────────────────────────────────
COPY app/ ./app/
COPY scripts/ ./scripts/
COPY alembic.ini ./
COPY migrations/ ./migrations/

# ── Data + cache dirs ─────────────────────────────────────────────────────────
RUN mkdir -p /app/data/raw /app/data/processed /app/data/policies /app/.cache

# ── Make startup script executable ───────────────────────────────────────────
RUN chmod +x /app/scripts/start.sh

# ── Non-root user for security ────────────────────────────────────────────────
RUN useradd -m -u 1000 appuser \
    && chown -R appuser:appuser /app
USER appuser

# ── Health check ──────────────────────────────────────────────────────────────
HEALTHCHECK --interval=15s --timeout=10s --start-period=60s --retries=5 \
    CMD curl -f http://localhost:8000/health || exit 1

EXPOSE 8000

# ── Start via script (waits for services + seeds data + starts uvicorn) ───────
CMD ["/app/scripts/start.sh"]
