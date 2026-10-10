# Tenant Safety — Execution & Order-of-Operations Runbook

**Inputs:** `TENANT_SAFETY_REMEDIATION_PLAN.md`, `APP_LAYER_TENANT_SAFETY_AUDIT_PLAN.md`  
**Purpose:** Single execution plan: what to fix first, what blocks what, what can be deferred, safe rollout order.  
**No implementation. No code. No schema changes. Report only.**

---

✅ **Confirmed clean (tenant-safe / no cross-tenant write-delete paths found in reviewed areas):**
- **Loads delete:** `delete_load()` fetches via `get_load(db, tenant_id, load_id)` and `get_load()` filters by `(Load.id == load_id, Load.tenant_id == tenant_id)` before delete. (Report H)
- **Brokers delete:** `delete_broker()` fetches via `get_broker(db, tenant_id, broker_id)` and `get_broker()` filters by `(Broker.id == broker_id, Broker.tenant_id == tenant_id)` before delete. (Report H)
- **Employee role delete:** SELECT and DELETE both filter by `EmployeeRole.id`, `EmployeeRole.employee_id`, and `EmployeeRole.tenant_id == tenant_id`. (Report I)
- **Payee scoping:** employees create/patch resolves Payee with `Payee.tenant_id == tenant_id`; pay_runs Payee usage is tenant-bounded by tenant-scoped PayRun/PayRunItem context. (Report K)

❌ **Confirmed gap requiring fix before DB enforcement:**
- **driver_phones create:** accepts `driver_id` in body but does not validate that the driver belongs to the current tenant before insert. (Report J)

⚠️ **Remaining review target (pending evidence):**
- **PayRunItem delete-by-pay_run_id** — need exact router/service delete query and WHERE proof.

**Objective:** Before touching the database, prove there are no remaining cross-tenant write or delete paths at the app layer.  
Only after that do we: update audit file → lock final runbook → rebuild DB composite FK foundation.

---

## 1. Ordered execution plan

### Phase 1 — Immediate app-layer fixes (no schema change)

**Goal:** Close write/read gaps so no new cross-tenant data can be created and no tenant data is leaked, without touching the database.

| # | Fix | Source | Blocks |
|---|-----|--------|--------|
| 1.1 | **driver_documents:** Validate `payload.driver_id` belongs to `tenant_id` before create (POST /api/v1/driver-documents). Resolve driver with `select(Driver).where(Driver.id == payload.driver_id, Driver.tenant_id == tenant_id)`; 404 if not found. | APP_LAYER §6.2 gap 1 | DB migration can later enforce; app fix prevents new violations. |
| 1.2 | **driver_documents:** Validate path `driver_id` belongs to `tenant_id` before create (POST /api/v1/driver-documents/{driver_id}). Same pattern. | APP_LAYER §6.2 gap 2 | Same. |
| 1.3 | **fleet:** Add tenant_id to trucks query. Use `select(Truck).where(Truck.tenant_id == tenant_id)` or raw SQL `WHERE tenant_id = :tid` with tenant_id. | APP_LAYER §6.2 gap 3 | Read leak; low today (one DB per tenant) but required for shared-DB or future. |
| 1.4 | **driver_phones:** Validate `payload.driver_id` belongs to `tenant_id` before create (POST /api/v1/driver-phones). Resolve driver with `select(Driver).where(Driver.id == payload.driver_id, Driver.tenant_id == tenant_id)`; 404 if not found. | Report J gap | Prevents cross-tenant/orphan references; required before DB enforcement. |

**Order:** 1.1 → 1.2 → 1.3 → 1.4 (no dependency between them; can parallelize).  
**Deferrable:** None if you want to stop new violations and align with DB plan. Fleet (1.3) can be deferred only if you accept the read-leak risk in shared-DB scenarios.

**Fleet read-leak note:** The fleet tenant filter is critical when multiple tenants share one DB (as tenant_demo may). If this DB is truly single-tenant, the filter is still a correctness/consistency requirement.

**Exit criterion:** All four fixes merged and deployed; no new cross-tenant writes via driver_documents or driver_phones; fleet returns only current tenant's trucks.

