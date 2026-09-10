# =============================================================================
# Fin AI Agent — Backend Dockerfile
# Multi-stage build for minimal production footprint and tight security.
# =============================================================================

# ── Stage 1: Builder ──────────────────────────────────────────────────────────
FROM python:3.11.9-slim-bookworm AS builder

# Stop Python from writing .pyc files and enable unbuffered output
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libgomp1 \
        git \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
# Create a virtual environment and install dependencies there
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --upgrade pip \
    && /opt/venv/bin/pip install -r requirements.txt \
    && /opt/venv/bin/pip install "flashrank==0.2.9"

# ── Stage 2: Runtime ──────────────────────────────────────────────────────────
FROM python:3.11.9-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app

# Install minimal runtime system dependencies (libgomp1 is needed by ONNX/FlashRank)
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
        libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Create a non-root user and necessary directories
RUN useradd -m -u 1000 appuser \
    && mkdir -p /app/data/raw /app/data/processed /app/data/policies /app/.cache \
    && chown -R appuser:appuser /app /opt/venv

# Copy the virtual environment from the builder stage
COPY --from=builder --chown=appuser:appuser /opt/venv /opt/venv

# Copy application source code
COPY --chown=appuser:appuser app/ ./app/
COPY --chown=appuser:appuser scripts/ ./scripts/
COPY --chown=appuser:appuser alembic.ini ./
COPY --chown=appuser:appuser migrations/ ./migrations/

# Ensure the startup script is executable
RUN chmod +x /app/scripts/start.sh

# Run as non-root user
USER appuser

# Health check
HEALTHCHECK --interval=15s --timeout=10s --start-period=60s --retries=5 \
    CMD curl -f http://localhost:8000/health || exit 1

EXPOSE 8000

# Start via script (waits for services + seeds data + starts uvicorn)
CMD ["/app/scripts/start.sh"]

