Trucking ERP Engineering Playbook

Last updated: 2025-12-31

This document is REQUIRED reading before adding any new module, router, model, or operational procedure.
Its purpose is to prevent startup failures, tenant data leaks, database drift, and unsafe production actions.

**Documentation map:** For navigation across design docs (email intake, trips, parser, platform), see [`docs/DOCUMENTATION_MASTER_INDEX.md`](DOCUMENTATION_MASTER_INDEX.md).

1) Runtime Basics (Ports + Base URLs)

(unchanged — verified correct)

Ports

Trucking ERP FastAPI API: 0.0.0.0:8000 (canonical)

Plane: do not run on this host

ERP owns port 8000 exclusively

Base URLs

BASE_URL: http://127.0.0.1:8000

API prefix: /api/v1

Health: GET /api/v1/health

2) Tenant Context Rules (HARD REQUIREMENT)
🔒 Authoritative Rule

Every operation MUST be tenant-scoped. No exceptions.

Enforcement

All tenant data routes REQUIRE tenant context

Tenant context must never be guessed or defaulted

Missing tenant context must fail early

Current Mechanics

Header:
X-Tenant-ID: <int>

Dev/testing default tenant is usually 1 (explicit only)

Missing tenant → 400 / 401 / 403

Expanded Rule (NEW – LOCKED)

Tenant isolation is enforced at three layers:

API / Middleware

Application Code

Database Constraints

If one layer fails, the others must still protect tenant data.

3) Module Introduction Protocol (MIP)

(unchanged — already solid and correct)

Steps 0–6 remain exactly as written, with one added constraint:

🔒 Tenant Safety Addition (applies to Steps 4 & 5)

Every SELECT / INSERT / UPDATE / DELETE must include tenant_id

ID-only queries are forbidden for tenant data

4) Common Causes of Startup Failures

(unchanged)

Add one more (now observed in real design):

Tenant context not enforced consistently across repos

5) Logging Discipline

(unchanged)

6) Canonical Imports

(unchanged)

7) Definition of Done (DoD)

(unchanged, but clarified)

A module is DONE only when:

App boots on port 8000

Health endpoint returns 200

Migrations are applied

Tenant scoping enforced at API + DB

Smoke tests pass

🔒 8) Multi-Tenant Safety & Driver Hiring (AUTHORITATIVE — NEW)

This section governs all admin driver creation, approval, rejection, and document handling.

8.1 Absolute Tenant Rule

Every query MUST include tenant_id

Every delete MUST include tenant_id

Every audit event MUST include tenant_id

❌ Never run tenant data queries using only id

8.2 Database Enforcement (MANDATORY)
Composite Keys

Tenant-owned tables must use:

PRIMARY KEY (id, tenant_id)

Composite Foreign Keys

Child tables must reference:

(parent_id, tenant_id)
REFERENCES parent_table (id, tenant_id)
ON DELETE CASCADE


This prevents cross-tenant data corruption even if code is wrong.

8.3 Admin → Add Driver Workflow (Office Only)
Add Driver

Admin creates driver_candidate

Status = PENDING

Partial info allowed

Documents optional at entry

Required Documents (MVP – CA & US)

DRIVER_LICENSE

DRUG_TEST

8.4 Approval (Transactional)

Approval MUST happen in one database transaction:

Validate required documents

Promote candidate → active driver

Copy documents → permanent tables

Delete staging documents (tenant-scoped)

Write audit event

Missing required docs → 409 Conflict

8.5 Rejection

Deletes all staging documents (tenant-scoped)

Keeps basic candidate info only

Candidate retained for future hiring

Rejected candidates cannot be approved

8.6 Audit Logging (Non-Optional)

Every state-changing action records:

tenant_id

actor (admin/system)

entity type

entity id

timestamp

structured payload

Audit logs are immutable and tenant-scoped.

8.7 Operational Safety Rules (EC2 Applies)

Manual SQL must include tenant_id

Emergency deletes must include tenant_id

No cross-tenant scripts allowed on EC2

Violations are production-blocking issues.

9) Blueprint (Canonical)

(Your entire “🚛 Trucking ERP Blueprint” section is already excellent and remains unchanged)
It now inherits the tenant safety and driver workflow rules above.

✅ Consolidation Summary

✅ No existing sections removed

✅ No dates altered

✅ Tenant safety rules elevated to first-class law

✅ Driver approval flow formally locked

✅ Engineering + EC2 operations aligned

✅ Ready for copy-paste
