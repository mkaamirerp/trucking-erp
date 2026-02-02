# Signup → Dashboard Flow (Canonical)

## Key invariants

1. **TenantStatus enum** (`app/models/platform.py`) must include all values referenced in code: `PENDING`, `PENDING_SETUP`, `PROVISIONING`, `ACTIVE`, `SUSPENDED`. Do not reference enum values that don't exist.

2. **JWT tenant_id** – If JWT is valid and includes `tenant_id`, middleware sets `request.state.tenant_id` and returns without calling `_resolve_tenant()`. Readiness enforcement comes from route dependencies (`get_tenant_db`, `require_active_tenant`) and explicit handler checks, not middleware.

3. **Me endpoints**
   - `GET /api/v1/auth/me` – Canonical for session validation. Uses `get_current_user` (JWT + DB load). Used by `sessionCheck.ts` (AuthContext).
   - `GET /api/v1/me` – Uses `require_tenant` + headers. Used by `useMe` with `fetchWithTenant` (adds X-Tenant-Slug from host). Both work when JWT populates `request.state`.

4. **Company setup route** – Canonical path: `POST /api/v1/public/company-setup`. Under `DEFAULT_ALLOW_PATHS` via `/api/v1/public`. Handler reads `X-Tenant-ID` or `X-Tenant-Slug` from headers (frontend adds via `fetchWithTenant`).

## Phase flow

| Phase | URL | API | Notes |
|-------|-----|-----|-------|
| 1 Signup | truckerp.me/signup | POST /api/v1/public/signup | Create tenant (PENDING), user, OTP. No DB provisioning. |
| 2 Verify OTP | truckerp.me/signup | POST /api/v1/public/verify-otp | Validate OTP, provision tenant DB (ALEMBIC_TENANT_DATABASE_URL), set cookies. Returns `company_setup_url`, `dashboard_url`. |
| 3 Company setup | {slug}.truckerp.me/company-setup | POST /api/v1/public/company-setup | Requires JWT cookies + X-Tenant-Slug. Saves profile, sets tenant ACTIVE. |
| 4 Dashboard | {slug}.truckerp.me/dashboard | GET /api/v1/auth/me or /api/v1/me | JWT + tenant from host. |
