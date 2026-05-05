# Phase 3L-C — Trip execution / custody schema + API plan (report only)

**Type:** Implementation-facing plan. **Not code.**  
**Upstream:** `PHASE3L_A_TRIP_EXECUTION_CUSTODY_DECISION_RECORD.md`, `PHASE3L_B_TRIP_ASSIGNMENT_CONTRACT.md`, `PLANNED_TRIP_LIFECYCLE_MODULE_CLOSE.md`.

**Legacy dispatch cutover (Slice 1):** **Generic `Load` PATCH** no longer introduces **new** **`Load.status = dispatched`** (**`409`**, **`LEGACY_LOAD_STATUS_DISPATCH_DEPRECATED`**). Board/read compatibility persists; writers for **new** dispatch/trip work are **Trip**-centric per this plan and **Decisions 6–7**.

---

## 1. Current schema / API baseline

### 1.1 `trips` (today)

- **Columns:** `id`, `tenant_id`, `trip_number`, **`status`** (`String(32)` — product uses **`planned`** / **`cancelled`**), `job_type`, `trailer_move_id` (legacy/unused in planned module context), `legacy_dispatch_trip_id` → `dispatch_trips.id`, **`driver_id`**, **`truck_id`**, **`trailer_id`**, **`assigned_at`** (nullable; not set on planned-trip create today), **`cancelled_at`**, `created_at`, `updated_at`.
- **Indexes:** tenant + `status`, trip_number unique per tenant, driver/truck/trailer, legacy id partial unique.

### 1.2 `trip_loads` (today)

- **Columns:** `id`, `tenant_id`, `trip_id`, `load_id`, **`status_within_trip`** (`String(32)`; **planned** memberships use **`planned`**; legacy/mirror uses **`active`** / **`removed`** on soft-remove), `sequence_hint`, `added_at`, **`removed_at`**, timestamps.
- **Constraints:** composite FK `(tenant_id, load_id)` → `loads`; **partial unique** active membership `(tenant_id, trip_id, load_id)` where **`removed_at IS NULL`**.

### 1.3 `loads` (today — assignment / mirror)

- **`driver_id`**, **`truck_id`**, **`trailer_id`** — dispatch/load workspace assignment.
- **`active_trip_id`** → planned **`trips.id`**; **backend mirror** from active `trip_loads` (not client-authoritative).
- **`trip_number`**, **`status`** (`DISPATCH_STATUSES` — still **drives dispatch board**).
- Other: `current_location`, `location_source` (not a custody chain).

