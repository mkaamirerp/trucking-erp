# Platform and Demo (Tenant) Databases — Complete Detail

**Generated:** 2026-03-05  
**Source:** Same Postgres server (`truckerp-postgres`), two databases.

---

## 1. Connection overview

| Database       | Purpose                         | Host (in Docker)   | Port | Database name  | User    | Credentials source |
|----------------|----------------------------------|--------------------|------|----------------|---------|--------------------|
| **Platform**  | Control plane: tenants, users, signup, auth | `truckerp-postgres` | 5432 | `trucking_erp` | postgres | SSM (or .env in dev) |
| **Demo tenant** | Business data for workspace "demo" | `truckerp-postgres` | 5432 | `tenant_demo`   | postgres | Same as platform (URL built with `db_name`) |

- **Platform DB** is used by the API for: tenant registry, users, memberships, signup/OTP, subscriptions, company profiles, onboarding payloads, audit.
- **Tenant DB** (`tenant_demo`) is used when the request is for tenant `demo` (subdomain or header): drivers, loads, people, payroll, brokers, etc.

---

## 2. Platform database: `trucking_erp`

- **Size:** ~9.7 MB  
- **Alembic version:** `0020_onboarding_token_lookup`  
- **Config:** `alembic_platform.ini`, migrations in `alembic_platform/versions/`

### 2.1 Tables and row counts

| Table                        | Rows | Description |
|-----------------------------|------|-------------|
| alembic_version             | 1    | Current platform migration revision |
| onboarding_token_lookup     | 8    | Invite/onboarding token lookup (tenant_id, application_id, expires_at) |
| plan_features               | 0    | Plan feature flags |
| plans                       | 0    | Subscription plans |
| platform_audit_log          | 0    | Platform-level audit events |
| platform_company_profiles  | 1    | Company profile per tenant (address, DOT/MC, W9, etc.) |
| platform_onboarding_payloads | 6  | Signup drafts (payload_json, expires_at, consumed_at) |
| platform_otp_tokens        | 1    | OTP for signup/verify |
| platform_security_events   | 12   | Signup attempts, IP, user-agent |
| platform_subscriptions     | 1    | Per-tenant subscription (plan, trial_ends_at) |
| platform_tenant_members   | 1    | User ↔ tenant membership (role) |
| platform_tenants           | 1    | Tenant registry (slug, status, db_status, db_name) |
| platform_users             | 1    | Users (email, password_hash, session_version, reset token) |
| platform_workspace_claims  | 0    | Legacy workspace claim state |
| reserved_slugs             | 0    | Reserved slugs (signup) |
| signup_attempts            | 1    | Signup attempt state |
| signup_otp_tokens          | 0    | Legacy signup OTP |
| slug_reservations          | 0    | Slug reservation state |
| tenant_memberships         | 1    | Membership gate (user_id, tenant_id, status, is_break_glass_owner) |

**Total:** 19 tables.

### 2.2 Platform tenant row (demo)

| Column        | Value        |
|---------------|--------------|
| id            | 53           |
| name          | 11036696     |
| slug          | demo         |
| status        | ACTIVE       |
| db_status     | READY        |
| db_name       | tenant_demo  |
| base_currency | USD         |
| timezone      | America/Toronto |
| country_code  | CA          |

### 2.3 Main columns (by table)

- **platform_tenants:** id, name, slug, status, plan, modules_enabled, privacy_mode, audit_visibility_mode, email_*, db_host, db_port, db_name, db_user, db_status, db_last_error, provisioned_at, base_currency, timezone, country_code, billing_*, created_at, updated_at  
- **platform_users:** id (UUID), email, first_name, last_name, phone, password_hash, is_email_verified, status, verification_token_*, password_reset_*, session_version, created_at, updated_at  
- **platform_tenant_members:** id, tenant_id, platform_user_id, role, created_at, updated_at  
- **tenant_memberships:** id, user_id, tenant_id, status, joined_at, is_break_glass_owner  
- **platform_company_profiles:** tenant_id, legal_name, address_*, usdot_number, mc_number, cvor_number, hst_number, w9_*, setup_completed_at, created_at, updated_at  
- **platform_onboarding_payloads:** id, tenant_id, payload_json (JSONB), status, expires_at, consumed_at, created_at, updated_at, public_id  
- **platform_otp_tokens:** purpose, email, user_id, onboarding_payload_id, otp_hash, expires_at, consumed_at, request_ip, user_agent, created_at  
- **platform_subscriptions:** tenant_id, plan, status, trial_ends_at, created_at, updated_at  
- **onboarding_token_lookup:** token, tenant_id, application_id, expires_at, created_at  

(Full column list available from `information_schema.columns` for `trucking_erp`.)

---

## 3. Demo tenant database: `tenant_demo`

