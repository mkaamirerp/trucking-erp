# Tenant-Safety Remediation Plan (tenant_demo)

**Rules: REPORT/PLAN ONLY. No code changes. No migrations applied. No schema edits.**

**Context (blockers):**
- Non-composite FKs: `driver_documents.driver_id` → `drivers.id`, `driver_document_files.driver_document_id` → `driver_documents.id`, `loads.broker_id` → `brokers.id`, `loads.driver_id` → `drivers.id`
- Index gaps: `driver_documents(tenant_id, driver_id)`, `driver_document_files(tenant_id, driver_document_id)`, `loads(tenant_id, status)`, `loads(tenant_id, driver_id)`, `loads(tenant_id, broker_id)`

---

## Section 1: Pre-check SQL

**1.1 — Verify parent tables have tenant-safe identity (UNIQUE on (tenant_id, id))**

```sql
-- List all unique and primary-key constraints on drivers, brokers, driver_documents.
-- For composite FK targets we need at least one UNIQUE or PRIMARY KEY on (tenant_id, id).
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
```

If no row exists with `columns = 'tenant_id, id'` for a given table, that table cannot be the target of a composite FK and must get `UNIQUE (tenant_id, id)` in the migration (see Section 3).

**1.2 — Alternative: check by constraint definition (index-backed)**

```sql
SELECT c.conrelid::regclass AS table_name,
       c.conname,
       pg_get_constraintdef(c.oid, true) AS definition
FROM pg_constraint c
WHERE c.conrelid IN ('public.drivers'::regclass, 'public.brokers'::regclass, 'public.driver_documents'::regclass)
  AND c.contype IN ('u', 'p')
ORDER BY c.conrelid::regclass::text, c.conname;
```

---

## Section 2: Data-violation SQL

Run these **before** changing FKs. Any non-zero row count indicates existing cross-tenant data that must be fixed or excluded before adding composite FKs (composite FK would fail on insert/update of violating rows). Orphans are unlikely because existing FKs should prevent them unless constraints were NOT VALID/disabled or data was loaded out-of-band; optional orphan checks are still fine.

**2.1 — driver_documents → drivers (tenant_id mismatch)**

```sql
SELECT COUNT(*)
FROM driver_documents dd
JOIN drivers d ON d.id = dd.driver_id
WHERE dd.tenant_id IS DISTINCT FROM d.tenant_id;
```

**2.2 — driver_document_files → driver_documents (tenant_id mismatch)**

```sql
SELECT COUNT(*)
FROM driver_document_files ddf
JOIN driver_documents dd ON dd.id = ddf.driver_document_id
WHERE ddf.tenant_id IS DISTINCT FROM dd.tenant_id;
```

**2.3 — loads → drivers (tenant_id mismatch)**

```sql
SELECT COUNT(*)
FROM loads l
JOIN drivers d ON d.id = l.driver_id
WHERE l.tenant_id IS DISTINCT FROM d.tenant_id;
```

**2.4 — loads → brokers (tenant_id mismatch)**

```sql
SELECT COUNT(*)
FROM loads l
JOIN brokers b ON b.id = l.broker_id
WHERE l.tenant_id IS DISTINCT FROM b.tenant_id;
```

**2.5 — Optional: list violating rows (for remediation)**

