# Load numbering — read-only report (2026-10-24)

**Mode:** Investigation only. **No code, schema, migration, API, or UI changes.**

**Owner decision (locked):** [`LOAD_NUMBERING_OWNER_DECISION_2026-10-24.md`](./LOAD_NUMBERING_OWNER_DECISION_2026-10-24.md).

**DB spot-check (read-only, disposable / non–`tenant_demo` where noted):**

| Database | `alembic_version` | `tenant_dispatch_numbering` | `loads` uniqueness |
|----------|-------------------|----------------------------|-------------------|
| `tenant_demo` | `fmp02_fmp_tenant_scope` | present | `uq_loads_tenant_load_number` |
| `tenant_flowtest_3cb8dd02` | `c4d5e6f7a8b9` (behind current heads) | **absent** (revision predates dispatch numbering migration) | `uq_loads_tenant_load_number` |
| `tenant_beartest_085a72a4` | `dw1c_composite_fk_set_null_optional_columns` | present (`tenant_id`, `trip_number_prefix`, `prefix_locked_at`, `next_numeric`, timestamps) | `uq_loads_tenant_load_number` |

**Container graph (2026-10-24):** `alembic -c alembic_tenant.ini heads` → `fmp02_fmp_tenant_scope (head)` and `i14_load_pod_evidence_x5 (head)`.

---

## 1. `tenant_dispatch_numbering` and `mint_next_trip_number`

### 1.1 Table and model

| Item | Location |
|------|----------|
| Migration creates table | `alembic_tenant/versions/e7f8a9b0c1d2_dispatch_trips_tenant_numbering.py:19–33` |
| SQLAlchemy model | `app/models/dispatch_trip.py:23–35` (`TenantDispatchNumbering`) |

**Columns (tenant DB):**

- `tenant_id` — **PK**, one row per tenant.
- `trip_number_prefix` — `varchar(16)`, default `''`.
- `prefix_locked_at` — timestamptz, nullable until admin locks prefix.
- `next_numeric` — `bigint`, server default `10001`.
- `created_at`, `updated_at` — timestamptz.

There is **no** per-month dimension; trip numbers are a **single monotonic sequence** per tenant after prefix lock.

### 1.2 Lock / transaction technique

```97:109:app/services/dispatch_trips.py
async def mint_next_trip_number(db: AsyncSession, tenant_id: int) -> str:
    """Acquire tenant_dispatch_numbering row lock, increment sequence, return new full trip_number.
    ...
    """
    row = await get_or_create_numbering_for_update(db, tenant_id)
    if row is None or row.prefix_locked_at is None or not (row.trip_number_prefix or "").strip():
        raise numbering_config_error()
    n = int(row.next_numeric)
    trip_number = f"{row.trip_number_prefix}{n:0{TRIP_NUMERIC_WIDTH}d}"
    row.next_numeric = n + 1
    return trip_number
```

```87:94:app/services/dispatch_trips.py
async def get_or_create_numbering_for_update(
    db: AsyncSession, tenant_id: int
) -> TenantDispatchNumbering | None:
    result = await db.execute(
        select(TenantDispatchNumbering).where(TenantDispatchNumbering.tenant_id == tenant_id).with_for_update()
    )
    row = result.scalar_one_or_none()
    return row
```

**Behavior:**

- `SELECT … FOR UPDATE` on the tenant’s numbering row **inside the caller’s transaction**.
- Increment `next_numeric`, format `prefix + zero-padded width`, return string.
- **Does not** `INSERT` the numbering row on mint; admin **`lock_trip_prefix`** creates/updates the row and sets `prefix_locked_at` (`app/services/dispatch_trips.py:112–135`).
- Mint **fails closed** with HTTP 409 if prefix not configured/locked (`numbering_config_error`, `app/services/dispatch_trips.py:77–84`).

### 1.3 Admin screen / API

| Surface | Path |
|---------|------|
| API | `app/routers/dispatch_numbering_admin.py:17–60` — `GET/PUT /api/v1/admin/dispatch-numbering` |
| UI | `apps/web/src/pages/AdminDispatchNumberingPage.tsx:6–45` — load/save `trip_number_prefix`, show `prefix_locked` |

Load numbering per owner decision **does not** need a user-configurable prefix; it **does** need the same **row-lock + increment** idiom, with **one counter row per `(tenant_id, period)`** instead of one row per tenant.

### 1.4 Reuse for loads “as-is”?

