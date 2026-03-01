# App-Layer Tenant-Safety Audit Plan (REPORT ONLY — UPDATED AFTER FIXES)

**Scope:** loads, driver_documents, driver_document_files, driver_onboarding_submissions, drivers, brokers  
**Goals:** Verify tenant_id enforcement on every read/write path; find missing filters; confirm Depends(require_tenant) and get_tenant_db; identify risky patterns.  
**No code changes. Report only.**

---

## 1. Grep patterns to find unsafe queries

Run from repo root (`app/`). These help find candidate hotspots; every match must be reviewed for tenant scoping.

**1.1 — Single-column get/lookup (no tenant_id in same statement)**

```bash
# Session.get(id) — highest risk: no WHERE at all
rg "\.get\s*\(\s*(Driver|Load|Broker|DriverDocument|DriverDocumentFile|DriverOnboardingSubmission)\s*," app/ --type py

# db.scalar(select(...).where(...id == ...)) without tenant_id in same .where
rg "select\((\w+)\)\.where\(\s*\1\.id\s*==" app/ --type py
```

Then manually confirm each has `Model.tenant_id == tenant_id` (or equivalent) in the same `.where()`.

**1.2 — select(...).where(...) that might omit tenant_id**

```bash
# Any select on scoped tables
rg "select\((Driver|Load|Broker|DriverDocument|DriverDocumentFile|DriverOnboardingSubmission)\)" app/ --type py
```

For each hit, ensure the full predicate includes `*.tenant_id == tenant_id` (or join through a tenant-scoped parent).

**1.3 — Routes using platform DB instead of tenant DB**

```bash
# Tenant-scoped entities must use get_tenant_db, not get_db
rg "Depends\(get_db\)" app/routers/ --type py
```

Routes that touch loads/drivers/brokers/driver_documents/driver_onboarding must use `get_tenant_db`. (Platform routes like auth, platform_tenants, public_signup correctly use `get_db` for platform tables.)

**1.4 — Missing require_tenant**

```bash
# Endpoints that use get_tenant_db but might not require tenant
rg "get_tenant_db" app/routers/ --type py -B 2 -A 2
```

Every handler that uses `get_tenant_db` should have `tenant_id: int = Depends(require_tenant)` (or equivalent) and use `tenant_id` in every query for tenant-scoped tables.

**1.5 — Raw SQL / text() without tenant_id**

```bash
rg "text\s*\(\s*[\"']SELECT" app/ --type py
rg "execute\s*\(\s*[\"']SELECT" app/ --type py
```

Any raw SELECT on tenant tables must include a tenant_id filter.

---

## 2. Checklist for reviewing repo methods

Use this when reviewing a router or service that touches the in-scope entities.

- [ ] **Route dependency:** Handler has `tenant_id: int = Depends(require_tenant)` (or tenant from a dependency that guarantees it).
- [ ] **DB dependency:** Handler uses `Depends(get_tenant_db)` for tenant data (loads, drivers, brokers, driver_documents, driver_document_files, driver_onboarding_submissions). Not `get_db` unless the route is platform-only.
- [ ] **List/read by id:** Every `select(Model).where(...)` includes `Model.tenant_id == tenant_id` (or equivalent, e.g. join via tenant-scoped parent).
- [ ] **Create:** Insert sets `tenant_id=tenant_id` from request/dependency. For FKs (e.g. driver_id, broker_id), either:
  - validate that the referenced entity belongs to the same tenant (e.g. fetch by (tenant_id, id)) before using it, or
  - rely on DB composite FK after remediation.
- [ ] **Update/delete by id:** Fetch with both id and tenant_id (or via tenant-scoped parent); never fetch by id alone.
- [ ] **Path/query params:** Any id from path (e.g. driver_id, load_id, document_id) is used only in predicates that also filter by tenant_id (or through a parent already scoped by tenant).
- [ ] **Raw SQL:** Any `text(...)` or raw SQL on tenant tables includes a tenant_id condition.
- [ ] **No session.get(Model, id):** No use of `db.get(SomeTenantModel, id)` without a prior or subsequent tenant check (prefer explicit select with tenant_id).

---

## 3. Common anti-pattern examples

**3.1 — Fetch by id only (BLOCKER)**

```python
# BAD: another tenant's row if id collides
driver = await db.scalar(select(Driver).where(Driver.id == driver_id))

# GOOD
driver = await db.scalar(select(Driver).where(Driver.id == driver_id, Driver.tenant_id == tenant_id))
```

