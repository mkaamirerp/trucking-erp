#!/usr/bin/env bash
# Reload API: rebuild + restart + show status and logs.
# Run after any backend code change. No exceptions.
# Usage: ./scripts/reload_api.sh   or   bash /home/admin/trucking_erp/scripts/reload_api.sh

set -e
REPO_ROOT="${REPO_ROOT:-/home/admin/trucking_erp}"
cd "$REPO_ROOT"

COMPOSE="docker compose -f docker-compose.yml"

echo "==> Rebuilding and starting truckerp-api..."
$COMPOSE build truckerp-api && $COMPOSE up -d truckerp-api

echo ""
echo "==> Container status"
$COMPOSE ps

echo ""
echo "==> API logs (last 50 lines)"
docker logs truckerp-api --tail 50

echo ""
echo "==> Done. If you see startup logs above, the new code is running."
