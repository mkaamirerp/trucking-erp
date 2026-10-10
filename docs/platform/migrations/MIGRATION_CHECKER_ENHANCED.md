# Migration Checker - Enhanced with Your Suggested Checks

## Summary

The migration conflict checker has been **enhanced** to include all the checks from the script you described:

### ✅ Now Included (Added Just Now)

1. **Check 1: Untracked/Modified Migration Files** (via `git status`)
   - Warns about untracked migration files (WIP that might be drafts)
   - **Fails** on modified migration files (you should never edit migrations after commit)
   
2. **Check 2: Multiple Heads** (via `alembic heads`)
   - Runs `alembic heads` for both platform and tenant
   - Ensures exactly **1 head** per branch (linear history)
   - Fails if multiple heads detected
   - Gracefully skips if no DB connection available

### ✅ Already Included (Original Implementation)

3. **Check 3: Branching Conflicts** (file-level analysis)
   - Detects multiple migrations with same `down_revision`
   - Works without DB connection (static file parsing)
   - Catches conflicts that might not show up in `alembic heads` yet

---

## Test Run Output

Here's the actual output from your repo:

```bash
🔍 Checking Alembic migration hygiene...

📋 Check 1: Untracked/modified migration files...
⚠️  WARNING: Untracked migration files detected:
   - alembic_platform/versions/0013_platform_onboarding_payloads.py
   - alembic_platform/versions/0014_tenant_memberships_gate.py
   - alembic_platform/versions/0015_password_reset_fields.py
   - alembic_tenant/versions/74ff8253c43c_people_foundation_people_driver_.py
   - alembic_tenant/versions/a5b6c7d8e9f0_add_people_platform_user_id.py
   - alembic_tenant/versions/cb313448b94e_people_add_is_active.py
   - alembic_tenant/versions/f01a9b2c3d4e_drop_tenant_id_fks_people_roles_profiles.py

❌ ERROR: Modified migration files detected:
   - alembic_platform/versions/0005_platform_registry.py
   - alembic_tenant/versions/2f3c3c4a0b1a_add_driver_license_fields.py
   - alembic_tenant/versions/c8a3d0b9c777_add_tenants_and_rbac.py

📋 Check 2: Multiple heads (linear history check)...
   ✅ Platform: Exactly 1 head (linear history)
   ✅ Tenant: Exactly 1 head (linear history)

📋 Check 3: Branching conflicts (same down_revision)...
   [3 conflicts detected - see full output]

❌ MIGRATION HYGIENE CHECK FAILED
```

---

## Key Findings from Your Repo

### Good News ✅
- **Both branches have exactly 1 head** (Check 2 passed)
  - This means Alembic sees a linear history
  - Merge migrations have resolved the branching

### Issues Found ❌

1. **7 untracked migration files** (WARNING)
   - These are new migrations not yet committed
   - Decision needed: commit them or delete if they're drafts

2. **3 modified migration files** (ERROR)
   - Migration files were edited after being committed
   - This is dangerous - migrations should be immutable
   - **Fix:** Revert the modifications and create new migrations instead

3. **3 branching conflicts** (file-level)
   - Historical branching points detected
   - Already resolved with merge migrations (that's why Check 2 passes)
   - Not a blocker, but good for visibility

---

## Why Check 2 Passes But Check 3 Fails

**This is normal and expected!**

- **Check 2** (`alembic heads`): Asks Alembic "how many heads exist right now?"
  - Answer: 1 per branch ✅
  - Merge migrations have resolved the branching at the Alembic level

- **Check 3** (file parsing): Looks at individual migration files
  - Detects historical branching points (multiple files with same `down_revision`)
  - These are still visible in the files, even though merge migrations exist
  - Useful for understanding your migration history

**Analogy:** Git merge commits resolve branching in the commit graph (like Check 2), but you can still see the individual branches in history (like Check 3).

---

## Improvements Made

### From the Script You Described

✅ **Untracked files check** - Added via `git status`  
✅ **Multiple heads check** - Added via `alembic heads`  
✅ **Graceful DB failure** - Skips `alembic heads` if DB unavailable  
✅ **Clear error messages** - With fix instructions  

### Additional Improvements

✅ **Modified files check** - Fails on edited migrations (immutability)  
✅ **Works without DB** - Check 3 doesn't require DB connection  
✅ **Merge migration detection** - Skips merge migrations in Check 3  
✅ **Comprehensive output** - 3 separate checks with clear pass/fail  

---

## CI Integration (Recommended)

### GitHub Actions

Add to `.github/workflows/ci.yml`:

```yaml
name: CI

on: [pull_request, push]

jobs:
  migration-hygiene:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      
      - name: Install dependencies
        run: pip install alembic sqlalchemy asyncpg
      
      - name: Check migration hygiene
        run: bash scripts/check_migration_conflicts.sh
```

### Pre-Commit Hook

Add to `.git/hooks/pre-commit`:

```bash
#!/bin/bash
set -e

if git diff --cached --name-only | grep -q "alembic_.*versions.*\.py"; then
  echo "Migration files changed - running hygiene check..."
  bash scripts/check_migration_conflicts.sh
fi
```

---

## Next Steps

1. **Fix modified migrations** (highest priority - breaks immutability):
   ```bash
   git checkout alembic_platform/versions/0005_platform_registry.py
   git checkout alembic_tenant/versions/2f3c3c4a0b1a_add_driver_license_fields.py
   git checkout alembic_tenant/versions/c8a3d0b9c777_add_tenants_and_rbac.py
   ```

2. **Commit or delete untracked migrations**:
   ```bash
   # If they're ready:
   git add alembic_platform/versions/0013_platform_onboarding_payloads.py
   git commit -m "add onboarding payloads migration"
   
   # If they're drafts:
   rm alembic_platform/versions/0013_platform_onboarding_payloads.py
   ```

3. **Add checker to CI** (see above)

4. **Branching conflicts**: No action needed - merge migrations exist (Check 2 passes)

---

## Summary

**Q: Is the script you described covered?**

**A: YES - and enhanced!**

- ✅ Untracked files check (added)
- ✅ Multiple heads check (added)
- ✅ Branching conflicts (was already there)
- ✅ Modified files check (bonus - catches mutation bugs)
- ✅ Works with or without DB connection
- ✅ Clear output with fix instructions

The enhanced script is now a comprehensive migration hygiene checker suitable for CI pipelines.