```sql
-- driver_documents ↔ drivers
SELECT dd.id AS driver_document_id, dd.tenant_id AS doc_tenant_id, dd.driver_id, d.tenant_id AS driver_tenant_id
FROM driver_documents dd
JOIN drivers d ON d.id = dd.driver_id
WHERE dd.tenant_id IS DISTINCT FROM d.tenant_id;

-- driver_document_files ↔ driver_documents
SELECT ddf.id AS file_id, ddf.tenant_id AS file_tenant_id, ddf.driver_document_id, dd.tenant_id AS doc_tenant_id
FROM driver_document_files ddf
JOIN driver_documents dd ON dd.id = ddf.driver_document_id
WHERE ddf.tenant_id IS DISTINCT FROM dd.tenant_id;

-- loads ↔ drivers
SELECT l.id AS load_id, l.tenant_id AS load_tenant_id, l.driver_id, d.tenant_id AS driver_tenant_id
FROM loads l
JOIN drivers d ON d.id = l.driver_id
WHERE l.tenant_id IS DISTINCT FROM d.tenant_id;

-- loads ↔ brokers
SELECT l.id AS load_id, l.tenant_id AS load_tenant_id, l.broker_id, b.tenant_id AS broker_tenant_id
FROM loads l
JOIN brokers b ON b.id = l.broker_id
WHERE l.tenant_id IS DISTINCT FROM b.tenant_id;
```

---

## Section 3: Migration plan steps (numbered)

**Prerequisite:** Run Section 2. If any violation count &gt; 0, fix data (e.g. align tenant_id or set driver_id/broker_id/driver_document_id to NULL where appropriate) so that after migration no row would violate the new composite FKs.

**3.1 — Add unique constraints on parent tables (required for composite FK targets)**

- **drivers:** Add `UNIQUE (tenant_id, id)`. Name suggestion: `uq_drivers_tenant_id_id`.  
  (PK is already `(id)`; adding this does not change PK, only adds a unique constraint so `(tenant_id, id)` can be referenced.)
- **brokers:** Add `UNIQUE (tenant_id, id)`. Name suggestion: `uq_brokers_tenant_id_id`.
- **driver_documents:** Add `UNIQUE (tenant_id, id)`. Name suggestion: `uq_driver_documents_tenant_id_id`.

Order: Can be done in any order (no FK dependencies between these three). Run in a single transaction to avoid partial state.

**3.2 — driver_documents: convert FK to composite**

- Drop existing constraint: `fk_driver_document_driver_id` (FK: `driver_id` → `drivers(id)`).
- Create new constraint: e.g. `fk_driver_documents_tenant_driver_to_drivers` on `(tenant_id, driver_id)` → `drivers(tenant_id, id)` with same delete rule (e.g. ON DELETE CASCADE).

**3.3 — driver_document_files: convert FK to composite**

- Drop: `fk_driver_document_files_driver_document_id` (FK: `driver_document_id` → `driver_documents(id)`).
- Create: e.g. `fk_driver_document_files_tenant_doc_to_driver_documents` on `(tenant_id, driver_document_id)` → `driver_documents(tenant_id, id)` (ON DELETE CASCADE).

**3.4 — loads: convert broker FK to composite**

- Drop: `loads_broker_id_fkey` (FK: `broker_id` → `brokers(id)`).
- Create: e.g. `fk_loads_tenant_broker_to_brokers` on `(tenant_id, broker_id)` → `brokers(tenant_id, id)`. Match current delete rule (e.g. ON DELETE RESTRICT). Note: `loads.broker_id` can be NULL; composite FK still allows NULLs (rows with broker_id NULL are not checked).

**3.5 — loads: convert driver FK to composite**

- Drop: `loads_driver_id_fkey` (FK: `driver_id` → `drivers(id)`).
- Create: e.g. `fk_loads_tenant_driver_to_drivers` on `(tenant_id, driver_id)` → `drivers(tenant_id, id)` (e.g. ON DELETE SET NULL).

**Drop/add order (downtime):**

- **Order:** 3.1 first (all three UNIQUEs). Then 3.2, 3.3 (driver_documents subtree). Then 3.4, 3.5 (loads). No need to drop child FKs before parent FKs here because we are only replacing FKs on the same tables.
- **Transaction / downtime:** A single transaction avoids a *committed* intermediate state without FKs; other sessions won't observe a FK-less state unless the transaction commits. Avoid long-running transactions; no table rewrites required. Adding UNIQUE(tenant_id, id) creates an index and validates uniqueness (full scan).

