#!/usr/bin/env bash
# Upgrade one tenant database to an explicit revision. Refuses "head".
# While the I14 POD branches are split, the only allowed targets are
# i14_load_pod_evidence_x5 (from x5) and i14_load_pod_evidence (from dw1c).
#
#   bash scripts/tenant_upgrade_revision.sh i14_load_pod_evidence_x5
#
# Must run inside truckerp-api at /app with ALEMBIC_TENANT_DATABASE_URL set.
set -euo pipefail

TARGET="${1:-}"
if [ -z "$TARGET" ] || [ "$TARGET" = "head" ] || [ "$TARGET" = "heads" ]; then
  echo "Refusing upgrade head. Pass an explicit revision."
  echo "  x5 tenants (no DW-1): i14_load_pod_evidence_x5"
  echo "  dw1c tenants (no POD): i14_load_pod_evidence"
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
if ! bash "${SCRIPT_DIR}/tenant_migrate_preflight.sh"; then
  echo "Upgrade aborted: preflight failed."
  exit 1
fi

cd /app
CURRENT="$(alembic -c alembic_tenant.ini current 2>/dev/null | awk '{print $1}' | head -n1 || true)"
export TARGET CURRENT
python - <<'PY'
import os
import sys
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

sys.path.insert(0, "/app")
from scripts.tenant_revision_plan import RevisionPlanError, assert_target_matches_history

target = os.environ["TARGET"]
current = os.environ.get("CURRENT") or None
if current in {"", "None"}:
    current = None
script = ScriptDirectory.from_config(Config("alembic_tenant.ini"))
try:
    plan = assert_target_matches_history(script, current, target)
except RevisionPlanError as exc:
    print(f"Refusing upgrade: {exc}", file=sys.stderr)
    sys.exit(1)
print("Pending revisions:")
for rev in plan:
    print(f"  {rev}")
PY

echo "Running: alembic -c /app/alembic_tenant.ini upgrade ${TARGET}"
alembic -c /app/alembic_tenant.ini upgrade "$TARGET"
echo "Tenant upgrade to ${TARGET} completed."
