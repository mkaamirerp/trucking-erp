# TruckERP — Decision 10 / Future assignment and active execution conflict guard

**Status:** **LOCKED** (design direction for **future** implementation — **do not** implement schema, API, or UI yet).  
**Related:** `DECISION_6_DISPATCHER_LOAD_WORKSPACE_ACTION_MODEL.md`, `DECISION_7_ACTIVE_EXECUTION_SIGNAL_MODEL.md`, `DECISION_8_DRIVER_DISPATCH_PACKAGE_SCHEMA.md` (draft), `DECISION_9_LOAD_READINESS_PLANNING_QUEUE.md`, `TRIP_EXECUTION_CUSTODY_MASTER_INDEX.md`, `PHASE3L_B_TRIP_ASSIGNMENT_CONTRACT.md`, `PHASE3L_C_TRIP_EXECUTION_SCHEMA_API_PLAN.md`.

**Anchors:**

- **Decision 6:** **Assign** / **Assign & Send** are planning/commitment actions.
- **Decision 7:** **Active execution** starts from the **first real execution signal**, not assignment; **`Trip.status = in_progress`** follows that signal.
- **Decision 9:** Verified saved loads enter **Ready / Unassigned** planning-queue **meaning**; preparation ≠ execution.
- **Future assigned trips** are **allowed**, but **impossible schedules** (relative to **active execution**) must be **guarded**.

---

## Locked decision

A **driver** / **truck** / **trailer** may have a **future assigned** trip while **currently** on another **`in_progress`** (actively executing) trip.

**However:** the **future** assigned trip **must not** be scheduled to **start** (first pickup / planned operational start) **before** the **current** active trip is **expected** to **finish** (final delivery / expected completion).

**Plain rule:** **Assignment** is allowed for **future planning**, **not** for **impossible** schedules.

---

## Examples

### Allowed

**Current Trip A**

- **`Trip.status`:** `in_progress`
- **Final delivery / expected completion:** **2026-01-02**

**Next Trip B**

- **First pickup / planned start:** **2026-01-03**

**Result:** **Allowed.** Driver may be **assigned** Trip B while still finishing Trip A.

### Conflict

**Current Trip A**

- **`Trip.status`:** `in_progress`
- **Final delivery / expected completion:** **2026-01-02**

**Next Trip B**

- **First pickup / planned start:** **2026-01-01**

**Result:** **Conflict.** Driver cannot reasonably be expected to **start** Trip B **before** finishing Trip A.

---

## Recommended comparison rule (design)

Compare:

- **Current active trip:** `final_delivery_or_expected_completion_at` (or equivalent operational end expectation).
- **Next trip:** `first_pickup_or_planned_start_at`.

**If**

```text
next_trip.first_pickup_or_planned_start_at < current_trip.final_delivery_or_expected_completion_at
```

**then**

```text
scheduling_conflict = true
```

**Default behavior (when implemented):**

- **Block** the assignment, **or** at minimum show a **hard conflict warning** (phasing TBD).
- **Do not** **silently** allow impossible schedules.

**Conflict message example (illustrative):**

> Driver is already committed to Trip IKL10001 until Jan 2, 2026. This new trip starts Jan 1, 2026 and conflicts with the active trip.

---

## Resource dimensions

This rule applies **separately** per committed **resource**:

- **Same driver**
- **Same truck**
- **Same trailer**

A **future** trip may be **assigned** only if the **relevant** resource is **not** booked into an **impossible** overlap (per the comparison above).

---

## Flexibility — messy dispatch reality

Real operations need slack; the system may **not** have perfect data:

- Delivery **appointment** may **change**
- Driver may **finish early**
- Load may be **repowered**
- Driver may **drop trailer** at terminal
- **Trailer** may be **swapped**
- **Team** operation may change **who** executes
- Dispatcher may know facts **not yet** in the system

**Future supervisor override** may allow a flagged conflict **only** with:

- **Required reason**
- **Actor** (user)
- **Timestamp**
- **Affected resource:** driver / truck / trailer
- **Linked trip IDs**
- **Audit event**
- **Optional** notes

**Example override reasons (non-exhaustive):**

- Current trip will be **repowered**
- Driver **dropping trailer** at terminal
- **Delivery appointment** changed
- **Trailer swap** planned
- **Team** operation
- **Manual dispatcher approval**

---

## Hard boundaries — Decision 10 does **NOT** mean

**Assignment** (including satisfying or overriding this guard) **does not**:

- Start **active execution** (**Decision 7**)
- Start **custody**
- Mark **pickup** / **delivery** milestones
- **Trigger payroll**
- **Rewrite** dispatch **board**
- Set **`Load.status = dispatched`** (legacy **board** vocabulary)

**Cross-check:**

- **Decision 7** remains the source for **`Trip.status = in_progress`** and execution start.
- **Decision 10** only guards whether a **future assignment’s schedule** is **possible** relative to **current active execution**.
- **Decision 9** remains the source for **Save Ready** / **planning queue** behavior — **not** scheduling conflict between **two committed** trips on the **same resource**.
- **Decision 8** **package send** (**Assign & Send**) **does not** bypass this guard when both apply — **commitment** and **dates** must remain **consistent** with product rules once implemented.

---

## Implementation note

- **Do not implement** comparison logic, override UX, or persistence **yet**.
- This document is a **locked product/design** decision for a **later** slice.

---

*End of Decision 10 — future assignment and active execution conflict guard.*