**Constraint names:** Use the exact names from `\d+ table_name` when dropping. Create names as above or match project naming (e.g. `fk_<child>_tenant_<role>_to_<parent>`).

---

## Section 4: Index plan steps (numbered)

**4.1 — driver_documents**

- Add index: `(tenant_id, driver_id)`. Name suggestion: `ix_driver_documents_tenant_driver_id`.  
- **Redundancy:** `ix_driver_documents_tenant_id` (tenant_id only) is a prefix of the new index; some optimizers can use the composite for tenant-only queries. Optional: drop `ix_driver_documents_tenant_id` later if proven redundant. `ix_driver_documents_driver_id` (driver_id only) does not cover tenant-scoped lookups; keep for now unless all queries are tenant+driver.

**4.2 — driver_document_files**

- Add index: `(tenant_id, driver_document_id)`. Name suggestion: `ix_driver_document_files_tenant_document_id`.  
- **Redundancy:** `ix_driver_document_files_tenant_id` may become redundant for tenant-only scans; optional to drop later. Keep `ix_driver_document_files_driver_document_id` unless all access is tenant+document.

**4.3 — loads**

- Add index: `(tenant_id, status)`. Name suggestion: `ix_loads_tenant_status`.  
- Add index: `(tenant_id, driver_id)`. Name suggestion: `ix_loads_tenant_driver_id`.  
- Add index: `(tenant_id, broker_id)`. Name suggestion: `ix_loads_tenant_broker_id`.  
- **Redundancy:** `ix_loads_tenant_id` is a prefix of all three; consider keeping for simple tenant-only lists or drop after confirming composite indexes are used. `ix_loads_status`, `ix_loads_driver_id`, `ix_loads_broker_id` are single-column; keep for now unless all queries are tenant-scoped (then composite can serve).

**4.4 — When to create indexes**

- Option A: In the same migration as the composite FKs (after adding UNIQUEs and FKs), so schema and performance are updated together.
- Option B: Separate migration after FKs, to keep steps smaller and measurable.

---

## Section 5: Acceptance checks SQL

Run after migration. All violation counts must be 0; constraint and index checks must show the new state.

**5.1 — No cross-tenant violations (same as Section 2; all must return 0)**

```sql
SELECT 'driver_documents→drivers' AS check_name, COUNT(*) AS violations
FROM driver_documents dd
JOIN drivers d ON d.id = dd.driver_id
WHERE dd.tenant_id IS DISTINCT FROM d.tenant_id
UNION ALL
SELECT 'driver_document_files→driver_documents',
       COUNT(*)
FROM driver_document_files ddf
JOIN driver_documents dd ON dd.id = ddf.driver_document_id
WHERE ddf.tenant_id IS DISTINCT FROM dd.tenant_id
UNION ALL
SELECT 'loads→drivers', COUNT(*)
FROM loads l
JOIN drivers d ON d.id = l.driver_id
WHERE l.tenant_id IS DISTINCT FROM d.tenant_id
UNION ALL
SELECT 'loads→brokers', COUNT(*)
FROM loads l
JOIN brokers b ON b.id = l.broker_id
WHERE l.tenant_id IS DISTINCT FROM b.tenant_id;
```

**5.2 — Composite FKs exist (constraint_type and columns)**

```sql
SELECT tc.table_name,
       tc.constraint_name,
       string_agg(kcu.column_name, ', ' ORDER BY kcu.ordinal_position) AS fk_columns,
       ccu.table_name AS ref_table,
       string_agg(ccu.column_name, ', ' ORDER BY kcu.ordinal_position) AS ref_columns
FROM information_schema.table_constraints tc
JOIN information_schema.key_column_usage kcu
  ON tc.constraint_name = kcu.constraint_name AND tc.table_schema = kcu.table_schema
JOIN information_schema.constraint_column_usage ccu
  ON ccu.constraint_name = tc.constraint_name
WHERE tc.constraint_type = 'FOREIGN KEY'
  AND tc.table_schema = 'public'
  AND tc.table_name IN ('driver_documents', 'driver_document_files', 'loads')
GROUP BY tc.table_name, tc.constraint_name, ccu.table_name
ORDER BY tc.table_name, tc.constraint_name;
```

