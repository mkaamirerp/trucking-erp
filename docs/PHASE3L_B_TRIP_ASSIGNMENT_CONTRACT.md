# Phase 3L-B — Trip assignment contract

**Type:** Report-first normative contract (documentation only).  
**Prerequisite:** `docs/PHASE3L_A_TRIP_EXECUTION_CUSTODY_DECISION_RECORD.md` (execution/custody foundation).  
**Status today:** Planned-trip module ships **create** trip with optional `driver_id` / `truck_id` / `trailer_id`; **no** trip assignment **update** API; **`assigned_at`** on `trips` is not set on create (remains `NULL`).

This document locks **who owns movement assignment** and **how reads/syncs must behave** before **`PATCH /trips/{id}`** (or equivalent) and trip workspace assignment UI are implemented.

---

## 1. Purpose

- Prevent **split brain** between **Load** dispatch assignment and **Trip** container assignment.
- Define **source of truth** by **lifecycle phase** without requiring the dispatch board or Load workspace to change in this phase.
- Set **API/UI expectations** for **effective assignment** (what operators should see) when a load has **active `trip_loads` membership**.

---

## 2. Definitions

| Term | Meaning |
|------|--------|
| **Movement assignment** | The **driver**, **truck**, and **trailer** (equipment set) that **physically perform** or are **booked to perform** the trip’s operational movement. |
| **Active trip membership** | A `trip_loads` row with **`removed_at IS NULL`** for the tenant-scoped load. |
| **Planned trip container** | A `trips` row with `status` in **`planned`** / **`cancelled`** in the **current** product module (`TRIP_CONTAINER_STATUS_*`; execution statuses are **future** per 3L-A). |
| **Load assignment fields** | **`loads.driver_id`**, **`loads.truck_id`**, **`loads.trailer_id`** (and nested read models on `LoadResponse`). |
| **Trip assignment fields** | **`trips.driver_id`**, **`trips.truck_id`**, **`trips.trailer_id`**, optional timestamp **`trips.assigned_at`** (execution phases may define when it is set). |

---

## 3. Normative rules (contract)

### 3.1 Single movement owner during active membership

**While a load has active membership on a non-cancelled trip container:**

- **Trip assignment fields are authoritative for “who is moving this load on this trip.”**
- **Load assignment fields** remain **stored** and may differ historically; they are **not** overridden by the client and must **not** be interpreted as **current movement truth** without applying §3.3 **effective assignment** rules.

**Rationale:** Matches 3L-A §7 and avoids the dispatch board (still load-keyed) showing a driver that contradicts the trip the load is on.

### 3.2 Pre-membership and pool loads

**When a load has no active trip membership** (including `active_trip_id` **NULL** and no active `trip_loads`):

- **Load assignment fields are authoritative** for movement intent in the **unassigned / assigned / dispatch-pool** workflows that exist today (board, load workspace assignment strip).

### 3.3 Effective assignment (read model)

Implementations that need a **single display triple** (driver, truck, trailer) **MUST** use:

| Condition | Effective assignment |
|-----------|----------------------|
| Load has **active** `trip_loads` on trip **T** and **T** is **not cancelled or voided** | **`T.driver_id`**, **`T.truck_id`**, **`T.trailer_id`** (with nested driver/truck/trailer from trip read APIs) |
| Otherwise | **`Load.driver_id`**, **`Load.truck_id`**, **`Load.trailer_id`** |

**Optional projection (future):** `LoadResponse` could expose **`effective_driver_id`** / computed nested objects **server-side** to keep the web and integrations consistent; **until then**, consuming UIs that show both load and trip context must apply the table above explicitly.

### 3.4 No client-side repair of `active_trip_id`

**Locked:** The UI **must not** write or “fix” **`loads.active_trip_id`**. It is a **backend mirror** of active membership (see `PLANNED_TRIP_LIFECYCLE_MODULE_CLOSE.md`).

### 3.5 Multi-load trips

- **One** movement assignment triple lives on the **trip header** (`trips.*`).
- **All** active member loads on that trip **share** that movement assignment for **effective** display per §3.3.
- **Per-load overrides** (different driver per load on same trip) are **out of contract** unless explicitly added in a future revision.

### 3.6 Create trip with assignment (current backend)

- **`POST /api/v1/trips`** accepts optional `driver_id`, `truck_id`, `trailer_id`; server **validates** tenant ownership (`_validate_assignment_targets` in `app/services/trips.py`).
- **Null** on create means “unassigned at trip level” even if member loads still have load-level assignment.

### 3.7 Update trip assignment (not implemented yet)

**When `PATCH` (or dedicated endpoints) exist, the contract requires:**

- **Same validation** as create (tenant-scoped driver/truck/trailer exist).
- **Idempotent** semantics: repeated sets with same IDs are safe.
- **Auditing:** actor and timestamp (and optional reason) for assignment changes **before** payroll integration (minimum: `updated_at` + application log or future audit table).
- **No silent mirroring** to **`loads.*`** unless a **named sync mode** is enabled (§4).

**Guards (recommended until execution module exists):** Allow assignment updates only for **`planned`** trips with **`cancelled_at IS NULL`**; stricter rules when `Trip.status` gains execution values (3L-A §8).

### 3.8 Cancelled or voided trip

- **Cancelled or voided** trip container: **effective assignment** for loads **no longer** on an active membership falls back to **Load** fields (§3.3).
- Loads that were only on that trip: **trip row** may still show historical IDs; **product UI** should not treat **cancelled or voided** trip equipment as **current** movement without an explicit product decision.

