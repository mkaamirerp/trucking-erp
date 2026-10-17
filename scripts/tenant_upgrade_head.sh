#!/usr/bin/env bash
# =============================================================================
# Tenant upgrade head: runs preflight then alembic upgrade head.
# MUST be run inside truckerp-api container at /app:
#   docker exec truckerp-api bash -lc 'cd /app && bash scripts/tenant_upgrade_head.sh'
# Optional: CONFIRM=1 to prompt before upgrade (default: no prompt, automation-safe).
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PREFLIGHT_SCRIPT="${SCRIPT_DIR}/tenant_migrate_preflight.sh"

git_safe_app() {
  GIT_CONFIG_COUNT=1 \
  GIT_CONFIG_KEY_0=safe.directory \
  GIT_CONFIG_VALUE_0=/app \
  git -C /app "$@"
}

# Drift proof: print commit so we know exactly what code is running migrations
echo "Tenant upgrade: repo at /app"
if COMMIT_ECHO="${TRUCKERP_APP_GIT_SHA:-${SOURCE_COMMIT:-${GIT_COMMIT:-}}}"; [ -n "$COMMIT_ECHO" ]; then
  echo "$COMMIT_ECHO"
else
  git_safe_app rev-parse --short HEAD 2>/dev/null || echo "(no .git — set TRUCKERP_APP_GIT_SHA for traceability)"
fi
echo ""

# Run preflight (read-only checks + 1 head + env gate)
if ! bash "$PREFLIGHT_SCRIPT"; then
  echo "Upgrade aborted: preflight failed."
  exit 1
fi

if [ "${CONFIRM:-0}" = "1" ]; then
  echo "Preflight passed. Proceed with tenant upgrade head? (y/N)"
  read -r r
  if [ "$r" != "y" ] && [ "$r" != "Y" ]; then
    echo "Upgrade cancelled."
    exit 0
  fi
fi

HEADS_OUT="$(cd /app && alembic -c alembic_tenant.ini heads 2>&1)"
HEAD_COUNT=$(printf "%s\n" "$HEADS_OUT" | grep -c '(head)' || true)
if [ "${HEAD_COUNT:-0}" -ne 1 ]; then
  echo "Refusing alembic upgrade head: tenant graph has ${HEAD_COUNT} heads."
  echo "$HEADS_OUT"
  echo "Use scripts/tenant_upgrade_revision.sh with an explicit revision."
  echo "  x5 tenants (no DW-1): i14_load_pod_evidence_x5"
  echo "  dw1c tenants (no POD): i14_load_pod_evidence"
  echo "See docs/load_trip/POD_MIGRATION_TARGETS.md"
  exit 1
fi

echo "Running: alembic -c /app/alembic_tenant.ini upgrade head"
cd /app && alembic -c /app/alembic_tenant.ini upgrade head
echo "Tenant upgrade head completed."
