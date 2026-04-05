# ANCHOR POINT — Multi-role onboarding MVP foundation complete

> **Document type:** Point-in-time milestone / historical snapshot — **not** the canonical production operator runbook.  
> **Tenant migrations (operators):** use `scripts/tenant_upgrade_head.sh` with `ALEMBIC_TENANT_DATABASE_URL` (see `docs/secrets.md`).  
> **Rollback** commands below use raw `alembic -c alembic_tenant.ini downgrade` for **emergency / dev replay of this anchor** — not routine prod operations.

**Date:** 2026-03-03  
**State:** Locked after verification

**Working note (memory):** Multi-role onboarding MVP foundation complete. application_type drives workflow; requested_role_code drives approval role; DriverProfile only for DRIVER; non-driver intake is minimal; naming refactor deferred.

---

## Architecture summary

- **application_type** drives workflow/form selection (which form the applicant sees)
- **requested_role_code** drives approval role assignment (PersonRole.role_code)
- **DriverProfile** created only when `requested_role_code == "DRIVER"`
- Non-driver applications use minimal common intake (name, contact, address)
- Legacy driver-heavy naming remains but is non-blocking

---

## Migrations applied (verified)

| Revision | File | down_revision |
|----------|------|---------------|
| `d4e5f6a7b8c9` | `d4e5f6a7b8c9_add_application_type_to_person_applications.py` | `b1c2d3e4f5a6` |
| `e5f6a7b8c9d0` | `e5f6a7b8c9d0_add_requested_role_code_to_person_applications.py` | `d4e5f6a7b8c9` |

---

## Rollback (verified down_revisions)

**Historical / dev rollback only** — bypasses `tenant_upgrade_head.sh` preflight; do not treat as standard operator upgrades.

To remove `requested_role_code` only:

```bash
docker exec truckerp-api bash -lc 'set -a && . /run/secrets/truckerp.env && set +a && cd /app && alembic -c alembic_tenant.ini downgrade d4e5f6a7b8c9'
```

To remove both `application_type` and `requested_role_code`:

```bash
docker exec truckerp-api bash -lc 'set -a && . /run/secrets/truckerp.env && set +a && cd /app && alembic -c alembic_tenant.ini downgrade b1c2d3e4f5a6'
```

---

## Manual test checklist (run before further changes)

Run: `ADMIN_EMAIL=<your-admin> ADMIN_PASSWORD=<...> ./tools/manual_test_multi_role_onboarding.sh`

Then verify DB: `APP_DRIVER_ID=<id1> APP_DISP_ID=<id2> ./tools/verify_multi_role_db.sh`

1. **Invite rows** — person_applications stores both `application_type` and `requested_role_code`
2. **DRIVER approval** — PersonRole(DRIVER) + DriverProfile created
3. **DISPATCHER approval** — PersonRole(DISPATCHER), no DriverProfile

---

## Next steps (when revisited)

- Do not refactor names yet
- Run manual tests and confirm DB outcomes before further changes
- See `docs/ONBOARDING_MULTI_ROLE_IMPLEMENTATION_PLAN.md` for future phases