| Aspect | Trip pattern | Load target (owner decision) |
|--------|--------------|------------------------------|
| Lock | `FOR UPDATE` on counter row | **Reusable** |
| Granularity | One row / tenant | **One row / tenant / month** (`YYYY-MM` in company TZ) |
| Admin prefix | Required before mint | **Not applicable** (format is fixed `Mon-YY-NNNN`) |
| `get_or_create` on mint | Trip: row must exist | Load: should **`INSERT … ON CONFLICT` or insert-if-missing then `FOR UPDATE`** for new month |
| String format | Prefix + fixed width numeric | **Variable width** suffix after 9999 |

**Conclusion:** Reuse the **transactional lock-and-increment** pattern, **not** the trip table or admin prefix flow. Implement a **dedicated** counter store (§2).

---

## 2. Proposed storage and migration plan

### 2.1 Proposed table: `tenant_load_number_periods`

| Column | Type | Notes |
|--------|------|--------|
| `tenant_id` | `integer` | PK part 1 |
| `period` | `char(7)` or `varchar(7)` | PK part 2; store **`YYYY-MM`** in company TZ at mint time (not `Mon-YY` — avoids locale parsing) |
| `next_numeric` | `bigint` | Next suffix to assign; start at **1** for a new period |
| `created_at` | `timestamptz` | Server default `now()` |
| `updated_at` | `timestamptz` | Server default `now()`, on update |

**Constraints / indexes:**

- `PRIMARY KEY (tenant_id, period)`
- Optional: `CHECK (period ~ '^[0-9]{4}-[0-9]{2}$')`
- No FK to `loads` (counter is independent; gaps allowed — §7)

**Mint algorithm (implementation sketch, not approved code):**

1. Resolve `period = YYYY-MM` from `now()` (or load `created_at` at insert) in `PlatformTenant.timezone` (§5).
2. In the **same transaction** as `loads` insert: upsert/select period row `FOR UPDATE`, read `n = next_numeric`, format display string `Mon-YY-{n:04d}` (widen width if `n > 9999`), set `next_numeric = n + 1`, assign `loads.load_number`.

**Alternative design (not recommended):** extend `tenant_dispatch_numbering` with `load_next_numeric` and a `load_period` column — couples trip admin lifecycle to load minting and does not model monthly reset cleanly.

### 2.2 Parent revision (dual heads)

Current heads:

- `fmp02_fmp_tenant_scope` ← `fmp01_future_movement_plan` ← `i14_load_pod_evidence` (DW-1 line)
- `i14_load_pod_evidence_x5` ← `x5y6z7a8b9c0` (x5 line)

`scripts/tenant_upgrade_head.sh` **refuses** `upgrade head` while `HEAD_COUNT != 1` (`scripts/tenant_upgrade_head.sh:44–53`). **`alembic upgrade heads` from x5 would apply both POD revisions** — forbidden (`tests/test_i14_pod_migration_graph.py:76–85`, `docs/load_trip/POD_MIGRATION_TARGETS.md`).

**Safe approach (owner-approved implementation phase):**

1. Add **two sibling revisions** with **identical `upgrade()`/`downgrade()` body** (same table DDL):
   - `ln01_load_number_periods_fmp` — `down_revision = "fmp02_fmp_tenant_scope"`
   - `ln01_load_number_periods_x5` — `down_revision = "i14_load_pod_evidence_x5"`
2. **Do not** merge heads in the same checkpoint unless owner approves a merge revision (would be the third merge concern after POD).
3. **Per-tenant upgrade** via `scripts/tenant_upgrade_revision.sh <target>` (`scripts/tenant_upgrade_revision.sh:12–16` refuses `head`/`heads`):

| Tenant `alembic_version` (examples) | Target after LN migration |
|-------------------------------------|---------------------------|
| `fmp02_fmp_tenant_scope` | `ln01_load_number_periods_fmp` |
| `i14_load_pod_evidence_x5` | `ln01_load_number_periods_x5` |
| `i14_load_pod_evidence` (no FMP yet) | Upgrade to `fmp01`/`fmp02` **or** x5 line per existing POD policy **before** LN revision on that branch — plan must match `POD_MIGRATION_TARGETS.md` |

**SQL (upgrade):** `CREATE TABLE tenant_load_number_periods (...)` + PK; **no data backfill** (counters start empty; first mint creates row).

**Downgrade:** `DROP TABLE tenant_load_number_periods` (only if no dependency; table is standalone).

**Tenants already migrated:** No change to existing `loads.load_number`. New table is empty until first post-deploy mint.

**After both LN revisions exist:** graph has **three heads** (`ln01_…_fmp`, `ln01_…_x5`, and any tenant still only on POD head without LN). Operations continue to use **explicit revision targets**, not `upgrade head`, until a future owner-approved merge.

---

## 3. Where `load_number` is assigned or accepted

### 3.1 Must call the new minter (new loads)

