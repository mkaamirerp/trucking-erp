# Trip number — implementation plan

**Legacy dispatch cutover (Slice 1, code):** **Generic `Load` PATCH** may no longer transition a load **into** **`Load.status = dispatched`** (API returns **`409`**, code **`LEGACY_LOAD_STATUS_DISPATCH_DEPRECATED`**). **Read** paths, **board display**, and **legacy cancel** (dispatched → `draft` / `ready` / `unassigned`) remain for compatibility. **Mint** **`trip_number`** for **new** execution is via **Trip** / planned-trip flows — **not** this load-status hop. **Target `Load.status` (new-write) and board direction** — **`DECISION_11_LOAD_STATUS_TARGET_BOARD_MIGRATION.md`** (**LOCKED**).

**Baseline:** [`DISPATCH_TRIP_NUMBER_RULE.md`](./DISPATCH_TRIP_NUMBER_RULE.md) (locked: **mint at Trip plan/create**, single pool, never reuse, `trips` canonical).

**Scope:** This report translates the baseline into **concrete schema, services, API, and UI work**. Trip number is **not** a dispatch-board-only field; it is the **operational reference** across dispatch, loads, issues, documents, and payroll **tracing**.

**Phase 3C (planned container):** [`PHASE3C_PLANNED_TRIP_IMPLEMENTATION_PROPOSAL.md`](./PHASE3C_PLANNED_TRIP_IMPLEMENTATION_PROPOSAL.md).

### Canonical vs denormalized (evolving — non-negotiable direction)

- **`trips` is canonical for the Trip container** and its **`trip_number`** (minted at **planned Trip create**).
- **`trip_loads`** is canonical for Trip↔Load membership.
- **`dispatch_trips`** may remain **legacy or mirrored** during migration; it **must not** introduce a **second numbering pool** or competing trip identity. Align per Phase 3C / dual-write notes below.
- If **`loads.active_dispatch_trip_id`**, **`loads.active_trip_id`**, and/or **`loads.trip_number`** exist, they are **read-model / convenience** only unless a doc explicitly states otherwise for a transitional window.
- **All writes** that create a new trip identity flow through the **shared allocator** (`tenant_dispatch_numbering` **FOR UPDATE**) in the same transaction as **`trips`** insert (and any mirrored `dispatch_trips` write). No random `UPDATE loads SET trip_number = …` elsewhere.

**Historical note (pre–Phase 3C code):** Some implementations minted only on load **`dispatched`** via **`dispatch_trips`**. New product rules **supersede** that timing; implementation work should **move/extend** the allocator to **`trips`** per Phase 3C proposal.

**Current codebase touchpoints (reference):**

- Loads / trips: `app/models/load.py`, `app/models/dispatch_trip.py`, `app/services/loads.py`, `app/services/dispatch_trips.py`, `app/routers/loads.py`, `app/schemas/load.py` (`LoadResponse` includes read-model `trip_number` where applicable)
- Dispatch board: `app/routers/dispatch.py`, `apps/web/src/pages/DeprecatedDispatchPage.tsx` (board/list UI; deep assign/edit flows defer to load workspace — see `LoadWorkspacePage.tsx`)
- Load workspace UI: **`apps/web/src/pages/LoadWorkspacePage.tsx`** (header/summary/strips for load + **trip** display), **`LoadsListPage.tsx`** (list + CSV includes `trip_number` when present)
- Tenant admin: `app/routers/tenant_admin.py` (tenant-scoped settings + `get_tenant_db`; **dispatch numbering** in tenant DB — see `AdminDispatchNumberingPage.tsx`)
- Payroll (tracing): `app/models/payroll.py` (`PayEntry`, `PayRunItem` with `metadata_json`), `app/routers/payroll.py`

---

## 1. Exact schema additions (tenant DB)

### 1.1 `tenant_dispatch_numbering`

Single row per tenant (`tenant_id` **PK**).

