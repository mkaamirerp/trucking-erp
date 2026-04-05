# DB / Tenant Isolation (LOCKED)

## Architecture
- Platform DB = control plane only (tenants/users/plans/registry).
- Tenant DB = all business data.
- Tenant routing must be registry-driven.

## Rules
- Never move business tables into platform DB.
- All tenant-scoped routes must use tenant DB session.
- Never allow tenant-unsafe UPDATE/DELETE; always scope by tenant.
- Before any SQL/schema/API change: state which DB is affected.