| Path | File:line | Current behavior |
|------|-----------|------------------|
| Commercial insert (shared) | `app/services/loads.py:532–536` | `payload.load_number or f"DRAFT-{uuid…}"` then `_ensure_unique_load_number` |
| HTTP create | `app/routers/loads.py:56–64` → `create_load` → `_insert_commercial_load_uncommitted` | Same |
| Workspace promote | `app/services/load_workspace_draft_promotion.py:153–158` | `draft_json_to_load_create` then `_insert_commercial_load_uncommitted` |
| Draft JSON → create payload | `app/services/load_workspace_draft_mapper.py:183–186` | Passes draft `loadNumber` into `LoadCreate.load_number` if set |
| Email intake load | `app/services/email_threads.py:229–232` | `_allocate_intake_style_load_number` → `INT-{uuid12}` (`email_threads.py:55–66`) |
| Demo seed | `app/scripts/seed_demo_operational_loads.py:396–485` | Explicit `DEMO-OPS-…` `load_number` (idempotent script; **not** production path) |

**Implementation note:** Centralizing in `_insert_commercial_load_uncommitted` covers API, promote, and any caller using that helper; **email intake** bypasses it today and needs a **separate** call before `Load(...)` insert.

### 3.2 Accept / validate only (no mint)

| Path | File:line |
|------|-----------|
| Uniqueness check | `app/services/loads.py:480–487` |
| Update load | `app/services/loads.py:761–762` (if `load_number` in payload) |
| Mark-ready prerequisites | `app/services/loads.py:364–395` (treats `load_number` as satisfying “Load # / PO #” gate — **see risk §4**) |
| Schema optional field | `app/schemas/load.py:89`, `157` |

### 3.3 Tests / fixtures (expect DRAFT/INT today)

| File | Note |
|------|------|
| `tests/test_loads_v1.py:98` | Asserts `DRAFT-` or explicit number |
| `tests/test_email_threads_api.py:346` | Asserts `INT-` prefix |
| `tests/test_load_writer_freeze_issue0a.py:187` | `DRAFT-` |
| Many tests | Pass explicit `load_number` — unaffected |

### 3.4 Parser

No `load_number` writes under `app/services/load_parser*` (grep 2026-10-24). Contract: `app/contracts/TruckERP_Rate_Confirmation_AI_Handoff_Contract_v2_FULL.json` (internal load number not an AI target).

---

## 4. Readers depending on `DRAFT-` / `INT-` / `DEMO-` or format

| Consumer | File:line | Break risk |
|----------|-----------|------------|
| Load list search | `app/services/loads.py:687–693` | **Low** — `ilike` works on `Oct-26-0001` |
| Trip list search | `app/services/trips.py:220` | **Low** |
| Manual form placeholder | `apps/web/src/loadWorkspace/LoadWorkspaceForm.tsx:284` | **UX** — shows `INT-...`; should show owner format example or “assigned on save” |
| Email intake test | `tests/test_email_threads_api.py:346` | **Test update** required |
| Draft auto tests | `tests/test_loads_v1.py:98`, `test_load_writer_freeze_issue0a.py:187` | **Test update** |
| SQL inventory script | `scripts/tenant_demo_load_inventory.sql:7–9` | **Reporting** — add bucket for `Mon-YY-` pattern |
| Demo seed prefix | `app/scripts/seed_demo_operational_loads.py:14–41` | **Intentional** `DEMO-OPS-` — keep or switch to minter for new demo rows (owner choice) |
| Lab / docs examples | `docs/load_parser/contracts/…`, `loadOperationalReferences.test.ts:40` | **Doc/test literals** only |

**Sorting:** `list_loads` orders by `Load.id.desc()` (`app/services/loads.py:678`), not `load_number` — **no break**.

**Payroll / fuel / toll joins:** Use `load_id` or metadata, not `load_number` prefix semantics (see settlement report). **No prefix dependency** found for payroll chain.

**Mark-ready / promote mismatch (product):** `validate_load_ready_prerequisites` counts **internal** `load_number` toward “Load # / PO #” (`app/services/loads.py:390–395`). After auto-mint, **every** load has an internal number, so legacy `mark_load_ready` could treat broker ref as optional when only internal number exists — **conflicts with owner “do not mix”** unless implementation **narrows** that check to `broker_load_reference` (+ operational refs only). Promotion path already skips mark-ready (`load_workspace_draft_promotion.py` uses `insert_as_ready=True`). **Flag for implementation + owner approval.**

---

## 5. Company time zone

| Item | Location |
|------|----------|
| Stored on tenant (platform DB) | `app/models/platform.py:80–81` — `PlatformTenant.timezone`, default `"America/Toronto"` |
| Exposed in admin company profile API | `app/routers/tenant_admin.py:72`, `238` — `timezone=tenant.timezone or "America/Toronto"` |
| Admin UI display | `apps/web/src/pages/AdminCompanyProfilePage.tsx:225` |

**Not** on `platform_company_profiles` — timezone is **tenant-level**, not document-profile address.

**Mint instant:** Use UTC `created_at` (or “now” at insert) converted with `zoneinfo.ZoneInfo(tenant.timezone)` to derive `YYYY-MM` and `Mon` / `YY` for display.

**Month boundary:** At local midnight on the 1st, `YYYY-MM` changes → **new period row**, suffix resets to `0001`. Loads created **one second before** midnight get the previous month’s period; loads **after** get the new month. No pickup-date coupling.

**Failure modes:** Invalid TZ string in DB → implementation must fail closed or fall back per owner policy (recommend: reject mint with clear error, admin fixes TZ).

---

## 6. User-supplied `payload.load_number` today

**Today:** `LoadCreate.load_number` optional (`app/schemas/load.py:89`); `_insert_commercial_load_uncommitted` uses client value when set (`app/services/loads.py:532`); updates allow change with uniqueness check (`app/services/loads.py:761–762`).

| Option | Behavior | Risks |
|--------|----------|-------|
| **A. Disallow on create** (ignore/clear client field; always mint) | Simplest operator story | Breaks tests/API clients that set explicit numbers; migration for integrations |
| **B. Optional override** (mint if blank; if provided, validate format + uniqueness) | Flexible for imports | Users can collide with minted sequence semantics; bypass monthly counter; support burden |
| **C. Override admin-only** | Mint for normal users | Role complexity |
| **D. Allow only before first save / draft legacy** | N/A once mint-at-create | Confusing with promote path |

**Recommendation for owner review:** **A** for operator paths (aligns with “our internal id”); keep **test/import** hooks via explicit env or admin API if needed. If **B**, do **not** advance `next_numeric` when override used unless owner wants consumed sequence numbers.

---

## 7. Concurrency, gaps, and tests

**Concurrency:** Two sessions minting for same `(tenant_id, period)` must serialize on the **same period row** (`FOR UPDATE`). Expect distinct suffixes; both succeed.

**Insert fails after mint:** If `loads` insert rolls back, the transaction should roll back **counter increment** when mint is in the **same transaction** (required). If mint were committed separately, gaps would appear — **avoid**.

**Gaps:** Acceptable on owner-approved design (rolled-back transactions, deleted drafts if ever minted outside load insert — should not happen). **Do not** reuse skipped numbers.

**Test plan (disposable clone):**

1. Bootstrap clone: `scripts/disposable_tenant_bootstrap.py` to revision on **x5 or fmp02 line** matching production target, then apply `ln01_*` when it exists.
2. Integration: two parallel `asyncio` tasks / threads calling create/promote/intake; assert distinct `load_number`, same period when TZ-fixed clock or mocked time.
3. Month rollover: unit test with frozen clock `2026-10-31 23:59:59` vs `2026-11-01 00:00:00` America/Toronto → `Oct-26-…` vs `Nov-26-0001`.
4. Overflow: unit test format `10000` → five digits, no truncation.

---

## 8. Sequencing vs Task 8/9 (settlement rate) and email intake

| Workstream | Interaction |
|------------|-------------|
| **Task 8 settlement rate (docs)** | **Independent** — `rate` / `customer_rate` / effective settlement (`docs/payroll_settlements/SETTLEMENT_RATE_OWNER_DECISION_2026-10-24.md`). No dependency on `load_number` format. |
| **Task 9 settlement implementation (future)** | **Low coupling** — payroll uses `load_id`; ensure UI labels keep broker vs internal ids separate (owner rules). Can proceed in parallel if mark-ready prerequisite fix (§4) is scoped correctly. |
| **Email intake** | **Must** switch `email_threads.py` INT allocator to shared minter in **same** checkpoint as `_insert_commercial_load_uncommitted` or immediately after; otherwise dual numbering rules. |
| **Workspace promote** | Same checkpoint as commercial insert minter; remove draft `loadNumber` passthrough unless owner chooses override (§6). |

**Recommended order:**

1. Schema: `tenant_load_number_periods` (paired revisions §2.2) — **checkpoint 1**, STOP.
2. Service: `mint_next_load_number` + wire `_insert_commercial_load_uncommitted` + email intake — **checkpoint 2**, STOP.
3. UI: remove `INT-` placeholder; show minted or read-only internal number — **checkpoint 3**.
4. Tests + disposable concurrency — with checkpoint 2 or 3.
5. Settlement rate **implementation** (Task 9) — **can** follow or parallel **after** checkpoint 2 if §4 mark-ready prerequisite is addressed or confirmed non-blocking for email/draft paths.

---

## STOP

Awaiting **owner approval** of this report and the owner decision doc before any implementation.
