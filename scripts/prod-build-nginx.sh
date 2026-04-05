#!/usr/bin/env bash
# Build frontend and bake it into the nginx image (deploy / public server).
# Run from repo root. Uses docker-compose.yml only.
# Usage: ./scripts/prod-build-nginx.sh

set -e
cd "$(git rev-parse --show-toplevel)"
COMPOSE=(docker compose -f docker-compose.yml)
echo "Building frontend..."
(cd apps/web && npm run build)
echo "Building nginx image with new dist..."
"${COMPOSE[@]}" build truckerp-nginx
echo "Done. Run: ${COMPOSE[*]} up -d truckerp-nginx"