### 1.4 Routes under `/api/v1/trips` (today)

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/trips` | Create planned trip (+ optional assignment + optional `load_ids`) |
| GET | `/trips` | Paginated list + filter |
| GET | `/trips/{id}` | Detail + member loads |
| POST | `/trips/{id}/cancel` | Cancel container |
| POST | `/trips/{id}/loads` | Add load |
| POST | `/trips/{id}/loads/{load_id}/remove` | Remove load (soft) |

**Missing for execution/custody:** assignment **update**, **status transition**, **custody events** write/read, **timeline** aggregate, **`trip_stops`** (if ever).

### 1.5 Gap summary

- No **execution** `Trip.status` values or transitions in DB/service.
- No **custody** or **terminal** first-class tables.
- No **audit row** per trip status change (only `updated_at`).
- **`Load.status`** remains the only operational column the **board** uses; no **`effective_*`** assignment on `LoadResponse`.

---

## 2. Minimal future DB changes (proposed)

### 2.1 Smallest safe additions

| Area | Proposal |
|------|----------|
| **`Trip.status`** | Keep **`String(32)`** (or widen if needed); add **CHECK constraint** or **app-enforced allowlist** for execution values; **migrate existing** `planned` / `cancelled` unchanged. |
| **Trip status audit (optional but recommended)** | **`trip_status_events`** (or `trip_state_history`): `id`, `tenant_id`, `trip_id`, `from_status`, `to_status`, `at`, `actor_user_id`, `reason`, `metadata` JSON optional — **append-only**; supports 3L-A audit needs without overloading `trips` row. |
| **Custody** | **`load_custody_events`** (name TBD): append-only facts keyed primarily by **`load_id`**; nullable **`trip_id`**, **`terminal_id`**, trailer from/to, **`event_type`**, **`event_at`**, **`actor_user_id`**, notes, source, void/correct columns (see §4). |
| **Terminal / yard** | **No** shared first-class terminal table found in models today (`LoadStop` has free-text-ish facility fields; `loads.current_location` is not structured). **v1 recommendation:** new **`terminals`** (or `yard_locations`) table: `id`, `tenant_id`, `name`, optional address FK or inline fields, `active` flag — **small**, tenant-scoped. **Alternative:** defer `terminal_id` and use **UUID/text `external_location_ref`** on events only — weaker for reporting; not preferred unless speed-critical. |
| **Indexes** | Every new table: **`(tenant_id, …)`** btree; custody: **`(tenant_id, load_id, event_at)`**, **`(tenant_id, trip_id, event_at)`** optional; partial index **`WHERE voided_at IS NULL`** if querying “current chain valid events.” |
| **Tenant isolation** | All PK/FK patterns match existing: **`tenant_id`** on row + composite FKs to `loads`/`trips` where applicable. |

### 2.2 What **not** to add yet (3L-C scope discipline)

- **`trip_stops`** / full operational stop graph (3L-A open question).
- **Quantity / partial skid** transfer columns beyond nullable placeholders (optional future fields can be NULL in v1).
- **Dock/door** modeling (3L-A V2).
- **Dispatch board** materialized views.
- **Renaming** `dispatch_trips` or merging with `trips`.
- **Auto-sync** `Trip` assignment → `loads.*` (forbidden by default per 3L-B).

---

## 3. Trip status expansion

### 3.1 Recommended canonical set (align with 3L-A §3)

**Decision 7 (locked) — trip header ladder:** **`planned` → `assigned` → `in_progress` → `completed`**, plus **`cancelled`** as terminal negative. **`in_progress`** = **first real execution signal** (not assignment or Assign & Send alone) — see **`DECISION_7_ACTIVE_EXECUTION_SIGNAL_MODEL.md`**. **Do not** introduce **`Trip.status = dispatched`** as the next container state after **`assigned`**. The rows below for **`dispatched`**, **`in_transit`**, and **`at_terminal`** are **pre–Decision-7 / exploratory granularity** — treat as **legacy trip-header vocabulary** or map to **stop-level**, **timeline**, or **sub-states under `in_progress`**; **Decision 7 supersedes** them for **`Trip.status`** after **`assigned`**.

| Status | Container-level | Notes |
|--------|-----------------|--------|
| `planned` | Yes | Current. |
| `assigned` | Yes | Resources committed (may pair with `assigned_at`); package may be sent; **not** active execution yet (**Decision 7**). |
| **`in_progress`** | Yes | **Locked** product state: **active execution** started (first accepted signal). |
| `dispatched` | Historical note | **Not** the next **`Trip.status`** after **`assigned`**. **Legacy / ambiguous** label (often confused with **`Load.status = dispatched`**). |
| `in_transit` | Historical note | **Pre–Decision-7** proposal; prefer **`in_progress`** + custody/timeline for trip header, or stop-level status. |
| `at_terminal` | Historical note | **Pre–Decision-7** proposal; same reconciliation as `in_transit`. |
| **`completed`** | Yes | **Recommended** as the trip-container terminal state meaning **assignment / operational responsibility ended** (including “delivered all” OR “handed off per custody” per 3L-A). |
| `cancelled` | Yes | Existing; keep **`cancelled_at`**. |
| **`voided`** | Optional | Admin “never happened”; only if audit needs ≠ `cancelled`. |

### 3.2 **`delivered` vs `completed`**

- **Recommendation:** Use **`completed`** on **`Trip.status`** for **container closed**.
- **Do not** use **`delivered`** on `Trip` unless product insists — it collides mentally with **`Load.status == delivered`** and with “all commercial loads delivered.”
- **All loads commercially delivered** remains reflected on **`Load.status`** (and custody **`delivered`** **event**), not necessarily as `Trip.status = delivered`.

### 3.3 Enum vs text

- **PostgreSQL:** Prefer **`TEXT` + CHECK** allowlist in migration **or** **SQLAlchemy-validated string** matching current `Trip.status` pattern (already `String(32)`).
- **Avoid** rigid DB ENUM type **unless** team wants migration friction on every new state; **Python/constants** as single source of allowed strings is often enough.

---

## 4. Custody event model

### 4.1 Proposed table: `load_custody_events` (illustrative)

| Column | Type | Notes |
|--------|------|--------|
| `id` | bigint PK | |
| `tenant_id` | int, NOT NULL | |
| `load_id` | int, NOT NULL | Composite FK `(tenant_id, load_id)` → `loads` |
| `trip_id` | int, nullable | FK trip when event is on a trip context |
| `from_trip_id` | int, nullable | **Handoff** source trip |
| `to_trip_id` | int, nullable | **Handoff** destination trip |
| `terminal_id` | int, nullable | FK to `terminals` if introduced |
| `from_trailer_id` / `to_trailer_id` | int, nullable | Trailer transfer |
| `from_truck_id` / `to_truck_id` | optional | If needed for audit |
| `event_type` | string | See §4.2 |
| `event_at` | timestamptz | Operational time |
| `recorded_at` | timestamptz | Server default now |
| `actor_user_id` | int, nullable | Platform/user id as available |
| `notes` | text, nullable | |
| `source` | string, nullable | `dispatcher_ui`, `mobile`, `api`, `import`, etc. |
| `voided_at` / `voided_by` / `void_reason` | nullable | **Correction pattern** (3L-A) |
| `replaces_event_id` | bigint, nullable | Link correction to voided row |

**v1:** Optional **JSON `payload`** for extensibility (terminal name snapshot if `terminal_id` null during rollout).

### 4.2 Minimum v1 `event_type` values

| Type | Intent |
|------|--------|
| `picked_up` | Freight **on** equipment / trip starts pickup obligation (tie to load + trip). |
| `arrived_terminal` | Arrival at terminal (with `terminal_id`). |
| `dropped_at_terminal` | Unload/stage at terminal (distinct from “on trailer in yard”). |
| `picked_up_from_terminal` | Outbound from terminal onto equipment / trip. |
| `trailer_transfer` | A→B trailer move (use from/to trailer ids). |
| `delivered` | **Commercial** delivery / receiver (still distinct from `Trip.completed`). |
| `handoff` | Explicit **trip-to-trip** or **trip-to-terminal custody** boundary. |

**Naming:** snake_case stable identifiers; display labels in API/i18n layer.

---

## 5. API plan (future only — shapes at high level)

### 5.1 Assignment

- **`PUT /api/v1/trips/{id}/assignment`** — **dedicated** resource for clearer RBAC and auditing. Body: subset `{ driver_id, truck_id, trailer_id }`.
- **Response:** `TripDetailResponse` (or slim `TripAssignmentResponse` + etag).
- **Validation:** tenant-scoped assets (existing `_validate_assignment_targets` pattern); **guards** per 3L-B / trip not cancelled/voided.

### 5.2 Transition

- **`POST /api/v1/trips/{id}/transition`**  
  - Body: `{ "to_status": "...", "reason": "...", "custody_event_ids": [...] optional }`  
  - **Server:** state machine validates **from → to**; may **require** linked custody events for risky transitions (e.g. `completed` with undelivered members per 3L-A).
  - **Response:** updated `TripDetailResponse` + optional `trip_status_event` echo.

### 5.3 Custody write

- **`POST /api/v1/trips/{id}/custody-events`** **or** **`POST /api/v1/loads/{id}/custody-events`** (prefer **load-scoped** as primary — custody is **load chain** truth; trip id inside body).
  - Body: `event_type`, `event_at`, `terminal_id?`, trailer fields, `notes`, `source`.
  - **Response:** created event DTO + **no** silent `Load.status` change unless policy slice explicitly allows (§7).

### 5.4 Timeline reads

- **`GET /api/v1/trips/{id}/timeline`** — **merged projection**: `trip_status_events` + custody events for **all member loads** (sorted, paged).
- **`GET /api/v1/loads/{id}/custody-events`** — ordered list, filter `include_voided=false` default.

All endpoints: **`get_tenant_db`**, **`require_tenant`**, existing auth.

---

## 6. Assignment integration (3L-B)

- **Authority:** While active membership on **non-cancelled/non-voided** trip container → **trip assignment** wins for **movement** (3L-B §3.1–3.3).
- **No silent Trip → Load sync** on assignment update (3L-B §4).
- **Read-model only** for **effective** assignment: optional **`GET /loads/{id}`** enrichment (`effective_driver_id` + nested objects **computed** server-side) **or** trip detail in parallel — **document** contract for web.
- **Order:** **Assignment endpoint before** broad **transition** endpoint is reasonable: operators can set equipment while still **`planned`** / **`assigned`**; transitions then reference stable assignment. **Alternatively:** ship **transition** first only for `planned → assigned` with assignment in body — slightly heavier. **Recommendation:** **C (assignment)** before **D (transition)** in slices (§10).

---

## 7. `Load.status` coupling

**Important:** **`Trip.status`** must **not** use **`dispatched`** as the **execution** transition after **`assigned`** (**Decision 7**). **Legacy** **`load.status` → `dispatched`** still triggers **`dispatch_trips`** trip number allocation behavior (`TRIP_ALLOCATED_AT_LOAD_STATUS` and related mirror rules). **Trip execution** transitions (e.g. **`assigned` → `in_progress`**) must **not** auto-call that load-status/mint path in v1 — avoids **double-mint** and competing `dispatch_trips` rows.

| Trip transition | v1 recommendation for `Load.status` |
|-----------------|-------------------------------------|
| `planned` → `assigned` | **No auto change** (or optional: only if all loads already `assigned` — **default off**). |
| `assigned` → `in_progress` | **No auto** in v1. **`Load.status = dispatched`** stays **legacy board/mint** vocabulary — **not** defined as the automatic mirror of **`Trip.status`** (**Decision 7**). |
| `in_progress` → `completed` | **No automatic** `delivered` on loads. **completed** trip may coexist with loads still **`in_transit`/`arrived_delivery`** on the board until custody **handoff** + load updates done elsewhere. |

**v1 principle:** **Trip transitions do not mutate `Load.status`** unless a **future** **`LOAD_STATUS_COUPLED_TRANSITIONS`** feature is explicitly specified and tested — default **decoupled** to protect board and legacy mint logic.

---

## 8. Dispatch board impact

- **No board rewrite in 3L-C:** board remains **`Load.status`** buckets from `GET /dispatch/board`.
- **Why:** Avoid training/regression risk; trip execution ships **additive** API + trip UI first (3L-A §6).
- **Future trip-first board needs:** **`GET /dispatch/board-by-trip`** or aggregate; `TripList` with nested loads + **effective** assignment; optional denorm flag per 3L-B — **Phase F** in 3L-A.

---

## 9. Migration safety

| Topic | Approach |
|-------|----------|
| **Existing `planned` / `cancelled` trips** | **Keep** values; migration only **adds** new allowed strings / tables **without** rewriting rows. |
| **`cancelled_at`** | **Invariant:** `status == cancelled` rows continue to use **`cancelled_at`**; new columns **nullable**; no backfill required. |
| **`dispatch_trips` / legacy mirror** | **Do not** change `dispatch_trips` schema in 3L-C; **do not** change `TRIP_ALLOCATED_AT_LOAD_STATUS` behavior in same slice as custody **without** dedicated regression pass. |
| **Tenant order** | Standard: **platform** migrations untouched; **tenant** migrations run **per DB**; **feature flag** off until backfill scripts (if any) complete. |
| **Rollback** | New tables **drop** in down-migration; **CHECK** on `trips.status` — **expand-only** first revision (remove values is hard); prefer **add** new states without **removing** old. |

---

## 10. Implementation slices (recommended order)

| Step | Content |
|------|--------|
| **A** | **Schema migration only** — `terminals` (optional), `load_custody_events`, optional `trip_status_events`; widen/check `trips.status` allowlist in app + optional DB CHECK. |
| **B** | **Models + Pydantic DTOs + service skeleton** (no public routes or routes behind flag). |
| **C** | **Assignment endpoint** (3L-B compliant, audit fields). |
| **D** | **`POST transition`** — limited edges: e.g. **`planned→assigned`**, **`assigned→in_progress`** only until custody gating exists (**Decision 7** — **no** **`assigned→dispatched`** on **`Trip.status`**). |
| **E** | **Custody append endpoint** + minimal types (`picked_up`, `handoff`, `arrived_terminal`). |
| **F** | **`GET timeline` / `GET custody-events`**. |
| **G** | **Trip workspace UI** execution controls (behind flag). |
| **H** | **Dispatch board** read-model / second tab — **later**. |

---

## 11. Tests / proofs required

- **Migration:** upgrade head on scratch DB + **existing fixture** DB with `planned`/`cancelled` rows; verify **no data loss**.
- **State machine:** allowed/forbidden transitions from 3L-A §8; **cancelled** trip rejects forward transition.
- **Assignment contract:** assignment update **does not** write `loads.driver_id` without explicit sync mode; **effective** read if implemented matches 3L-B table.
- **Custody:** append-only; **void** creates new row / marks old; **no hard delete**.
- **`Load.status`:** assertions that default trip transition **does not** change load status (unless flag on in specific test).
- **`active_trip_id`:** integration test that only **membership services** update mirror; API rejects client patch to `active_trip_id` if ever exposed.
- **Tenant isolation:** cross-tenant negative tests on all new endpoints.

---

## 12. Open questions before coding

1. **`voided`:** separate status vs `cancelled` + reason?
2. **`terminals` v1:** required table vs **integer id stub** + name in event payload?
3. **First transition slice:** which **exact** edges ship without custody gating? (Aligned with **Decision 7:** **`planned→assigned`** first; **`assigned→in_progress`** when signals exist — **no** **`Trip.status = dispatched`** after **`assigned`**.)
4. **`completed` trip** with undelivered loads: **mandatory** custody event types / count?
5. **Coupling to `dispatch_trips`:** when **`Trip.status`** first reaches **`in_progress`** (or later execution states), interaction with **existing** **legacy** load-driven **`dispatched`** mint — **same release train** or **later**?
6. **`event_at` vs server time:** allow backdated events? **Max backdate** window?
7. **RBAC:** roles for transition vs custody vs void?
8. **Mobile / ELD** as `source` — in scope for v1 schema?

---

*End of Phase 3L-C trip execution schema + API plan.*
