#!/usr/bin/env bash
# Run Fuel pytest with integration isolation (tenant_pytest) and host venv deps (pdfminer).
#
# Usage:
#   ./scripts/run_fuel_pytest.sh tests/test_fuel_dashboard_stats.py -v
#   ./scripts/run_fuel_pytest.sh tests/test_fuel*.py -q
#
# Never points at tenant_demo — mutating integration tests require tenant_pytest.

set -euo pipefail
REPO_ROOT="${REPO_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
cd "$REPO_ROOT"

VENV_PY="${REPO_ROOT}/venv/bin/python"
if [[ ! -x "$VENV_PY" ]]; then
  VENV_PY="/home/admin/trucking_erp/venv/bin/python"
fi
if [[ ! -x "$VENV_PY" ]]; then
  echo "No venv python found (expected ${REPO_ROOT}/venv or /home/admin/trucking_erp/venv)" >&2
  exit 1
fi

PG_IP="$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' truckerp-postgres 2>/dev/null || true)"
if [[ -z "$PG_IP" ]]; then
  echo "Container truckerp-postgres not found (is the stack up?)" >&2
  exit 1
fi

if [[ -z "${DATABASE_URL:-}" ]]; then
  if ! docker inspect truckerp-api >/dev/null 2>&1; then
    echo "Set DATABASE_URL or start truckerp-api so secrets can be read." >&2
    exit 1
  fi
  RAW="$(docker exec truckerp-api bash -lc 'set -a && . /run/secrets/truckerp.env && set +a && printf %s "$DATABASE_URL"')"
  export DATABASE_URL="${RAW//truckerp-postgres/$PG_IP}"
fi

export INTEGRATION_DB="${TRUCKERP_INTEGRATION_TENANT_DB:-tenant_pytest}"
export BASE_URL="${DATABASE_URL}"
# Swap path db segment to tenant_pytest (postgresql:// or postgresql+asyncpg://).
TENANT_URL="$(python3 - <<PY
from urllib.parse import urlparse, urlunparse
import os
raw = os.environ["BASE_URL"]
parsed = urlparse(raw)
path = "/" + os.environ["INTEGRATION_DB"]
print(urlunparse(parsed._replace(path=path)))
PY
)"

export ENVIRONMENT="${ENVIRONMENT:-test}"
export ALLOW_TENANT_RESOLUTION_SHORTCUTS="${ALLOW_TENANT_RESOLUTION_SHORTCUTS:-true}"
export TEST_BYPASS_AUTH="${TEST_BYPASS_AUTH:-1}"
export TENANT_DATABASE_URL="${TENANT_URL}"
export ALEMBIC_TENANT_DATABASE_URL="${TENANT_URL}"
export TRUCKERP_INTEGRATION_TENANT_DB="${INTEGRATION_DB}"
export TRUCKERP_INTEGRATION_TENANT_SLUG="${TRUCKERP_INTEGRATION_TENANT_SLUG:-pytest}"

echo "Fuel pytest: ENVIRONMENT=$ENVIRONMENT TENANT_DATABASE_URL db=$(python3 -c "from urllib.parse import urlparse; import os; print(urlparse(os.environ['TENANT_DATABASE_URL']).path.lstrip('/'))")" >&2

if [[ "${RUN_FUEL_TENANT_MIGRATE:-0}" == "1" ]]; then
  echo "Running alembic tenant upgrade head on integration DB..." >&2
  export ALEMBIC_TENANT_DATABASE_URL="${TENANT_URL}"
  (cd "$REPO_ROOT" && PYTHONPATH="$REPO_ROOT" "$VENV_PY" -m alembic -c alembic_tenant.ini upgrade head) >&2
fi

exec "$VENV_PY" -m pytest "$@"
