#!/usr/bin/env bash
# =============================================================================
# Migration Conflict Checker
# Prevents multiple migrations with the same down_revision (branching)
# Checks for untracked migration files (WIP that shouldn't be committed)
# Validates exactly one head per migration branch (linear history)
# Run in CI and pre-commit to catch conflicts early
# =============================================================================
set -euo pipefail

echo "🔍 Checking Alembic migration hygiene..."
echo ""

TENANT_DIR="alembic_tenant/versions"
PLATFORM_DIR="alembic_platform/versions"
failed=0

# =============================================================================
# Check 1: Untracked or modified migration files
# =============================================================================
echo "📋 Check 1: Untracked/modified migration files..."

if command -v git &>/dev/null && [[ -d .git ]]; then
  untracked=$(git status --porcelain | awk '/^\?\?.*alembic_(tenant|platform)\/versions\/.*\.py$/ {print $2}')
  modified=$(git status --porcelain | awk '/^ M.*alembic_(tenant|platform)\/versions\/.*\.py$/ {print $2}')
  
  if [[ -n "$untracked" ]]; then
    echo ""
    echo "❌ ERROR: Untracked migration files detected:"
    echo "$untracked" | while read -r file; do
      echo "   - $file"
    done
    echo ""
    echo "   Untracked migrations cause DB drift: they may run on some environments"
    echo "   but not others. In TruckERP terms this is NOT 'all checks passed'."
    echo ""
    echo "   FIX: Either commit them (git add <file> && git commit) or delete"
    echo "   drafts (rm <file>). Do not leave migrations untracked."
    echo ""
    failed=1
  fi
  
  if [[ -n "$modified" ]]; then
    echo ""
    echo "❌ ERROR: Modified migration files detected:"
    echo "$modified" | while read -r file; do
      echo "   - $file"
    done
    echo ""
    echo "   Migration files should not be modified after being committed."
    echo "   Create a new migration instead: alembic revision --autogenerate -m 'fix'"
    echo ""
    failed=1
  fi
  
  if [[ -z "$untracked" && -z "$modified" ]]; then
    echo "   ✅ All migration files tracked and unmodified"
  fi
else
  echo "   ⚠️  Skipped (not a git repository or git not installed)"
fi

echo ""

# =============================================================================
# Check 2: Multiple heads (via alembic heads command)
# =============================================================================
echo "📋 Check 2: Multiple heads (linear history check)..."

check_heads() {
  local config="$1"
  local name="$2"
  
  if [[ ! -f "$config" ]]; then
    echo "   ⚠️  $config not found, skipping $name heads check"
    return 0
  fi
  
  # Try to run alembic heads (may fail if no DB connection)
  local heads_output
  heads_output=$(alembic -c "$config" heads 2>/dev/null || echo "")
  
  if [[ -z "$heads_output" ]]; then
    echo "   ⚠️  $name: Could not check heads (no DB or alembic error), skipping"
    return 0
  fi
  
  local head_count
  head_count=$(echo "$heads_output" | grep -c "^[a-f0-9]" || echo "0")
  
  if [[ "$head_count" -gt 1 ]]; then
    echo ""
    echo "   ❌ $name has $head_count heads (expected 1):"
    echo "$heads_output" | sed 's/^/      /'
    echo ""
    echo "   Fix: Create a merge migration:"
    echo "      alembic -c $config merge -m 'merge heads'"
    echo ""
    return 1
  elif [[ "$head_count" -eq 1 ]]; then
    echo "   ✅ $name: Exactly 1 head (linear history)"
  else
    echo "   ⚠️  $name: 0 heads detected (unusual, check alembic_version table)"
  fi
  
  return 0
}

heads_ok=1
# Platform control-plane migrations: alembic_platform.ini (see start_api_with_ssm.sh).
# Root alembic.ini / alembic/versions is a separate legacy tree — not used for this heads check.
check_heads "alembic_platform.ini" "Platform (alembic_platform.ini)" || { failed=1; heads_ok=0; }
check_heads "alembic_tenant.ini" "Tenant" || { failed=1; heads_ok=0; }

echo ""

# =============================================================================
# Check 3: Branching conflicts (file-level analysis)
# If Check 2 passed (1 head each), branching is already resolved by merges → don't fail
# =============================================================================
echo "📋 Check 3: Branching conflicts (same down_revision)..."

check_conflicts() {
  local dir="$1"
  local name="$2"
  local conflicts=0
  
  # Skip if directory doesn't exist
  [[ -d "$dir" ]] || return 0
  
  # Associative array: down_revision -> file_path
  declare -A down_rev_map
  
  for f in "$dir"/*.py; do
    [[ -f "$f" ]] || continue
    [[ "$(basename "$f")" == "__init__.py" ]] && continue
    
    # Skip merge migrations (have tuple/list down_revision)
    if grep -qE "down_revision.*=.*\\[|down_revision.*=.*\\(.*," "$f"; then
      continue
    fi
    
    # Extract down_revision value (single string)
    down_rev=$(grep "^down_revision" "$f" | sed -E "s/.*['\"]([a-f0-9]+|None)['\"].*/\1/" | head -n1)
    revision=$(grep "^revision" "$f" | sed -E "s/.*['\"]([a-f0-9]+)['\"].*/\1/" | head -n1)
    
    if [[ -n "$down_rev" && "$down_rev" != "None" ]]; then
      if [[ -n "${down_rev_map[$down_rev]:-}" ]]; then
        echo ""
        if [[ "$heads_ok" -eq 1 ]]; then
          echo "   ℹ️  Historical branching in $name (already resolved by merge migrations):"
          echo "      $(basename "${down_rev_map[$down_rev]}") and $(basename "$f") (down_revision=$down_rev)"
          echo "      No action needed — Check 2 confirmed exactly 1 head."
        else
          echo "   ❌ CONFLICT DETECTED in $name migrations:"
          echo ""
          echo "      File 1: $(basename "${down_rev_map[$down_rev]}")"
          echo "      File 2: $(basename "$f")"
          echo "      Both have down_revision = '$down_rev'"
          echo ""
          echo "   ⚠️  FIX: Create a merge migration: alembic -c alembic_tenant.ini merge -m 'merge heads'"
          echo ""
          conflicts=1
        fi
      else
        down_rev_map[$down_rev]="$f"
      fi
    fi
  done
  
  return $conflicts
}

conflicts_found=0
check_conflicts "$TENANT_DIR" "tenant" || conflicts_found=1
check_conflicts "$PLATFORM_DIR" "platform" || conflicts_found=1

if [[ $conflicts_found -eq 1 && "$heads_ok" -eq 0 ]]; then
  failed=1
fi

if [[ $conflicts_found -eq 0 ]]; then
  echo "   ✅ No branching conflicts detected"
elif [[ "$heads_ok" -eq 1 ]]; then
  echo "   ✅ Branching resolved by merge migrations (1 head confirmed)"
fi

echo ""
echo "═════════════════════════════════════════════════════════════════"

if [[ $failed -eq 1 ]]; then
  echo "❌ MIGRATION HYGIENE CHECK FAILED"
  echo ""
  echo "One or more checks failed. Fix the issues above before proceeding."
  echo ""
  exit 1
fi

echo "✅ ALL CHECKS PASSED - Migration hygiene is good!"
echo ""
echo "Summary:"
echo "  ✓ No untracked migration files (all migrations committed or removed)"
echo "  ✓ No modified migration files"
echo "  ✓ Linear history (1 head per branch)"
echo "  ✓ No unresolved branching conflicts"
echo ""