### 3.9 Remove load from trip

- Backend ends active membership (`removed_at`, `status_within_trip` → removed pattern) and **refreshes** `loads.active_trip_id`.
- After removal: **effective assignment** for that load returns to **Load** fields unless it joins **another** trip.

---

## 4. Sync policy: Trip → Load (and reverse)

**Default (contract):** **Do not** automatically copy trip assignment onto every member **Load** row when trip assignment changes.

**Why:** Avoid hidden coupling, last-write-wins between load workspace and trip workspace, and unexpected board updates (3L-A §7.2–7.3).

**Allowed exceptions (require explicit feature flag + doc update):**

| Mode | Behavior |
|------|----------|
| **`BOARD_DENORM_SYNC`** (example name) | On trip assignment commit, **optionally** update **all** member loads’ `driver_id`/`truck_id`/`trailer_id` to match trip **if** load `status` is in an allowed set (e.g. not `delivered`). Must be **idempotent** and **logged**. |
| **One-shot on attach** | When adding a load to a trip, **optionally** initialize trip assignment from the first load or from a **dispatcher choice** — still **explicit** in API design, not silent magic. |

Any sync mode must remain consistent with **`active_trip_id`** and membership writes in `app/services/trips.py` (single service layer owns mutations).

---

## 5. Relationship to legacy `dispatch_trips` / load status

- **Today,** legacy **dispatch trip** behavior and **trip number minting** are still tied to **`Load.status`** transitions (`TRIP_ALLOCATED_AT_LOAD_STATUS`, `PRE_DISPATCH_TRIP_CANCEL_STATUSES` in `app/constants/trip_dispatch.py`).
- **Planned container** `trips` and **`trip_loads`** are a **separate** product path.
- **Contract:** This document does **not** merge the two worlds; it only defines **assignment authority** for loads with **trip container** membership (today primarily the **planned** lifecycle; future **`Trip.status`** values per **Decision 7** — **`assigned`**, **`in_progress`**, **`completed`**, **`cancelled`** — do not change §3.1–§3.3 while the load remains an active member on a container that is not **cancelled** or **voided**). **Legacy / pre–Decision-7** granular labels (**`dispatched`**, **`in_transit`**, **`at_terminal`** as **trip header** states) must **not** be read as overriding the locked ladder; prefer **`in_progress`** plus stop/timeline granularity. A **future** doc should map **when** legacy dispatch trip and planned container are unified (3L-A open question #8).

---

## 6. UI expectations (non-binding layout; binding semantics)

| Surface | Today | Contract expectation |
|---------|--------|------------------------|
| **Trip workspace** | Displays trip header assignment (name or `#id`). | **Reads** trip fields; if assignment editors are added, they **write trip only** (via future API), not load mirror repair. |
| **Load workspace / dispatch strip** | Edits **Load** assignment. | While load has **active membership on a trip container that is not cancelled or voided**, **prefer showing effective assignment** (§3.3); **editing** load assignment without leaving the trip may conflict with contract — **either** disable with explanation **or** define “detach / override” flows in a future revision. |
| **Dispatch board** | Uses **LoadResponse** per load. | Until **`effective_*`** or board denorm exists, board may **differ** from trip page for multi-load trips; **known gap** to close in a later phase (3L-A §6 / step F). |

---

## 7. `assigned_at` (trips)

- **Today:** Not set on planned-trip create.
- **Contract placeholder:** When execution/assignment phases are introduced, define **`assigned_at`** as “movement assignment **committed**” (dispatcher/driver booked) **distinct** from **`in_progress`** (first execution signal) and **distinct** from **legacy** **`Load.status = dispatched`** / “rolled out” wording on the board. Exact trigger is an **open** implementation detail.

---

## 8. Multi-phase alignment (3L-A sequence)

| Phase | Assignment contract role |
|-------|---------------------------|
| **3L-B (this doc)** | Freeze **source of truth** and **read rules** before PATCH/UI. |
| **3L-A step C–D** | Migrations + trip state transitions must **not** violate §3.1–3.3; new states may tighten **when** assignment can change. |
| **Trip workspace UI** | Pickers/patch must follow **§3.6–3.7** and **§4**. |
| **Board read-model** | May introduce **denorm** or **aggregates** per §4 exceptions. |

---

## 9. Open questions (for product / owner before PATCH)

1. **Load workspace while on trip:** Block load assignment edits, **warn-only**, or **auto-detach** from trip on change?
2. **`assigned_at`:** Set on first non-null trip assignment, or only when **`Trip.status`** becomes **`assigned`** (future)?
3. **Team / secondary driver:** Out of scope until people model supports it; trip row today has **single** `driver_id`.
4. **Partial assignment:** Is **driver-only** assign valid (truck/trailer NULL), and for **which** job types?
5. **BOARD_DENORM_SYNC:** Do any tenants require trip→load copy for TMS parity in v1 of PATCH?

---

## 10. References

- `docs/PHASE3L_A_TRIP_EXECUTION_CUSTODY_DECISION_RECORD.md` — §7 assignment implications, §9 step B, execution ladder.
- `docs/PLANNED_TRIP_LIFECYCLE_MODULE_CLOSE.md` — `active_trip_id` mirror, shipped behaviors.
- `app/models/trip.py`, `app/models/load.py` — column ownership.
- `app/services/trips.py` — `_validate_assignment_targets`, `create_planned_trip`, membership + mirror sync.

---

*End of Phase 3L-B trip assignment contract.*