Expected: Each of the four FKs shows **two** columns (tenant_id and the id column) in both fk_columns and ref_columns. No single-column FK from these tables to drivers, brokers, or driver_documents.

**5.3 — Parent UNIQUE(tenant_id, id) exist**

```sql
SELECT tc.table_name, tc.constraint_name, tc.constraint_type,
       string_agg(kcu.column_name, ', ' ORDER BY kcu.ordinal_position) AS columns
FROM information_schema.table_constraints tc
JOIN information_schema.key_column_usage kcu
  ON tc.constraint_name = kcu.constraint_name AND tc.table_schema = kcu.table_schema
WHERE tc.table_schema = 'public'
  AND tc.table_name IN ('drivers', 'brokers', 'driver_documents')
  AND tc.constraint_type IN ('UNIQUE', 'PRIMARY KEY')
GROUP BY tc.table_name, tc.constraint_name, tc.constraint_type
ORDER BY tc.table_name, tc.constraint_name;
```

Expected: At least one constraint per table with `columns = 'tenant_id, id'` (or equivalent order).

**5.4 — Composite indexes exist**

```sql
SELECT tablename, indexname, indexdef
FROM pg_indexes
WHERE schemaname = 'public'
  AND tablename IN ('driver_documents', 'driver_document_files', 'loads')
  AND (indexdef LIKE '%tenant_id%' AND indexdef LIKE '%driver_id%'
       OR indexdef LIKE '%tenant_id%' AND indexdef LIKE '%driver_document_id%'
       OR indexdef LIKE '%tenant_id%' AND indexdef LIKE '%status%'
       OR indexdef LIKE '%tenant_id%' AND indexdef LIKE '%broker_id%')
ORDER BY tablename, indexname;
```

Expected: Indexes covering (tenant_id, driver_id), (tenant_id, driver_document_id), (tenant_id, status), (tenant_id, driver_id), (tenant_id, broker_id) as per Section 4.

---

## Acceptance criteria (summary)

- **DB prevents cross-tenant references:** All four FKs are composite (tenant_id + id column); Section 5.2 confirms. Composite FKs enforce referential integrity (prevent cross-tenant references at write-time), but the application must still include tenant filters in queries/joins to avoid cross-tenant reads.
- **No existing violations:** Section 5.1 returns 0 for all four checks.
- **Tenant-scoped queries remain fast:** Section 5.4 confirms the planned composite indexes exist.
- **Rerunnable proof:** Sections 5.1–5.4 are the exact SQL queries to rerun to prove no violations and correct constraints/indexes.

---

## Section 6: Evidence — Assumptions (SQL + expected output)

**6.1 — Do UNIQUE(tenant_id, id) exist?**

Run:

```sql
SELECT tc.table_name,
       tc.constraint_name,
       tc.constraint_type,
       string_agg(kcu.column_name, ', ' ORDER BY kcu.ordinal_position) AS columns
FROM information_schema.table_constraints tc
JOIN information_schema.key_column_usage kcu
  ON tc.constraint_name = kcu.constraint_name AND tc.table_schema = kcu.table_schema
WHERE tc.table_schema = 'public'
  AND tc.table_name IN ('drivers', 'brokers', 'driver_documents')
  AND tc.constraint_type IN ('UNIQUE', 'PRIMARY KEY')
GROUP BY tc.table_name, tc.constraint_name, tc.constraint_type
ORDER BY tc.table_name, tc.constraint_name;
```