---

### Phase 2 — Pre-migration validation

**Goal:** Confirm no existing data violates the composite FK rules; fix any violations so the DB migration can succeed.

| # | Step | Source | Blocks |
|---|------|--------|--------|
| 2.1 | Run **data-violation SQL** (TENANT_SAFETY §2) on each tenant DB: driver_documents→drivers, driver_document_files→driver_documents, loads→drivers, loads→brokers. Record counts. | REMEDIATION §2 | Phase 3/4 (migration will fail if counts > 0). |
| 2.2 | If any count > 0: run **remediation playbook** (TENANT_SAFETY §9). Prefer "fix tenant_id to match parent" or "repoint FK (set to NULL)"; delete only as last resort. Re-run violation counts until all 0. | REMEDIATION §9 | Phase 3/4. |
| 2.3 | Run **pre-check SQL** (TENANT_SAFETY §1): confirm drivers, brokers, driver_documents have no UNIQUE(tenant_id, id) yet (expected). Confirm id/tenant_id types. | REMEDIATION §1, §6 | Informational; migration adds UNIQUEs. |
| 2.4 | **Go/No-Go checklist** (Section 3 below). Sign-off before Phase 3 or 4. | This runbook | Phase 3/4. |

**Order:** 2.1 → 2.2 (repeat until clean) → 2.3 → 2.4.  
**Deferrable:** 2.3 is optional if you already know schema state.

**Exit criterion:** All four violation counts = 0 on every tenant DB that will be migrated; Go/No-Go passed.

---

### Phase 3 — DB composite FK rollout (dev variant)

**Goal:** Apply composite FKs and indexes in a single transaction. Use for dev, staging, or small/empty tenant DBs where brief blocking is acceptable.

| # | Step | Source | Blocks |
|---|------|--------|--------|
| 3.1 | Add UNIQUE(tenant_id, id) on **drivers**, **brokers**, **driver_documents** (names: uq_drivers_tenant_id_id, uq_brokers_tenant_id_id, uq_driver_documents_tenant_id_id). | REMEDIATION §3.1, §7.2 | 3.2–3.5 (composite FKs require these). |
| 3.2 | Drop FK `fk_driver_document_driver_id`; add composite FK driver_documents(tenant_id, driver_id) → drivers(tenant_id, id). | REMEDIATION §3.2 | — |
| 3.3 | Drop FK `fk_driver_document_files_driver_document_id`; add composite FK driver_document_files(tenant_id, driver_document_id) → driver_documents(tenant_id, id). | REMEDIATION §3.3 | — |
| 3.4 | Drop FK `loads_broker_id_fkey`; add composite FK loads(tenant_id, broker_id) → brokers(tenant_id, id). | REMEDIATION §3.4 | — |
| 3.5 | Drop FK `loads_driver_id_fkey`; add composite FK loads(tenant_id, driver_id) → drivers(tenant_id, id). | REMEDIATION §3.5 | — |
| 3.6 | Create composite indexes: driver_documents(tenant_id, driver_id), driver_document_files(tenant_id, driver_document_id), loads(tenant_id, status), loads(tenant_id, driver_id), loads(tenant_id, broker_id). | REMEDIATION §4 | Optional in same tx; can be separate migration. |

**Order:** 3.1 (all three UNIQUEs) → 3.2 → 3.3 → 3.4 → 3.5 [→ 3.6]. Run 3.1–3.5 (and optionally 3.6) in **one transaction** so the "no FK" window is not visible.  
**Deferrable:** 3.6 can be a follow-up migration.

**Exit criterion:** Acceptance checks (REMEDIATION §5) pass: violation counts 0, composite FKs present, parent UNIQUEs present, composite indexes present.

---

### Phase 4 — DB composite FK rollout (prod-safe variant)

**Goal:** Same schema outcome as Phase 3 but with minimal write blocking: use CONCURRENTLY for index creation, then one short transaction for FK swaps.