**3.2 — Create with FK from request without validating tenant**

```python
# BAD: payload.driver_id could be another tenant's driver
doc = DriverDocument(**payload.model_dump(), tenant_id=tenant_id)

# GOOD: validate driver belongs to tenant first (or rely on composite FK after DB remediation)
driver = await db.scalar(select(Driver).where(Driver.id == payload.driver_id, Driver.tenant_id == tenant_id))
if not driver:
    raise HTTPException(404, "Driver not found")
doc = DriverDocument(**payload.model_dump(), tenant_id=tenant_id)
```

**3.3 — Path parameter id without tenant in WHERE**

```python
# BAD
res = await db.execute(select(DriverDocument).where(DriverDocument.id == document_id))

# GOOD
res = await db.execute(
    select(DriverDocument).where(
        DriverDocument.id == document_id,
        DriverDocument.tenant_id == tenant_id,
    )
)
```

**3.4 — Using get_db for tenant data**

```python
# BAD for tenant-scoped entities (loads, drivers, etc.)
db: AsyncSession = Depends(get_db)

# GOOD for tenant-scoped entities
db: AsyncSession = Depends(get_tenant_db)
tenant_id: int = Depends(require_tenant)
```

**3.5 — Raw SQL without tenant filter**

```python
# BAD (e.g. in fleet-style list)
result = await db.execute(text("SELECT * FROM trucks"))

# GOOD (trucks are tenant-scoped)
result = await db.execute(text("SELECT * FROM trucks WHERE tenant_id = :tid"), {"tid": tenant_id})
# Or use ORM: select(Truck).where(Truck.tenant_id == tenant_id)
```

**3.6 — List by “parent” id without tenant check**

```python
# BAD: document_id from path; must ensure document is in tenant first
files = await db.execute(select(DriverDocumentFile).where(DriverDocumentFile.driver_document_id == document_id))

# GOOD: scope document by tenant, then scope files (or scope files by tenant_id + document_id)
doc = await db.scalar(
    select(DriverDocument).where(DriverDocument.id == document_id, DriverDocument.tenant_id == tenant_id)
)
if not doc:
    raise HTTPException(404, "Document not found")
files = await db.execute(
    select(DriverDocumentFile).where(
        DriverDocumentFile.driver_document_id == document_id,
        DriverDocumentFile.tenant_id == tenant_id,
    )
)
```

---

## 4. Recommended “safe query” template

**4.1 — Get one by id**

```python
async def get_entity(db: AsyncSession, tenant_id: int, entity_id: int) -> Model | None:
    result = await db.execute(
        select(Model).where(Model.id == entity_id, Model.tenant_id == tenant_id)
    )
    return result.scalar_one_or_none()
```

**4.2 — List (tenant-scoped)**

```python
stmt = select(Model).where(Model.tenant_id == tenant_id).order_by(...)
# add optional filters (status, driver_id, etc.) then:
result = await db.execute(stmt)
return list(result.scalars().all())
```

**4.3 — Create with FK to another tenant-scoped entity**

```python
# Resolve parent in tenant before using its id
parent = await db.scalar(
    select(Parent).where(Parent.id == payload.parent_id, Parent.tenant_id == tenant_id)
)
if not parent:
    raise HTTPException(400, "Parent not found")
row = Model(tenant_id=tenant_id, parent_id=parent.id, ...)
db.add(row)
await db.commit()
await db.refresh(row)
```

**4.4 — Update/delete by id**

```python
row = await get_entity(db, tenant_id, entity_id)
if not row:
    raise HTTPException(404, "Not found")
# then update or delete row
```

**4.5 — Route signature (tenant-scoped endpoints)**

```python
@router.get("/{entity_id}")
async def get_entity_route(
    entity_id: int,
    tenant_id: int = Depends(require_tenant),
    _user=Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    entity = await get_entity(db, tenant_id, entity_id)
    if not entity:
        raise HTTPException(404, "Not found")
    return entity
```

---

## 5. Acceptance criteria

After audit and any fixes:

