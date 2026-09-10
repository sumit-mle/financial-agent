#!/bin/bash
# =============================================================================
# Production deployment script
# Rebuilds frontend in production mode (nginx) and restarts services
# =============================================================================
set -euo pipefail

echo "═══════════════════════════════════════════════════"
echo "  Fin AI Agent — Production Deployment"
echo "═══════════════════════════════════════════════════"

# Stop dev services
echo "▶ Stopping dev containers..."
docker-compose down

# Rebuild frontend in production mode
echo "▶ Building production frontend (nginx + static assets)..."
docker-compose -f docker-compose.yml -f docker-compose.prod.yml build frontend

# Start all services in production mode
echo "▶ Starting production stack..."
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d

# Wait for health checks
echo "▶ Waiting for services..."
sleep 10

# Show status
docker-compose -f docker-compose.yml -f docker-compose.prod.yml ps

echo ""
echo "═══════════════════════════════════════════════════"
echo "  ✓ Production deployment complete!"
echo "═══════════════════════════════════════════════════"
echo ""
echo "  API:      http://localhost:8000/docs"
echo "  Frontend: http://localhost:3000"
echo "  Health:   http://localhost:8000/health"
echo ""
echo "To view logs:"
echo "  docker-compose -f docker-compose.yml -f docker-compose.prod.yml logs -f"
echo ""
