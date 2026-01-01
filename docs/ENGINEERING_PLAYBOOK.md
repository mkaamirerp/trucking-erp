# Trucking ERP Engineering Playbook
Last updated: 2025-12-31

This document is REQUIRED reading before adding any new module, router, or model.
Its purpose is to prevent uvicorn/FastAPI startup failures, port conflicts, and database drift.

---

## 1) Runtime Basics (Ports + Base URLs)

### Ports
- **Trucking ERP FastAPI API:** 0.0.0.0:8000 (canonical)
- **Plane (on hold):** do not run on this host
- ERP owns 8000; do not share that port with any other process/manager.

### Base URLs
Smoke tests use:
- BASE_URL default: http://127.0.0.1:8000
- API prefix: /api/v1

Health endpoint:
- GET /api/v1/health

---

## 2) Tenant Context Rules

- All tenant data routes REQUIRE the header:
  X-Tenant-ID: <int>
- Dev/testing default tenant is usually: 1
- Routers must NOT guess or default tenant_id.
- Missing tenant context must fail early (400/401/403).

---

## 3) Module Introduction Protocol (MIP)

Every new module MUST follow these steps in order.

### Step 0 — Observe before changes
Check running processes and ports:
- Only one uvicorn per port.
- Verify before starting anything.

---

### Step 1 — Add router (NO database)
- Add router + endpoints returning static JSON.
- Register router in app/main.py.

Acceptance:
- App boots
- /api/v1/health returns 200

---

### Step 2 — Add models ONLY
- Add SQLAlchemy models.
- No DB queries at import time.
- No startup side effects.

Acceptance:
- App boots
- No crashes at startup

---

### Step 3 — Add migration immediately
Every model/schema change requires Alembic migration.

Acceptance:
- Migration applied
- App boots cleanly

---

### Step 4 — Add DB READS
- SELECT queries only
- Always scoped by tenant_id

Acceptance:
- Smoke passes read steps
- No cross-tenant data

---

### Step 5 — Add DB WRITES
- INSERT / UPDATE must include tenant_id
- Prefer soft-delete / deactivate patterns

Acceptance:
- Smoke passes fully
- No hard deletes unless explicitly allowed

---

### Step 6 — Extend smoke tests
Add:
- Happy path
- Validation failure (422)
- Missing tenant header failure

Acceptance:
- Smoke test is green

---

## 4) Common Causes of Startup Failures

1) Import-time side effects (DB calls during import)
2) Model vs DB schema drift
3) Port conflicts (multiple uvicorns)
4) Router registration mistakes
5) Dependency injection mismatch
6) Tenant context not injected

Rule:
- Never debug uvicorn first.
- Always inspect logs and startup code.

---

## 5) Logging Discipline

Canonical dev start:
nohup venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 > /tmp/truckerp_8000.log 2>&1 &

Always inspect logs before restarting services.

---

## 6) Canonical Imports

Database dependency:
from app.core.database import get_db

Legacy imports are deprecated and forbidden in new code.

---

## 7) Definition of Done (DoD)

A module is DONE only when:
- App boots on port 8001
- Health endpoint returns 200
- Migrations are applied
- Tenant scoping enforced
- Smoke tests pass
