# 🔒 TruckERP — Load Lifecycle & Operational Events (LOCKED)

**Status:** locked. Changes require explicit architecture review.

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

## 2) Load Lifecycle (High-Level Only)

This is the stable lifecycle (**do not overload this**):

- Draft
- Ready
- Assigned
- Dispatched
- In Transit
- Delivered
- Closed

Notes:

- **Delivered** = operational completion
- **Closed** = business/accounting completion
- Do **not** add split/reject/yard into lifecycle

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

System state:

- Lifecycle: **In Transit**
- Progress: **Partial Delivery**
- Remaining Stops: **2**

### 3.5 Rejected Delivery

Receiver refuses freight.

System result:

- Custody → **Driver**
- Status → **Problem / Hold**
- Next → **Return to yard** OR **reattempt**

### 3.6 Return to Yard (CRITICAL)

Failed delivery → driver returns freight.

System state:

- Lifecycle: **In Transit**
- Sub-status: **Yard Hold**
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

State:

- Lifecycle: **In Transit**
- Sub-status: **Partial Delivery / Returned to Yard**
- Custody: **Yard (Trailer 404)**

Next Action:

- Reassign remaining 2 stops

Result:

- New Trip T005
- Driver: new driver
- Stops: remaining 2

---

## 5) Design Rules (LOCK THESE)

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

- **Load** = persistent truth
- **Trip** = execution layer
- **Events** = state changes

🔒 **STATUS: LOCKED ARCHITECTURE**

This model must be followed for:

- Dispatch UI
- Trip system
- Load handling
- Future automation

