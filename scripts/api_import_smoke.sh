#!/usr/bin/env bash
# Pre-deploy / post-up gate: ensure the API image can import app.main (catches import-time errors
# like NameError before marking the backend healthy). Does not rebuild or touch nginx.
# ("smoke" here means a quick import health check — not tenant_smoke_* databases.)
#
# Usage (after truckerp-api container is up):  bash scripts/api_import_smoke.sh
# Env: TRUCKERP_API_CONTAINER (default truckerp-api), API_IMPORT_SMOKE_MAX_WAIT (default 120)

set -euo pipefail

CONTAINER="${TRUCKERP_API_CONTAINER:-truckerp-api}"
MAX_WAIT="${API_IMPORT_SMOKE_MAX_WAIT:-120}"

echo "==> Import smoke: import app.main (with /run/secrets/truckerp.env when present — matches runtime Settings)"

IMPORT_PY='set -a; [ -f /run/secrets/truckerp.env ] && . /run/secrets/truckerp.env; set +a; cd /app && python3 -c "import app.main"'

n=0
while [ "$n" -lt "$MAX_WAIT" ]; do
  if out=$(docker exec "$CONTAINER" bash -lc "$IMPORT_PY" 2>&1); then
    echo "OK"
    exit 0
  fi

  if printf '%s' "$out" | grep -qiE 'restarting|container .* is not running|No such container'; then
    n=$((n + 1))
    sleep 1
    continue
  fi
  # Startup race: SSM render may not have written truckerp.env yet.
  if printf '%s' "$out" | grep -qiE 'database_url|Field required'; then
    n=$((n + 1))
    sleep 1
    continue
  fi

  printf '%s\n' "$out"
  echo "FAIL: import app.main — stop deployment. Inspect traceback above and fix import/startup."
  echo "    Do not mark backend healthy or continue nginx rollout until this passes."
  docker logs "$CONTAINER" --tail 100 2>/dev/null || true
  exit 1
done

echo "FAIL: timeout after ${MAX_WAIT}s waiting for ${CONTAINER} to accept import app.main."
docker logs "$CONTAINER" --tail 100 2>/dev/null || true
exit 1