**Expected columns:** `table_name`, `constraint_name`, `constraint_type`, `columns`

**Actual evidence (tenant_demo):**

| table_name       | constraint_name         | constraint_type | columns   |
|------------------|-------------------------|-----------------|-----------|
| brokers          | brokers_pkey            | PRIMARY KEY     | id        |
| driver_documents | driver_documents_pkey   | PRIMARY KEY     | id        |
| drivers          | drivers_pkey            | PRIMARY KEY     | id        |
| drivers          | uq_drivers_payee_id      | UNIQUE          | payee_id  |

**Conclusion:** None of the three tables has a constraint on `(tenant_id, id)`. UNIQUE(tenant_id, id) is **required** on all three for composite FK targets. The PK is `(id)` only; it does not imply uniqueness of (tenant_id, id).

**6.2 — id type and PK**

Run:

```sql
SELECT table_name, column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name IN ('drivers', 'brokers', 'driver_documents')
  AND column_name IN ('id', 'tenant_id')
ORDER BY table_name, ordinal_position;
```

**Expected columns:** `table_name`, `column_name`, `data_type`, `is_nullable`

**Actual evidence (tenant_demo):**

| table_name       | column_name | data_type | is_nullable |
|------------------|-------------|-----------|-------------|
| brokers          | id          | integer   | NO          |
| brokers          | tenant_id   | integer   | NO          |
| driver_documents | id          | integer   | NO          |
| driver_documents | tenant_id   | integer   | NO          |
| drivers          | id          | integer   | NO          |
| drivers          | tenant_id   | integer   | NO          |

**Conclusion:** `id` is **integer** and NOT NULL on all three; `tenant_id` is **integer** and NOT NULL. The new UNIQUE(tenant_id, id) is not redundant with the PK (PK is id only); it is required for composite FK references.

---

## Section 7: Locking / downtime analysis (Postgres)

**7.1 — Per-step lock and risk**

| Step | Operation | Locks (typical) | Risk in production |
|------|------------|------------------|---------------------|
| Add UNIQUE(tenant_id, id) | CREATE UNIQUE INDEX (default) | ShareLock on table for duration of index build; blocks writes (INSERT/UPDATE/DELETE) on that table until index is built | **High** if table is large: full table scan + index build; can take seconds to minutes. |
| Add UNIQUE via CREATE UNIQUE INDEX CONCURRENTLY | Index build with minimal lock | Does not take full ShareLock for whole build; allows concurrent writes | **Low**; build is longer but non-blocking. Cannot run inside explicit transaction (Postgres limitation). |
| DROP CONSTRAINT (FK) | ALTER TABLE ... DROP CONSTRAINT | AccessExclusiveLock | **Low** if quick; duration depends on contention. |
| ADD CONSTRAINT (FK) | ALTER TABLE ... ADD CONSTRAINT | Strong locks; validation scan on child table | **Variable**; ADD FOREIGN KEY performs validation that can hold locks longer on large tables. Don't assume "brief"—duration depends on table size and activity. |
| CREATE INDEX (non-unique) | CREATE INDEX (default) | ShareLock on table for duration | Same as UNIQUE index build; use CONCURRENTLY for prod. |

**Practical advice:** Use `lock_timeout` and retry logic where appropriate; lock duration for DROP/ADD CONSTRAINT is not guaranteed to be brief.

**7.2 — Variant A (dev/simple): one-transaction approach**

- Use for: dev, staging, or small tables where brief blocking is acceptable.
- A single transaction avoids a *committed* intermediate state without FKs; other sessions won't observe a FK-less state unless the transaction commits.

**Steps:**

