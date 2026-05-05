# TruckERP — Decision 9 / Load readiness and planning queue mapping

**Status:** **LOCKED** (direction — product semantics; implementation still **not** started).  
**Related:** `DECISION_6_DISPATCHER_LOAD_WORKSPACE_ACTION_MODEL.md`, `DECISION_7_ACTIVE_EXECUTION_SIGNAL_MODEL.md`, `DECISION_8_DRIVER_DISPATCH_PACKAGE_SCHEMA.md` (draft), `TRIP_EXECUTION_CUSTODY_MASTER_INDEX.md`, `PHASE3L_B_TRIP_ASSIGNMENT_CONTRACT.md`, `PHASE3L_C_TRIP_EXECUTION_SCHEMA_API_PLAN.md`.

---

## Locked decision

**Save Draft** and **Save Ready** are **load-preparation** / **readiness** states, **not** **trip-execution** states.

When the dispatcher **saves a verified load without assigning it**, the load is intended to land in a **Ready / Unassigned Load Planning Queue** (product meaning below; exact UI/API/DB representation is **implementation detail**).

---

## Meaning

### Save Draft

- Load is **incomplete** or **still being reviewed**.

### Save Ready

- Load is **verified enough** for **dispatch planning**: scheduling, assignment, **combining**, **splitting**, or **holding for later**.

### Ready / Unassigned Load Planning Queue

- Load is **clean enough to work with**.
- Dispatch can decide **later** what **trip** the load belongs to (if any).
- Load is **not yet committed** to driver / truck / trailer.
- Load **can** be added to a **new** trip.
- Load **can** be added to an **existing** trip.
- **Multiple** ready loads **can** be **combined** into **one** trip.
- **Multiple** ready loads **can** be **split** into **different** trips.

---

## Example

Two **Boston** loads are **Save Ready**.

**Option A — one trip**

Both loads on **Trip IKL10001**:

- Load A pickup  
- Load B pickup  
- Load A delivery  
- Load B delivery  

**Option B — split**

- **Trip IKL10001** = Load A only  
- **Trip IKL10002** = Load B only  

**Option C — partial commit**

- Load A **assigned** now (trip action).  
- Load B stays in **Ready / Unassigned** queue.

---

## Hard boundaries — **Save Ready** does **NOT** (by itself)

- **Create a Trip**
- **Assign** driver / truck / trailer
- Create **`TripLoad` membership** automatically — **unless** the user explicitly chooses a **trip** action (add to trip, create trip + add, etc.)
- **Send** driver **dispatch package** (**Decision 6** — **Assign & Send** is separate)
- **Start active execution** (**Decision 7**)
- Set **`Trip.status = assigned`** or **`in_progress`**
- Set **`Load.status = dispatched`**
- **Start custody**
- **Trigger payroll**
- **Rewrite** the dispatch board

**Cross-check:**

- **Decision 6** defines **Save Draft / Save Ready / Assign / Assign & Send** — Decision 9 pins **preparation vs execution** boundaries for **Save Ready** (and **Save Draft** as not-ready).
- **Decision 7** — package send and assignment do **not** equal **`in_progress`**; **Save Ready** does **not** advance trip execution.

---

## Trip-first boundary

| Layer | Role |
|-------|------|
| **Load** | Commercial / broker / customer **truth** and **verification / preparation** object. |
| **Trip** | **Operational execution** container. |
| **`TripLoad`** | **Explicit membership** between **Trip** and **Load**. |

**Decision 9** does **not** make the **Load page** the **final operational execution root**. It only states: **verified loads** enter a **planning queue** until dispatch chooses the **next** action (trip membership, assignment, etc.).

---

## Legacy / current board note

**Current production** may still use **`Load.status`** and **legacy** **dispatched** **board** behavior. Conclusion **for this decision:** **Do not rewrite the board** as a prerequisite of adopting Decision 9 semantics. Decision 9 defines the **target readiness / planning meaning** and should **coexist** with legacy behavior until a **deliberate** migration.

**Legacy dispatch cutover (Slice 1, code):** Regardless of future queue UX, the API no longer allows **new** **`Load.status → dispatched`** via **generic PATCH**; use **Trip** / **`TripLoad`** / planned-trip flows for **new** operational commitment (**`LEGACY_LOAD_STATUS_DISPATCH_DEPRECATED`** on violation).

---

## Production reality note

If **production testing** shows this **queue model** creates **workflow problems**, **revisit** the design **before** implementation proceeds **deeper**.

---

*End of Decision 9 — load readiness and planning queue mapping.*
