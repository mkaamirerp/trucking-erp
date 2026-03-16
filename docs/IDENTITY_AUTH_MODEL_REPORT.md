# Identity/Auth Model — Current Implementation Report

**Generated:** 2026-03-15  
**Purpose:** Document the actual identity and auth implementation (as implemented, not intended design).

---

## 1. Current identity/auth model

### Platform users

| Attribute | Value |
|-----------|-------|
| **Table/Model** | `platform_users` / `PlatformUser` |
| **Database** | Platform DB (`trucking_erp`) |
| **Purpose** | Global identity per email. Stores credentials, profile, session, reset tokens. |

**Columns:** `id` (UUID), `email`, `first_name`, `last_name`, `phone`, `password_hash`, `is_email_verified`, `status`, `verification_token_hash`, `verification_token_expires_at`, `password_reset_token_hash`, `password_reset_expires_at`, `session_version`, `created_at`, `updated_at`

---

### Tenant users

There is no separate "tenant user" table. "Tenant users" are platform users linked to tenants via memberships. There is no tenant-local login identity.

---

### Login/auth credentials

| Attribute | Value |
|-----------|-------|
| **Table** | `platform_users` |
| **Database** | Platform DB |
| **Stored fields** | `password_hash`, `password_reset_token_hash`, `password_reset_expires_at`, `session_version` |

---

### Password hashes / password auth

| Attribute | Value |
|-----------|-------|
| **Storage** | `platform_users.password_hash` (Platform DB) |
| **Validation** | `app/utils/password.py` — `verify_password()`, `hash_password()` |

---

### Tenant memberships

| Attribute | Value |
|-----------|-------|
| **Table** | `platform_tenant_members` / `PlatformTenantMember` |
| **Database** | Platform DB |
| **Purpose** | Links platform users to tenants; holds tenant-specific role. |
| **Columns** | `id`, `tenant_id`, `platform_user_id`, `role`, `created_at`, `updated_at` |

| Attribute | Value |
|-----------|-------|
| **Table** | `tenant_memberships` / `TenantMembership` |
| **Database** | Platform DB |
| **Purpose** | Access gate: active/suspended/pending/invited. Enforced by middleware before most API routes. |
| **Columns** | `id`, `user_id`, `tenant_id`, `status`, `joined_at`, `is_break_glass_owner` |

---

### Roles / access levels

| Attribute | Value |
|-----------|-------|
| **Storage** | `platform_tenant_members.role` (Platform DB) |
| **Values** | `TENANT_OWNER`, `TENANT_ADMIN`, etc. |
| **Usage** | `app/deps/admin.py` — `is_tenant_admin()` for admin UI/APIs. |

---

### Workspace creator / founder / owner

| Attribute | Value |
|-----------|-------|
| **Model** | Same `PlatformUser` + `PlatformTenantMember` + `TenantMembership` |
| **Creator role** | `PlatformTenantMember.role = "TENANT_ADMIN"` at signup |
| **Creator gate** | `TenantMembership.is_break_glass_owner = True`, `status = "active"` after provisioning |
| **Tenant DB** | Creator also seeded in tenant DB as `people` row with `platform_user_id` and `person_roles.role_code = 'OWNER'` |

---

## 2. Login flow as implemented today

1. **User goes to `demo.truckerp.me/login`**
   - Frontend may call `GET /api/v1/public/tenant/demo` to confirm workspace exists.
   - User submits email/password.

2. **Request hits backend**
   - `POST /api/v1/auth/login` with tenant context (subdomain → slug `demo`).
   - `require_tenant` returns `tenant_id` from `request.state.tenant_id`.
   - Middleware has already run: For login, tenant is resolved from subdomain. `PUBLIC_AUTH_PATHS` includes `/api/v1/auth/login` → membership gate is skipped (user not authenticated yet).

