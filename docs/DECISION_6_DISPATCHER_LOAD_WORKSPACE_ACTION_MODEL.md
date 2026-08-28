# TruckERP — Decision 6 / Dispatcher load workspace action model

> **STATUS: LOCK RETAINED, IMPLEMENTATION-STATE TEXT UPDATED BY LATER DECISIONS.**  
> The action meanings in this document remain part of the decision spine. However, the original statement that implementation “has not started” is historical. Read [`DECISION_14_TRIP_ASSIGNMENT_FIRST_SLICE.md`](./DECISION_14_TRIP_ASSIGNMENT_FIRST_SLICE.md) for the later assignment slice and [`000_TRIP_CONTAINER_IS_DISPATCH_CONTROL_CENTER.md`](./000_TRIP_CONTAINER_IS_DISPATCH_CONTROL_CENTER.md) for current UI ownership: **Trip page = Trip Container = Dispatch Control Center**. Load Workspace remains commercial/readiness/document truth and may initiate or link to trip actions; it is not the execution control center.

**Context:** This decision was written while designing the trip **execution / custody / assignment** layer after the **planned-trip lifecycle** foundation. It is a **product decision**, not a claim that later implementation has not begun.

**Related:** `TRIP_EXECUTION_CUSTODY_MASTER_INDEX.md`, `PHASE3L_B_TRIP_ASSIGNMENT_CONTRACT.md`, `PHASE3L_C_TRIP_EXECUTION_SCHEMA_API_PLAN.md`, `PHASE3L_D_OWNER_DECISION_CHECKLIST.md`, `DECISION_14_TRIP_ASSIGNMENT_FIRST_SLICE.md`, `000_TRIP_CONTAINER_IS_DISPATCH_CONTROL_CENTER.md`.

---

## Locked decision

The dispatcher verifies and corrects commercial/load data from the canonical **Load Workspace**. The dispatcher chooses the **next business action** from a **top action bar** or dropdown. Operational execution itself belongs to the Trip-backed Dispatch Control Center per 000.

### Preferred UI action bar

1. **Save Draft**
2. **Save Ready**
3. **Assign**
4. **Assign & Send**

If there is room, show **buttons**. If not, use a **primary** button plus **dropdown** / **more actions** menu.

---

## Action meanings

### 1. Save Draft

- Save current load data.
- Used when load is **incomplete** or still being reviewed.
- Does **not** make the load ready for dispatch.
- Does **not** require trip assignment.

### 2. Save Ready

- Save **verified** load data.
- Marks load as **clean / ready** for planning or assignment.
- **No** driver/truck/trailer required.
- Load can appear in an **unassigned / ready** planning area later.

### 3. Assign

- **Creates or updates** the **trip assignment** (driver, truck, trailer as applicable).
- **`Trip.status` may become `assigned`** when transitioning from **`planned`** per execution slice rules.
- This is **dispatch commitment only** — it does **not** send the dispatch package to the driver unless a separate action does so.
- Supports **advance planning**, including assigning a **next** load while the driver is still on a **current** trip.

### 4. Assign & Send

- **Fast dispatcher action** initiated from load verification/planning context.
- Dispatcher can, in one product flow: save corrections, make load ready if required, create/update **trip** and **membership** as needed, assign equipment, and **send** the driver the job information.
- Driver can receive trip/load information **before** getting home or **before** finishing the current trip.
- **Backend** should treat this as **multiple safe facts** even if the **UI** presents one button.

#### Backend meaning of Assign & Send (composite)

- Save load corrections.
- Mark load ready if required.
- Create trip if needed.
- Add load to trip if needed.
- Assign driver/truck/trailer (trip authority per **3L-B**).
- Set **`Trip.status = assigned`** if the trip was **`planned`** and policy allows (aligned with first execution transition slice — see **3L-C**).
- Create a **driver dispatch package** snapshot.
- **Version** that package.
- **Send** package to driver.
- Record **`sent_by`**, **`sent_at`**, recipient/driver, **package version**, included documents/instructions.
- Write **audit / history** events.

---

## Hard boundaries

**Assign** / **Assign & Send** must **NOT**:

- mark pickup complete
- mark driver **en route** unless a **separate execution** action exists
- **start custody**
- change load to **delivered**
- trigger **payroll**
- create **false** movement/mileage events
- **create/update `dispatch_trips` in V1** unless explicitly designed later (see **3L-C** guardrails)
- **rewrite** the dispatch board
- **silently sync** trip assignment back into **load** assignment fields (see **3L-B**)
- **assume** the driver is currently available

---

## Overlap / queuing rule

A driver may **already be on an active trip** and still receive a **future** assigned trip (e.g. en route to Boston or just unloaded; dispatcher books the next load).

- **Allow** multiple **future / planned / assigned** trips for the **same** driver/truck/trailer when they are **queued**.
- **Block** or require **supervisor override** for **overlapping active execution** (define “active execution” in implementation).
- **Assignment** = **commitment**, not **physical movement**.

---

## Dispatch package concept

A **separate driver-facing dispatch package** sits **between assignment** and **execution/custody**.

### Dispatch package should track (conceptual)

- **Package status:** e.g. draft/not sent, sent_to_driver, viewed_by_driver, accepted/rejected (if supported later)
- **Package version**
- **`sent_at`**
- **`sent_by_user_id`**
- **Driver recipient**
- **Included** load/trip snapshot
- **Included** stops, references, documents, notes, instructions
- Whether package becomes **outdated** after load/trip edits
- **Resend** / **update package** behavior

### Reason

**`Trip.status = assigned` alone** does **not** prove the driver **received** the information. Dispatch needs proof that the load/trip **package was sent** and eventually **viewed** / accepted.

---

## Terminology warning

Avoid using **“Dispatched”** too early as a heavy backend label — companies use it differently:

- sometimes = driver **was sent** the information
- sometimes = driver **started executing**
- sometimes = truck **en route**

**Cross-check — Decision 7 (locked):** The **`Trip.status`** ladder does **not** include **`dispatched`** as the step after **`assigned`**. After commitment, the next trip header state for **active execution** is **`in_progress`**, entered only on the **first real execution signal** — see **`DECISION_7_ACTIVE_EXECUTION_SIGNAL_MODEL.md`**. **`Load.status` / board “dispatched”** remains **legacy** in that trip-header sense.

### Preferred terms (until execution layer fully defined)

| Concept | Meaning |
|---------|--------|
| **Assign** | **Commitment** (equipment + trip; no implied send) |
| **Assign & Send** | Commitment + **driver package sent** |
| **Start trip / Mark en route** | **Future** execution action (not this decision) |
| **Pickup / custody / terminal / delivery** | **Future** custody layer |

---

## Implementation note

This decision **does not** prescribe exact API routes. Map composite actions to **3L-B** (assignment authority on trip), **3L-C** slices, **Decision 14** (dedicated assignment slice), and **master index** guardrails when coding.

---

*End of Decision 6 — dispatcher load workspace action model.*
