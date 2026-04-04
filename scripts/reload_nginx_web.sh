#!/usr/bin/env bash
# Canonical frontend deploy: Vite build + rebuild nginx image (dist is baked in, not bind-mounted).
# After this, tenants get the new app on normal navigation/reload — see docs/FRONTEND_DEPLOY.md.
set -e
REPO_ROOT="${REPO_ROOT:-/home/admin/trucking_erp}"
cd "$REPO_ROOT"

echo "==> npm run build (apps/web)"
(cd apps/web && npm run build)

COMPOSE="docker compose -f docker-compose.yml"
echo "==> docker compose build truckerp-nginx && up -d truckerp-nginx"
$COMPOSE build truckerp-nginx && $COMPOSE up -d truckerp-nginx

echo ""
$COMPOSE ps truckerp-nginx
echo ""
echo "Done. index.html is served with no-store; hashed /assets/* are immutable. See docs/FRONTEND_DEPLOY.md."