1. BEGIN;
2. Add UNIQUE(tenant_id, id) on **drivers** (creates index; holds lock for duration).
3. Add UNIQUE(tenant_id, id) on **brokers**.
4. Add UNIQUE(tenant_id, id) on **driver_documents**.
5. Drop FK `fk_driver_document_driver_id` on driver_documents; add composite FK driver_documents(tenant_id, driver_id) → drivers(tenant_id, id).
6. Drop FK `fk_driver_document_files_driver_document_id` on driver_document_files; add composite FK driver_document_files(tenant_id, driver_document_id) → driver_documents(tenant_id, id).
7. Drop FK `loads_broker_id_fkey`; add composite FK loads(tenant_id, broker_id) → brokers(tenant_id, id).
8. Drop FK `loads_driver_id_fkey`; add composite FK loads(tenant_id, driver_id) → drivers(tenant_id, id).
9. Create new composite indexes (driver_documents, driver_document_files, loads) — or in a follow-up migration.
10. COMMIT;

**Downtime:** Entire transaction duration. Keep it short; avoid long-running DDL in same transaction.

**7.3 — Variant B (prod-safe): concurrent index + constraint attach, then FK changes**

- Use for: production; large tables; need to avoid long blocking writes.

**Phase 1 — Concurrent unique indexes (no transaction; each statement autocommit)**

1. `CREATE UNIQUE INDEX CONCURRENTLY uq_drivers_tenant_id_id ON drivers (tenant_id, id);`
2. **REQUIRED — Index validity check:** Verify the new index is valid before attaching the constraint. Check `pg_index.indisvalid = true` for the index (e.g. `SELECT indexrelid::regclass, indisvalid FROM pg_index WHERE indexrelid = 'uq_drivers_tenant_id_id'::regclass;`). Optionally monitor progress with `pg_stat_progress_create_index`. Only after validity is confirmed, run: `ALTER TABLE drivers ADD CONSTRAINT uq_drivers_tenant_id_id UNIQUE USING INDEX uq_drivers_tenant_id_id;` Verify your Postgres version supports `ALTER TABLE … ADD CONSTRAINT … UNIQUE USING INDEX …` (widely supported in modern PG), and use it to attach the already-built unique index without a second table scan.
3. Repeat for **brokers**: CREATE UNIQUE INDEX CONCURRENTLY, then **check pg_index.indisvalid**, then ALTER TABLE ... ADD CONSTRAINT ... UNIQUE USING INDEX ...
4. Repeat for **driver_documents**: CREATE UNIQUE INDEX CONCURRENTLY, then **check pg_index.indisvalid**, then ALTER TABLE ... ADD CONSTRAINT ... UNIQUE USING INDEX ...

**Phase 2 — FK changes (can be one transaction)**

5. BEGIN;
6. Drop/add the four FKs as in Section 3 (driver_documents → drivers; driver_document_files → driver_documents; loads → broker; loads → driver).
7. COMMIT;

**Phase 3 — Optional: composite indexes CONCURRENTLY (separate, no transaction)**

8. CREATE INDEX CONCURRENTLY ... for each of the five composite indexes (driver_documents, driver_document_files, loads x3).

**Adaptation note:** CONCURRENTLY cannot run inside an explicit transaction. So Phase 1 and Phase 3 run as standalone statements; only Phase 2 is a single transaction. If a CONCURRENTLY build fails (e.g. duplicate key), the invalid index may remain and must be dropped before retrying.

---

## Section 8: Index redundancy table

