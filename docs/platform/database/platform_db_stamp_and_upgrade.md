# Platform DB: Stamp and upgrade (container)

Use these steps when the platform DB’s Alembic revision is out of sync (e.g. missing columns like `status`, `superseded_at`, `public_id`) or the cleanup script fails with schema errors.

**In this project the platform DB uses `alembic_platform.ini` and `alembic_platform/versions/`** — not `alembic.ini` or `alembic/versions/`.

---

## ⚠️ Do not stamp forward to the latest revision

**Do NOT stamp to 0017 or 0018** (or any newer revision) unless you are **100% sure** the DB schema already has every change up to that revision. Stamping forward tells Alembic “you’re already at 0018,” so it will **skip** running 0017 and 0018. If those migrations were never applied, columns like `status`, `superseded_at`, `public_id` will stay missing and the app/cleanup script will fail.

**Safe approach:** Find the **last revision the DB schema actually matches** (often 0014 or earlier), stamp to **that** revision (or `base`), then run **`alembic upgrade head`** so all missing migrations run for real.

---

## Step 1 – See what revision the DB thinks it’s at

```bash
docker exec truckerp-api sh -lc 'set -a && . /run/secrets/truckerp.env && set +a && cd /app && alembic -c alembic_platform.ini current'
```

Note the revision ID (or “empty” if no revision).

---

## Step 2 – Find the revision the DB schema actually matches

Inspect the platform DB (e.g. with `psql` or a DB tool) and compare to what each migration adds. For example:

- **0016** – `platform_onboarding_payloads.tenant_id` nullable  
- **0017** – `platform_otp_tokens`: `onboarding_payload_id`, `superseded_at`; `platform_onboarding_payloads`: `status`, `updated_at`  
- **0018** – `platform_onboarding_payloads.public_id`

If `platform_onboarding_payloads` has no `status` or `public_id`, the DB is at most **0015** (or earlier). If it has `status` but no `public_id`, it matches **0017**, etc. Pick the **latest revision whose changes are all present** in the DB.

When in doubt, stamp to an **older** revision (e.g. **0014** or **0015**) or **`base`**; then `upgrade head` will apply everything from there and is safe.

---

## Step 3 – List platform migration files and revision IDs (optional)

```bash
docker exec truckerp-api sh -lc 'ls -la /app/alembic_platform/versions'
docker exec truckerp-api sh -lc 'grep -h "^revision" /app/alembic_platform/versions/*.py'
```

Use this to confirm the revision ID string you’ll use for stamping (e.g. `0014_tenant_memberships`, `0015_password_reset`).

---

## Step 4 – Stamp the DB to the revision it actually matches

Set the revision pointer to the one you identified in Step 2. Use the **revision ID** (the string value), not the filename. If the DB has never been migrated or you’re unsure, use **`base`**.

```bash
docker exec truckerp-api sh -lc 'set -a && . /run/secrets/truckerp.env && set +a && cd /app && alembic -c alembic_platform.ini stamp <revision_id>'
```

Examples:

```bash
# If the DB matches up to 0014 (no 0015+ changes):
alembic -c alembic_platform.ini stamp 0014_tenant_memberships

# If the DB matches nothing / you want to start from scratch:
alembic -c alembic_platform.ini stamp base
```

**Do not** use `0017_otp_signup_refinements` or `0018_onboarding_public_id_uuid` here unless the schema already has all columns those migrations add.

---

## Step 5 – Apply all missing migrations (for real)

```bash
docker exec truckerp-api sh -lc 'set -a && . /run/secrets/truckerp.env && set +a && cd /app && alembic -c alembic_platform.ini upgrade head'
```

This runs every migration after the stamped revision and actually creates/alters columns.

---

## Step 6 – Verify current revision

```bash
docker exec truckerp-api sh -lc 'set -a && . /run/secrets/truckerp.env && set +a && cd /app && alembic -c alembic_platform.ini current'
```

You should see the head (e.g. `0018_onboarding_public_id_uuid`).

---

## Step 7 – Run cleanup script (dry run)

```bash
docker exec truckerp-api sh -lc 'set -a && . /run/secrets/truckerp.env && set +a && cd /app && python -m app.scripts.cleanup_onboarding'
```

Or use the wrapper:

```bash
./scripts/cleanup_onboarding.sh
```

The script should run without “missing column” errors once the platform schema is up to date.

---

## Notes

- **Config**: Platform = `alembic_platform.ini` and `alembic_platform/versions/`. Tenant DB uses `alembic_tenant.ini` and `alembic_tenant/versions/`.
- **Stamp** only to a revision the DB **already matches**. Then **upgrade head** to apply the rest. Stamping forward to a revision you haven’t applied leaves the schema behind and causes missing-column issues.
- To roll back the revision pointer (rare):  
  `alembic -c alembic_platform.ini stamp <older_revision_id>`
