#!/usr/bin/env bash
# =============================================================================
# ARCHIVED — DO NOT USE ON CURRENT PROD COMPOSE WITHOUT REVIEW
# =============================================================================
# Historical helper from an older local/dev layout. It:
# - Injects TENANT_DATABASE_URL into compose (current prod file uses SSM; no
#   tenant URL in YAML by design).
# - Defaulted to obsolete DB name tenant_smoke_active (canonical demo DB is
#   tenant_demo — see docs/DATABASES_PLATFORM_AND_DEMO.md).
# - Assumes docker network truckerp_net and API hostname truckerp-api.
#
# Kept only for archaeology. Prefer: scripts/reload_api.sh, tenant routing
# checks in ops runbooks, and scripts/export_schema_docs.sh for schema dumps.
# =============================================================================

set -euo pipefail

FILE=""
for f in docker-compose.yml compose.yml docker-compose.yaml compose.yaml; do
  [ -f "$f" ] && FILE="$f" && break
done
[ -n "$FILE" ] || { echo "❌ No compose file found"; exit 1; }
echo "== Using compose file: $FILE =="

TS="$(date -u +%Y%m%d_%H%M%S)"
cp -a "$FILE" "${FILE}.bak_${TS}"
echo "✅ Backed up to ${FILE}.bak_${TS}"

python3 - <<PY
import sys, re
from pathlib import Path

path = Path("$FILE")
txt = path.read_text()

if "TENANT_DATABASE_URL" in txt:
    print("✅ TENANT_DATABASE_URL already present (no change).")
    sys.exit(0)

lines = txt.splitlines(True)
out = []
in_api = False
inserted = False

def indent_of(s): return len(s) - len(s.lstrip(" "))

for i, line in enumerate(lines):
    out.append(line)

    if re.match(r"^\\s*truckerp-api:\\s*$", line):
        in_api = True

    if in_api and re.match(r"^\\s{2}[^\\s].*:\\s*$", line) and not re.match(r"^\\s{2}truckerp-api:\\s*$", line):
        in_api = False

    if in_api and re.match(r"^\\s*environment:\\s*$", line):
        base_indent = indent_of(line)
        item_indent = " " * (base_indent + 2)

        j = i + 1
        while j < len(lines) and lines[j].strip() == "":
            j += 1
        next_line = lines[j] if j < len(lines) else ""

        if next_line.lstrip().startswith("-"):
            out.append(f"{item_indent}- TENANT_DATABASE_URL=postgresql+asyncpg://postgres:postgres@truckerp-postgres:5432/tenant_smoke_active\\n")
        else:
            out.append(f"{item_indent}TENANT_DATABASE_URL: postgresql+asyncpg://postgres:postgres@truckerp-postgres:5432/tenant_smoke_active\\n")
        inserted = True
        break

if not inserted:
    print("❌ Could not find truckerp-api environment block to patch. No changes written.")
    sys.exit(2)

path.write_text("".join(out))
print("✅ Patched TENANT_DATABASE_URL into compose.")
PY

echo
echo "== Recreating truckerp-api =="
docker compose -f "$FILE" up -d --force-recreate --no-deps truckerp-api

echo
echo "============================================================"
echo "TENANT ROUTING SMOKE (docker-network)"
echo "============================================================"

docker run --rm --network truckerp_net alpine:3.20 sh -lc '
  apk add --no-cache curl >/dev/null
  api="http://truckerp-api:8000/api/v1"
  BASE_DOMAIN="${BASE_DOMAIN:-truckerp.me}"
  SLUG="${TENANT_SLUG:-demo}"

  hit() {
    name="$1"; shift
    code=$(curl -sS -o /tmp/body -w "%{http_code}" "$@")
    echo "[$name] http_code=$code"
    if [ "$code" -ge 400 ]; then
      echo "--- body ---"; cat /tmp/body; echo; echo "------------"
    fi
    echo "$code"
  }

  # Tenant routing uses Host (workspace subdomain), not X-Tenant-* headers.
  c1=$(hit "Host OK   " -H "Host: ${SLUG}.${BASE_DOMAIN}" "$api/drivers")
  c2=$(hit "Host miss " "$api/drivers")
  c3=$(hit "Host bad  " -H "Host: zzz-nonexistent.${BASE_DOMAIN}" "$api/drivers")

  echo
  [ "$c1" = "401" ] && echo "✅ Workspace Host, no auth => 401" || echo "❌ Expected 401 got $c1"
  [ "$c2" = "400" ] && echo "✅ Missing workspace Host => 400" || echo "❌ Missing Host expected 400 got $c2"
  [ "$c3" = "403" ] && echo "✅ Unknown workspace => 403" || echo "❌ Unknown workspace expected 403 got $c3"

  [ "$c1" = "401" ] && [ "$c2" = "400" ] && [ "$c3" = "403" ]
' || {
  echo
  echo "============================================================"
  echo "❌ Smoke failed — last API logs"
  echo "============================================================"
  docker logs --tail 250 truckerp-api || true
  exit 1
}

echo
echo "✅ All tenant routing checks passed."