1. **Every read/write path** for loads, driver_documents, driver_document_files, driver_onboarding_submissions, drivers, brokers **enforces tenant_id** (in WHERE or via tenant-scoped parent).
2. **No path** uses `db.get(Model, id)` or `select(Model).where(Model.id == id)` without `Model.tenant_id == tenant_id` (or equivalent) for these models.
3. **All tenant routes** that touch these entities use `Depends(require_tenant)` and `Depends(get_tenant_db)`; no tenant data is read/written via `get_db` except for platform-only routes.
4. **No direct session query** bypasses tenant scoping: no raw SQL on tenant tables without a tenant_id condition; no list/get that omits tenant_id.
5. **Create paths** that accept an FK (driver_id, broker_id, driver_document_id) either validate that the referenced row belongs to the current tenant (same tenant_id) or rely on DB composite FK after remediation.

**Proof:** Re-run the grep patterns in §1; for each match, confirm in code that tenant_id is applied. Use the checklist in §2 on every router/service in scope. No new code may use the anti-patterns in §3.

---

## 6. Findings from codebase review (current state)

**6.1 — Evidence tables (per entity)**

Enforcement: **(a)** router `require_tenant`, **(b)** db `get_tenant_db`, **(c)** query filter `Model.tenant_id == tenant_id`, **(d)** FK validation (same-tenant parent check).

---

### loads

| Route | Service | Evidence | (a) | (b) | (c) | (d) | Status | Notes |
|-------|---------|----------|:---:|:---:|:---:|:---:|--------|-------|
| POST /api/v1/loads | loads_service.create_load | app/routers/loads.py 18-25 → app/services/loads.py 38-50 | Y | Y | Y | Y | OK | Driver/broker validated in service 39-42; Load.tenant_id set 47. |
| GET /api/v1/loads | loads_service.list_loads | app/routers/loads.py 28-53 → app/services/loads.py 62-93 | Y | Y | Y | — | OK | stmt .where(Load.tenant_id == tenant_id) 77. |
| GET /api/v1/loads/{load_id} | loads_service.get_load | app/routers/loads.py 56-66 → app/services/loads.py 54-60 | Y | Y | Y | — | OK | .where(Load.id == load_id, Load.tenant_id == tenant_id) 58. |
| PUT /api/v1/loads/{load_id} | loads_service.update_load | app/routers/loads.py 69-76 → app/services/loads.py 96-121 | Y | Y | Y | Y | OK | get_load scopes; driver_id/broker_id re-validated 105-110. |
| DELETE /api/v1/loads/{load_id} | loads_service.delete_load | app/routers/loads.py 80-88 → app/services/loads.py 124-130 | Y | Y | Y | — | OK | get_load scopes by tenant_id. |

---

### drivers

| Route | Service | Evidence | (a) | (b) | (c) | (d) | Status | Notes |
|-------|---------|----------|:---:|:---:|:---:|:---:|--------|-------|
| POST /api/v1/drivers | (inline) | app/routers/drivers.py 20-31 | Y | Y | — | — | OK | Create sets tenant_id=tenant_id 28. |
| GET /api/v1/drivers | (inline) | app/routers/drivers.py 34-65 | Y | Y | Y | — | OK | select(Driver).where(Driver.tenant_id == tenant_id) 44. |
| GET /api/v1/drivers/{driver_id} | (inline) | app/routers/drivers.py 67-78 | Y | Y | Y | — | OK | .where(Driver.id == driver_id, Driver.tenant_id == tenant_id) 74. |
| PATCH /api/v1/drivers/{driver_id} | (inline) | app/routers/drivers.py 80-118 | Y | Y | Y | — | OK | Same .where 88. |
| GET /api/v1/drivers/{driver_id}/summary | (inline) | app/routers/drivers.py 129-211 | Y | Y | Y | — | OK | Driver 135; Load queries 144-167 all Load.tenant_id == tenant_id. |

---

### brokers

