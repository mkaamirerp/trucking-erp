#!/usr/bin/env bash
# Build apps/web/dist and deploy static assets for PRODUCTION / public-server workflow.
#
# Canonical path: dist is baked into the truckerp-nginx image (docker-compose.yml).
# Run from repo root.
#
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/apps/web"
npm run build
cd "$ROOT"

docker compose -f docker-compose.yml build truckerp-nginx
docker compose -f docker-compose.yml up -d truckerp-nginx
echo "OK: truckerp-nginx rebuilt with baked dist and restarted (prod compose only)."
