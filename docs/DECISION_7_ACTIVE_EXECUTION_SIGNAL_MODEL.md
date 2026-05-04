# TruckERP — Decision 7 / Active execution signal model

**Context:** Trip **execution / custody** layer after **planned-trip lifecycle** and **Decision 6** (dispatcher load workspace). **Implementation has not started.** This document is **report / product decision only** — not code.

**Related:** `TRIP_EXECUTION_CUSTODY_MASTER_INDEX.md`, `DECISION_6_DISPATCHER_LOAD_WORKSPACE_ACTION_MODEL.md`, `PHASE3L_C_TRIP_EXECUTION_SCHEMA_API_PLAN.md`, `PHASE3L_D_OWNER_DECISION_CHECKLIST.md`.

---

## Locked decision

**Active execution does not start from trip assignment alone.**

### Assignment / Assign & Send only mean

- Driver / truck / trailer are **committed**.
- **Dispatch package** may be **sent** to the driver.
- Driver may receive **all load/trip info** before finishing the **current** trip.

### They do **not** mean

- Truck **started moving**
- **Pickup** happened
- **Custody** started
- Load **delivered**
- **Payroll** started
- **Dispatch board** rewritten

---

## When active execution begins

**Active execution** begins from the **first real execution signal**.

### Accepted execution signals

**1. Driver app status update**

- Start Trip
- En Route
- Arrived Pickup
- Loaded
- Arrived Delivery
- Delivered

**2. Dispatcher manual action**

- Start Trip / Mark En Route
- Manual correction if driver forgot or app failed

**3. Future geofence signal (not implemented now)**

- Truck enters pickup / delivery **geofence**
- Truck leaves stop geofence after configured distance/radius (e.g. **2–5 miles**)

**Geofence rules:** Events should start as **suggestion / confidence / auto-event** with **manual override**. **Do not implement geofencing now** — future work only.

---

## Simple `Trip.status` model (product)

| Status | Meaning |
|--------|---------|
| **`planned`** | Trip exists; **no** committed driver/equipment yet. |
| **`assigned`** | Driver/truck/trailer **committed**; package **may** be sent; **not** moving yet. |
| **`in_progress`** | **First real execution signal** has occurred. |
| **`completed`** | Trip **responsibility** is finished (aligned with **Decision 1** — not “load delivered” on trip). |
| **`cancelled`** | Trip cancelled; **number not reused** (per **3L-D**). |

### Vocabulary: **`dispatched`** (legacy / ambiguous — not `Trip.status` after `assigned`)

Outside this ladder, **`dispatched`** often appears on **`Load.status`**, the **dispatch board**, and **`dispatch_trips`** / mint rules (“load dispatched”). That usage is **legacy load-centric vocabulary** and is **easy to confuse** with “driver sent the packet” vs “truck rolling.” **Decision 7 supersedes** any plan to use **`Trip.status = dispatched`** as the **next** state after **`assigned`**. If granular road/terminal labels are needed, model them as **stop-level status**, **timeline**, or **`in_progress` sub-states** — not a **`Trip.status = dispatched`** hop after commitment.

### Stop-level statuses (later)

May later track, per stop or operational row:

- pending
- en_route
- arrived
- loaded / unloaded
- delivered
- departed

---

## Business rule

**Future assigned trips** are allowed while the driver is still completing a **current active trip**.

---

## Guardrail

- **Block** or require **supervisor override** for **overlapping active execution** for the same driver/truck/trailer.
- **Do not** block **future planning / assignment** (queued **assigned** trips remain allowed).

---

## Geofencing note

**Geofencing is future work. Do not implement now.** When added, it should support arrival / departure / delivered **suggestions** or **auto-events** with **confidence** and **manual override**.

---

## Cross-check against Decision 6

| Decision 6 | Decision 7 |
|------------|------------|
| **Assign & Send** sends a **versioned driver dispatch package**. | Sending that package **does not** start **active execution**. |
| **Assign** = commitment. | Only the **first execution signal** moves the trip into **`in_progress`**. |

---

*End of Decision 7 — active execution signal model.*