| Column | Type | Notes |
|--------|------|--------|
| `tenant_id` | `INTEGER` PK | Aligns with tenant-scoping pattern used elsewhere |
| `trip_number_prefix` | `VARCHAR(16)` NOT NULL | Validated uppercase alphanumeric; set before lock |
| `prefix_locked_at` | `TIMESTAMPTZ` NULL | NULL ⇒ prefix may be set once via API; NOT NULL ⇒ immutable |
| `next_numeric` | `BIGINT` NOT NULL | Default `10000` or `1` per padding policy; incremented atomically |
| `created_at` / `updated_at` | `TIMESTAMPTZ` | Standard audit |

**Index:** PK only; optional `UNIQUE` redundant on PK.

**Migration:** `INSERT` default row optional — or **lazy insert** on first prefix save in service.

### 1.2 `dispatch_trips`

| Column | Type | Notes |
|--------|------|--------|
| `id` | `SERIAL` PK | |
| `tenant_id` | `INTEGER` NOT NULL | Index |
| `trip_number` | `VARCHAR(32)` NOT NULL | Full string, e.g. `IKL10001` |
| `job_type` | `VARCHAR(32)` NOT NULL | `freight_load` \| `trailer_move` |
| `status` | `VARCHAR(32)` NOT NULL | e.g. `active`, `cancelled`, `superseded` — supports lifecycle |
| `load_id` | `INTEGER` NULL FK → `loads.id` ON DELETE **RESTRICT** or SET NULL per policy | Non-null iff freight |
| `trailer_move_id` | `INTEGER` NULL FK | Placeholder until `trailer_moves` exists — FK deferred optional |
| `assigned_at` | `TIMESTAMPTZ` NOT NULL | server_default `now()` |
| `created_at` / `updated_at` | `TIMESTAMPTZ` | |

**Constraints (required):**

- `UNIQUE (tenant_id, trip_number)`
- **Exactly one target:** e.g.  
  `(CASE WHEN load_id IS NOT NULL THEN 1 ELSE 0 END) + (CASE WHEN trailer_move_id IS NOT NULL THEN 1 ELSE 0 END) = 1`
- **job_type vs FK:** `CHECK` e.g. `(job_type = 'freight_load' AND load_id IS NOT NULL AND trailer_move_id IS NULL) OR (job_type = 'trailer_move' AND trailer_move_id IS NOT NULL AND load_id IS NULL)` — adjust when trailer table lands

**Partial unique (exactly one active trip per assignment target):**

- **Freight:** `UNIQUE (tenant_id, load_id) WHERE status = 'active' AND load_id IS NOT NULL`
- **Trailer move (when `trailer_moves` exists):** `UNIQUE (tenant_id, trailer_move_id) WHERE status = 'active' AND trailer_move_id IS NOT NULL`  
  Same rule, symmetric enforcement — design now so migration + services do not treat loads as special forever.

**Indexes (query paths):**

- `(tenant_id, trip_number)` — unique covers lookups
- `(tenant_id, load_id)` WHERE `status = 'active'`
- `(tenant_id, status)` optional for admin/audit lists

### 1.3 Read-optimized copy on `loads` (optional; convenience only)

| Column | Type | Notes |
|--------|------|--------|
| `active_dispatch_trip_id` | `INTEGER` NULL FK → `dispatch_trips.id` | **Read-model pointer** to the active trip row, if any |
| `trip_number` | `VARCHAR(32)` NULL | **Denormalized copy** of active `dispatch_trips.trip_number` |

**Rules:**

- These fields **must never** become the source of truth. **`dispatch_trips`** authorizes all trip identity and lifecycle; load columns are **derived**.
- **Never** accept `trip_number` / `active_dispatch_trip_id` from `LoadCreate` / `LoadUpdate` (reject if sent).
- Update load copy **only** inside **`dispatch_trips`** allocation/cancel/complete helpers, same DB transaction as the canonical row change.
- **Search:** May query `Load.trip_number` for convenience **or** join `dispatch_trips`; if both exist, treat DB uniqueness on `dispatch_trips` as authoritative on conflict.

**Alternative (minimal):** Omit load columns; always join `dispatch_trips` for active trip — valid, slightly heavier reads.

### 1.4 Trailer moves (future)

- Table `trailer_moves` + same `dispatch_trips` linkage and shared allocator (baseline).
- Same partial unique for `(tenant_id, trailer_move_id) WHERE status = 'active'`.

