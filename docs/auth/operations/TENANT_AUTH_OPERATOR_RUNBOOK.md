# Tenant auth cutover — operator runbook

Commands assume the **API container** at `/app`, secrets in `/run/secrets/truckerp.env`, and compose from `/home/admin/trucking_erp`:  
**All hosts:** `docker compose -f docker-compose.yml` only (single compose file; prod SSM under `/truckerp/prod/...`).

Replace `<tenant_id>` with the numeric `platform_tenants.id`.

---

## Cutover sequence (mandatory order)

Do **not** skip steps or flip `tenant_auth_mode` until the verify gate passes.

| Step | Action |
|------|--------|
| 1. Prepare | Run **Section 1** — `sync_tenant_auth_from_platform` for this tenant (repeat until you intend to verify). |
| 2. Verify (gate) | Run **Section 2** — `verify_tenant_auth_cutover`. **Required before any `UPDATE` on `tenant_auth_mode`.** |
| 3. Confirm readiness | Exit code `0`, **no** `VERIFY FAILED:` output, and a line ending with `verify_tenant_auth_cutover OK tenant_id=…`. If anything else, follow **Pre-flip abort** below — do not flip. |
| 4. Flip | **Section 3** — run the single-tenant platform `UPDATE … tenant_auth_mode = 'tenant'` only after step 3. |
| 5. Post-flip validation | **Section 3** smoke checks (login, `/api/v1/auth/me`, invite, forgot/reset on that host). Treat as **mandatory sign-off**, not optional curiosity. |
| 6. Rollback after a bad flip | **Section 5** (and **Section 4** if drift is suspected). |

**Pre-flip abort (verify failed):** Do **not** change `tenant_auth_mode`. Re-run **Section 1**, fix underlying data if needed, re-run **Section 2** until the gate passes. Escalate if `VERIFY FAILED` persists after a clean sync.

---

## 1. Seed / sync (platform → tenant auth)

Idempotent: aligns `tenant_users`, `tenant_workspace_members`, and `platform_tenant_user_map` from `PlatformUser` + memberships.

```bash
docker exec truckerp-api bash -lc \
  'set -a && . /run/secrets/truckerp.env && set +a && cd /app && \
   python -m app.scripts.sync_tenant_auth_from_platform --tenant-id=<tenant_id>'
```

---

## 2. Pre-cutover verify (mandatory gate before flip)

**Blocking:** Until this command exits `0` with success output below, you **must not** run any SQL that sets `tenant_auth_mode` to `tenant` for this id.

**Success criteria:**

- Exit code `0`.
- Stdout contains **no** `VERIFY FAILED:` block.
- Final success line: `verify_tenant_auth_cutover OK tenant_id=<tenant_id> members=<n>`.

If any criterion fails, stop — follow **Pre-flip abort** in the table above (re-sync, re-verify; **no flip**).

```bash
docker exec truckerp-api bash -lc \
  'set -a && . /run/secrets/truckerp.env && set +a && cd /app && \
   python -m app.scripts.verify_tenant_auth_cutover --tenant-id=<tenant_id>'
```

---

## 3. Cutover (per tenant): flip only after Section 2 passes

1. **Confirm Section 1 and Section 2** for this tenant: sync done, verify exits `0` with `verify_tenant_auth_cutover OK` and no `VERIFY FAILED`.
2. **Flip** — **platform database only**, one row — only after step 1.

   **SQL (run against platform DB, not a tenant DB):**

   ```sql
   UPDATE platform_tenants SET tenant_auth_mode = 'tenant' WHERE id = <tenant_id>;
   ```

   - **Which database:** The PostgreSQL database that holds **`platform_tenants`** and the rest of the `platform_*` control-plane schema — the same database `alembic_platform.ini` targets (**not** `tenant_<slug>` / `platform_tenants.db_name`, which is where business data lives). Overview and naming: `docs/DATABASES_PLATFORM_AND_DEMO.md` (platform database section); typical docker-compose name is `trucking_erp`, but **confirm** the final path segment of `DATABASE_URL` in `/run/secrets/truckerp.env` (that segment is the platform DB name).
   - **Sanity check:** If `\dt` shows tenant business tables as the main app surface (e.g. `people`, `loads`) and you do **not** see `platform_tenants`, you are connected to a **tenant** database — **stop**; reconnect to the platform database before running the `UPDATE`.
   - **Canonical operator execution:** Use `scripts/db_run.sh` so `POSTGRES_PASSWORD` and friends come from `/run/secrets/truckerp.env` (see `docs/secrets.md`). Example (replace `trucking_erp` if your platform DB name differs):

     ```bash
     ./scripts/db_run.sh 'PGPASSWORD="${POSTGRES_PASSWORD}" psql -h truckerp-postgres -U postgres -d trucking_erp -v ON_ERROR_STOP=1 -c "UPDATE platform_tenants SET tenant_auth_mode = '\''tenant'\'' WHERE id = <tenant_id>;"'
     ```

   - **Do not** run this `UPDATE` without a green **Section 2** — raw SQL does not replace the verify gate.

