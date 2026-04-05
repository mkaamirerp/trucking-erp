#!/usr/bin/env bash
# Bring up the production-shaped stack (docker-compose.yml only).
# Run from repo root.
# Usage: ./scripts/dev-up.sh

set -e
cd "$(git rev-parse --show-toplevel)"

COMPOSE="docker compose -f docker-compose.yml"

echo "Building images (cached when unchanged)..."
$COMPOSE build truckerp-api truckerp-nginx

echo "Starting stack..."
$COMPOSE up -d

echo "Done. API reload helper: scripts/reload_api.sh. Frontend publish: scripts/publish_frontend.sh."
