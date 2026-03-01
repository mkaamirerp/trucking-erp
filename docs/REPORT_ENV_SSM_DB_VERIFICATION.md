# ENV + SSM + DB Naming Verification Report (Dev vs Prod)

**Date:** 2026-02-26  
**Host:** This host (EC2 dev or local).  
**Stop rule:** No claims without command outputs; passwords redacted (`:****@`).

---

## A) Environment and compose in use

### Compose files

- **Base:** `docker-compose.yml` (prod-style: API command = `start_api_with_ssm.sh`, tmpfs `/run/secrets`, no env_file).
- **Override in use:** `docker-compose.dev.yml` (dev overrides: ports 8000, TOOLS_DEV_*, bind mount `.:/app`).
- **Effective command:** `docker compose -f docker-compose.yml -f docker-compose.dev.yml` → API still runs **`/app/scripts/start_api_with_ssm.sh`** (dev override does not change the command).

**Evidence (script and SSM paths):**

```text
# scripts/start_api_with_ssm.sh (lines 41–44)
if {
  fetch_path "/truckerp/prod/platform/"
  fetch_path "/truckerp/prod/shared/"
} 2>/dev/null | awk ... | sort > "$SECRETS_FILE"
```

**Conclusion A:** On this host we are running with **dev override** (ports, volume) but **prod SSM paths**: `/truckerp/prod/platform/` and `/truckerp/prod/shared/`. The API is started by `start_api_with_ssm.sh`; secrets come only from SSM (no .env).

---

## B) SSM inventory (redacted)

Commands run (password portion between `:` and `@` replaced with `****`):

| Parameter | Command / result |
|-----------|------------------|
| `/truckerp/prod/platform/DATABASE_URL` | `aws ssm get-parameter --name "/truckerp/prod/platform/DATABASE_URL" --with-decryption ...` |
| `/truckerp/prod/platform/POSTGRES_ADMIN_URL` | `aws ssm get-parameter ... POSTGRES_ADMIN_URL ...` |
| `/truckerp/prod/platform/TENANT_DATABASE_URL` | `aws ssm get-parameter ... TENANT_DATABASE_URL ...` |
| `/truckerp/prod/shared/JWT_SECRET` | Existence + length only (value not printed). |

**Outputs (redacted):**

```text
/truckerp/prod/platform/DATABASE_URL
  postgresql+asyncpg://postgres:****@truckerp-postgres:5432/trucking_erp

/truckerp/prod/platform/POSTGRES_ADMIN_URL
  postgresql+asyncpg://postgres:****@truckerp-postgres:5432/postgres

/truckerp/prod/platform/TENANT_DATABASE_URL
  postgresql+asyncpg://postgres:****@truckerp-postgres:5432/truckerp

/truckerp/prod/shared/JWT_SECRET
  present (length 86)
```

**Dev path check:**

```text
$ aws ssm get-parameters-by-path --path "/truckerp/dev" --recursive --region us-east-1
{
    "Parameters": []
}
```

**Conclusion B:** SSM has **prod** params only. `TENANT_DATABASE_URL` in SSM points at DB name **`truckerp`**. No parameters under `/truckerp/dev/`.

---

## C) Runtime env file (container)

```text
$ docker exec truckerp-api sh -lc 'grep DATABASE_URL /run/secrets/truckerp.env'
ASYNC_DATABASE_URL=postgresql+asyncpg://postgres:****@truckerp-postgres:5432/trucking_erp
DATABASE_URL=postgresql+asyncpg://postgres:****@truckerp-postgres:5432/trucking_erp
TENANT_DATABASE_URL=postgresql+asyncpg://postgres:****@truckerp-postgres:5432/truckerp
ALEMBIC_TENANT_DATABASE_URL=postgresql+asyncpg://postgres:****@truckerp-postgres:5432/truckerp
```

**Conclusion C:** Runtime env is exactly what SSM provides (plus script-derived `ALEMBIC_TENANT_DATABASE_URL`). Both tenant vars point at database **`truckerp`**.

---

## D) Postgres DB reality

```text
$ docker exec truckerp-postgres psql -U postgres -d postgres -c '\l'

                                                  List of databases
     Name     |  Owner   | Encoding |  Collate   |   Ctype    | ...
--------------+----------+----------+------------+------------+----
 postgres     | postgres | UTF8     | en_US.utf8 | en_US.utf8 |
 template0    | postgres | UTF8     | en_US.utf8 | en_US.utf8 |
 template1    | postgres | UTF8     | en_US.utf8 | en_US.utf8 |
 tenant_demo  | postgres | UTF8     | en_US.utf8 | en_US.utf8 |
 trucking_erp | postgres | UTF8     | en_US.utf8 | en_US.utf8 |
(5 rows)
```

