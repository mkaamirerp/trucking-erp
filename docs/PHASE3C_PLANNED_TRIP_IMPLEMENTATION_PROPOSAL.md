# Phase 3C — Planned Trip container (implementation proposal)

**Status:** Proposal only — **not** implemented by this document.  
**Locked product rules:** [`DISPATCH_TRIP_NUMBER_RULE.md`](./DISPATCH_TRIP_NUMBER_RULE.md), [`TRIP_CONTAINER_VS_LOAD_FOUNDATION.md`](./TRIP_CONTAINER_VS_LOAD_FOUNDATION.md) §11.1, [`TRIP_FIRST_DDL_CONTRACT.md`](./TRIP_FIRST_DDL_CONTRACT.md).  
**Allocator / migration context:** [`DISPATCH_TRIP_NUMBER_IMPLEMENTATION_PLAN.md`](./DISPATCH_TRIP_NUMBER_IMPLEMENTATION_PLAN.md).

---

## 1. Objective

Move **primary trip identity** to the **`trips`** Trip container: **mint `trip_number` on planned Trip create**, allow **zero active Loads**, keep **Load cancellation** and **Trip cancellation** separate, and expose **manual Trip cancel** + **membership add/remove** APIs—**without** changing parser/Lab, intake PDF behavior, or prematurely pivoting the dispatch board.

---

## 2. In scope (Phase 3C)

### 2.1 Planned Trip create (API)

- **`POST /api/v1/trips`** (name TBD) creates a **`trips`** row with `status` e.g. **`planned`** (or **`draft`** per enum lock).
- **Same transaction:** `tenant_dispatch_numbering` **`FOR UPDATE`**, mint **`trip_number`**, bump sequence — **one pool** with existing freight allocator ([baseline](./DISPATCH_TRIP_NUMBER_RULE.md)).
- **Optional at create:** `job_type`, nullable `driver_id` / `truck_id` / `trailer_id` (all may be null).
- **Zero `trip_loads` rows** at create is **valid** (scheduling shell).

### 2.2 Allocator: move / extend from `dispatch_trips` to `trips`

- **New Trip container** → **`INSERT trips`** carries **canonical `trip_number`**.
- **Legacy path:** Where code today mints on **`dispatched`** via **`dispatch_trips`**, Phase 3C **reconciles** so the same logical movement does **not** receive **two** numbers:
  - Preferred: **create or link `trips` first**, then **`dispatch_trips`** (if retained) references **`trips.id`** or mirrors lifecycle in the same txn; **or**
  - Transitional: dual-write in one transaction with explicit **single mint** rule (documented in service comments + tests).
- **Never** increment **`next_numeric`** twice for one new **`trips.id`**.

### 2.3 Zero-load planned trips

- **Read APIs** (`GET /api/v1/trips`, `GET /api/v1/trips/{id}`) already support **member_load_count = 0**; ensure list/detail **copy** explains planning shell ([`TRIP_CONTAINER_VS_LOAD_FOUNDATION.md`](./TRIP_CONTAINER_VS_LOAD_FOUNDATION.md)).
- **No** requirement to attach a Load at create.

### 2.4 Manual Trip cancel (API)

- **`POST /api/v1/trips/{id}/cancel`** (or `PATCH` with constrained body — exact shape TBD).
- **Effects:**
  - `trips.status` → **`cancelled`**
  - `cancelled_at` set when column exists (migration if missing on tenant `trips`).
  - **`trip_number` unchanged** forever.
  - All **active** `trip_loads` rows **closed** (`removed_at`, `status_within_trip` e.g. **`removed`**).
  - **Loads:** **not** auto-cancelled; commercial status unchanged unless a **separate** explicit action runs.

### 2.5 Add / remove Load membership

- **Add:** **`POST /api/v1/trips/{trip_id}/loads`** with `load_id`, optional `sequence_hint` — inserts **`trip_loads`** with appropriate `status_within_trip` (**`planned`** / **`active`** per rules), enforcing **partial unique** (no duplicate active `(tenant_id, trip_id, load_id)`).
- **Remove:** **`POST /api/v1/trips/{trip_id}/loads/{load_id}/remove`** (or DELETE with audit) — sets **`removed_at`**, **`status_within_trip = removed`**, **does not** by itself set **`trips.status = cancelled`**.
- **Authority:** Membership truth remains **`trip_loads`**; **`loads.active_trip_id`** updated only as **non-authoritative** convenience in same transaction if still used.

### 2.6 Load cancellation separate from Trip cancellation

- **Load cancel** = commercial / operational **`loads.status`** transition (add **`cancelled`** if product locks it) + any existing business rules.
- **Service rule:** Load cancel **closes** `trip_loads` membership for that load’s active trip link **but** **must not** auto-call **Trip cancel** ([§11.1](./TRIP_CONTAINER_VS_LOAD_FOUNDATION.md)).
- **Only Load on Trip cancels (before or after dispatch):** Trip stays **operational/audit** record; dispatcher may **manually cancel Trip**, **complete with exception**, or **add another Load** later ([foundation](./TRIP_CONTAINER_VS_LOAD_FOUNDATION.md) §11.1.7–11.1.8).

### 2.7 Tests (target)

- Mint on **`trips`** create; prefix missing → 409/422.
- Zero-load Trip list/detail.
- Manual Trip cancel closes memberships; Loads unchanged without second action.
- Load cancel does not set `trips.status = cancelled`.
- No double sequence bump for one Trip.

---

## 3. Deferred (not Phase 3C)

- **Dispatch board** pivot to trip-first layout and drag/drop.
- **Parser / Lab** changes; intake **load** draft still **does not** mint trips by itself.
- **`trip_stops`**, **custody**, **terminal handoff** execution models.
- **Payroll** schema redesign (tracing fields only, proportional to existing plan).
- **Trailer moves** full parity if not already modeled.
- **Removing `dispatch_trips`** entirely (may remain mirrored for one or more releases).
- **Auto Trip status transitions** when last load drops off (product may keep Trip **`planned`** or **`in_progress`** until dispatcher acts—lock in UX copy).

---

## 4. Dependencies

- **`tenant_dispatch_numbering`** row + locked prefix (existing admin path).
- Tenant **`trips`** / **`trip_loads`** tables (Phase 1 migration) + any **`cancelled_at`** column add if not present.
- Service flip / dual-write agreement with **Phase 2** read authority if `trips` is not yet live writer everywhere ([`PHASE1_TRIP_FOUNDATION_PLAN.md`](./PHASE1_TRIP_FOUNDATION_PLAN.md)).

---

## 5. Doc sync

When Phase 3C ships, update **verification checklists** in [`DISPATCH_TRIP_NUMBER_IMPLEMENTATION_PLAN.md`](./DISPATCH_TRIP_NUMBER_IMPLEMENTATION_PLAN.md) §9 and any **OpenAPI** descriptions for Trip create/cancel/membership.
