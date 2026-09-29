#!/usr/bin/env bash
# Canonical frontend deploy: Vite build + rebuild nginx image (dist is baked in, not bind-mounted).
# After this, tenants get the new app on normal navigation/reload — see docs/FRONTEND_DEPLOY.md.
#
# Usage (canonical prod tree):
#   /home/admin/trucking_erp/scripts/reload_nginx_web.sh
#
# Fuel feature worktree:
#   REPO_ROOT=/home/admin/trucking_erp-fuel /home/admin/trucking_erp-fuel/scripts/reload_nginx_web.sh

set -euo pipefail

PROD_ROOT="/home/admin/trucking_erp"
FUEL_ROOT="/home/admin/trucking_erp-fuel"

REPO_ROOT="$(cd "${REPO_ROOT:-$PROD_ROOT}" && pwd)"

case "$REPO_ROOT" in
  "$PROD_ROOT"|"$FUEL_ROOT") ;;
  *)
    echo "ERROR: nginx reload must use ${PROD_ROOT} or ${FUEL_ROOT} (got ${REPO_ROOT})." >&2
    exit 1
    ;;
esac

cd "$REPO_ROOT"

if [ -n "${COMPOSE_PROJECT_NAME:-}" ] && [ "$COMPOSE_PROJECT_NAME" != "trucking_erp" ]; then
  echo "ERROR: COMPOSE_PROJECT_NAME must be trucking_erp (got ${COMPOSE_PROJECT_NAME})." >&2
  exit 1
fi
export COMPOSE_PROJECT_NAME=trucking_erp

echo "==> REPO_ROOT=${REPO_ROOT}"
echo "==> COMPOSE_PROJECT_NAME=${COMPOSE_PROJECT_NAME}"

echo "==> npm run build (apps/web)"
(cd apps/web && npm run build)

COMPOSE="docker compose -f docker-compose.yml"
echo "==> docker compose build truckerp-nginx && up -d --no-deps truckerp-nginx"
$COMPOSE build truckerp-nginx && $COMPOSE up -d --no-deps truckerp-nginx

echo ""
$COMPOSE ps truckerp-nginx
echo ""
echo "Done. index.html is served with no-store; hashed /assets/* are immutable. See docs/FRONTEND_DEPLOY.md."
