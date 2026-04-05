#!/usr/bin/env bash
# Run the web app with Vite dev server (LOCAL). Open http://localhost:5173
#
# Requires an API reachable from your browser (e.g. ./scripts/dev-up.sh — docker compose -f docker-compose.yml only).

set -e
cd "$(dirname "$0")/.."
cd apps/web
exec npm run dev
