#!/usr/bin/env sh
set -eu

# --- Tenant-scoped code locations (adjust as your repo evolves) ---
TENANT_DIRS="
app/routers/tenant
app/services/tenant
app/repos/tenant
tenant_api
"

existing_dirs=""
for d in $TENANT_DIRS; do
  if [ -d "$d" ]; then
    existing_dirs="$existing_dirs $d"
  fi
done

if [ -z "$existing_dirs" ]; then
  echo "No tenant directories found; grep gate skipped."
  exit 0
fi

echo "Tenant safety grep gate scanning:$existing_dirs"

fail() {
  echo "❌ $1"
  exit 1
}

# Prefer ripgrep if installed
if command -v rg >/dev/null 2>&1; then
  FIND="rg -n --hidden --no-ignore-vcs"
else
  FIND="grep -R -n"
fi

# Allow raw SQL in these locations only (migrations/scripts)
ALLOW_RE='/(alembic|alembic_tenant|migrations|scripts)/'

# ------------------------------
# RULE A: Tenant code must NOT use platform DB deps
# ------------------------------
# Typical mistakes:
#   from app.deps.db import get_db
#   Depends(get_db)
#   PLATFORM_DATABASE_URL
if $FIND "from[[:space:]]+app\.deps\.db[[:space:]]+import[[:space:]]+get_db|Depends\([[:space:]]*get_db[[:space:]]*\)|PLATFORM_DATABASE_URL" $existing_dirs >/dev/null 2>&1; then
  echo "Matches:"
  $FIND "from[[:space:]]+app\.deps\.db[[:space:]]+import[[:space:]]+get_db|Depends\([[:space:]]*get_db[[:space:]]*\)|PLATFORM_DATABASE_URL" $existing_dirs || true
  fail "Tenant code references platform DB deps. Use get_tenant_db + tenant resolver."
fi

# ------------------------------
# RULE B: Forbid raw SQL helpers in tenant code (text(), execute('SELECT...'))
# ------------------------------
# text(
if $FIND "text\(" $existing_dirs 2>/dev/null | grep -Ev "$ALLOW_RE" >/dev/null 2>&1; then
  echo "Matches:"
  $FIND "text\(" $existing_dirs 2>/dev/null | grep -Ev "$ALLOW_RE" || true
  fail "Raw SQL via text() found in tenant code. Use safe SQLAlchemy constructs or allowlist intentionally."
fi

# .execute("SELECT ...") / .execute(f"SELECT ...") / etc.
if $FIND "\.execute\([[:space:]]*(f|r)?(\"|')[[:space:]]*(SELECT|UPDATE|DELETE|INSERT)\b" $existing_dirs 2>/dev/null | grep -Ev "$ALLOW_RE" >/dev/null 2>&1; then
  echo "Matches:"
  $FIND "\.execute\([[:space:]]*(f|r)?(\"|')[[:space:]]*(SELECT|UPDATE|DELETE|INSERT)\b" $existing_dirs 2>/dev/null | grep -Ev "$ALLOW_RE" || true
  fail "Raw SQL passed to execute() found in tenant code. Must use parameterized SQLAlchemy Core/ORM patterns."
fi

# ------------------------------
# RULE C: Keep tenant routers thin (no direct db.execute in tenant routers)
# ------------------------------
if [ -d "app/routers/tenant" ]; then
  if $FIND "\.execute\(" app/routers/tenant 2>/dev/null | grep -Ev "$ALLOW_RE" >/dev/null 2>&1; then
    echo "Matches:"
    $FIND "\.execute\(" app/routers/tenant 2>/dev/null | grep -Ev "$ALLOW_RE" || true
    fail "Direct db.execute() in tenant routers. Put DB work in repos/services enforcing tenant_id."
  fi
fi

echo "✅ Tenant safety grep gate passed."
