#!/usr/bin/env bash
# Run load optimistic-concurrency integration tests inside truckerp-api (real DB from secrets).
# Usage: bash scripts/run_load_concurrency_integration_tests.sh
set -euo pipefail
REPO_ROOT="${REPO_ROOT:-/home/admin/trucking_erp}"
cd "$REPO_ROOT"

if ! docker compose -f docker-compose.yml ps --status running --format '{{.Name}}' 2>/dev/null | grep -q '^truckerp-api$'; then
  echo "truckerp-api container not running" >&2
  exit 1
fi

docker exec truckerp-api bash -lc '
  pip install -q pytest pytest-asyncio httpx
  set -a && . /run/secrets/truckerp.env && set +a
  cd /app
  python -m pytest \
    tests/test_loads_v1.py \
    tests/test_dispatch_trip_numbers.py \
    tests/test_customs_brokers_slice.py \
    -q --tb=short
'