| # | Step | Source | Blocks |
|---|------|--------|--------|
| 4.1 | **Phase 4a — Concurrent unique indexes (no transaction).** For each of drivers, brokers, driver_documents: CREATE UNIQUE INDEX CONCURRENTLY ... ON table (tenant_id, id); then ALTER TABLE ... ADD CONSTRAINT ... UNIQUE USING INDEX ...; | REMEDIATION §7.3 Phase 1 | 4.2 (FKs need these). |
| 4.2 | **Phase 4b — FK changes (one transaction).** BEGIN; drop/add the four FKs as in REMEDIATION §3.2–3.5; COMMIT. | REMEDIATION §7.3 Phase 2 | — |
| 4.3 | **Phase 4c — Composite indexes (optional, no transaction).** CREATE INDEX CONCURRENTLY for each of the five composite indexes. | REMEDIATION §4, §7.3 Phase 3 | — |

**Order:** 4.1 (all three tables) → 4.2 → 4.3. 4.1 and 4.3 cannot run inside an explicit transaction (CONCURRENTLY).  
**Deferrable:** 4.3 can be run later.

**Important Postgres note (report-only):** Adding a FOREIGN KEY can require validating existing rows, which may scan the referencing table and hold locks that block writes longer than expected on large tables. If `loads`, `driver_documents`, or `driver_document_files` are large, plan a maintenance window accordingly.

**Optional prod-safe refinement (report-only):** Consider adding new FKs as **NOT VALID** in Phase 4b, then validating them later during low-traffic time:

```sql
-- Example pattern (do not run here; report-only)
ALTER TABLE loads
  ADD CONSTRAINT loads_tenant_broker_fk
  FOREIGN KEY (tenant_id, broker_id) REFERENCES brokers (tenant_id, id)
  NOT VALID;

-- Later:
ALTER TABLE loads VALIDATE CONSTRAINT loads_tenant_broker_fk;
```

This keeps the FK definition in place quickly, and defers full validation cost.

**Exit criterion:** Same as Phase 3 (REMEDIATION §5).

---

### Phase 5 — Post-migration cleanup (index drops optional)

**Goal:** Remove redundant single-column indexes if desired; do not in the same change as composite FK/add-index work.

| # | Step | Source | Blocks |
|---|------|--------|--------|
| 5.1 | After confirming query plans use the new composite indexes, consider dropping: ix_driver_documents_tenant_id, ix_driver_document_files_tenant_id, ix_loads_tenant_id (one drop per table). | REMEDIATION §8 | None. |

**Order:** Only after Phase 3 or 4 is stable and plans verified.  
**Deferrable:** Entire phase is optional; "drop later" only.

**Exit criterion:** Redundant indexes dropped (or decision documented to keep them).

---

## What gets fixed first / what blocks what

- Phase 1 (app) does not block Phase 2. Phase 1 is recommended first so no new violations are introduced while you validate and fix data.
- Phase 2 blocks Phase 3 and Phase 4: migration will fail if violation counts > 0.
- Phase 3 vs Phase 4: Choose one per environment (dev/staging vs prod). Phase 4 does not block Phase 3 for a different DB.
- Phase 5 is after Phase 3 or 4; it never blocks FKs.

## What can be deferred

- **Phase 1.3 (fleet):** If you accept read-leak risk in shared-DB or future schema; current one-DB-per-tenant limits impact.
- **Phase 3.6 / 4.3 (composite indexes):** Can be a separate migration after FKs.
- **Phase 5:** Optional; drop redundant indexes only after verification.

---

## 2. Risk matrix

For each gap or change: risk type (read leak vs write corruption), severity, mitigated by (app fix / DB FK / both).

