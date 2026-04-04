# Tenant auth cutover — operator runbook

Commands assume the **API container** at `/app`, secrets in `/run/secrets/truckerp.env`, and compose from `/home/admin/trucking_erp`:  
`docker compose -f docker-compose.yml` (standard deployment). Optional local iteration may use `-f docker-compose.dev.yml` in addition—see `docker-compose.dev.yml`.

Replace `<tenant_id>` with the numeric `platform_tenants.id`.

---

## 1. Seed / sync (platform → tenant auth)

Idempotent: aligns `tenant_users`, `tenant_workspace_members`, and `platform_tenant_user_map` from `PlatformUser` + memberships.

```bash
docker exec truckerp-api bash -lc \
  'set -a && . /run/secrets/truckerp.env && set +a && cd /app && \
   python -m app.scripts.sync_tenant_auth_from_platform --tenant-id=<tenant_id>'
```

---

## 2. Pre-cutover verify

Must print **no** `VERIFY FAILED` lines and exit `0`.

```bash
docker exec truckerp-api bash -lc \
  'set -a && . /run/secrets/truckerp.env && set +a && cd /app && \
   python -m app.scripts.verify_tenant_auth_cutover --tenant-id=<tenant_id>'
```

---

## 3. Cutover (per tenant)

1. Complete steps **1** and **2** successfully for this tenant.
2. Set auth mode on **platform DB** only (one tenant):

   - `UPDATE platform_tenants SET tenant_auth_mode = 'tenant' WHERE id = <tenant_id>;`  
     (or equivalent via your admin SQL / migration tool.)

3. Restart API if your stack caches tenant metadata (optional; depends on deployment).

4. Smoke: login, refresh, `/api/v1/auth/me`, invite, forgot/reset on that workspace host.

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

1. Run **4** until exit `0` when any drift was possible.
2. Set `tenant_auth_mode = 'platform'` for that tenant only.
3. Require users to **sign in again** (tokens issued in tenant mode use `tenant_users.id` as `sub`).
4. Confirm platform passwords/session versions match expectations (sync in step 1 copies from platform into tenant; after failed dual-write, reconcile fixes tenant from platform).

---

## Related

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