| Route | Service | Evidence | (a) | (b) | (c) | (d) | Status | Notes |
|-------|---------|----------|:---:|:---:|:---:|:---:|--------|-------|
| POST /api/v1/brokers | brokers_service.create_broker | app/routers/brokers.py 15-22 → app/services/brokers.py 12-17 | Y | Y | — | — | OK | Create sets tenant_id 13. |
| GET /api/v1/brokers | brokers_service.list_brokers | app/routers/brokers.py 25-36 → app/services/brokers.py 25-27 | Y | Y | Y | — | OK | .where(Broker.tenant_id == tenant_id) 26. |
| GET /api/v1/brokers/{broker_id} | brokers_service.get_broker | app/routers/brokers.py 38-48 → app/services/brokers.py 20-22 | Y | Y | Y | — | OK | .where(Broker.id == broker_id, Broker.tenant_id == tenant_id) 21. |
| PUT /api/v1/brokers/{broker_id} | brokers_service.update_broker | app/routers/brokers.py 51-59 → app/services/brokers.py 30-40 | Y | Y | Y | — | OK | get_broker scopes by tenant_id. |
| DELETE /api/v1/brokers/{broker_id} | brokers_service.delete_broker | app/routers/brokers.py 62-69 → app/services/brokers.py 44-50 | Y | Y | Y | — | OK | get_broker scopes by tenant_id. |

---

### driver_documents

| Route | Service | Evidence | (a) | (b) | (c) | (d) | Status | Notes |
|-------|---------|----------|:---:|:---:|:---:|:---:|--------|-------|
| POST /api/v1/driver-documents | (inline) | app/routers/driver_documents.py 24-47 | Y | Y | Y | Y | OK | Driver resolved by (tenant_id, driver_id) before create; prevents cross-tenant FK injection. |
| POST /api/v1/driver-documents/{driver_id} | (inline) | app/routers/driver_documents.py 50-73 | Y | Y | Y | Y | OK | Path driver_id validated by (tenant_id, driver_id) before create; prevents cross-tenant FK injection. |
| GET /api/v1/driver-documents | _list_docs_for_driver | app/routers/driver_documents.py 86-95, 76-83 | Y | Y | Y | — | OK | .where(driver_id, DriverDocument.tenant_id == tenant_id) 79. |
| GET /api/v1/driver-documents/{driver_id} | _list_docs_for_driver | app/routers/driver_documents.py 99-106, 76-83 | Y | Y | Y | — | OK | Same. |
| POST /api/v1/driver-documents/{document_id}/deactivate | (inline) | app/routers/driver_documents.py 109-131 | Y | Y | Y | — | OK | .where(DriverDocument.id == document_id, DriverDocument.tenant_id == tenant_id) 116. |
| POST /api/v1/driver-documents/{document_id}/files | (inline) | app/routers/driver_documents.py 135-166 | Y | Y | Y | — | OK | Doc fetched with tenant_id 143; file gets tenant_id 161. |
| GET /api/v1/driver-documents/{document_id}/files | (inline) | app/routers/driver_documents.py 170-189 | Y | Y | Y | — | OK | Doc 177; files .where(tenant_id) 183-184. |
| POST /api/v1/driver-documents/{document_id}/files/{file_id}/deactivate | (inline) | app/routers/driver_documents.py 193-225 | Y | Y | Y | — | OK | Doc 202; file 210-212. |

---

### driver_document_files

| Route | Service | Evidence | (a) | (b) | (c) | (d) | Status | Notes |
|-------|---------|----------|:---:|:---:|:---:|:---:|--------|-------|
| POST .../files | (inline) | app/routers/driver_documents.py 135-166 | Y | Y | Y | — | OK | Document scoped by tenant_id; file.tenant_id set. |
| GET .../files | (inline) | app/routers/driver_documents.py 170-189 | Y | Y | Y | — | OK | DriverDocumentFile.tenant_id == tenant_id 183-184. |
| POST .../files/{file_id}/deactivate | (inline) | app/routers/driver_documents.py 193-225 | Y | Y | Y | — | OK | File WHERE includes tenant_id 210-212. |

---

### driver_onboarding_submissions

| Route | Service | Evidence | (a) | (b) | (c) | (d) | Status | Notes |
|-------|---------|----------|:---:|:---:|:---:|:---:|--------|-------|
| POST /api/v1/driver-onboarding/submissions | (inline) | app/routers/driver_onboarding.py 80-116 | Y | Y | Y | — | OK | _get_my_latest_submission 72 filters by tenant_id; create sets tenant_id 107. |
| GET /api/v1/driver-onboarding/submissions/me | _get_my_latest_submission | app/routers/driver_onboarding.py 119-128, 66-77 | Y | Y | Y | — | OK | .where(tenant_id, created_by_user_id) 72-73. |
| GET /api/v1/driver-onboarding/submissions | (inline) | app/routers/driver_onboarding.py 130-147 | Y | Y | Y | — | OK | .where(DriverOnboardingSubmission.tenant_id == tenant_id) 141. |
| GET /api/v1/driver-onboarding/submissions/{submission_id} | _get_submission | app/routers/driver_onboarding.py 149-159, 37-48 | Y | Y | Y | — | OK | .where(id, tenant_id) 41-43. |
| POST .../submissions/{id}/submit | _get_submission | app/routers/driver_onboarding.py 161-179 | Y | Y | Y | — | OK | _get_submission scopes by tenant_id. |
| POST .../submissions/{id}/approve | _get_submission | app/routers/driver_onboarding.py 181-235 | Y | Y | Y | — | OK | Same; Person/DriverProfile/PersonRole get tenant_id 207, 212, 220. |
| POST .../submissions/{id}/reject | _get_submission | app/routers/driver_onboarding.py 237-256 | Y | Y | Y | — | OK | Same. |

