#!/usr/bin/env bash
# Full rebuild: frontend npm build, API image rebuild, restart API + nginx.
# Usage: ./scripts/rebuild.sh   or   bash /home/admin/trucking_erp/scripts/rebuild.sh
# To type just "rebuild", add to ~/.bashrc:  alias rebuild='/home/admin/trucking_erp/scripts/rebuild.sh'

set -e
REPO_ROOT="${REPO_ROOT:-/home/admin/trucking_erp}"
cd "$REPO_ROOT"

COMPOSE="docker compose -f docker-compose.yml"

echo "==> 1/3 Frontend: npm run build"
(cd apps/web && npm run build)

echo ""
echo "==> 2/3 API + Nginx: rebuild images; start API; import smoke; then nginx"
$COMPOSE build truckerp-api truckerp-nginx
$COMPOSE up -d --force-recreate truckerp-api
bash "$REPO_ROOT/scripts/api_import_smoke.sh"
$COMPOSE up -d --force-recreate truckerp-nginx

echo ""
echo "==> 3/3 Container status"
$COMPOSE ps

echo ""
echo "==> Done. Frontend: baked into nginx image. API: rebuilt and running."
