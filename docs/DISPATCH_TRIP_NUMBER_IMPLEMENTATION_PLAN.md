# Trip number — implementation plan

**Baseline:** [`DISPATCH_TRIP_NUMBER_RULE.md`](./DISPATCH_TRIP_NUMBER_RULE.md) (locked: technical + cross-module business intent).

**Scope:** This report translates the baseline into **concrete schema, services, API, and UI work**. Trip number is **not** a dispatch-board-only field; it is the **operational reference** across dispatch, loads, issues, documents, and payroll **tracing**.

### Canonical vs denormalized (non-negotiable)

- **`dispatch_trips` is canonical.** `trip_number`, lifecycle `status`, and links to load / trailer move are **owned** here.
- If **`loads.active_dispatch_trip_id`** and/or **`loads.trip_number`** exist, they are **read-model / convenience fields only** (lists, search, fewer joins). They are **not** a second source of truth.
- **All writes** that materially change “what is the active trip for this load?” flow through **`dispatch_trips`** + the allocation/cancel services, which then **sync** denormalized columns in the same transaction. No random `UPDATE loads SET trip_number = …` elsewhere.
- Later contributors must **not** “fix” trip display by editing load rows; that pattern would drift from truth.

**Current codebase touchpoints (reference):**

- Loads: `app/models/load.py`, `app/services/loads.py` (`update_load`, `list_loads_for_board`, list/search), `app/routers/loads.py`, `app/schemas/load.py` (`LoadResponse`)
- Dispatch board: `app/routers/dispatch.py`, `apps/web/src/pages/DispatchPage.tsx` (assign + `status: dispatched`)
- Load UI: `apps/web/src/pages/LoadDetailPage.tsx`, `LoadsListPage.tsx`
- Tenant admin: `app/routers/tenant_admin.py` (pattern for tenant-scoped settings + `get_tenant_db` / platform + tenant split — **numbering lives in tenant DB**)
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

**Core function signature (conceptual):**

```text
async def ensure_active_trip_for_load_assignment(
    db: AsyncSession,
    tenant_id: int,
    load: Load,
    *,
    assigned_at: datetime | None = None,
) -> DispatchTrip
```

**Steps (single transaction with `update_load` or called from it):**

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

Canonical state is always on **`dispatch_trips.status`**. Suggested **v1 vocabulary** (adjust enum names in code, not concepts):