| New composite index | Table | Existing single-column index that becomes redundant | Reason | Recommendation |
|---------------------|--------|------------------------------------------------------|--------|-----------------|
| (tenant_id, driver_id) | driver_documents | ix_driver_documents_tenant_id | Left prefix of composite; planner can use composite for WHERE tenant_id = ? | **Drop later** after confirming plans use the composite (e.g. EXPLAIN on tenant-scoped queries). |
| (tenant_id, driver_id) | driver_documents | ix_driver_documents_driver_id | Not redundant; driver_id-only queries not covered by (tenant_id, driver_id) | **Keep.** |
| (tenant_id, driver_document_id) | driver_document_files | ix_driver_document_files_tenant_id | Left prefix | **Drop later** if tenant-only queries use composite. |
| (tenant_id, driver_document_id) | driver_document_files | ix_driver_document_files_driver_document_id | Not redundant for document-only lookups | **Keep.** |
| (tenant_id, status) | loads | ix_loads_tenant_id | Left prefix | **Drop later** if tenant-only lists use (tenant_id, status) or other composite. |
| (tenant_id, status) | loads | ix_loads_status | Not redundant for status-only filters | **Keep.** |
| (tenant_id, driver_id) | loads | (same ix_loads_tenant_id) | Prefix | **Drop later** (one drop of ix_loads_tenant_id if all tenant queries use composites). |
| (tenant_id, driver_id) | loads | ix_loads_driver_id | Not redundant | **Keep.** |
| (tenant_id, broker_id) | loads | (same ix_loads_tenant_id) | Prefix | See above. **Drop later.** |
| (tenant_id, broker_id) | loads | ix_loads_broker_id | Not redundant | **Keep.** |

**Rule:** Do **not** drop any index in the same change that adds the composite. Drop only in a later migration after verifying query plans and load.

---

## Section 9: Data remediation playbook (SQL-only)

If Section 2 violation counts are &gt; 0, fix before adding composite FKs.

**9.1 — driver_documents → drivers (tenant_id mismatch)**

- **Option A — Fix child tenant_id to match parent (preferred when document belongs to driver’s tenant):**  
  Update `driver_documents.tenant_id` to match `drivers.tenant_id` for the joined driver.  
- **Option B — Repoint FK:** Set `driver_documents.driver_id = NULL` (if nullable) or update to a driver in the same tenant.  
- **Option C — Delete orphan (last resort):** Delete driver_document rows that reference a driver in another tenant (only if business rules allow).

**SQL — List violations:**

```sql
SELECT dd.id AS driver_document_id, dd.tenant_id AS doc_tenant_id, dd.driver_id, d.tenant_id AS driver_tenant_id
FROM driver_documents dd
JOIN drivers d ON d.id = dd.driver_id
WHERE dd.tenant_id IS DISTINCT FROM d.tenant_id;
```

**SQL — Fix tenant_id to match parent (Option A):**

```sql
UPDATE driver_documents dd
SET tenant_id = d.tenant_id
FROM drivers d
WHERE d.id = dd.driver_id
  AND dd.tenant_id IS DISTINCT FROM d.tenant_id;
```

**SQL — Repoint: set driver_id to NULL (Option B, if column nullable):**

```sql
UPDATE driver_documents dd
SET driver_id = NULL
FROM drivers d
WHERE d.id = dd.driver_id
  AND dd.tenant_id IS DISTINCT FROM d.tenant_id;
```

**9.2 — driver_document_files → driver_documents (tenant_id mismatch)**

- **Option A:** Update `driver_document_files.tenant_id` to match `driver_documents.tenant_id`.
- **Option B:** Set `driver_document_id = NULL` if nullable (rare).
- **Option C:** Delete file rows that point at a document in another tenant (last resort).

**SQL — List:**

```sql
SELECT ddf.id AS file_id, ddf.tenant_id AS file_tenant_id, ddf.driver_document_id, dd.tenant_id AS doc_tenant_id
FROM driver_document_files ddf
JOIN driver_documents dd ON dd.id = ddf.driver_document_id
WHERE ddf.tenant_id IS DISTINCT FROM dd.tenant_id;
```

**SQL — Fix tenant_id (Option A):**

```sql
UPDATE driver_document_files ddf
SET tenant_id = dd.tenant_id
FROM driver_documents dd
WHERE dd.id = ddf.driver_document_id
  AND ddf.tenant_id IS DISTINCT FROM dd.tenant_id;
```

**9.3 — loads → drivers (tenant_id mismatch)**