- **Size:** ~9.6 MB  
- **Alembic version:** `e8f9a0b1c2d3`  
- **Config:** `alembic_tenant.ini`, migrations in `alembic_tenant/versions/`  
- **Used when:** Request is for tenant slug `demo` (e.g. demo.truckerp.me).

### 3.1 Tables and row counts

| Table                        | Rows | Description |
|-----------------------------|------|-------------|
| alembic_version             | 1    | Current tenant migration revision |
| audit_log                   | 0    | Tenant audit events |
| brokers                     | 0    | Brokers (tenant_id, name, mc_number, phone, email) |
| driver_document_files       | 0    | Document file storage keys (per driver_document) |
| driver_documents            | 0    | Driver documents (doc_type, expiry, status) |
| driver_onboarding_submissions | 0  | Driver onboarding applications |
| driver_phones               | 0    | Driver phone numbers |
| driver_phones_old           | 0    | Legacy |
| driver_profiles             | 0    | Driver profile (linked to people/person_roles) |
| drivers                     | 0    | Legacy drivers (pre–people model) |
| employee_roles              | 0    | Employee role assignments |
| employees_legacy_20260305   | 0    | Legacy snapshot |
| loads                       | 0    | Loads (status, broker, driver, revenue, etc.) |
| pay_entries                 | 0    | Pay entries |
| pay_periods                 | 0    | Pay periods |
| pay_profiles                | 0    | Pay profiles |
| pay_run_items               | 0    | Pay run line items |
| pay_runs                    | 0    | Pay runs |
| people                      | 1    | People (tenant_id, platform_user_id, first_name, last_name, email, onboarding_status) |
| permissions                 | 79   | Permission definitions (key, description) |
| person_roles                | 1    | Person ↔ role (role_code, e.g. OWNER, driver) |
| role_permissions            | 350  | Role ↔ permission mapping |
| roles                       | 21   | Roles (name, scope, tenant_id, is_system) |
| tenant_audit_logs           | 0    | Tenant audit log |
| tenants                     | 1    | Legacy tenant row (name, slug, status) |
| trucks                      | 0    | Trucks (plate_number, model, tenant_id) |
| user_roles                  | 0    | User ↔ role (legacy) |
| users                       | 0    | Legacy users (tenant-scoped) |

**Total:** 28 tables.

### 3.2 Tenant row (legacy table `tenants`)

| Column   | Value       |
|----------|-------------|
| id       | 1           |
| name     | Demo Fleet  |
| slug     | demo-fleet  |
| status   | active      |

### 3.3 Main columns (by table)

- **people:** id, tenant_id, onboarding_status, first_name, last_name, phone, email, address fields, platform_user_id, is_active, created_at, updated_at  
- **person_roles:** id, tenant_id, person_id, role_code, is_primary, is_active, created_at, updated_at  
- **roles:** id, name, scope, tenant_id, is_system, description  
- **permissions:** id, key, description  
- **role_permissions:** role_id, permission_id, created_at  
- **loads:** tenant_id, status, broker_id, driver_id, pickup/delivery, revenue, dates, etc.  
- **brokers:** tenant_id, name, mc_number, phone, email, notes  
- **drivers:** tenant_id, first_name, last_name, email, phone (legacy)  
- **driver_profiles:** tenant_id, person_id, etc.  
- **pay_periods,** **pay_runs,** **pay_entries,** **pay_run_items:** payroll data  
- **tenants:** id, name, slug, status, created_at, updated_at (legacy, one row per tenant DB)  

(Full column list: 287 columns across 28 tables from `information_schema.columns` for `tenant_demo`.)

---

## 4. How the API uses them

- **Platform DB**  
  - Used by: auth, signup, verify-otp, platform tenant list, membership checks, company profile, subscriptions.  
  - Session: `AsyncSessionLocal` (from `app.core.database`), `get_db()`.

- **Tenant DB (`tenant_demo` when slug = demo)**  
  - Used by: drivers, loads, payroll, brokers, people, person_roles, dashboard, driver onboarding, etc.  
  - Session: `get_tenant_db()` builds URL by taking `POSTGRES_ADMIN_URL` (or `DATABASE_URL`) and replacing the database name with `platform_tenants.db_name` (e.g. `tenant_demo`).

- **Credentials:** From SSM (prod) or .env (dev). Same user/password for both databases; only the database name in the URL changes.

---

## 5. Quick reference

| What you need           | Platform              | Demo (tenant)     |
|-------------------------|-----------------------|-------------------|
| Database name           | trucking_erp          | tenant_demo       |
| Alembic config          | alembic_platform.ini  | alembic_tenant.ini |
| Migrations directory    | alembic_platform/versions/ | alembic_tenant/versions/ |
| Current revision        | 0020_onboarding_token_lookup | e8f9a0b1c2d3 |
| Tenant registry row     | platform_tenants (id=53, slug=demo, db_name=tenant_demo) | tenants (id=1, slug=demo-fleet) |
