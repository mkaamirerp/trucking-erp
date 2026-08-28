# 🔒 TruckERP — Load Lifecycle & Operational Events (LOCKED)

> **STATUS: PARTIALLY SUPERSEDED (2026-08-28).**  
> Keep this document for the durable principles that a Load persists across Trips, operational events matter, and custody must remain visible. Its old **Load lifecycle/status ladder** (`Assigned`, `Dispatched`, `In Transit`, `Delivered`, `Closed`) is **not** the current new-write `Load.status` model. For current status ownership use [`DECISION_11_LOAD_STATUS_TARGET_BOARD_MIGRATION.md`](./DECISION_11_LOAD_STATUS_TARGET_BOARD_MIGRATION.md): new writes are **`draft` / `ready` / `cancelled`**; Trip/TripLoad/custody own operational execution. For current Trip/Dispatch UI ownership use [`000_TRIP_CONTAINER_IS_DISPATCH_CONTROL_CENTER.md`](./000_TRIP_CONTAINER_IS_DISPATCH_CONTROL_CENTER.md).

**Status:** historical architecture lock with the status-ladder portion superseded by later decisions.

---

## 1) Core Principle

- **A Load is a continuous entity.**
- **A Trip is a temporary execution container.**
- **A Load does not end when a trip ends.**

Loads can:

- move forward
- split
- partially complete
- fail delivery
- return to yard
- be reassigned to new trips

---

## 2) Load Lifecycle (HISTORICAL — SUPERSEDED FOR `Load.status` NEW WRITES)

This was the earlier lifecycle model:

- Draft
- Ready
- Assigned
- Dispatched
- In Transit
- Delivered
- Closed

**Current rule:** do not implement this list as the new `Load.status` write model. Decision 11 owns current status semantics: `draft`, `ready`, `cancelled` for new writes; operational assignment/execution/delivery belongs to Trip / TripLoad / custody/event truth.

Historical notes:

- **Delivered** was used here as operational completion
- **Closed** was used here as business/accounting completion
- Do **not** add split/reject/yard into a single lifecycle field

---

## 3) Operational Events (Real-World Logic)

These define what actually happens to a load.

### 3.1 Pickup

- **Facility → Driver**

### 3.2 Delivery

- **Driver → Receiver**

### 3.3 Split Load 🔀

Load is divided across different trips.

- Load A → Trip T003 (South)
- Load B → Trip T004 (North)

Rules:

- **Same load record continues**
- **Only trip assignment changes**

### 3.4 Partial Delivery

Example:

- Total Stops: 10
- Delivered: 8
- Remaining: 2

Historical state wording in this document used:

- Lifecycle: **In Transit**
- Progress: **Partial Delivery**
- Remaining Stops: **2**

Current implementations should express execution/progress through Trip / TripLoad / custody/event models rather than introducing `In Transit` as a new `Load.status` write.

### 3.5 Rejected Delivery

Receiver refuses freight.

System result concept:

- Custody → **Driver**
- Operational problem / hold condition
- Next → **Return to yard** OR **reattempt**

Do not encode the operational problem as a new execution-style `Load.status` without a later explicit decision.

### 3.6 Return to Yard (CRITICAL)

Failed delivery → driver returns freight.

Conceptual state:

- Operational movement remains incomplete
- Custody: **Terminal / Yard / Trailer**

⚠️ This is **not** Delivered.

### 3.7 Reassignment

Remaining freight is moved to a new trip.

- Remaining Stops → New Trip T005
- New Driver Assigned

Rules:

- **Do not create new load**
- **Same load continues**
- **Only trip changes**

---

## 4) Combined Real Scenario (Reference)

Example: **Load B — JB Hunt**

- Stops: 10
- Delivered: 8
- Remaining: 2

Operational truth:

- Partial delivery / returned to yard
- Custody: **Yard (Trailer 404)**

Next Action:

- Reassign remaining 2 stops

Result:

- New Trip T005
- Driver: new driver
- Stops: remaining 2

---

## 5) Design Rules (STILL VALID UNLESS A LATER DECISION OVERRIDES THEM)

### Rule 1 — Load never splits into new loads

- Always remains **one load**
- Only trips branch

### Rule 2 — Lifecycle stays simple

- Do **not** mix lifecycle with operational events

### Rule 3 — Events drive reality

These define actual system behavior:

- Split
- Partial delivery
- Rejection
- Yard return
- Reassignment

### Rule 4 — Custody is always visible

At any point the system must answer:

- **Who has the freight right now?**

Options:

- Driver
- Terminal
- Trailer at yard
- Facility
- Unknown / disputed

### Rule 5 — Trip is disposable

- Trips start and end
- Load persists across trips

---

## 6) Summary (Core Model)

- **Load** = persistent commercial truth
- **Trip** = execution layer
- **Events / custody** = operational continuity truth

🔒 **DURABLE PRINCIPLES RETAINED; OLD LOAD STATUS LADDER SUPERSEDED**

For current implementation, cross-check:

- `DECISION_11_LOAD_STATUS_TARGET_BOARD_MIGRATION.md`
- `TRIP_EXECUTION_CUSTODY_MASTER_INDEX.md`
- `000_TRIP_CONTAINER_IS_DISPATCH_CONTROL_CENTER.md`
