#!/usr/bin/env bash
# Run pytest from the repo venv with DATABASE_URL pointing at Postgres over the Docker bridge.
# Postgres is not published on the host; substitute truckerp-postgres with the container IP.
#
# Usage:
#   ./scripts/run_host_pytest.sh tests/test_brokers_foundation.py -q
#   DATABASE_URL can be omitted; it is taken from truckerp-api secrets when available.

set -euo pipefail
REPO_ROOT="${REPO_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
cd "$REPO_ROOT"

VENV_PY="${REPO_ROOT}/venv/bin/python"
if [[ ! -x "$VENV_PY" ]]; then
  echo "Expected venv at ${REPO_ROOT}/venv — create it and pip install -r requirements.txt -r requirements-dev.txt" >&2
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

export ENVIRONMENT="${ENVIRONMENT:-test}"
export TEST_BYPASS_AUTH="${TEST_BYPASS_AUTH:-1}"

exec "$VENV_PY" -m pytest "$@"
