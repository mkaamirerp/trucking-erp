#!/usr/bin/env sh
set -eu

echo "== Tenant safety: grep gate =="
./scripts/ci_tenant_safety_grep.sh

echo "== Tenant safety: pytest gates =="
pytest -q tests/ci

echo "✅ CI tenant safety checks passed."