- **tenant_demo:** exists.  
- **truckerp:** does **not** exist.  
- **trucking_erp:** exists (platform DB).

**Conclusion D:** On this host, the tenant DB that exists is **tenant_demo**. SSM’s `TENANT_DATABASE_URL`/`ALEMBIC_TENANT_DATABASE_URL` point at **truckerp**, which does not exist here, so tenant migrations fail with “database truckerp does not exist”.

---

## E) Conclusion and recommendation

### 1) Why does TENANT_DATABASE_URL point at “truckerp” in env?

- **SSM** stores `/truckerp/prod/platform/TENANT_DATABASE_URL` with value `.../truckerp` (prod convention: one “default” tenant DB named `truckerp` in prod).
- **Script behavior:** The script no longer strips `TENANT_DATABASE_URL`; it writes whatever it gets from SSM and then sets `ALEMBIC_TENANT_DATABASE_URL=$turl`.
- So the env reflects **SSM**, not a script bug. On this host we use **prod SSM paths** but a **dev Postgres** where the real tenant DB is **tenant_demo**, not **truckerp**.

### 2) Correct approach for our architecture

- **Runtime tenant routing:** Uses `platform_tenants.db_name` (registry); the app does **not** need `TENANT_DATABASE_URL` for per-request tenant DB selection.
- **Tenant migrations:** Require **one** tenant DB URL for `alembic -c alembic_tenant.ini upgrade head`. That URL must be **an existing DB on the host** (e.g. `tenant_demo` on this dev host, or `truckerp` where that DB exists).

So: keep registry-driven routing as-is; fix **only** how we get **ALEMBIC_TENANT_DATABASE_URL** (and optionally TENANT_DATABASE_URL) for the environment we’re actually running in (dev vs prod).

### 3) “Solve forever” fix (explicit)

**Option 1 – Dev SSM path with tenant_demo**

- Create `/truckerp/dev/platform/` (and optionally `/truckerp/dev/shared/`) in SSM with dev values.
- In dev, set **TENANT_DATABASE_URL** (and thus ALEMBIC_TENANT_DATABASE_URL) to `.../tenant_demo` under `/truckerp/dev/`.
- Change **start_api_with_ssm.sh** (or dev compose) so that when running in dev it uses **SSM path** `/truckerp/dev/...` instead of `/truckerp/prod/...` (e.g. via `SSM_PATH_PREFIX=/truckerp/dev` or `SSM_ENV=dev` that the script reads and chooses the path). No manual sed; one env var to switch.

**Option 2 – Explicit dev override (no new SSM path)**

- Keep using **prod** SSM paths.
- Add a **dev-only** override: if e.g. `TRUCKERP_DEV_TENANT_DB=tenant_demo` is set (in dev compose or env), then after writing `truckerp.env` from SSM, the script **rewrites** only the tenant URL line(s) to use that DB name (same host/user/password as in SSM, only DB name replaced). So `ALEMBIC_TENANT_DATABASE_URL` (and optionally `TENANT_DATABASE_URL`) end up pointing at `tenant_demo` on this host without creating `/truckerp/dev/` in SSM.

**Recommendation**

- **Option 1** is cleaner long-term (dev and prod fully separated in SSM; same script, different path).
- **Option 2** is minimal change (no new SSM params; one env var in dev compose to force tenant DB name for this host).

Implement either one so that on this host `ALEMBIC_TENANT_DATABASE_URL` resolves to `.../tenant_demo` and tenant migrations can run without changing prod SSM.

---

**Evidence summary**

| Check | Result |
|-------|--------|
| Compose in use | docker-compose.yml + docker-compose.dev.yml |
| API started by | start_api_with_ssm.sh |
| SSM paths fetched | /truckerp/prod/platform/, /truckerp/prod/shared/ |
| SSM TENANT_DATABASE_URL | .../truckerp (redacted) |
| Runtime TENANT_DATABASE_URL | .../truckerp (redacted) |
| Runtime ALEMBIC_TENANT_DATABASE_URL | .../truckerp (redacted) |
| DBs on host | postgres, template0, template1, **tenant_demo**, **trucking_erp** |
| DB “truckerp” | Does not exist |
| /truckerp/dev/* | Parameters: [] |