- **Option A:** Update `loads.tenant_id` to match `drivers.tenant_id` (only if load truly belongs to driver’s tenant).
- **Option B:** Set `loads.driver_id = NULL` (unassign driver).
- **Option C:** Delete load (last resort; usually wrong).

**SQL — List:**

```sql
SELECT l.id AS load_id, l.tenant_id AS load_tenant_id, l.driver_id, d.tenant_id AS driver_tenant_id
FROM loads l
JOIN drivers d ON d.id = l.driver_id
WHERE l.tenant_id IS DISTINCT FROM d.tenant_id;
```

**SQL — Fix tenant_id (Option A) or unassign driver (Option B):**

```sql
-- Option A (use with care: changes load’s tenant)
UPDATE loads l
SET tenant_id = d.tenant_id
FROM drivers d
WHERE d.id = l.driver_id
  AND l.tenant_id IS DISTINCT FROM d.tenant_id;

-- Option B (unassign driver)
UPDATE loads l
SET driver_id = NULL
FROM drivers d
WHERE d.id = l.driver_id
  AND l.tenant_id IS DISTINCT FROM d.tenant_id;
```

**9.4 — loads → brokers (tenant_id mismatch)**

- **Option A:** Update `loads.tenant_id` to match `brokers.tenant_id` (only if load truly belongs to broker’s tenant).
- **Option B:** Set `loads.broker_id = NULL`.
- **Option C:** Delete load (last resort).

**SQL — List:**

```sql
SELECT l.id AS load_id, l.tenant_id AS load_tenant_id, l.broker_id, b.tenant_id AS broker_tenant_id
FROM loads l
JOIN brokers b ON b.id = l.broker_id
WHERE l.tenant_id IS DISTINCT FROM b.tenant_id;
```

**SQL — Fix tenant_id (Option A) or unassign broker (Option B):**

```sql
-- Option A
UPDATE loads l
SET tenant_id = b.tenant_id
FROM brokers b
WHERE b.id = l.broker_id
  AND l.tenant_id IS DISTINCT FROM b.tenant_id;

-- Option B
UPDATE loads l
SET broker_id = NULL
FROM brokers b
WHERE b.id = l.broker_id
  AND l.tenant_id IS DISTINCT FROM b.tenant_id;
```

**Safety:** Run LIST queries first; fix in a transaction with a final re-run of Section 2 counts to confirm 0 before running the composite FK migration.

---

## Section 10: Naming standards

Use consistently across the repo.

**10.1 — Unique constraints (tenant_id + id)**

- Pattern: `uq_<table>_tenant_id_id`
- Examples: `uq_drivers_tenant_id_id`, `uq_brokers_tenant_id_id`, `uq_driver_documents_tenant_id_id`

**10.2 — Composite indexes**

- Pattern: `ix_<table>_<column1>_<column2>` (and `ix_<table>_tenant_<suffix>` where the leading column is tenant_id).
- Examples:
  - `ix_driver_documents_tenant_driver_id` for (tenant_id, driver_id)
  - `ix_driver_document_files_tenant_document_id` for (tenant_id, driver_document_id)
  - `ix_loads_tenant_status`, `ix_loads_tenant_driver_id`, `ix_loads_tenant_broker_id`

**10.3 — Composite FK constraints**

- Pattern: `fk_<child_table>_tenant_<role>_to_<parent_table>`
- Examples:
  - `fk_driver_documents_tenant_driver_to_drivers`
  - `fk_driver_document_files_tenant_doc_to_driver_documents`
  - `fk_loads_tenant_broker_to_brokers`
  - `fk_loads_tenant_driver_to_drivers`

**Consistency:** Align with existing names (e.g. `fk_person_roles_tenant_person_to_people`, `ux_driver_profiles_tenant_person_id`) so tenant-scoped constraints and indexes are recognizable by name.

---

NO CHANGES MADE. REPORT/PLAN ONLY.
