#!/usr/bin/env bash
# Reload production API: rebuild API image and recreate the API container only.
# Does not rebuild nginx.
#
# Usage (canonical prod tree):
#   /home/admin/trucking_erp/scripts/reload_api.sh
#
# Fuel feature worktree (this repo path):
#   REPO_ROOT=/home/admin/trucking_erp-fuel /home/admin/trucking_erp-fuel/scripts/reload_api.sh

set -euo pipefail

PROD_ROOT="/home/admin/trucking_erp"
FUEL_ROOT="/home/admin/trucking_erp-fuel"

REPO_ROOT="$(cd "${REPO_ROOT:-$PROD_ROOT}" && pwd)"

case "$REPO_ROOT" in
  "$PROD_ROOT"|"$FUEL_ROOT") ;;
  *)
    echo "ERROR: API reload must use ${PROD_ROOT} or ${FUEL_ROOT} (got ${REPO_ROOT})." >&2
    exit 1
    ;;
esac

cd "$REPO_ROOT"

if [ -n "${COMPOSE_PROJECT_NAME:-}" ] && [ "$COMPOSE_PROJECT_NAME" != "trucking_erp" ]; then
  echo "ERROR: COMPOSE_PROJECT_NAME must be trucking_erp (got ${COMPOSE_PROJECT_NAME})." >&2
  exit 1
fi
export COMPOSE_PROJECT_NAME=trucking_erp

branch="$(git rev-parse --abbrev-ref HEAD)"
if [ "$REPO_ROOT" = "$PROD_ROOT" ] && [ "$branch" != "main" ]; then
  echo "ERROR: ${PROD_ROOT} reload requires branch main (got ${branch})." >&2
  exit 1
fi
if [ "$REPO_ROOT" = "$FUEL_ROOT" ] && [ "$branch" != "feat/fuel-card" ] && [ "$branch" != "main" ]; then
  echo "ERROR: ${FUEL_ROOT} reload requires feat/fuel-card or main (got ${branch})." >&2
  exit 1
fi

if [ -n "$(git status --porcelain)" ]; then
  echo "ERROR: API reload requires a clean worktree (commit or stash changes first)." >&2
  git status -sb >&2
  exit 1
fi

if [ -z "${TRUCKERP_APP_GIT_SHA:-}" ]; then
  TRUCKERP_APP_GIT_SHA="$(git rev-parse --short HEAD)"
fi
export TRUCKERP_APP_GIT_SHA

echo "==> REPO_ROOT=${REPO_ROOT}"
echo "==> branch=${branch}"
echo "==> HEAD=$(git rev-parse HEAD)"
echo "==> TRUCKERP_APP_GIT_SHA=${TRUCKERP_APP_GIT_SHA}"
echo "==> COMPOSE_PROJECT_NAME=${COMPOSE_PROJECT_NAME}"
echo "==> Rebuilding and recreating truckerp-api only (no nginx)..."

COMPOSE="docker compose -f docker-compose.yml"

$COMPOSE build truckerp-api && $COMPOSE up -d --no-deps truckerp-api

bash "$REPO_ROOT/scripts/api_import_smoke.sh"

echo ""
echo "==> Container status"
$COMPOSE ps truckerp-api

echo ""
echo "==> API logs (last 50 lines)"
docker logs truckerp-api --tail 50

echo ""
echo "==> Done. If you see startup logs above, the new code is running."