| Status | Meaning |
|--------|---------|
| **`active`** | Current operational trip for that load/trailer move; at most one per target ([§1.2](#12-dispatch_trips)). |
| **`cancelled`** | Dispatch assignment was **undone** or voided (load left dispatched pool or similar). Row **retained**; `trip_number` **immutable**; **never reused**. |
| **`superseded`** | A **new** active trip was minted for the same load (rare product path). Historical row; still searchable. |
| **`completed`** | *(Optional v1)* Operational closure when load reaches terminal state (e.g. **delivered**) — trip is no longer “active” but remains **searchable** and **referenceable** for payroll/audit. If v1 skips `completed`, **`active`** may persist until `cancelled`; product can add `completed` later. |

**“Voided”** in UI copy maps to **`cancelled`** unless legal/compliance later needs a distinct `voided` code — same semantics: not deleted, not reused.

**Searchability:** All non-deleted `dispatch_trips` rows remain queryable by **`trip_number`** and filters for **admin / support / payroll tracing**, including **cancelled** and incomplete trips.

**Payroll references:** If a pay line or entry recorded **`trip_number`** (or optional `dispatch_trip_id`) while the trip was **active**, that reference **remains valid** after **`cancelled`** or **`completed`** — it is **historical tracing**, not “trip must be active to pay.” Numbers are **not** recycled onto new trips.

**Resource-only reassignment:** Changing **driver / truck / trailer** on the load **without** undoing dispatch commit does **not** change `dispatch_trips.status` or `trip_number`; only resource FKs on **`loads`** update.

---

## 4. Dispatch assignment integration point

**Primary hook:** `app/services/loads.py` — **`update_load`**, after field validation, **before** `commit`.

### 4.1 Locked commit point (business rule — not a loose enum)

This matches [`DISPATCH_TRIP_NUMBER_RULE.md`](./DISPATCH_TRIP_NUMBER_RULE.md) **§3 Allocation timing**.

- **Trip number is born** on the **first transition of the load into `dispatched` status** (`old_status != 'dispatched'` → `new_status == 'dispatched'`).
- Transition **only** into **`assigned`** (without `dispatched`) **does not** allocate a trip — resources may be “slotted” first; **dispatch commit** is the **`dispatched`** edge (aligned with `DispatchPage.tsx` **Dispatch** button today).
- Implementation: one internal constant, e.g. `TRIP_ALLOCATED_AT_LOAD_STATUS = "dispatched"`, and a single branch in `update_load` — **do not** leave “maybe assigned, maybe dispatched” in code comments.

**Eligibility at commit:** Require valid dispatch commit per product — **recommend** **driver_id** and **truck_id** NOT NULL when entering `dispatched` (match current UI guard); allocator runs **after** status/resource checks succeed.

### 4.2 Algorithm sketch

- If **new status is `dispatched`** and **no active `dispatch_trips`** row for this load → call **`ensure_active_trip_for_load_assignment`** (allocates + syncs load read-model if present).
- If **already `dispatched`** and only **`driver_id` / `truck_id` / `trailer_id`** change → **do not** allocate; existing active trip unchanged ([§3b resource-only](#3b-trip-row-lifecycle-cancelled-completed-superseded-resource-only)).
- If status moves **from `dispatched`** back to a **pre-dispatch** status (undo) → set active trip to **`cancelled`**, clear load **read-model** pointers; **never** delete row or reuse number.
- New operational trip later → new `dispatch_trips` row + **`superseded`** or prior **`cancelled`** per [baseline lifecycle](./DISPATCH_TRIP_NUMBER_RULE.md#2-assignment-lifecycle).

**Other entry points:** Bulk dispatch, mobile, etc. must call the **same** allocator on the **same** `dispatched` commit semantics.

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
| **Admin — dispatch numbering** | Form: prefix, lock; show error link when dispatch blocked |
| **`DispatchPage.tsx`** | Card / row: show **`trip_number`** when present; handle 409 from API with toast + link to admin |
| **`LoadDetailPage.tsx`** | Header/summary: **`trip_number`** next to `load_number` with clear labels (“Broker ref” vs “Trip”) |
| **`LoadsListPage.tsx`** | Column or secondary line for `trip_number`; search box passes `trip_number` query if backend supports |
| **`LoadInboxPage.tsx`** / intake | Show **`trip_number` only when it exists** (post-`dispatched` / active trip). **Never** fabricate or reserve trip numbers during intake or draft stages ([intake boundary](#intake-and-draft-boundary) below) |
| **Global search (future)** | Route to trip or load by `trip_number` |
| **Issue / `issue_hold` UX** | When moving load to issue or showing notes, display **trip** prominently; future issue form: store `dispatch_trip_id` |
| **Payroll — pay entry list / edit** | Optional columns “Trip #”; exports / printed pay detail include `trip_number` when set |
| **Pay run / settlement review** | Line items show trip for traceability |
| **Driver-facing / print** | Trip sheets, summaries: **`trip_number`** as operational id |

**API client:** `apps/web/src/api.ts` — extend `Load` type + admin numbering functions + payroll types.

### Intake and draft boundary

- **Draft / email-intake loads** have **no** `trip_number` until dispatch assignment **commits** ([baseline](DISPATCH_TRIP_NUMBER_RULE.md): not at draft creation, not in intake pipeline).
- UI: omit trip field or show “—” / “After dispatch” for pre-dispatch loads; **do not** call numbering APIs from intake.

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

1. **Schema** — migrations for `tenant_dispatch_numbering`, `dispatch_trips`, constraints, partial uniques, optional load read-model columns.  
2. **Numbering config API** — admin prefix get/put + lock; block rules documented.  
3. **Allocation service** — `FOR UPDATE` sequence; create `dispatch_trips`; sync load read-model; tests.  
4. **Dispatch assignment integration** — `update_load` locked to **`dispatched`** transition ([§4.1](#41-locked-commit-point-business-rule--not-a-loose-enum)); cancel → [§3b](#3b-trip-row-lifecycle-cancelled-completed-superseded-resource-only).  
5. **Read APIs + search** — `LoadResponse`, board, list filters by `trip_number`, optional trip-by-number GET.  
6. **UI surfaces** — admin numbering, dispatch board, load detail, lists (intake: [boundary](#intake-and-draft-boundary)).  
7. **Payroll + issue references** — proportional tracing ([§1.6](#16-settlement--payroll-proportional-tracing--do-not-redesign-payroll), [§7](#7-issue--exception-and-settlement-paths-cross-module)); trailer moves allocator when entity exists.

**Prerequisite before coding:** Commit point in **§4.1** is **locked** to **`dispatched`** in v1 (also mirrored in baseline **§3**).

### First slice (implemented in repo)

- Tenant migration **`e7f8a9b0c1d2`**: `tenant_dispatch_numbering`, `dispatch_trips`, load read-model columns + FK.
- Models: `app/models/dispatch_trip.py`, `Load` extensions (read-model only).
- Services: `app/services/dispatch_trips.py` (prefix lock, allocate, cancel active); `update_load` integration in `app/services/loads.py` (**mint only** on first **`dispatched`**; cancel trip when returning to draft/ready/unassigned).
- Admin API: `GET`/`PUT` `/api/v1/admin/dispatch-numbering` (`app/routers/dispatch_numbering_admin.py`).
- Schemas: `LoadResponse` exposes read-model ids; `LoadCreate`/`LoadUpdate` reject client trip fields.

---

## 9. Verification checklist (post-implementation)

- [ ] First transition to **`dispatched`** after prefix lock creates `dispatch_trips` + visible `trip_number` (not on **`assigned` alone`).  
- [ ] Dispatch without locked prefix → **409/422** + stable `TRIP_NUMBER_PREFIX_NOT_CONFIGURED`.  
- [ ] Resource-only reassignment → **same** trip number.  
- [ ] Cancel dispatch → trip row **not** deleted; number **not** reused.  
- [ ] Search finds load by **`trip_number`**.  
- [ ] Payroll line or entry can show **`trip_number`** when linked.  
- [ ] Baseline doc scenarios ([`DISPATCH_TRIP_NUMBER_RULE.md`](./DISPATCH_TRIP_NUMBER_RULE.md)) satisfied.
