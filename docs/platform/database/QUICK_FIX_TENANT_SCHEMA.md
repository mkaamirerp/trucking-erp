# Quick Fix: Tenant Schema Issues

## Current Error

```
Provisioning failed: column "is_primary" of relation "person_roles" does not exist
```

## One-Line Fix

```bash
bash scripts/fix_tenant_schema.sh tenant_demo
```

Replace `tenant_demo` with your actual tenant database name.

---

## What This Does

1. ✅ Checks if `is_primary` column exists in `person_roles`
2. ✅ Adds it if missing (`ALTER TABLE` with `DEFAULT false`)
3. ✅ Renames legacy `role` → `role_code` if needed
4. ✅ Adds `people.is_active` if missing
5. ✅ Validates final schema

---

## After Running the Fix

**Test provisioning:**
```bash
# Via API
curl -X POST http://your-domain/api/v1/platform/tenants/2/provision

# Or retry the operation that failed
```

**Expected:** Provisioning succeeds without schema errors.

---

## Prevent Future Issues

The permanent migration validation system is now active:

**For developers:**
```bash
# Before committing migrations, run:
bash scripts/check_migration_conflicts.sh
```

**For CI/CD:**
Add the conflict checker to your CI pipeline (see `docs/MIGRATION_VALIDATION.md`).

**Automatic validation:**
Schema validation now runs automatically during tenant provisioning. If migrations are out of sync, you'll get a clear error message immediately, not during INSERT.

---

## Need More Help?

See full documentation: `docs/MIGRATION_VALIDATION.md`
