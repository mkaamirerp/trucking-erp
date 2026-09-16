#!/usr/bin/env bash
# Reload production API: rebuild API image and recreate the API container only.
# Does not rebuild nginx.
#
# Usage: /home/admin/trucking_erp-prod-main/scripts/reload_api.sh

set -euo pipefail

PROD_ROOT="/home/admin/trucking_erp-prod-main"
FORBIDDEN_ROOT="/home/admin/trucking_erp"

REPO_ROOT="$(cd "${REPO_ROOT:-$PROD_ROOT}" && pwd)"

if [ "$REPO_ROOT" != "$PROD_ROOT" ]; then
  echo "ERROR: production API reload must use ${PROD_ROOT} (got ${REPO_ROOT})." >&2
  echo "       ${FORBIDDEN_ROOT} is not a production deploy tree." >&2
  exit 1
fi

cd "$REPO_ROOT"

if [ -n "${COMPOSE_PROJECT_NAME:-}" ] && [ "$COMPOSE_PROJECT_NAME" != "trucking_erp" ]; then
  echo "ERROR: COMPOSE_PROJECT_NAME must be trucking_erp (got ${COMPOSE_PROJECT_NAME})." >&2
  exit 1
fi
export COMPOSE_PROJECT_NAME=trucking_erp

branch="$(git rev-parse --abbrev-ref HEAD)"
if [ "$branch" != "main" ]; then
  echo "ERROR: production reload requires branch main (got ${branch})." >&2
  exit 1
fi

if [ -n "$(git status --porcelain)" ]; then
  echo "ERROR: production reload requires a clean worktree." >&2
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
$COMPOSE ps

echo ""
echo "==> API logs (last 50 lines)"
docker logs truckerp-api --tail 50

echo ""
echo "==> Done. If you see startup logs above, the new code is running."
