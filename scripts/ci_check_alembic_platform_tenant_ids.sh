#!/usr/bin/env bash
# Guardrail: Platform and tenant migration chains must not cross-reference revision ids.
# - Tenant migrations must not have down_revision pointing to platform revision ids (e.g. 0005_..., c8a3d0b9c777).
# - Platform migrations must not have down_revision pointing to tenant revision ids.
set -e

PLATFORM_DIR="alembic_platform/versions"
TENANT_DIR="alembic_tenant/versions"

echo "Checking Alembic platform/tenant revision id separation..."

# Extract revision ids from Python files: revision = "id" or revision: str = "id" or revision = 'id'
extract_revision_ids() {
  local dir=$1
  [[ ! -d "$dir" ]] && return
  grep -hE 'revision\s*[=:].*["'"'"']([^"'"'"']+)["'"'"']' "$dir"/*.py 2>/dev/null | \
    sed -E 's/.*["'"'"']([^"'"'"']+)["'"'"'].*/\1/' | sort -u
}

# Check if any file in dir contains down_revision and the given id in quotes (whole token)
references_id() {
  local dir=$1
  local id=$2
  [[ ! -d "$dir" ]] && return 1
  for f in "$dir"/*.py; do
    [[ -f "$f" ]] || continue
    if grep -q "down_revision" "$f" && (grep -q "\"$id\"" "$f" || grep -q "'$id'" "$f"); then
      echo "$f"
      return 0
    fi
  done
  return 1
}

PLATFORM_IDS=$(extract_revision_ids "$PLATFORM_DIR")
# Also treat c8a3d0b9c777 as platform id (used as parent in platform chain; tenant must use tc8a3d0b9c777)
PLATFORM_IDS="$PLATFORM_IDS"$'\n'"c8a3d0b9c777"

FAIL=0

# Tenant must not reference any platform revision id
for id in $PLATFORM_IDS; do
  [[ -z "$id" ]] && continue
  if references_id "$TENANT_DIR" "$id"; then
    echo "ERROR: Tenant migrations must not have down_revision pointing to platform revision id: $id"
    echo "  (Use tenant-only revision ids; platform and tenant chains are separate.)"
    FAIL=1
  fi
done

# Platform must not reference any tenant revision id
TENANT_IDS=$(extract_revision_ids "$TENANT_DIR")
for id in $TENANT_IDS; do
  [[ -z "$id" ]] && continue
  if references_id "$PLATFORM_DIR" "$id"; then
    echo "ERROR: Platform migrations must not have down_revision pointing to tenant revision id: $id"
    echo "  (Platform and tenant chains are separate.)"
    FAIL=1
  fi
done

if [[ $FAIL -eq 1 ]]; then
  exit 1
fi

echo "Platform/tenant revision id separation check passed."