3. **API restart after flip:** In this codebase, `tenant_auth_mode` is loaded from the platform DB on each request (request-scoped DB session in tenant middleware and auth; **no documented in-process cache** of the mode). **Correctness:** the new mode can apply on the **next** request without restarting. **Operator rule:** if you are unsure about extra layers (custom proxies, older notes that assumed caching, or multi-replica edge cases outside this repo), **restart `truckerp-api` once** after the `UPDATE`. **Safe default:** always restart after flip.

   ```bash
   cd /home/admin/trucking_erp && docker compose -f docker-compose.yml restart truckerp-api
   ```

   (Or your standard reload, e.g. `scripts/reload_api.sh` where that exists for your stack.)

4. **Post-flip validation (mandatory):** on that workspace host, confirm login, token refresh, `GET /api/v1/auth/me`, invite flow, and forgot/reset behave as expected. Record failures and roll back (**Section 5**) if auth is broken.

---

## 4. Reconcile before rollback (trust restore)

If dual-write failed or drift is suspected **before** switching back to platform auth:

```bash
docker exec truckerp-api bash -lc \
  'set -a && . /run/secrets/truckerp.env && set +a && cd /app && \
   python -m app.scripts.reconcile_tenant_auth_before_rollback --tenant-id=<tenant_id>'
```

Exits non-zero if verify still fails after sync — **do not** trust rollback until errors are cleared.

---

## 5. Rollback (to platform auth)

1. Run **Section 4** until exit `0` when any drift was possible.
2. Set `tenant_auth_mode = 'platform'` for that tenant only — **same platform database** as in Section 3 (not a tenant DB).
3. Require users to **sign in again** (tokens issued in tenant mode use `tenant_users.id` as `sub`).
4. Confirm platform passwords/session versions match expectations (sync in step 1 copies from platform into tenant; after failed dual-write, reconcile fixes tenant from platform).

---

## Related

- Platform vs tenant DB names and roles: `docs/DATABASES_PLATFORM_AND_DEMO.md`
- Tenant DB migrations: `bash scripts/tenant_upgrade_head.sh` (container, see `.cursor/rules/tenant-migrations.mdc`).
- READY repair: a later `provision_tenant_db` call on an already **READY** tenant runs a full idempotent member sync (see `app/services/tenant_provisioning.py`).

## Automated tests (optional)

- **Canonical login smoke** (login hardening + admin unlock — keep small; see `.cursor/rules/login-smoke-suite-canonical.mdc`):

  ```bash
  docker exec truckerp-api bash -lc 'set -a && . /run/secrets/truckerp.env && set +a && cd /app && python -m pytest tests/test_login_hardening_smoke.py tests/test_admin_sign_in_unlock_smoke.py -q'
  ```

  If the container does not bind-mount the repo, copy those two files under `/app/tests/` before running.

- **Invite E2E** (`tests/test_tenant_invite_accept_e2e.py`): set `RUN_INVITE_E2E=1` and `INVITE_E2E_*`; tests remove synthetic `invited_*` / `invited_t_*` users afterward.
- **Drift E2E** (`tests/test_tenant_auth_cutover_drift_e2e.py`): set `RUN_DRIFT_CUTOVER_E2E=1` and `DRIFT_E2E_TENANT_ID`; temporarily corrupts `session_version` on a mapped `tenant_user`, asserts verify fails, then restores.