### 1.5 Issue / exception persistence (phased)

**Today:** Loads use `status = issue_hold` and `load_notes` — no separate `trip_issues` table.

**Phase A (minimal):**

- Ensure **`trip_number`** (and/or `dispatch_trip_id`) appears on API responses for the load in `issue_hold` so UI and search can use it.

**Phase B (recommended):** Add `dispatch_trip_id` (nullable FK) to:

- `load_notes` **or**
- A future `trip_events` / `dispatch_issues` table with `tenant_id`, `dispatch_trip_id`, `severity`, `body`, `created_by`

baseline: issues should tie to **trip** for “driver called about IKL10001” — FK to `dispatch_trips.id` is the clean join key; `trip_number` string duplicated on the issue row **optional** for export/search without joins.

### 1.6 Settlement / payroll (proportional tracing — do not redesign payroll)

**Principle:** Trip number is a **tracing / reference key** in payroll and settlement flows. It is **not** a reason to re-own payroll around trips or rebuild pay models.

**Today:** `PayEntry` has `reference_code`; `PayRunItem` has `metadata_json`.

**v1 scope (recommended):**

- Show **`trip_number`** on pay-related **UI lists, detail, and exports/CSV** where a line relates to work that already has a trip (join or copy from snapshot).
- Use **`reference_code`** and/or **`metadata_json`** to carry `trip_number` (and optionally `dispatch_trip_id`) when recording or generating lines — **minimal schema change**.
- **Optional later:** nullable **`dispatch_trip_id`** on `pay_entries` (or pay line table) **only if** joins become painful; not required on day one.

**Do not:** Redesign pay ownership, pay run structure, or entitlements around trips. Add **visibility + optional FK**, not a new payroll domain model.

---

## 2. Admin prefix configuration storage

- **DB:** `tenant_dispatch_numbering` (§1.1), **tenant DB only** (not `platform_tenants`).
- **Router:** New endpoints under tenant admin umbrella, e.g.:
  - `GET /api/v1/admin/dispatch-numbering` — returns `{ trip_number_prefix, prefix_locked, next_numeric_exposed: false }` (never expose sequence cursor to client)
  - `PUT /api/v1/admin/dispatch-numbering` — body `{ trip_number_prefix }`; allowed only if `prefix_locked_at IS NULL`; validates format; sets row + lock timestamp in **one** commit if “confirm lock” UX, or separate `POST .../lock`
- **Auth:** Reuse `tenant_admin` patterns (`require_entitlement("admin_sensitive")`, `get_tenant_db`, `require_tenant`).
- **Frontend:** New section under existing admin / company settings: “Dispatch trip numbers” with explanation that prefix is **permanent** after save.

---

## 3. Backend allocation flow

**Module:** e.g. `app/services/dispatch_trips.py` (or `trip_numbers.py`).

**Core function signatures (conceptual — Phase 3C+):**

```text
async def create_planned_trip(
    db: AsyncSession,
    tenant_id: int,
    *,
    job_type: str,
    status: str = "planned",
    # optional: driver_id, truck_id, trailer_id — all nullable
) -> Trip

async def ensure_active_trip_for_load_assignment(
    db: AsyncSession,
    tenant_id: int,
    load: Load,
    *,
    assigned_at: datetime | None = None,
) -> DispatchTrip  # legacy signature; may return Trip or align to trips.id — see Phase 3C
```

**`create_planned_trip` steps (single transaction):**

1. Load `tenant_dispatch_numbering` **FOR UPDATE** (same as freight allocator).
2. If `prefix_locked_at` is NULL or prefix empty → raise **`TRIP_NUMBER_PREFIX_NOT_CONFIGURED`**.
3. Build `trip_number`, bump `next_numeric`.
4. `INSERT INTO trips` (`status` e.g. `planned`, nullable equipment, **`trip_number`** set).
5. **Do not** require `trip_loads` rows; **zero active loads** is allowed at create.

**`ensure_active_trip_for_load_assignment` (legacy / until unified):** If the load already participates in a **non-cancelled Trip** via **`trip_loads`**, **attach or update** per product rules **without** minting a second number. Otherwise follow dual-write alignment in Phase 3C (link new `trip_loads` row to existing **`trips`** or create Trip first—implementation choice must preserve **one pool, one mint per new Trip identity**).

