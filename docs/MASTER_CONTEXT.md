# 🚛 TRUCKERP — MASTER CONTEXT (AUTHORITATIVE)

Paste this first when opening a new Cursor agent. Say: "You are operating under MASTER_CONTEXT. Confirm understanding before making changes."

---

## 1️⃣ Project Overview

TruckERP is a multi-tenant SaaS system with strict separation:

### Platform Layer (Control Plane)

- **Database:** `trucking_erp`
- **Contains:** `platform_users`, `platform_tenants`, `platform_tenant_members`, `platform_subscriptions`, OTP tables, signup tables, security events, plans, audit logs.
- **Platform DB NEVER contains business data.**

### Tenant Layer (Business Plane)

- Each tenant has its own database (e.g. `tenant_demo`, `tenant_<slug>`).
- **Contains:** people, drivers, loads, fleet, payroll, dispatch, etc.
- **Tenant routes MUST use `get_tenant_db`.**
- **Platform routes MUST use `get_db`.**
- Cross-tenant leakage is unacceptable.

---

## 2️⃣ Auth Architecture (Current Official Behavior)

### Platform Users Table

- **Table:** `platform_users`
- **Columns:** `id` (UUID), `email`, `password_hash`, `is_email_verified`, `status`, `session_version`, `password_reset_token_hash`, `password_reset_token_expires_at`

### Login Rules

- Email + password login **REQUIRED**.
- `password_hash` must exist for password login.
- If `password_hash` is NULL: return "Password not set. Use reset password."
- Never silently fail.

### Signup Rules

- In `public_signup.py`: If payload contains password, must store `hash_password(password)`.
- If OTP-only mode: `password_hash` may be NULL.
- **NEVER overwrite existing `password_hash` with None.**

### Forgot Password Rules

- `/api/v1/auth/forgot-password` must return **200** (never 410).
- If email exists: generate token, store hashed token, set expiry.
- Always generic response.

### Reset Password Rules

- Verify token hash + expiry.
- Set new `password_hash`.
- Increment `session_version`.
- Clear reset token fields.

---

## 3️⃣ Tenant Resolution Rules

- Tenant is resolved via: **subdomain** (e.g. `demo.truckerp.me`) **OR** required header.
- If tenant cannot resolve: return **403**, log: `tenant_context outcome=resolve_error`.
- Never modify tenant middleware unless explicitly required.

---

## 4️⃣ Docker and Deployment Discipline (CRITICAL)

This project **does NOT** auto-reload code.

After **ANY** backend code change:

```bash
cd /home/admin/trucking_erp
docker compose -f docker-compose.yml -f docker-compose.dev.yml build truckerp-api
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d truckerp-api
docker logs --tail 50 truckerp-api
```

Or one command: `./scripts/reload_api.sh`

**No restart = old code still running.** This is mandatory. Always use both compose files (`-f docker-compose.yml -f docker-compose.dev.yml`).

---

## 5️⃣ Tenant Migration Execution Doctrine (Cursor-proof)

### Problem we hit (2026-02-26)

Cursor delivered code + alembic tenant migration for:

- document_requirements
- person_application_requests
- request_id column on person_application_files

…but migration was **NOT** executed because `ALEMBIC_TENANT_DATABASE_URL` was not available in the Cursor environment (missing DB password/secrets). This caused runtime 500s when app code expected tables/columns that did not exist in `tenant_demo`.

### Locked Rules (must follow every time)

1. **No one may say "applied" unless migration was actually run on the target tenant DB** and proof is captured.
2. **Tenant migrations REQUIRE `ALEMBIC_TENANT_DATABASE_URL`.**
   - If it's missing, stop and report **"MIGRATION NOT RUN"**.
3. **Environment of truth** (dev/prod):
   - Secrets are sourced from `/run/secrets/truckerp.env` (rendered from SSM).
   - Any shell running alembic **MUST** explicitly `source` this file in the same command.
4. **Proof required** after running tenant migration:
   - `alembic current` against tenant DB
   - `\d+` for new/modified tables
   - head count = 1 (no multiple heads)

### One-command Preflight (must run before any tenant migration)

```bash
docker exec truckerp-api sh -lc 'grep -E "^(ALEMBIC_TENANT_DATABASE_URL|TENANT_DATABASE_URL|DATABASE_URL)=" /run/secrets/truckerp.env || true'
```

### One-command Tenant Migration Run (standard)

```bash
docker exec truckerp-api sh -lc 'set -a && . /run/secrets/truckerp.env && set +a && cd /app && alembic -c alembic_tenant.ini upgrade head'
```

### Required Post-Run Proof Commands (tenant_demo example)

```bash
docker exec truckerp-api sh -lc 'set -a && . /run/secrets/truckerp.env && set +a && cd /app && alembic -c alembic_tenant.ini current'
docker exec truckerp-postgres psql -U postgres -d tenant_demo -c "\d+ document_requirements"
docker exec truckerp-postgres psql -U postgres -d tenant_demo -c "\d+ person_application_requests"
docker exec truckerp-postgres psql -U postgres -d tenant_demo -c "\d+ person_application_files"
```

### Reporting format (mandatory)

Any Cursor **"implementation complete"** message **MUST** include:

- ✅ code changes list
- ✅ migration revision id
- ✅ **"MIGRATION RUN: YES/NO"**
  - If **YES:** include post-run proof outputs (or paste key lines)
  - If **NO:** state exactly what's missing (usually `ALEMBIC_TENANT_DATABASE_URL`) and stop

**Why this fixes it permanently:** This turns the failure mode into a **process gate**: if secrets aren't present → nobody proceeds pretending it's applied; if migration ran → proof is always collected and copy-pastable.

---

## 6️⃣ Known Historical Failure (DO NOT REPEAT)

- **Issue:** Signup created `platform_users.password_hash=None`; forgot-password returned 410.
- **Result:** User locked out permanently. Manual DB hash insertion required to regain access.
- This must **NEVER** happen again.

---

## 7️⃣ Non-Negotiable Rules

- **Before touching auth/signup:** Read `.cursor/rules/alembic-platform-tenant-config.mdc` and auth/signup rules in `.cursor/rules`. Confirm behavior against this MASTER_CONTEXT.
- **After changes:** Restart container, run curl acceptance tests, paste output.
- No assumptions.

---

## 8️⃣ Acceptance Gate Template (Always Run)

- **Tenant OK:**  
  `curl -i https://demo.truckerp.me/api/v1/public/tenant/demo`

- **Login OK:**  
  `curl -i https://demo.truckerp.me/api/v1/auth/login -H 'Content-Type: application/json' --data '{"email":"...","password":"..."}'`

- **Forgot password OK:**  
  `curl -i https://demo.truckerp.me/api/v1/auth/forgot-password -H 'Content-Type: application/json' --data '{"email":"..."}'`

- Reset then login again: expect 200.

---

## 9️⃣ Engineering Philosophy

- Platform DB = identity + control. Tenant DB = business data.
- No cross-tenant writes.
- No overwriting `password_hash` with None.
- No silent auth behavior changes.
- Restart after every backend change.
- Proof via curl before declaring success.

---

## How You Use This

When opening a new Cursor agent:

1. Paste this file first (or open `docs/MASTER_CONTEXT.md` or `.cursor/context/master_context.mdc`).
2. Say: "You are operating under MASTER_CONTEXT. Confirm understanding before making changes."
3. If the agent cannot summarize it correctly, do not proceed.
