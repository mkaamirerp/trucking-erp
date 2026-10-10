# Forbidden SQL Appendix (Tenant Safety)

This appendix defines **forbidden query patterns** that can break tenant isolation, plus the **approved tenant-safe patterns** to use instead.

---

## 0) Core Rule

Any query that can touch tenant business data must be **tenant-scoped**:

- Use the **tenant DB session** (never platform DB session)
- Require **`tenant_id`** in repo/service APIs
- Enforce scoping via SQLAlchemy (ORM/Core), not raw SQL strings

---

## 1) Absolute Forbidden (Reject PR / Fail CI)

### 1A) Platform DB dependency inside tenant code

**Forbidden**
- `from app.deps.db import get_db`
- `Depends(get_db)`
- Any use of platform DB session inside tenant routers/services/repos

**Why**
- One accidental import can route tenant traffic to the wrong DB.

**Correct**
- Use tenant-scoped dependencies only (e.g., `get_tenant_db` / tenant resolver).

---

### 1B) Raw SQL strings in tenant code

**Forbidden**
- `text("SELECT ...")` in tenant code
- `session.execute("SELECT ...")`
- `session.execute(f"SELECT ...")`
- Any multiline SQL string in tenant paths

**Why**
- Easy to forget `tenant_id`
- Easy to interpolate unsafe user input
- Hard to enforce consistently

**Correct**
- SQLAlchemy Core/ORM expressions + explicit tenant filters.

---

### 1C) Building SQL strings with user input

**Forbidden**
- `f"WHERE tenant_id = {tenant_id}"`
- `"... WHERE driver_id=" + driver_id`
- Any string concatenation/formatting into SQL

**Why**
- SQL injection risk
- Tenant bypass risk

**Correct**
- SQLAlchemy expressions (bind params handled safely).

---

### 1D) Any tenant query missing tenant filter (even in tenant DB)

Even if connected to the tenant DB, queries must include `tenant_id` (Option 2 contract).

**Forbidden**
- `select(Driver)` with no `.where(Driver.tenant_id == tenant_id)`
- `update(Driver).where(Driver.id == id)` with no tenant condition
- `delete(Driver).where(Driver.id == id)` with no tenant condition

**Why**
- Protects against future mistakes (shared schemas, sharding, wrong-session bugs)
- Makes scoping auditable and enforceable

---

## 2) Strongly Discouraged (Needs Explicit Justification)

### 2A) Direct `db.execute()` inside tenant routers

**Discouraged**
- Tenant router calling `db.execute(...)` directly

**Why**
- Routers become unsafe/inconsistent
- Harder to enforce `tenant_id` patterns

**Correct**
- Routers call service/repo methods that force `tenant_id`.

---

### 2B) “Helper” functions that return unscoped queries

**Discouraged**
- `def base_query(): return select(Model)`
- `def get_by_id(db, id): return db.get(Model, id)` (no tenant)

**Why**
- Someone will reuse and forget scoping

**Correct**
- Helpers must accept `tenant_id` and apply scoping internally.

---

## 3) Allowed Exceptions (Narrow + Documented)

### 3A) Migrations and Alembic
Raw SQL is allowed in:
- `alembic/`
- `alembic_tenant/`
- `migrations/`

Reason: schema operations sometimes require SQL.

### 3B) Scripts (explicit admin tooling)
Allowed in:
- `scripts/`

Rules:
- Read-only by default, or clearly labeled destructive
- Must never be imported by runtime app code

---

## 4) Tenant-Safe Patterns (Approved)

### 4A) Repo method signatures must include `tenant_id`
✅ `DriverRepo.get_by_id(db, tenant_id, driver_id)`  
❌ `DriverRepo.get_by_id(db, driver_id)`

### 4B) SELECT must scope by `tenant_id`
✅ `select(Driver).where(Driver.tenant_id == tenant_id, Driver.id == driver_id)`  
❌ `select(Driver).where(Driver.id == driver_id)`

### 4C) UPDATE/DELETE must scope by `tenant_id`
✅ `update(Driver).where(Driver.tenant_id == tenant_id, Driver.id == driver_id)`  
❌ `update(Driver).where(Driver.id == driver_id)`

✅ `delete(Driver).where(Driver.tenant_id == tenant_id, Driver.id == driver_id)`  
❌ `delete(Driver).where(Driver.id == driver_id)`

### 4D) FOR UPDATE must scope by `tenant_id`
✅ `select(Driver).where(Driver.tenant_id == tenant_id, Driver.id == driver_id).with_for_update()`  
❌ `select(Driver).where(Driver.id == driver_id).with_for_update()`

---

## 5) Enforcement (Mechanical Guarantees)

CI checks (installed):

- **Grep gate** blocks:
  - platform DB deps in tenant code
  - raw SQL helpers (`text()`, `execute("SELECT...")`)
  - direct executes in tenant routers

- **Pytest gate** blocks:
  - tenant repo public methods missing `tenant_id`

If any **Absolute Forbidden** pattern appears, the PR must fail.

---

## 6) Red-Flag Review Checklist

If you see any of these in tenant code, stop the PR:

- `get_db`
- `text(`
- `.execute("SELECT`
- string SQL
- repo methods missing `tenant_id`
- queries filtered only by primary key and not `tenant_id`