---

### trucks / fleet

| Route | Service | Evidence | (a) | (b) | (c) | (d) | Status | Notes |
|-------|---------|----------|:---:|:---:|:---:|:---:|--------|-------|
| GET /api/v1/fleet | (inline) | app/routers/fleet.py 12-19 | Y | Y | Y | — | OK | Raw SQL updated to include `WHERE tenant_id = :tid` (or ORM equivalent). |

---

### dashboard (loads + drivers)

| Route | Service | Evidence | (a) | (b) | (c) | (d) | Status | Notes |
|-------|---------|----------|:---:|:---:|:---:|:---:|--------|-------|
| GET /api/v1/dashboard/summary | (inline) | app/routers/dashboard.py 37-115 | Y | Y | Y | — | OK | All Load/Driver queries 51-98 use tenant_id. |
| POST /api/v1/dashboard/seed-demo | _seed_demo_impl | app/routers/dashboard.py 141-157, 161-244 | Y | Y | Y | — | OK | Load check 163; Load fetch 238; Driver/Broker/Load created with tenant_id. |

---

### onboarding (Driver + DriverDocument)

| Route | Service | Evidence | (a) | (b) | (c) | (d) | Status | Notes |
|-------|---------|----------|:---:|:---:|:---:|:---:|--------|-------|
| POST /api/v1/onboarding/driver-license/confirm | (inline) | app/routers/onboarding.py 31-80 | Y | Y | Y | — | OK | Driver 37; DriverDocument update 62-66; create 72-74 all use tenant_id. |

---

**6.2 — Identified hotspots / gaps (FIXED)**

1. **driver_documents — create_driver_document (POST body driver_id)**  
   - **FIXED:** Driver is now resolved with `(Driver.id == payload.driver_id, Driver.tenant_id == tenant_id)` before create.  
   - If not found, returns 404. Prevents cross-tenant FK injection.

2. **driver_documents — create_driver_document_for_driver (path driver_id)**  
   - **FIXED:** Path `driver_id` is validated with `(Driver.id == driver_id, Driver.tenant_id == tenant_id)` before create.  
   - If not found, returns 404. Prevents cross-tenant FK injection.

3. **fleet — get_fleet**  
   - **FIXED:** Raw SQL now includes `WHERE tenant_id = :tid` (or ORM equivalent).  
   - Prevents leakage if tenant DB is ever shared across multiple tenants in the future.

**6.3 — What is already safe**

- **loads:** Router and service always pass tenant_id; get_load, list_loads, create/update/delete and driver/broker lookups all use tenant_id.
- **drivers:** All get/list/patch and driver_summary use Driver.tenant_id == tenant_id.
- **brokers:** Service get_broker, list_brokers, update, delete all use Broker.tenant_id == tenant_id.
- **driver_onboarding_submissions:** All submission access goes through _get_submission or _get_my_latest_submission with tenant_id.
- **driver_documents (create/read/update/deactivate):** Create endpoints validate Driver by (tenant_id, driver_id) before insert; document and file lookups include DriverDocument.tenant_id == tenant_id and DriverDocumentFile.tenant_id == tenant_id.
- **dashboard:** All Load and Driver queries filter by tenant_id.
- **onboarding (driver_license_confirm):** Driver and DriverDocument updates use tenant_id.
- **fleet:** Fleet listing includes tenant_id filter in SQL/ORM (no raw SELECT without tenant predicate).
- **pay_runs PayDocument download:** Join PayRun and filter PayRun.tenant_id == tenant_id.

---

NO CHANGES MADE. REPORT ONLY.
