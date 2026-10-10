# Migration Validation System

## Overview

This document describes the **permanent migration validation system** that prevents migration conflicts and schema drift in TruckERP.

**Problem it solves:** Migration conflicts were discovered too late (during INSERT operations), causing weekly firefighting. The system now catches conflicts **when migrations are created** (CI) and **when tenants are provisioned** (runtime).

---

## Components

### 1. Conflict Checker (`scripts/check_migration_conflicts.sh`)

**Purpose:** Comprehensive migration hygiene checker that validates:
1. **Untracked/modified files** - Catches WIP migrations that shouldn't be committed
2. **Multiple heads** - Ensures exactly 1 head per branch (linear history via `alembic heads`)
3. **Branching conflicts** - Detects multiple migrations with same `down_revision`

**When to run:**
- Before committing migrations: `bash scripts/check_migration_conflicts.sh`
- In CI/pre-commit hooks (recommended)
- Before deploying

**What it checks:**

**Check 1: Untracked/Modified Files**
```bash
❌ ERROR: Untracked migration files detected:
   - alembic_tenant/versions/abc123_draft_migration.py
   Untracked migrations cause DB drift. Commit them or delete drafts.
```
Untracked migrations **fail** the check (not just warn). In TruckERP, "all checks passed" means no untracked migrations — otherwise DBs can drift (migrations run in one environment but not another).

**Check 2: Multiple Heads**
```bash
✅ Platform: Exactly 1 head (linear history)
✅ Tenant: Exactly 1 head (linear history)
```

**Check 3: Branching Conflicts**
```bash
❌ CONFLICT DETECTED in tenant migrations:
   File 1: 2f5725edf9c4_add_soft_deactivate_fields_to_driver_.py
   File 2: 4b5c1a9c1d5f_add_driver_document_snapshots.py
   Both have down_revision = '9d4695445bae'
```