3. **Login handler** (`app/routers/auth.py`)
   - Uses `get_db` → Platform DB session.
   - Looks up `PlatformUser` by email (Platform DB).
   - Looks up `PlatformTenantMember` by `platform_user_id` and `tenant_id` (Platform DB).
   - If no membership → 401 "Invalid email or password".
   - If `user.password_hash` is `None` → 401 "Password not set for this account. Use 'Forgot password' to set one."
   - Verifies password with `verify_password()`.
   - Loads `PlatformTenant` (with company_profile).
   - Checks `tenant.status == "ACTIVE"` and `tenant.db_status == "READY"`.
   - **Note:** `PlatformUser.status` is NOT checked; deactivated users can still log in if they pass password verification.

4. **JWT issuance**
   - `create_access_token(user_id=user.id, tenant_id=tenant.id, tenant_slug=tenant.slug, roles=[membership.role])`
   - Tokens contain: `sub` (user_id), `tenant_id`, `tenant_slug`, `roles`.

5. **Cookies**
   - Sets `access_token` and `refresh_token` cookies with shared domain.

6. **Response**
   - Returns `workspace_url` (e.g. `https://demo.truckerp.me/dashboard`); frontend may redirect there.

7. **Subsequent authenticated requests**
   - Middleware decodes JWT → `request.state.user_id`, `request.state.roles`.
   - Resolves tenant from host → headers → JWT.
   - Membership gate: `TenantMembership` where `user_id`, `tenant_id`, `status='active'`.
   - If no active membership → 403 "User does not have access to this tenant".

8. **`get_current_user`** (for routes that use it)
   - Reads `PlatformUser` from Platform DB by `user_id`.
   - Reads `PlatformTenant` and `PlatformTenantMember` from Platform DB.
   - Role from `PlatformTenantMember.role`.

---

## 3. Tenant user creation as implemented today

There is **no** tenant-admin "invite user" or "create user" flow in the backend. `/admin/users` is a placeholder in the frontend (`AdminPlaceholderPage`).

**Only flow that creates users: public signup (verify-otp)**

| Step | What happens |
|------|--------------|
| 1 | User completes signup step 1 (`POST /api/v1/public/signup`); payload stored in `platform_onboarding_payloads`; OTP sent. |
| 2 | User submits OTP (`POST /api/v1/public/verify-otp`). |
| 3 | OTP validated → creates platform rows in one transaction: `platform_tenants`, `platform_users` (email, name, phone, password_hash, is_email_verified=True, status="ACTIVE"), `platform_tenant_members` (role TENANT_ADMIN), `tenant_memberships` (initially status="pending", is_break_glass_owner=True), `platform_subscriptions` |
| 4 | `provision_tenant_db()` creates tenant DB, runs migrations, seeds creator via `_seed_tenant_creator()`. |
| 5 | `TenantMembership.status` set to `"active"`. |
| 6 | Transaction committed. |
| 7 | Auth cookies issued. |

**Answers for the signup flow**

| Question | Answer |
|----------|--------|
| Tables written | `platform_tenants`, `platform_users`, `platform_tenant_members`, `tenant_memberships`, `platform_subscriptions` (Platform DB); `people`, `person_roles` in tenant DB. |
| User in platform DB, tenant DB, or both? | Both. Platform: identity; Tenant: `people` with `platform_user_id`, `person_roles.role_code='OWNER'`. |
| Username stored | Not used; only `first_name`, `last_name`, `email`. |
| Email stored | `platform_users.email` and `people.email` (tenant DB). |
| Phone stored | `platform_users.phone` and `people.phone` (tenant DB). |
| Access level | `platform_tenant_members.role` (Platform DB). |
| Can new user log in immediately? | Yes; cookies are set right after verify-otp. |
| Password set | From signup form → hashed in payload_json → stored in `platform_users.password_hash`. |

---

## 4. Isolation check

