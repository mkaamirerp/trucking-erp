#!/usr/bin/env bash
set -e

echo "Checking Alembic migrations for invalid down_revision=None..."

# Only the true first migration of each chain may have down_revision=None.
# All other migrations must set down_revision to their parent revision.
# Whitelist: known root migrations (one per chain). Any other file with None fails.
ALLOWED_NONE=(
  "alembic/versions/a59de96e634e_create_drivers_table.py"
  "alembic_tenant/versions/a59de96e634e_create_drivers_table.py"
)

BAD_FILES=""
for dir in alembic/versions alembic_platform/versions alembic_tenant/versions; do
  if [[ ! -d "$dir" ]]; then continue; fi
  for f in "$dir"/*.py; do
    [[ -f "$f" ]] || continue
    if grep -qE 'down_revision *= *None' "$f" 2>/dev/null; then
      allowed=0
      for a in "${ALLOWED_NONE[@]}"; do
        if [[ "$f" == "$a" ]]; then allowed=1; break; fi
      done
      if [[ "$allowed" -eq 0 ]]; then
        BAD_FILES="$BAD_FILES$f"$'\n'
      fi
    fi
  done
done

if [[ -n "$BAD_FILES" ]]; then
  echo "ERROR: Found migrations with down_revision=None (only the first migration per chain may have None):"
  echo "$BAD_FILES"
  exit 1
fi

echo "Alembic down_revision check passed."
