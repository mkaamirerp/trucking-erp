# Schema: tenant_smoke_active

Generated: 2026-01-06T07:24:09Z

## Tables

- `public.alembic_version`
- `public.audit_log`
- `public.driver_document_files`
- `public.driver_documents`
- `public.driver_phones`
- `public.driver_phones_old`
- `public.drivers`
- `public.employee_roles`
- `public.employees_legacy_20260106`
- `public.pay_entries`
- `public.pay_periods`
- `public.pay_profiles`
- `public.pay_run_items`
- `public.pay_runs`
- `public.permissions`
- `public.plan_features`
- `public.plans`
- `public.platform_audit_log`
- `public.platform_tenant_members`
- `public.platform_tenants`
- `public.platform_users`
- `public.role_permissions`
- `public.roles`
- `public.tenant_subscriptions`
- `public.tenants`
- `public.trucks`
- `public.user_roles`
- `public.users`

---

## `public.alembic_version`

**Primary Key:** `(version_num)`

**Foreign Keys:**
- _(none)_

### Columns

| # | Column | Type | Boolean? | Nullable? | Default | Enum values |
|---:|---|---|---|---|---|---|
| 1 | `` | version_num |   | character varying(255) | ` ` | ||NO|||| |