| Question | Answer |
|----------|--------|
| **Are tenant users platform-level identities?** | Yes. All "tenant users" are `platform_users` linked via memberships. |
| **Are tenant users stored only in tenant DB?** | No. Login identity lives only in platform DB. Tenant DB has `people` with optional `platform_user_id` for business context, not auth. |
| **Does the current implementation violate strict tenant isolation?** | Partially. Auth is fully centralized in the platform DB. Tenant DBs do not contain credentials or membership. Isolation is enforced by membership checks, not by separate per-tenant identity stores. |
| **Centralized vs tenant-local** | Centralized: users, credentials, memberships, roles (platform DB). Tenant-local: `people` (profile/business data) and `person_roles` (OWNER, etc.) in tenant DB. |

---

## 5. Founder/master admin handling

| Attribute | Value |
|-----------|-------|
| **Platform-only?** | No. |
| **Tenant-only?** | No. |
| **Both?** | Yes. |
| **Platform tables/rows at signup** | `platform_users`, `platform_tenant_members` (role TENANT_ADMIN), `tenant_memberships` (status active, is_break_glass_owner=True). |
| **Tenant tables/rows at signup** | `people` (with `platform_user_id`), `person_roles` (role_code OWNER, is_primary=True). |
| **Role inside tenant** | `person_roles.role_code = 'OWNER'` in tenant DB; `platform_tenant_members.role = 'TENANT_ADMIN'` in platform DB. |

---

## 6. Password reset / deactivate as implemented today

### A. Platform-side

| Question | Answer |
|----------|--------|
| Can platform deactivate a user? | No dedicated API. `PlatformUser.status` exists (default "ACTIVE") but is not used in login or middleware. |
| Where is that state stored? | `platform_users.status` (Platform DB). |

### B. Tenant-side

| Question | Answer |
|----------|--------|
| Can tenant admin deactivate a user? | No API. `TenantMembership.status` can be active/suspended/pending/invited, but no route updates it. |
| Where is that state stored? | `tenant_memberships.status` (Platform DB). |
| Can tenant admin reset password? | No. Forgot-password and reset-password are global, not tenant-scoped; tenant admin cannot force a reset for another user. |
| What is missing? | Deactivation routes (platform and tenant); tenant-admin password-reset flow; use of `PlatformUser.status` in login. |

---

## 7. Exact files

| Category | Files |
|----------|-------|
| **Models** | `app/models/platform.py` (PlatformUser, PlatformTenantMember, TenantMembership), `app/models/person.py` (Person, PersonRole) |
| **Routers** | `app/routers/auth.py`, `app/routers/public_signup.py`, `app/routers/tenant_admin.py`, `app/routers/me.py` |
| **Auth helpers** | `app/deps/auth.py` (get_current_user, CurrentUser), `app/deps/admin.py` (is_tenant_admin), `app/utils/jwt_auth.py`, `app/utils/password.py` |
| **Middleware** | `app/middleware/tenant_context.py` |
| **Services** | `app/services/tenant_provisioning.py` (_seed_tenant_creator) |
| **Frontend** | `apps/web/src/pages/LoginPage.tsx`, `apps/web/src/pages/SignupPage.tsx`, `apps/web/src/components/TenantGatedLogin.tsx`, `apps/web/src/hooks/useMe.tsx`, `apps/web/src/api.ts`, `apps/web/src/tenant.ts` |

---

## 8. Final conclusion

| Item | Value |
|------|-------|
| **Current model** | Hybrid (platform-centric for auth; tenant-local for business/people data) |
| **Tenant users live in** | Both (identity in platform DB; people in tenant DB) |
| **Credentials live in** | Platform DB only |
| **Tenant RBAC lives in** | Platform DB (`platform_tenant_members.role`, `tenant_memberships.status`) |
| **Isolation status** | Preserved (tenant isolation enforced via membership checks; no credentials in tenant DBs) |
| **Recommended next action** | Add routes to enforce `PlatformUser.status` and `TenantMembership.status` (platform and tenant deactivation), implement tenant-admin user-invite flow, and add tenant-admin password reset (or equivalent) if required. |
