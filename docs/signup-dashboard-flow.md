# Signup → Dashboard Flow (Canonical)

## Key invariants

1. **TenantStatus enum** (`app/models/platform.py`) must include all values referenced in code: `PENDING`, `PENDING_SETUP`, `PROVISIONING`, `ACTIVE`, `SUSPENDED`. Do not reference enum values that don't exist.

2. **Tenant resolution (single-source-of-truth)** – Middleware resolves tenant via `_resolve_tenant_from_request()` in order: host/subdomain (authoritative for browser) → X-Tenant-Slug / X-Tenant-ID headers (match or override) → JWT tenant_id (fallback for internal). Readiness enforcement comes from route dependencies (`get_tenant_db`, `require_active_tenant`) and explicit handler checks, not middleware.

3. **Me endpoints**
   - `GET /api/v1/auth/me` – Canonical for session validation. Uses `get_current_user` (JWT + DB load). Used by `sessionCheck.ts` (AuthContext).
   - `GET /api/v1/me` – Uses `require_tenant` + headers. Used by `useMe` with `fetchWithTenant` (adds X-Tenant-Slug from host). Both work when JWT populates `request.state`.

4. **Company setup route** – Canonical path: `POST /api/v1/public/company-setup`. Prefill: `GET /api/v1/public/company-setup/prefill` returns read-only Step-1 data from onboarding payload + required_remaining_fields. Complete Setup writes profile once and consumes payload. See `.cursor/rules/26_onboarding_payload_flow.md`.

5. **Onboarding payload** – Step-1 signup data is stored in `platform_onboarding_payloads` (tenant_id, payload_json, expires_at, consumed_at). Not written to `platform_company_profiles` until Step 4 (Complete Setup). Payload expires (e.g. 7 days); consumed_at set when setup completes.

## Phase flow (single-step signup, no OTP)

| Phase | URL | API | Notes |
|-------|-----|-----|-------|
| 1 Signup | truckerp.me/signup | POST /api/v1/public/signup | Single request: validate slug, create tenant + user + membership + subscription, provision tenant DB, set auth cookies. Returns `redirect_url`. No OTP. |
| 2 Dashboard | {slug}.truckerp.me/ | Redirect after signup | User lands on workspace root/dashboard immediately. Optional banner: "Your email is not verified. Verify later in Settings." |
| 3 Company setup (optional) | Settings | POST /api/v1/public/company-setup | Optional; user can fill company details later in Settings. Not required to access dashboard. |

**Legacy (kept for Settings / email verify):** `POST /api/v1/public/verify-otp`, `POST /api/v1/public/resend-otp` remain available but are not used in the main signup flow.

## Minimal signup endpoint contract

**Request** `POST /api/v1/public/signup`:

```json
{
  "workspace_slug": "acme",
  "email": "a@b.com",
  "password": "**********",
  "first_name": "A",
  "last_name": "B",
  "company_legal_name": "Acme Inc"
}
```

All of `first_name`, `last_name`, `company_legal_name` are optional. Required: `workspace_slug`, `email`, `password`.

**Response** (201):

```json
{
  "success": true,
  "tenant_slug": "acme",
  "redirect_url": "https://acme.truckerp.me/"
}
```

Backend sets `access_token` and `refresh_token` cookies (httponly, domain for subdomain). Frontend should redirect to `redirect_url`; user is logged in.

## Running the API

**Do not create a `.env` file or run with an inline `DATABASE_URL`.** Configuration comes from SSM. In production, the API is started with env from `/run/secrets/truckerp.env` (written by your SSM startup script, e.g. `scripts/start_api_with_ssm.sh`). For local runs, set required vars in the environment from your SSM or other secure source; do not add a repo `.env` or hardcode URLs.

## Making changes take effect (frontend + containers)

When you change **frontend** files under `apps/web/`, you must run the Vite build **before** rebuilding containers, or the nginx container will serve old assets. Order:

1. **Frontend build:** `cd apps/web && npm run build` (writes `apps/web/dist/`).
2. **Container rebuild:** `docker compose up --build -d` (API image and nginx image copy the new `dist/`).

If you only change backend (Python) code, a container rebuild is enough; no Vite step needed.

## Fix: "Workspace schema is not ready" (loads/drivers tables missing)

If the dashboard shows zeros and **Seed demo data** fails with "Workspace schema is not ready. Run tenant migrations…", the tenant DB exists but migrations were run only up to an old revision (before the `loads` table).

**Driver list empty but count &gt; 0 (new tenants):** Seed and default driver data must use validation-safe values (e.g. `@demo.test` for email, not `@demo.local`). See **docs/driver-list-root-cause-and-prevention.md** (§0 and §3) so new tenants never get "List could not be loaded" with a non-zero driver count.

1. **Config (new tenants):** `app/core/config.py` sets `tenant_alembic_target_rev = "head"` so **new** signups always get the current tenant schema (loads, drivers, etc.) without hardcoding a revision.
2. **Existing tenant:** Run tenant migrations for that workspace once (from project root, with platform DB URL set):
   ```bash
   PYTHONPATH=. python scripts/run_tenant_migrations.py <tenant_slug>
   ```
   Example: `PYTHONPATH=. python scripts/run_tenant_migrations.py acme`. Then reload the dashboard and use **Seed demo data** again.