**How to fix conflicts:**
1. **Delete the wrong migration** (if it's a draft/mistake)
2. **Create a merge migration:** `alembic merge -m "merge heads"`
3. **Repoint one migration** to come after the other

**Note:** If Check 2 passes (1 head) but Check 3 fails (branching conflicts), it means the branches have been resolved with merge migrations. This is correct and expected. Check 3 detects historical branching points for visibility, but merge migrations have already resolved them at the Alembic level.

---

### 2. Schema Validator (`app/services/tenant_schema_validation.py`)

**Purpose:** Validates that provisioned tenant DBs have the correct schema (tables, columns).

**Validates:**
- Required tables exist: `tenants`, `people`, `person_roles`, `driver_profiles`, etc.
- Required columns exist: `person_roles.is_primary`, `person_roles.role_code`, `people.is_active`
- Legacy columns are fixed: `person_roles.role` → `role_code`
- Alembic version is recorded

**Usage in code:**
```python
from app.services.tenant_schema_validation import validate_tenant_schema_strict

# After running migrations, before marking tenant READY:
validate_tenant_schema_strict(tenant_db_url)  # Raises exception if invalid
```

**Already integrated in:** `app/services/tenant_provisioning.py` (line ~132)

**Effect:** Provisioning **fails immediately** with a clear error if schema is wrong, not later during INSERT.

---

### 3. Schema Fix Script (`scripts/fix_tenant_schema.sh`)

**Purpose:** One-time fix for existing tenant DBs with schema drift.

**Usage:**
```bash
# Fix tenant_demo database
bash scripts/fix_tenant_schema.sh tenant_demo

# Fix a different tenant database
bash scripts/fix_tenant_schema.sh tenant_acme
```

**What it fixes:**
- Adds `person_roles.is_primary` if missing
- Renames `person_roles.role` → `role_code` if legacy column exists
- Adds `people.is_active` if missing
- Validates schema after fixes

**When to use:**
- After discovering a schema mismatch error
- After resolving migration conflicts
- When migrating from an old schema version

---

## Workflow: Preventing Migration Conflicts

### Before Creating a New Migration

1. **Check current state:**
   ```bash
   bash scripts/check_migration_conflicts.sh
   ```

2. **Pull latest migrations:**
   ```bash
   git pull origin main
   ```

3. **Create your migration:**
   ```bash
   alembic -c alembic_tenant.ini revision --autogenerate -m "add feature"
   ```

4. **Check for new conflicts:**
   ```bash
   bash scripts/check_migration_conflicts.sh
   ```

5. If conflicts detected → fix before committing (see below)

---

### Resolving Detected Conflicts

**Scenario 1: Draft Migration (Not Committed)**

If you have an untracked migration that conflicts:
```bash
# Check git status
git status | grep alembic_tenant/versions

# Delete the draft migration
rm alembic_tenant/versions/abc123_draft_migration.py
```

**Scenario 2: Both Migrations Are Valid (Parallel Development)**

Create a merge migration:
```bash
# Alembic will detect the heads and create a merge
alembic -c alembic_tenant.ini merge -m "merge parallel migrations"

# This creates a new migration with:
# down_revision = ('abc123', 'def456')  # tuple of both heads
```

**Scenario 3: One Migration Should Come After the Other**

Edit the newer migration to point to the other:
```python
# In the newer migration file:
down_revision = 'abc123'  # The other migration's revision
```

---

## Current State of Conflicts

As of implementation, there are **3 existing conflicts** in the tenant migration tree:

1. `2f5725edf9c4` vs `4b5c1a9c1d5f` (both revise `9d4695445bae`)
2. `9e4f2c1b7a6d` vs `a867a473deb7` (both revise `8c84780c154b`)  
   ✅ Already resolved with merge migration `168cb4699baf`
3. `b6f6bba0c1d3` vs `c8a3d0b9c777` (both revise `5b013e5ac73d`)

**Action required:**
- Some conflicts already have merge migrations (e.g., `168cb4699baf`)
- Others may need merge migrations created
- The conflict checker will report these until merges are in place

**Important:** Existing conflicts don't break things if merge migrations exist. The checker helps prevent **new** conflicts from being introduced.

---

## Integration with CI/CD

### Pre-Commit Hook (Recommended)

Add to `.git/hooks/pre-commit`:
```bash
#!/bin/bash
set -e

echo "Checking for migration conflicts..."
bash scripts/check_migration_conflicts.sh

if git diff --cached --name-only | grep -q "alembic_.*versions.*\.py"; then
  echo "✅ Migration files changed - conflict check passed"
fi
```

### GitHub Actions

Add to `.github/workflows/ci.yml`:
```yaml
- name: Check migration conflicts
  run: bash scripts/check_migration_conflicts.sh
```

---

## Why untracked migrations fail the check (and why they’re still there)

**Why they’re still there:**  
Untracked migration files are normal files on disk that have never been `git add`’d and committed. Git doesn’t track them, so they don’t appear in `git status` as “modified” — only as “untracked”. Nothing removes them unless you commit them or delete them. So they stay in the repo directory until you act, including “next week.”

**Why we treat them as FAIL:**  
If a migration is untracked:

- It might run on your machine (Alembic sees it on disk) but not in CI or on another clone (where the file doesn’t exist).
- Or the opposite: someone else has it, you don’t — same migration tree, different schema outcomes.
- Result: **DB drift** between environments and “works on my machine” failures.

So in TruckERP, “all checks passed” means: **no untracked migration files**. Either commit them (they’re part of the product) or delete them (they’re drafts). Don’t leave migrations untracked.

---

## Troubleshooting

### "Missing is_primary column" Error During Provisioning

**Symptom:**
```
Provisioning failed: column "is_primary" of relation "person_roles" does not exist
```

**Cause:** Tenant DB was created with an old/wrong migration that didn't include the column.

**Fix:**
```bash
# Fix the schema
bash scripts/fix_tenant_schema.sh tenant_demo

# Retry provisioning
curl -X POST http://localhost:8000/api/v1/platform/tenants/2/provision
```

---

### "Schema validation failed" Error

**Symptom:**
```
SchemaValidationError: Tenant schema validation failed:
  - person_roles table missing required columns: is_primary
```

**Cause:** Schema doesn't match what the code expects (migration conflict or incomplete migration).

**Fix:**
1. Check for conflicts: `bash scripts/check_migration_conflicts.sh`
2. Fix conflicts (delete draft or create merge)
3. Fix existing tenant DB: `bash scripts/fix_tenant_schema.sh tenant_demo`
4. For new tenants: re-run provisioning after fixing migrations

---

### Conflict Checker Reports False Positives

**Symptom:** Checker reports conflicts for migrations that already have merge migrations.

**Explanation:** The checker detects all branching points, even if they're later merged. This is intentional - it helps identify all merge points in history.

**Action:** No action needed if a merge migration exists. For new conflicts, create a merge migration.

---

## Summary: Fail-Closed Design

**Before (reactive):**
- Migration conflicts discovered during INSERT
- Manual debugging to find which migration ran
- Weekly firefighting

**After (proactive):**
- ✅ Conflicts detected **when created** (CI check)
- ✅ Schema validated **during provisioning** (fail-fast)
- ✅ Clear error messages with fix instructions
- ✅ One-time fix script for existing DBs

**Result:** Build SaaS, not fix Alembic. Migration issues are caught at creation time, not in production.

---

## Files Created/Modified

**New files:**
- `scripts/check_migration_conflicts.sh` - Conflict checker
- `scripts/fix_tenant_schema.sh` - Schema fix script
- `app/services/tenant_schema_validation.py` - Schema validator
- `docs/MIGRATION_VALIDATION.md` - This documentation

**Modified files:**
- `app/services/tenant_provisioning.py` - Added schema validation after migrations

---

## Next Steps

1. ✅ Run conflict checker to see current state
2. ⚠️ Fix existing tenant DB if needed: `bash scripts/fix_tenant_schema.sh tenant_demo`
3. ✅ Add conflict checker to CI/pre-commit
4. ✅ Test provisioning - schema validation is now active
5. ⚠️ Create merge migrations for remaining conflicts (if any)

For questions or issues, see troubleshooting section above.
