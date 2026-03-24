#!/usr/bin/env sh
set -eu

echo "== DB URL helper name guard =="
chmod +x scripts/ci_db_url_helper_guard.sh
./scripts/ci_db_url_helper_guard.sh

echo "== Tenant safety: grep gate =="
./scripts/ci_tenant_safety_grep.sh

echo "== Tenant safety: pytest gates =="
pytest -q tests/ci

echo "✅ CI tenant safety checks passed."