| Gap or change | Risk type | Severity | Mitigated by |
|---------------|-----------|----------|--------------|
| driver_documents create (body driver_id) | Write corruption (cross-tenant document linked to other tenant's driver) | High | App fix (validate driver in tenant); DB FK (composite FK rejects invalid insert after migration). Both recommended. |
| driver_documents create (path driver_id) | Write corruption (same) | High | App fix + DB FK (same). |
| driver_phones create (body driver_id) | Write corruption (cross-tenant/orphan phone linked to other tenant's driver) | High | App fix (validate driver in tenant). |
| fleet GET trucks no tenant_id | Read leak (return other tenants' trucks if shared DB) | Medium today (one DB per tenant); High if shared-DB | App fix (add tenant_id filter). DB has no FK for "trucks in tenant"; app-only. |
| Single-column FKs (driver_documents→drivers, etc.) | Write corruption (app bug or bypass can insert cross-tenant references) | High | DB FK (composite FK prevents at DB layer). App fixes reduce likelihood before migration. |
| Missing composite indexes (tenant_id, driver_id, etc.) | Performance (slower tenant-scoped queries) | Low–medium | DB (add indexes in Phase 3/4 or 3.6/4.3). |
| Redundant single-column indexes | Minor (extra writes, disk) | Low | Phase 5 optional drop. |
| PayRunItem delete-by-pay_run_id (pending evidence) | Potential delete across tenant boundary if missing tenant filter | High if real | App evidence + fix required before DB enforcement. |

**Summary:** Write corruption (cross-tenant FKs) is mitigated by both app validation (Phase 1) and composite FKs (Phase 3/4). Read leak (fleet) is mitigated by app fix only. Run Phase 1 first to stop new violations; then Phase 2 → Phase 3 or 4 for DB enforcement.

---

## 3. Go/No-Go checklist before applying DB migration

Before starting Phase 3 or Phase 4 on a given tenant DB:

- [ ] **Phase 1 complete:** App fixes (driver_documents create validation, driver_phones create validation, fleet tenant_id filter) are deployed so no new cross-tenant writes and no fleet leak.
- [ ] **PayRunItem delete-by-pay_run_id evidence:** Verified tenant-scoped DELETE (or remediated) if this endpoint exists and can delete rows. If not applicable, explicitly documented as N/A with proof.
- [ ] **Phase 2.1–2.2 complete:** Data-violation counts (REMEDIATION §2) are 0 for all four checks (driver_documents→drivers, driver_document_files→driver_documents, loads→drivers, loads→brokers). Any violations have been remediated (§9).
- [ ] **Backup:** Tenant DB backup or snapshot taken; restore tested or documented.
- [ ] **Maintenance window (prod):** If Phase 4: CONCURRENTLY steps can run during traffic; Phase 4b (FK swap) should be brief. If Phase 3: single transaction will block writes on affected tables for duration; window agreed.
- [ ] **Constraint names verified:** Exact current FK names confirmed (e.g. `\d+ driver_documents`, `\d+ loads`) so drop statements use correct names (REMEDIATION §3).
- [ ] **Alembic / migration tooling:** If using Alembic, revision and script reviewed; dry-run or applied on a copy of tenant DB first if possible.
- [ ] **Rollback plan read:** Section 4 below understood; decision made on whether to keep downgrade migration or restore from backup if needed.

**No-Go:** If any violation count > 0 after remediation attempts, do not run the composite FK migration until data is fixed or explicitly excluded (e.g. rows set to NULL). Migration will fail on ADD CONSTRAINT if violating rows exist.

---

## 4. Rollback strategy if migration fails mid-process

**If Phase 3 (single transaction) fails:**  
Transaction rollback restores pre-migration state; no partial FK or UNIQUE state. Fix the failure (e.g. fix remaining data violations, correct constraint names), then re-run Phase 2 checks and Phase 3 again.

**If Phase 4 fails:**

- **During Phase 4a (CONCURRENTLY unique indexes):** If one CREATE UNIQUE INDEX CONCURRENTLY fails (e.g. duplicate key), the index may be left INVALID. Drop the invalid index; fix data (Phase 2); retry that index. Other tables' indexes are independent.
- **During Phase 4b (FK transaction):** If BEGIN…COMMIT fails, rollback restores pre–Phase 4b state. UNIQUEs from 4a remain. Fix cause (e.g. violation introduced after 2.2, or typo in constraint name); re-run violation checks; retry 4b.
- **During Phase 4c (composite indexes):** No FK state change. If an index build fails, drop invalid index if left behind; retry or defer.

**If migration succeeds but application or data issues are found later:**

- **Revert schema (downgrade):** Use REMEDIATION plan downgrade steps: drop composite FKs, recreate single-column FKs, drop UNIQUE(tenant_id, id) on parents. Run in reverse order of upgrade. Requires a migration/downgrade script.
- **Restore from backup:** Restore tenant DB from pre-migration backup; redeploy app version that does not depend on composite FKs. Use if downgrade is not scripted or is too risky.

**Recommendation:** Keep Alembic (or equivalent) downgrade steps for the composite FK migration so rollback is scripted and repeatable. For prod, prefer "fix forward" (fix data, fix app) over full rollback when possible.

**Rollback completeness check (report-only):** Ensure TENANT_SAFETY_REMEDIATION_PLAN.md explicitly documents downgrade steps for:
- Dropping composite FKs (tenant_id,id)
- Recreating original single-column FKs
- Dropping UNIQUE(tenant_id, id) constraints (or unique indexes)
- Recreating any indexes that were dropped (if Phase 5 was executed)

If downgrade is not fully specified, treat "restore from backup" as the primary rollback mechanism.

---

## 5. Phase 1 verification evidence (report-only)

Use the following to verify that Phase 1 app-layer fixes prevent cross-tenant or invalid driver_id from creating rows.

### 1) API call example — expect 404

Attempt to create a record using a driver_id that does not belong to the current tenant (or a non-existent driver_id). The API must return 404 and must not insert a row.

**Option A — Invalid / non-existent driver_id (e.g. 999999):**

```bash
# Replace ACCESS_TOKEN and TENANT_ID with a valid JWT and tenant (e.g. from login).
# TENANT_ID=1 and driver_id=999999: no driver 999999 in tenant 1 → 404.

curl -s -w "\nHTTP_CODE:%{http_code}" -X POST "http://localhost:8000/api/v1/driver-documents" \
  -H "Content-Type: application/json" \
  -H "X-Tenant-ID: 1" \
  -H "Authorization: Bearer ACCESS_TOKEN" \
  -d '{
    "driver_id": 999999,
    "doc_type": "CDL",
    "title": "Test CDL",
    "is_current": true
  }'
```

**Option B — Path variant (POST /driver-documents/{driver_id}):**

```bash
curl -s -w "\nHTTP_CODE:%{http_code}" -X POST "http://localhost:8000/api/v1/driver-documents/999999" \
  -H "Content-Type: application/json" \
  -H "X-Tenant-ID: 1" \
  -H "Authorization: Bearer ACCESS_TOKEN" \
  -d '{"doc_type": "CDL", "title": "Test CDL", "is_current": true}'
```

**Option C — driver_phones (POST /driver-phones):**

```bash
curl -s -w "\nHTTP_CODE:%{http_code}" -X POST "http://localhost:8000/api/v1/driver-phones" \
  -H "Content-Type: application/json" \
  -H "X-Tenant-ID: 1" \
  -H "Authorization: Bearer ACCESS_TOKEN" \
  -d '{
    "driver_id": 999999,
    "phone": "+15555550123",
    "label": "mobile",
    "is_primary": true
  }'
```

**Expected response (Phase 1 fix in place):**
- HTTP status: **404**
- Body (example): `{"detail":"Driver not found"}`

If the fix were missing, the first endpoint might return 201 and insert a row with (tenant_id=1, driver_id=999999), which would be a cross-tenant or orphan risk.

**Note:** The create-document endpoints do not create driver_document_files; files are added only via POST /driver-documents/{document_id}/files. So after the 404, no document row exists, and therefore no file rows can exist for that document.

### 2) Read-only SQL to prove no rows were inserted

Run these after the API call above (with 404). They must return no rows for the attempted driver_id and tenant_id.

**2.1 — driver_documents (attempted driver_id + tenant_id)**

Use the same tenant_id and driver_id as in the API call (e.g. tenant_id=1, driver_id=999999):

```sql
-- Replace :tid and :did with the tenant_id and driver_id used in the API call.
SELECT id, tenant_id, driver_id, doc_type, title, created_at
FROM driver_documents
WHERE tenant_id = 1 AND driver_id = 999999
ORDER BY created_at DESC;
```

If the Phase 1 fix is working, this returns 0 rows. If it returns any row, the create would have incorrectly inserted (e.g. before the fix or with fix reverted).

**2.1b — driver_phones (attempted driver_id + tenant_id)**

```sql
SELECT id, tenant_id, driver_id, phone, created_at
FROM driver_phones
WHERE tenant_id = 1 AND driver_id = 999999
ORDER BY created_at DESC;
```

Expected: 0 rows.

**2.2 — Optional: created_at time window**

If you know the approximate time of the API call, you can narrow the check:

```sql
-- Example: no document created in the last 5 minutes for this tenant+driver pair.
SELECT id, tenant_id, driver_id, doc_type, created_at
FROM driver_documents
WHERE tenant_id = 1
  AND driver_id = 999999
  AND created_at > now() - interval '5 minutes';
```

Expected: 0 rows.

**2.3 — driver_document_files**

The create-document endpoints do not create files; only POST .../driver-documents/{document_id}/files does. So there is no new file row for a document that was never created. For completeness (to prove no file was attached to a non-existent or wrong document):

```sql
-- No file rows reference a document with the attempted driver_id in this tenant.
-- (Only needed if you had created a document by some other path; after 404 create, no document exists.)
SELECT ddf.id, ddf.driver_document_id, ddf.tenant_id, ddf.uploaded_at
FROM driver_document_files ddf
JOIN driver_documents dd ON dd.id = ddf.driver_document_id AND dd.tenant_id = ddf.tenant_id
WHERE dd.tenant_id = 1 AND dd.driver_id = 999999;
```

Expected: 0 rows (no document with driver_id=999999 in tenant 1, so no files for it).

**Summary:** Run the API call with an invalid or cross-tenant driver_id; assert 404 and `{"detail":"Driver not found"}`. Then run the read-only SQL above; assert 0 rows for that (tenant_id, driver_id). No schema changes; no writes except the single attempted API call that correctly returns 404.

### 3) Fleet verification evidence (report-only)

After Phase 1.3 is deployed (tenant filter added to fleet query), verify the fleet endpoint cannot return rows for the wrong tenant in a shared-DB scenario.

**Option A — API-level check (preferred):**
- Ensure you have at least two tenants with at least one truck each.
- Call GET /api/v1/fleet with Tenant A credentials / X-Tenant-ID: A and confirm only Tenant A trucks are returned.
- Repeat for Tenant B.

**Option B — Read-only DB evidence:**

Run these on the tenant DB (example uses tenant_demo).

```sql
-- Count trucks per tenant (sanity)
SELECT tenant_id, COUNT(*)
FROM trucks
GROUP BY tenant_id
ORDER BY tenant_id;

-- Spot-check one tenant's rows (should match API output when calling with that tenant)
SELECT id, tenant_id, plate_number, model, driver_name
FROM trucks
WHERE tenant_id = 1
ORDER BY id;
```

Expected: API output for X-Tenant-ID: 1 matches the WHERE tenant_id = 1 query result (same set of truck IDs).

**Fleet endpoint response contract (report-only):**  
Declared response_model: `List[dict]` (GET /api/v1/fleet in app/routers/fleet.py). Actual return: `jsonable_encoder(rows)` where rows are SQLAlchemy Truck instances. FastAPI's jsonable_encoder turns each instance into a dict with the model's mapped attribute names as keys (id, tenant_id, plate_number, model, driver_name), so the response is a list of dicts. Conclusion: The declared type and the actual shape match: a list of dicts with the Truck attributes. No mismatch.

**Optional follow-up (no code change):** Introduce a Pydantic response model (e.g. FleetTruckOut) and use response_model=List[FleetTruckOut] for a stable, documented API contract; not required for consistency.

---

## 6. Phase 2 pre-migration command list (tenant_demo)

One-command-at-a-time, read-only. DB: tenant_demo. No migrations, no schema changes.

**Multi-tenant note (report-only):** Run this same checklist against each tenant database that will receive the composite-FK migration (replace tenant_demo accordingly). The examples below use tenant_demo only as a concrete target.

### (a) Evidence pre-checks

**Command 1 — Constraints on drivers, brokers, driver_documents (UNIQUE / PRIMARY KEY):**

```bash
docker exec truckerp-postgres psql -U postgres -d tenant_demo -c "
SELECT tc.table_name,
       tc.constraint_name,
       tc.constraint_type,
       string_agg(kcu.column_name, ', ' ORDER BY kcu.ordinal_position) AS columns
FROM information_schema.table_constraints tc
JOIN information_schema.key_column_usage kcu
  ON tc.constraint_name = kcu.constraint_name
  AND tc.table_schema = kcu.table_schema
WHERE tc.table_schema = 'public'
  AND tc.table_name IN ('drivers', 'brokers', 'driver_documents')
  AND tc.constraint_type IN ('UNIQUE', 'PRIMARY KEY')
GROUP BY tc.table_name, tc.constraint_name, tc.constraint_type
ORDER BY tc.table_name, tc.constraint_name;
"
```

Expected "good" (pre-migration): No row with columns = 'tenant_id, id'. You should see only PK on id and any other UNIQUEs (e.g. payee_id). So "good" here means "we confirmed UNIQUE(tenant_id, id) is missing and will be added in Phase 3/4".

**Command 2 — id and tenant_id column types:**

```bash
docker exec truckerp-postgres psql -U postgres -d tenant_demo -c "
SELECT table_name, column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name IN ('drivers', 'brokers', 'driver_documents')
  AND column_name IN ('id', 'tenant_id')
ORDER BY table_name, ordinal_position;
"
```

Expected "good": Six rows (id and tenant_id for each table); data_type = integer, is_nullable = NO for all.

### (b) Violation counts (4 checks)

**Command 3 — driver_documents → drivers:**

```bash
docker exec truckerp-postgres psql -U postgres -d tenant_demo -c "
SELECT COUNT(*)
FROM driver_documents dd
JOIN drivers d ON d.id = dd.driver_id
WHERE dd.tenant_id IS DISTINCT FROM d.tenant_id;
"
```

Expected "good": count = 0.

**Command 3b — Orphan check (driver_documents → drivers):**

```bash
docker exec truckerp-postgres psql -U postgres -d tenant_demo -c "
SELECT COUNT(*)
FROM driver_documents dd
LEFT JOIN drivers d ON d.id = dd.driver_id
WHERE d.id IS NULL;
"
```

Expected "good": count = 0.

*Why this matters (report-only):* The mismatch check uses an INNER JOIN and will not count orphan rows. Orphans will cause the composite FK add/validate step to fail.

**Command 4 — driver_document_files → driver_documents:**

```bash
docker exec truckerp-postgres psql -U postgres -d tenant_demo -c "
SELECT COUNT(*)
FROM driver_document_files ddf
JOIN driver_documents dd ON dd.id = ddf.driver_document_id
WHERE ddf.tenant_id IS DISTINCT FROM dd.tenant_id;
"
```

Expected "good": count = 0.

**Command 4b — Orphan check (driver_document_files → driver_documents):**

```bash
docker exec truckerp-postgres psql -U postgres -d tenant_demo -c "
SELECT COUNT(*)
FROM driver_document_files ddf
LEFT JOIN driver_documents dd ON dd.id = ddf.driver_document_id
WHERE dd.id IS NULL;
"
```

Expected "good": count = 0.

**Command 5 — loads → drivers:**

```bash
docker exec truckerp-postgres psql -U postgres -d tenant_demo -c "
SELECT COUNT(*)
FROM loads l
JOIN drivers d ON d.id = l.driver_id
WHERE l.tenant_id IS DISTINCT FROM d.tenant_id;
"
```

Expected "good": count = 0.

**Command 5b — Orphan check (loads → drivers):**

```bash
docker exec truckerp-postgres psql -U postgres -d tenant_demo -c "
SELECT COUNT(*)
FROM loads l
LEFT JOIN drivers d ON d.id = l.driver_id
WHERE l.driver_id IS NOT NULL
  AND d.id IS NULL;
"
```

Expected "good": count = 0.

**Command 6 — loads → brokers:**

```bash
docker exec truckerp-postgres psql -U postgres -d tenant_demo -c "
SELECT COUNT(*)
FROM loads l
JOIN brokers b ON b.id = l.broker_id
WHERE l.tenant_id IS DISTINCT FROM b.tenant_id;
"
```

Expected "good": count = 0.

**Command 6b — Orphan check (loads → brokers):**

```bash
docker exec truckerp-postgres psql -U postgres -d tenant_demo -c "
SELECT COUNT(*)
FROM loads l
LEFT JOIN brokers b ON b.id = l.broker_id
WHERE l.broker_id IS NOT NULL
  AND b.id IS NULL;
"
```

Expected "good": count = 0.

If any of commands 3–6 return a count > 0, run the optional list-violations queries below and the remediation playbook (REMEDIATION §9) before Phase 3/4.

### (c) Optional — list violations (for remediation)

Only needed if one of the counts above was > 0.

**Command 7 — List driver_documents ↔ drivers violations:**

```bash
docker exec truckerp-postgres psql -U postgres -d tenant_demo -c "
SELECT dd.id AS driver_document_id, dd.tenant_id AS doc_tenant_id, dd.driver_id, d.tenant_id AS driver_tenant_id
FROM driver_documents dd
JOIN drivers d ON d.id = dd.driver_id
WHERE dd.tenant_id IS DISTINCT FROM d.tenant_id;
"
```

Expected "good": 0 rows.

**Command 8 — List driver_document_files ↔ driver_documents violations:**

```bash
docker exec truckerp-postgres psql -U postgres -d tenant_demo -c "
SELECT ddf.id AS file_id, ddf.tenant_id AS file_tenant_id, ddf.driver_document_id, dd.tenant_id AS doc_tenant_id
FROM driver_document_files ddf
JOIN driver_documents dd ON dd.id = ddf.driver_document_id
WHERE ddf.tenant_id IS DISTINCT FROM dd.tenant_id;
"
```

Expected "good": 0 rows.

**Command 9 — List loads ↔ drivers violations:**

```bash
docker exec truckerp-postgres psql -U postgres -d tenant_demo -c "
SELECT l.id AS load_id, l.tenant_id AS load_tenant_id, l.driver_id, d.tenant_id AS driver_tenant_id
FROM loads l
JOIN drivers d ON d.id = l.driver_id
WHERE l.tenant_id IS DISTINCT FROM d.tenant_id;
"
```

Expected "good": 0 rows.

**Command 10 — List loads ↔ brokers violations:**

```bash
docker exec truckerp-postgres psql -U postgres -d tenant_demo -c "
SELECT l.id AS load_id, l.tenant_id AS load_tenant_id, l.broker_id, b.tenant_id AS broker_tenant_id
FROM loads l
JOIN brokers b ON b.id = l.broker_id
WHERE l.tenant_id IS DISTINCT FROM b.tenant_id;
"
```

Expected "good": 0 rows.

### Order summary

| Step | Command | Purpose |
|------|---------|---------|
| (a) | 1, 2 | Evidence: constraints and column types |
| (b) | 3, 4, 5, 6 | Violation counts (all must be 0 for Phase 3/4) |
| (c) | 7, 8, 9, 10 | Optional: list violating rows if any count > 0 |

---

## 7. Document references

- **TENANT_SAFETY_REMEDIATION_PLAN.md:** Pre-check SQL (§1), data-violation SQL (§2), migration steps (§3), index plan (§4), acceptance checks (§5), evidence (§6), locking/Variant A&B (§7), index redundancy (§8), remediation playbook (§9), naming (§10).
- **APP_LAYER_TENANT_SAFETY_AUDIT_PLAN.md:** Grep patterns (§1), checklist (§2), anti-patterns (§3), safe-query template (§4), acceptance criteria (§5), evidence tables and gaps (§6).

**NO IMPLEMENTATION. NO CODE. NO SCHEMA CHANGES. REPORT ONLY.**

✅ This keeps your original content intact and adds the new audit findings without chopping sections.
