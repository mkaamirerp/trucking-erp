# TruckERP — Decision 10 / Future assignment and active execution conflict guard

**Status:** **LOCKED** (design + trip schedule field names). **Code deferred** — see **Implementation note — deferred (why not today)** (updated **2026-08-12**).  
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

## Recommended comparison rule (design) — **locked field names (2026-08-12)**

**Authoritative trip-level bounds** (nullable timestamptz on **`trips`** when implemented):

| Field | Meaning |
|-------|---------|
| **`planned_start_at`** | Next / candidate trip’s planned operational start (first pickup / planned start). |
| **`expected_completion_at`** | Active (`in_progress`) trip’s expected finish (final delivery / expected completion). |

**Do not** infer the conflict guard from **load-stop** appointments (`LoadStop.appointment_date` / `scheduled_at`) or other stop-level dates. Stops may later **prefill** these trip fields in the UI; the **guard** reads **trip** columns only.

**If both bounds exist:**

```text
next.planned_start_at < active.expected_completion_at
  → scheduling_conflict = true
```

where **`active`** is another trip on the **same** driver / truck / trailer with **`Trip.status = in_progress`** (exclude the trip being updated).

**Missing scheduling bounds (locked policy for first implementation):**

- If **`planned_start_at`** and/or the active trip’s **`expected_completion_at`** is missing → **do not silently block** assignment.
- Surface scheduling data as **incomplete** (allow assignment; optional soft warning later) until a separate product policy locks warn-vs-require.

**Default behavior when both bounds exist and conflict:**

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
- **Architecture (not Decision 10’s home):** Decision 10 guards **schedule feasibility** only. It does **not** transfer custody or start execution. **Future reservation ≠ current custody ≠ execution eligibility** — see [`trip-foundation.md`](./trip-foundation.md) §1A Three Parallel Truths.

---

## Implementation note — deferred (why not today)

**Status (2026-08-12):** Design + field names are **locked**; **code is deferred**.

### Why we are **not** implementing today

1. **Priority / sequencing:** Trip Container shell, driver-card cleanup, legacy dispatch deprecation, and Start Execution UI shipped first (COMMITs 1–3). Decision 10 is the **next** scheduling slice, not a same-day cut.
2. **Schema prerequisite not shipped yet:** `trips.planned_start_at` and `trips.expected_completion_at` do not exist in the tenant DB. Implementing the guard without those columns would force a forbidden shortcut (inferring from load stops).
3. **Still deferred from original lock:** Supervisor **override** UX, exact **timezone** handling, and hard-block vs hard-warning phasing remain later product choices once fields + guard exist.
4. **Avoid half-shipped safety:** A guard that blocks on missing dates or invents bounds from stops would **mis-fire** on real messy dispatch data and fight the locked “missing bounds → do not silently block” rule.

### When we do it later — suggested order

| Step | Work |
|------|------|
| **4a** | Tenant Alembic: add nullable `planned_start_at`, `expected_completion_at` on `trips`; SQLAlchemy model + trip read/write schemas as needed. |
| **4b** | In `update_trip_assignment` (`PUT /api/v1/trips/{id}/assignment`): per-resource check vs other `in_progress` trips using the comparison above; **409** with clear codes when both bounds exist and conflict; **allow** when bounds incomplete. |
| **Later** | Supervisor override + audit; UI to edit/display trip schedule bounds; soft incomplete-data warning if desired. |

**Hook point (unchanged):** `app/services/trips.py` :: `update_trip_assignment` (after `_validate_assignment_targets`, before mutating assignment columns).

---

*End of Decision 10 — future assignment and active execution conflict guard.*