**Steps (historical freight path — to be reconciled with `trips` first):**

1. If load already has **active** `dispatch_trips` row (`active_dispatch_trip_id` or query), **return existing** (resource-only reassignment).
2. Load `tenant_dispatch_numbering` **FOR UPDATE**.
3. If `prefix_locked_at` is NULL or prefix empty → raise **`HTTPException(409 or 422, detail={ "code": "TRIP_NUMBER_PREFIX_NOT_CONFIGURED", ... })`** per baseline.
4. Build `trip_number = f"{prefix}{next_numeric:0{WIDTH}d}"`.
5. `UPDATE tenant_dispatch_numbering SET next_numeric = next_numeric + 1`.
6. `INSERT INTO dispatch_trips` (`status='active'`, `job_type='freight_load'`, `load_id=...`).
7. `UPDATE loads SET active_dispatch_trip_id=..., trip_number=...` (if denormalizing).

**Concurrency:** Row lock on `tenant_dispatch_numbering` guarantees serial allocation per tenant.

**Trailer moves (later):** Same function family with `ensure_active_trip_for_trailer_move_assignment`.

**Undo / cancel:** See [§3b Trip row lifecycle](#3b-trip-row-lifecycle-cancelled-completed-superseded-resource-only).

---

## 3b. Trip row lifecycle (cancelled, completed, superseded, resource-only)

**Evolving ownership:**

- **`trips.status`** (and **`trips.cancelled_at`** when present) are **canonical** for the **Trip container** (planned Trip cancel, execution progression).
- **`dispatch_trips.status`** describes **legacy / mirrored freight assignment** rows until retired; must stay **consistent** with the **`trips`** row for the same logical Trip.

Suggested **v1 vocabulary** on **`dispatch_trips`** (adjust enum names in code, not concepts):

| Status | Meaning |
|--------|---------|
| **`active`** | Current operational trip for that load/trailer move; at most one per target ([§1.2](#12-dispatch_trips)). |
| **`cancelled`** | Dispatch assignment was **undone** or voided (load left dispatched pool or similar). Row **retained**; `trip_number` **immutable**; **never reused**. |
| **`superseded`** | A **new** active trip was minted for the same load (rare product path). Historical row; still searchable. |
| **`completed`** | *(Optional v1)* Operational closure when load reaches terminal state (e.g. **delivered**) — trip is no longer “active” but remains **searchable** and **referenceable** for payroll/audit. If v1 skips `completed`, **`active`** may persist until `cancelled`; product can add `completed` later. |

**“Voided”** in UI copy maps to **`cancelled`** unless legal/compliance later needs a distinct `voided` code — same semantics: not deleted, not reused.

**Searchability:** All non-deleted `dispatch_trips` rows remain queryable by **`trip_number`** and filters for **admin / support / payroll tracing**, including **cancelled** and incomplete trips.

**Payroll references:** If a pay line or entry recorded **`trip_number`** (or optional `dispatch_trip_id`) while the trip was **active**, that reference **remains valid** after **`cancelled`** or **`completed`** — it is **historical tracing**, not “trip must be active to pay.” Numbers are **not** recycled onto new trips.

**Resource-only reassignment:** Changing **driver / truck / trailer** **without** undoing dispatch commit does **not** change **`trip_number`**; update assignment on **`trips`** when that table is canonical, and legacy **`loads`** / **`dispatch_trips`** fields only as aligned by dual-write.

---

## 4. Dispatch assignment integration point

**Primary hook:** `app/services/loads.py` — **`update_load`**, after field validation, **before** `commit`.

### 4.1 Allocation timing (two paths during migration)

**Target (locked product):** **New Trip identity** → mint **`trip_number`** on **`trips`** insert (**planned Trip create**). See [`DISPATCH_TRIP_NUMBER_RULE.md`](./DISPATCH_TRIP_NUMBER_RULE.md) §3.

**Legacy code path (until removed):** Some deployments still allocate **only** when a load first hits **`dispatched`**, via **`dispatch_trips`**. Phase 3C **moves/extends** the allocator so **`create_planned_trip`** uses the same **`tenant_dispatch_numbering`** transaction; **`update_load`** then **links** Loads via **`trip_loads`** and/or aligns **`dispatch_trips`** **without** a second mint for the same Trip.

**Do not** leave “maybe assigned, maybe dispatched” undocumented—implementation plan and Phase 3C proposal must name the **single** mint per new **`trips.id`**.

### 4.1a Historical note (superseded for new work)

Previously this section locked mint to **load `dispatched`** only. That rule is **superseded** for **new Trip containers**; see **§4.1** above.

### 4.2 Algorithm sketch (legacy `dispatch_trips` path; align with `trips` in Phase 3C)

- If **new status is `dispatched`** and **no active `dispatch_trips`** row for this load → call **`ensure_active_trip_for_load_assignment`** (must **not** mint a **second** `trip_number` if a **`trips`** row already exists for this movement—see Phase 3C dual-write).
- If **already `dispatched`** and only **`driver_id` / `truck_id` / `trailer_id`** change → **do not** allocate; existing active trip unchanged ([§3b resource-only](#3b-trip-row-lifecycle-cancelled-completed-superseded-resource-only)).
- If status moves **from `dispatched`** back to a **pre-dispatch** status (undo) → set active **`dispatch_trips`** to **`cancelled`**, clear load **read-model** pointers; **never** delete row or reuse number. **Trip container (`trips`)** lifecycle must stay **consistent** (may also set `trips.status` / memberships per product).
- New operational trip later → **new** `trips` row + new number; legacy **`dispatch_trips`** row **`cancelled`** / **`superseded`** per [baseline lifecycle](./DISPATCH_TRIP_NUMBER_RULE.md#2-assignment-lifecycle).

**Other entry points:** Bulk dispatch, mobile, etc. must call the **same** allocator rules after Phase 3C (no duplicate mint).

**Idempotency:** Repeated saves while **`dispatched`** with existing active trip → no second allocation.

### 4.3 Leaving `dispatched`: exact cancel transitions (v1)

The active **`dispatch_trips`** row is **cancelled** and load read-model **`trip_number` / `active_dispatch_trip_id`** cleared **only** when **all** are true:

1. Previous status was **`dispatched`**.
2. New status is **not** **`dispatched`**.
3. New status is in **`PRE_DISPATCH_TRIP_CANCEL_STATUSES`**: **`draft`**, **`ready`**, or **`unassigned`**.

**Never** cancels on normal forward or lateral operations, including non-exhaustively: **`dispatched` → `assigned`**, **`arrived_pickup`**, **`in_transit`**, **`arrived_delivery`**, **`delivered`**, **`issue_hold`**, or any status **outside** the three pre-dispatch statuses above. Expanding the cancel set is a **product** change.

Code: `app/constants/trip_dispatch.py` (`PRE_DISPATCH_TRIP_CANCEL_STATUSES`) and `app/services/loads.py` (`update_load`).

### 4.4 V1 driver / truck / trailer gate

- **Required** the first time a load enters **`dispatched`:** **`driver_id`** and **`truck_id`** must both be non-null; otherwise **400** with `DISPATCH_RESOURCES_REQUIRED`.
- **`trailer_id`:** **optional** in v1 (matches typical dispatch-board behavior; trailer may be unset when minting).

### 4.5 Prefix lock API (confirmed v1 behavior)

- **First successful `PUT`:** creates **`tenant_dispatch_numbering`** when missing, normalizes/stores prefix, sets **`prefix_locked_at`**, and ensures **`next_numeric`** is at least **10001** if the row was uninitialized.
- **After lock:** any further **`PUT`** returns **409** with code **`TRIP_PREFIX_ALREADY_LOCKED`** — prefix cannot be changed through the product API.
- **`GET`:** returns current prefix (if any) and **`prefix_locked`**; **never** returns **`next_numeric`**.

### 4.6 Sequence start and first trip string (confirmed)

- Migration + service default for **`next_numeric`** is **10001**.
- **First** allocation uses that value as the numeric segment with **5-digit zero padding** → **`{PREFIX}10001`** (e.g. `IKL10001`).
- The counter is **incremented after** minting, so the second trip is **`{PREFIX}10002`**, etc.

---

## 5. Read / write API changes

### 5.1 Write API (trip number)

- **`LoadCreate` / `LoadUpdate`:** Do **not** add `trip_number`; if clients send it → **422** or strip with warning (prefer **reject** for clarity).
- **No** `PATCH /dispatch-trips/{id}/trip_number`.

### 5.2 Read API — loads & board

- **`LoadResponse`:** Add `trip_number: str | None`, `dispatch_trip_id: int | None` (optional but helps admin/support).
- **`GET /api/v1/dispatch/board`:** Ensure serialization uses updated `LoadResponse` (already `LoadResponse.model_validate`).
- **`GET /api/v1/loads` / search:** Extend `loads_service` filters: query param `trip_number` (exact or `ilike` on suffix — document); include `Load.trip_number` in `or_()` search alongside `load_number` where baseline requires “find by human reference.”

### 5.3 Read API — trip detail (optional but aligned with baseline)

- **`GET /api/v1/dispatch/trips/{trip_number}`** or **by id** — returns trip + nested load summary, driver, truck, stops. Powers “IKL10001” global search / deep link.
- **`GET /api/v1/dispatch/trips`** — audit list (admin) with filters.

### 5.4 Admin numbering API

- As in §2; **read** returns lock state; **write** only unlocks nothing after lock.

### 5.5 Payroll API (tracing — minimal)

- Prefer surfacing **`trip_number`** in **responses and exports** via `reference_code` / `metadata_json` first.
- Add explicit DTO fields only where the UI already needs them; **avoid** a payroll schema rewrite in the first milestone.

---

## 6. UI surfaces to update

| Surface | Change |
|---------|--------|
| **Admin — dispatch numbering** | Form: prefix, lock; show error when **planned Trip create** **or** dispatch is blocked |
| **`DeprecatedDispatchPage.tsx`** | Card / row / table: show **`trip_number`** when present; handle 409 from API with toast + link to admin |
| **`LoadWorkspacePage.tsx`** | Header/summary / context: **`trip_number`** next to broker/load identity with clear labels (operational **Trip** vs broker refs / load #) |
| **`LoadsListPage.tsx`** | List + export: `trip_number` column where applicable; search passes through `listLoads` `search` / backend filters as implemented |
| **`LoadInboxPage.tsx`** / intake | Show **`trip_number` only when it exists** (post-`dispatched` / active trip). **Never** fabricate or reserve trip numbers during intake or draft stages ([intake boundary](#intake-and-draft-boundary) below) |
| **Global search (future)** | Route to trip or load by `trip_number` |
| **Issue / `issue_hold` UX** | When moving load to issue or showing notes, display **trip** prominently; future issue form: store `dispatch_trip_id` |
| **Payroll — pay entry list / edit** | Optional columns “Trip #”; exports / printed pay detail include `trip_number` when set |
| **Pay run / settlement review** | Line items show trip for traceability |
| **Driver-facing / print** | Trip sheets, summaries: **`trip_number`** as operational id |

**API client:** `apps/web/src/api.ts` — extend `Load` type + admin numbering functions + payroll types.

### Intake and draft boundary

- **Draft / email-intake loads** do **not** receive a **`trip_number` by virtue of being draft** ([baseline](DISPATCH_TRIP_NUMBER_RULE.md)): no client-supplied number; intake does not bump the allocator.
- **Planned Trip** may be created **without** any Load; that path **does** mint via **`trips`** create (not intake).
- UI: for **loads** without an attached Trip, omit trip field or show “—”; for **Trips list/detail**, show planned trips with zero loads when applicable.

---

## 7. Issue / exception and settlement paths (cross-module)

### 7.1 Issues / exceptions

- **Baseline:** “my trip IKL10001” must resolve quickly.
- **Implementation:**  
  - **Short term:** `LoadResponse.trip_number` + search by trip on load list; load notes UI shows trip in header.  
  - **Medium:** `load_notes` or issue rows carry `dispatch_trip_id`; list issues filterable by `trip_number`.  
  - **Notifications / SMS (future):** template includes `trip_number`.

### 7.2 Settlement / payroll

- **Baseline:** Payroll is **not** owned by trip number; trip number **traces** work → pay ([§1.6](#16-settlement--payroll-proportional-tracing--do-not-redesign-payroll)).
- **Implementation (proportional):**  
  - Show **`trip_number`** on pay UI and **exports** where a line ties to dispatched work.  
  - Prefer **`reference_code` / `metadata_json`** before adding columns.  
  - **Optional** nullable `dispatch_trip_id` only when justified — **not** a prerequisite for v1.

---

## 8. Implementation sequencing (recommended — reduces churn)

1. **Schema** — existing: `tenant_dispatch_numbering`, `dispatch_trips`, …; **Phase 3C:** ensure **`trips`** + **`trip_loads`** receive allocator integration ([`PHASE3C_PLANNED_TRIP_IMPLEMENTATION_PROPOSAL.md`](./PHASE3C_PLANNED_TRIP_IMPLEMENTATION_PROPOSAL.md)).
2. **Numbering config API** — admin prefix get/put + lock; block **planned Trip create** and dispatch when missing.
3. **Allocation service** — `FOR UPDATE` sequence; **`create_planned_trip` → `INSERT trips`**; reconcile **`dispatch_trips`** / **`trip_loads`** / load read-models in one transaction where required.
4. **Dispatch assignment integration** — **`update_load`** and board flows attach to **`trips`** via **`trip_loads`** without second mint; cancel / undo rules stay consistent with baseline.
5. **Read APIs + search** — `LoadResponse`, board, **`GET /api/v1/trips`**, filters by `trip_number`.
6. **UI surfaces** — Trip workspace, lists, dispatch (intake: [boundary](#intake-and-draft-boundary)).
7. **Payroll + issue references** — proportional tracing; prefer **`trips.id`** / `trip_number` in metadata over time.

**Prerequisite before coding:** Read [**`DISPATCH_TRIP_NUMBER_RULE.md` §3**](./DISPATCH_TRIP_NUMBER_RULE.md#3-allocation-timing) — mint on **planned Trip create**; single pool.

### First slice (implemented in repo — historical)

- Tenant migration **`e7f8a9b0c1d2`**: `tenant_dispatch_numbering`, `dispatch_trips`, load read-model columns + FK.
- **Subsequent evolution:** Phase 1 `trips` / `trip_loads` foundation ([`PHASE1_TRIP_FOUNDATION_PLAN.md`](./PHASE1_TRIP_FOUNDATION_PLAN.md)); **Phase 3C** moves allocator primary mint to **`trips`** per proposal doc.

- Models: `app/models/dispatch_trip.py`, `Load` extensions (read-model only); `trips` / `trip_loads` per tenant migrations.
- Services: `app/services/dispatch_trips.py` (prefix lock, allocate, cancel active); `update_load` integration in `app/services/loads.py` (historically **mint on first `dispatched`** — superseded for **new** planned-trip flow).
- Admin API: `GET`/`PUT` `/api/v1/admin/dispatch-numbering` (`app/routers/dispatch_numbering_admin.py`).
- Schemas: `LoadResponse` exposes read-model ids; `LoadCreate`/`LoadUpdate` reject client trip fields.

---

## 9. Verification checklist (post-implementation)

- [ ] **Planned Trip create** after prefix lock mints **`trips.trip_number`** (may have **zero** `trip_loads`).  
- [ ] Trip / dispatch without locked prefix → **409/422** + stable `TRIP_NUMBER_PREFIX_NOT_CONFIGURED`.  
- [ ] Resource-only reassignment → **same** trip number on **same `trips` row**.  
- [ ] Cancel / abandon → rows **retained**; number **not** reused.  
- [ ] **Load cancel** does **not** auto **Trip cancel**; **manual Trip cancel** closes memberships, not commercial loads by default ([`TRIP_CONTAINER_VS_LOAD_FOUNDATION.md`](./TRIP_CONTAINER_VS_LOAD_FOUNDATION.md) §11.1).  
- [ ] Search finds Trip / loads by **`trip_number`**.  
- [ ] Baseline doc scenarios ([`DISPATCH_TRIP_NUMBER_RULE.md`](./DISPATCH_TRIP_NUMBER_RULE.md)) satisfied.
