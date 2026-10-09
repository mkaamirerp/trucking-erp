# TruckERP Load / Trip Master Architecture

**Status:** CANONICAL ARCHITECTURE LOCK

## Authority rule

This file is the **canonical current architecture** for Load / Trip / TripLoad / Dispatch / Custody boundaries.

Before changing related code, schema, APIs, UI, migrations, or business rules, agents **must read this file first**.

If another documentation file conflicts with this master:

**STOP.**

Do **not** choose whichever document appears newer or says “LOCKED.”

**Report the conflict.**

The master remains authoritative until an **owner-approved decision** explicitly updates this master.

A new decision document does **not** silently supersede this master.

After an approved architecture change:

1. update this master,
2. update the relevant detailed decision,
3. then implement.

**Required-read scope (non-exhaustive):** Load, Trip, TripLoad, Dispatch, Trip Container, Load Workspace, Trip Workspace, driver/truck/trailer assignment, `Load.status`, `Trip.status`, trip number, `dispatch_trips`, `active_trip_id`, custody, terminal/yard, handoff, recovery/repower, operational board / planning queue, payroll/read-model dependencies involving Load/Trip.

**Synthesis note:** This master does **not** invent new business rules. It consolidates already locked / current decisions and shipped architecture boundaries. Detail docs remain useful for nuance; they lose on shared semantics when they conflict here.

**Related UI lock (same operational world):** `docs/000_TRIP_CONTAINER_IS_DISPATCH_CONTROL_CENTER.md` — Trip = Trip Container = Dispatch Control Center (labels for one Trip-backed surface, not a second product).

---

## 1. Four truths

| Truth | Role |
|-------|------|
| **LOAD** | Commercial / broker / customer / revenue truth |
| **TRIP** | Operational / movement / payable execution truth |
| **TRIPLOAD** | Explicit membership between Load and Trip |
| **CUSTODY / AUDIT** | Continuity of physical responsibility, location, handoff, and transfer |

These are **separate but reconcilable** truths.

**Never** duplicate a commercial Load merely because the freight moves across multiple Trips.

**Future reservation ≠ current custody ≠ execution eligibility.**

---

## 2. Load ownership

### Load owns

- broker / customer relationship
- broker load / reference identifiers
- rate / revenue
- rate confirmation and commercial documents
- commodity / weight
- contractual pickup / delivery obligations
- commercial notes
- commercial cancellation
- other broker / customer facts

### Target new-write `Load.status`

| Value | Meaning |
|-------|---------|
| **`draft`** | Incomplete / unverified commercial Load |
| **`ready`** | Commercially verified enough for **dispatch planning** |
| **`cancelled`** | Commercial Load itself is cancelled / no longer worked |

**`Load.status` is NOT the execution ladder.**

### Legacy `Load.status` values (historical / read compatibility only)

May exist on historical rows and compatibility read paths:

- `unassigned`
- `assigned`
- `dispatched`
- `arrived_pickup`
- `in_transit`
- `arrived_delivery`
- `delivered`
- `issue_hold`

They **must not** be used for **new** operational execution truth.

**`Load.status = dispatched`** is **not** a new execution trigger.

Commercial Load cancel (`Load.status = cancelled`) is **not** the same as `Trip.status = cancelled`. Trip cancel while Load remains valid must **not** auto-force Load cancelled without explicit product rules.

Primary detail: `DECISION_11_LOAD_STATUS_TARGET_BOARD_MIGRATION.md`, `DECISION_9_LOAD_READINESS_PLANNING_QUEUE.md`.

---

## 3. Trip ownership

### Trip owns

- trip number
- driver assignment
- truck assignment
- trailer assignment
- movement / execution lifecycle
- operational responsibility
- execution timing
- operational completion / cancellation

### Canonical `Trip.status`

```
planned → assigned → in_progress → completed
cancelled  (terminal negative state)
```

| Value | Meaning |
|-------|---------|
| **`planned`** | Trip exists; resources not yet committed |
| **`assigned`** | Driver / truck / trailer committed; not necessarily moving |
| **`in_progress`** | First real execution signal occurred |
| **`completed`** | This Trip’s operational responsibility is finished |
| **`cancelled`** | Trip cancelled; record and trip number remain for audit |

**Assignment alone does NOT mean `in_progress`.**

**`Trip.status = completed` does NOT mean Load delivered.**

### Do NOT use as canonical Trip header lifecycle

- `dispatched`
- `in_transit`
- `at_pickup`
- `at_delivery`
- `delivered`
- `problem_hold`
- `open`
- `active`

Granular road / stop / facility / problem conditions belong in **stop-level status**, **timeline**, or **custody** — **not** as Trip header replacements for the ladder above.

Legacy rows may still contain invalid header values (e.g. historical `active` / `open` contamination from mirror writers). Those are **data/remediation** concerns, not the target product vocabulary.

Primary detail: `DECISION_7_ACTIVE_EXECUTION_SIGNAL_MODEL.md`, `TRIP_EXECUTION_CUSTODY_MASTER_INDEX.md` §4.

---

## 4. TripLoad membership

TripLoad (`trip_loads`) is the **membership bridge**.

- One Trip may carry **multiple** Loads.
- One Load may participate in **multiple** Trips over its lifecycle.

### Canonical membership meanings (`status_within_trip`)

| Value | Meaning |
|-------|---------|
| **`planned`** | Future reservation / planned membership |
| **`active`** | Current movement responsibility |
| **`completed`** | That Trip’s responsibility for that Load completed normally |
| **`removed`** | Membership removed / replanned / cancelled from that Trip |

### Open vs active

**Open membership:**

```text
status_within_trip IN ('planned', 'active')
AND completed_at IS NULL
AND removed_at IS NULL
```

**Active membership:**

```text
status_within_trip = 'active'
AND completed_at IS NULL
AND removed_at IS NULL
```

**Open is NOT the same as active.**

### V1 cardinality per Load

- maximum **one** open **active** membership
- maximum **one** open **planned** membership
- unlimited completed / removed history

**Valid:** active Trip A + planned Trip B.

**Invalid:** two open active memberships; two open planned memberships.

Completing A does **NOT** automatically activate B.

### Completion vs removal timestamps

- **completed:** set `completed_at`; do **not** misuse `removed_at`
- **removed:** set `removed_at`; do **not** misuse `completed_at`

Do not confuse `trip_loads.status_within_trip = removed` with `Load.status = cancelled`.

Primary detail: `trip-foundation.md` §1A (membership semantics), `PHASE3L_B_TRIP_ASSIGNMENT_CONTRACT.md`.

---

## 5. `loads.active_trip_id`

**Lock:**

`loads.active_trip_id` is a **backend compatibility / read convenience mirror** of the Load’s **CURRENT ACTIVE Trip only**.

It is **NOT**:

- TripLoad source of truth
- a planned Trip pointer
- an arbitrary open-membership pointer
- something the frontend may write or “repair”

**TripLoad membership is authoritative.**

A Load may have:

- active Trip A, **and**
- planned Trip B,

while `active_trip_id` points **only** to A.

Older docs that treated `active_trip_id` as “any open membership” or as live operational authority **conflict with this master** — see §18.

---

## 6. `dispatch_trips`

**Current target role:**

`dispatch_trips` is **legacy / compatibility / migration infrastructure**.

It is **not** the authority for **new** Trip execution.

**New Load writes must not mint execution by:**

```text
Load.status = dispatched  →  dispatch_trips
```

Canonical new operational work uses:

- Trip
- TripLoad
- Trip assignment
- Trip execution APIs
- Custody / events

Legacy rows, read paths, and backfill evidence may remain until migration is proven safe.

**Do not** delete `dispatch_trips` or compatibility mirrors merely because they are no longer new-write authority.

Payroll / reporting / read-model dependencies must be audited first (see §16).

Primary detail: `DISPATCH_TRIP_NUMBER_RULE.md` (evolution sections), `LOAD_INTEGRITY_AUDIT_AND_REMEDIATION_PLAN.md` (Issue 0A+).

---

## 7. Trip number

**Lock:**

- Trip number belongs to the **Trip container**.
- Trip number is minted when the **planned Trip is created**, according to the current allocator contract.
- It is **never reused**.
- Cancelling a Trip does **not** release / reuse its number.
- One Trip has **one** operational trip number regardless of number of member Loads / stops.

Stop-level fields (pickup number, PO, appointment, facility) are **not** trip numbers.

Legacy `dispatch_trips` allocation on `Load.status = dispatched` is **historical compatibility only**.

Primary detail: `DISPATCH_TRIP_NUMBER_RULE.md`.

---

## 8. Workspace / UI authority

### Load Workspace (`LoadWorkspacePage`)

Owns:

- commercial Load creation
- commercial editing
- PDF / Rate Confirmation verification
- Save Draft
- Mark / Save Ready
- commercial Load facts

**Must not own new operational:**

- driver assignment
- truck assignment
- trailer assignment
- Trip execution progression

### Trip Workspace / Trip Container

Owns:

- operational Trip authority
- Trip membership
- driver / truck / trailer assignment
- start execution
- completion / cancellation
- operational context

**Locked product identity:** Trip = Trip Container = Dispatch Control Center — one Trip-backed operational world. Operator language may say “Dispatch”; backend may say “Trip.” That must **not** imply a second lifecycle from `Load.status` lanes.

### Legacy `/dispatch` board

`DeprecatedDispatchPage` / `/dispatch` is **compatibility / visual salvage** during retirement — **not** current operational authority.

Do **not** build a second Load page pretending to be Trip execution.

Do **not** revive `Load.status = dispatched` as a new writer.

Do **not** write `dispatch_trips` from **new Trip** flows.

Primary detail: `000_TRIP_CONTAINER_IS_DISPATCH_CONTROL_CENTER.md`, `DECISION_11`, Issue 0A/0C in `LOAD_INTEGRITY_AUDIT_AND_REMEDIATION_PLAN.md`.

---

## 9. Planning queue vs operational board

### Load planning queue

Based on **commercial Load readiness**.

- Ready Loads not yet committed to current execution
- Used for: planning, combining, splitting, holding, adding to new/existing Trip

**Save Ready** (without a Trip action) does **not** by itself: create Trip, assign equipment, send package, start `in_progress`, set `Load.status = dispatched`, start custody, or start payroll.

### Trip operational board / container

Based on **`Trip.status`**:

`planned` | `assigned` | `in_progress` | `completed` | `cancelled`

Used for: operational assignment, movement, execution, completion, exceptions.

### Legacy board

Legacy `/dispatch` Load.status board is **compatibility / read-only during retirement** and must **not** be treated as current operational authority.

Primary detail: `DECISION_9_LOAD_READINESS_PLANNING_QUEUE.md`, `000_TRIP_CONTAINER_IS_DISPATCH_CONTROL_CENTER.md`.

---

## 10. Driver / truck / trailer

**Current / new operational assignment authority lives on Trip.**

Legacy `Load.driver_id` / `Load.truck_id` / `Load.trailer_id` may remain **readable** as historical compatibility snapshots.

- Do **not** create new Load-level operational assignment.
- Do **not** remove historical snapshots until readers / payroll / history are migrated.
- Do **not** silently sync Trip assignment back onto Load assignment fields as the default.

Primary detail: `PHASE3L_B_TRIP_ASSIGNMENT_CONTRACT.md`, `DECISION_14_TRIP_ASSIGNMENT_FIRST_SLICE.md`.

---

## 11. Completion / delivery

**Lock:**

- **Trip completion ≠ Load delivery.**
- A Trip may complete while the Load remains commercially active if responsibility is transferred through an **explicit** custody / handoff path.
- A Load may continue through another Trip.
- Load final delivery and receiver proof are **separate** from Trip header completion.
- Do **not** introduce `Trip.status = delivered`.

Custody event type `delivered` (receiver / proof) may exist and is **not** the Trip header state.

Primary detail: `DECISION_7`, `DECISION_12`, `trip-foundation.md` (completion vs delivery distinction).

---

## 12. Custody / terminal / handoff

**Lock:**

- Custody is **separate** from commercial Load state and Trip header lifecycle.
- Terminal / yard must use **structured tenant-owned identity** (not free-text as the identity of “which terminal”).
- Handoff / transfer must be **auditable**.
- Trailer-to-trailer transfer must **not** be implemented as a silent `trailer_id` overwrite.
- Custody history must preserve **continuity** (append-only with void/correct patterns as locked).
- Trip must **not** close with undelivered freight unless responsibility / custody is **explicitly resolved** per locked custody rules.
- Do **not** copy every custody / stop condition into `Trip.status`.

Primary detail: `DECISION_12_TERMINAL_YARD_CUSTODY_FOUNDATION.md`, custody sections of `TRIP_EXECUTION_CUSTODY_MASTER_INDEX.md`.

---

## 13. Exception / recovery / repower

**Lock:**

- Trip exception ≠ Load cancellation.
- Preserve original Trip + trip number.
- Recovery / repower requiring another operational movement creates / uses a **separate** Trip with its **own** number and custody chain.
- Do **not** silently swap assignment on historical execution.
- Commercial Load may remain valid through recovery.
- `Load.status = cancelled` only for true commercial cancel.

Payroll guard (summary): incomplete trip responsibility → review-required posture — no silent auto full pay / auto zero as the default; recovery trip payroll separate from original. Detail remains in Decision 13.

Primary detail: `DECISION_13_TRIP_EXCEPTION_RECOVERY_REPOWER.md`.

---

## 13A. Multi-Trip continuation / relay — LOCKED

A single commercial Load may be executed through multiple Trips.

The Load is **NOT** duplicated merely because:

- a long-haul driver hands the freight/trailer to a city driver,
- freight is staged at a company yard/terminal,
- a driver/truck breaks down,
- a repower/recovery movement is required,
- responsibility transfers to another Trip.

The commercial Load keeps its original broker/customer obligation, commercial pickup/delivery, references, documents, and revenue.

Each Trip represents only the operational responsibility assigned to that Trip/driver/truck.

### Planned relay example

**Commercial Load:** Boston → Toronto

| | |
|--|--|
| **Trip 1** | Boston → Company Yard — Long-haul Driver A / Truck A |
| **Trip 1 end** | Responsibility ends at the yard through an **explicit planned** handoff/custody transition |
| **Trip 2** | Company Yard → Toronto receiver — Day Driver B / Truck B |
| | Same Load. New Trip. New trip number. Separate TripLoad history. Separate operational/pay responsibility. |

The Load’s contractual origin/destination remains **Boston → Toronto**.

**Do NOT** rewrite the Load to Boston → Yard.

### Breakdown / repower example

**Commercial Load:** Toronto → Boston

**Trip 1 originally assigned responsibility:** Toronto → Boston — Driver A / Truck A

**Actual event:** Truck breaks down in Albany.

**Preserve Trip 1:**

- same trip number
- same Driver A / Truck A historical assignment
- original assigned Toronto → Boston responsibility remains historically visible
- actual Trip 1 responsibility ended at Albany because of the exception

**Do NOT** rewrite Trip 1 as though Driver B was always assigned.  
**Do NOT** silently change the original assigned destination from Boston to Albany.

Record **explicit custody/handoff** at Albany.

**Trip 2:** Albany → Boston — Driver B / Truck B — new Trip number — same commercial Load — new TripLoad membership.

Trip 2 becomes the current **ACTIVE** Trip when its membership becomes active.

`loads.active_trip_id` points only to the current ACTIVE Trip. It never represents both Trip 1 and Trip 2.

### Payroll / mileage responsibility

Load mileage/revenue and driver Trip mileage/pay responsibility are **separate** concepts.

**Example:** Toronto → Boston planned distance ≈ 500 miles.

If Driver A’s responsibility ends in Albany after ≈ 320 miles, do **NOT** automatically pay:

- the full 500 miles, or
- zero miles.

Trip 1 is an incomplete responsibility case and follows Decision 13 **`review_required`** / pay-review policy.

Trip 2 payroll is calculated/reviewed separately for Albany → Boston.

The settlement/payroll system must be able to trace which Trip performed which operational segment.

### Core rule

Same Load, multiple Trips when operational responsibility changes.

- Preserve the original Trip and its historical assignment.
- Record custody/handoff explicitly.
- Create the continuation/recovery Trip with a new Trip number.
- Keep operational and payroll responsibility separate by Trip.

Primary detail: `DECISION_12_TERMINAL_YARD_CUSTODY_FOUNDATION.md`, `DECISION_13_TRIP_EXCEPTION_RECOVERY_REPOWER.md`.

---

## 14. Load parser / intake boundary

Parser / intake **hydrates / proposes** commercial Load data.

- AI / parser output is **not** operational execution truth.
- Human review / acceptance boundary applies.
- Parser / intake must **not** automatically:
  - create Trip execution
  - assign driver / truck / trailer
  - start custody
  - start payroll
  - advance `Trip.status`
  - write `dispatch_trips`
  - set `Load.status = dispatched`

Load review remains **commercial intake**.

Primary detail: `LOAD_PAGE_INTAKE_IMPLEMENTATION_TRACKER.md` safety boundaries, parser/product rules.

---

## 15. Payroll / finance compatibility

**Going forward:** Trip is operational / payable tracing truth.

**Today:** Legacy `Load.trip_number` / `active_dispatch_trip_id` / `dispatch_trips` may still be consumed by existing payroll / reporting code.

**Do NOT remove those mirrors until:**

1. exact finance / payroll readers are identified,
2. canonical Trip replacements are proven,
3. historical tracing is preserved,
4. regression tests pass.

**No silent money / history changes.**

Primary detail: `PAYROLL_TRIP_TRACING.md` (where present), Decision 13 payroll guards, Issue 0D posture in `LOAD_INTEGRITY_AUDIT_AND_REMEDIATION_PLAN.md`.

---

## 16. Document precedence table

Master **always wins** on shared architecture semantics. Detailed decisions may provide extra detail only where they do **not** contradict this master.

| Document | Classification |
|----------|----------------|
| `TRIP_EXECUTION_CUSTODY_MASTER_INDEX.md` | **DETAIL CURRENT** (index + consolidated principles; defer to this master on conflicts) |
| `trip-foundation.md` | **SUPERSEDED IN PART** (membership / four-truths / active_trip_id detail still useful; granular Trip.status ladder language superseded) |
| `TRIP_CONTAINER_OPERATIONAL_RULES.md` | **DETAIL CURRENT** (pointer into `trip-foundation.md`; master wins on conflicts) |
| `000_TRIP_CONTAINER_IS_DISPATCH_CONTROL_CENTER.md` | **DETAIL CURRENT** (UI / product identity lock) |
| `TRIP_CONTAINER_VS_LOAD_FOUNDATION.md` | **DETAIL CURRENT** (Trip vs Load foundation; master wins on status ladders) |
| `LOAD_LIFECYCLE_AND_OPERATIONAL_EVENTS_LOCK.md` | **SUPERSEDED IN PART** (continuity / split / yard event ideas may remain useful; Load ops ladder superseded by Decision 11 / this master) |
| `PHASE1_TRIP_FOUNDATION_PLAN.md` | **SHIPPED HISTORICAL RECORD** (Phase 1 scope; live-authority warning is historical) |
| `PHASE3C_PLANNED_TRIP_IMPLEMENTATION_PROPOSAL.md` | **HISTORICAL / TRANSITIONAL** (proposal toward planned trips) |
| `PHASE3D_TRIP_ACTION_READ_FIRST.md` | **HISTORICAL / TRANSITIONAL** |
| `PHASE3L_A_TRIP_EXECUTION_CUSTODY_DECISION_RECORD.md` | **DETAIL CURRENT** (execution/custody decision record; master wins on shared semantics) |
| `PHASE3L_B_TRIP_ASSIGNMENT_CONTRACT.md` | **DETAIL CURRENT** |
| `PHASE3L_C_TRIP_EXECUTION_SCHEMA_API_PLAN.md` | **DETAIL CURRENT** / transitional implementation plan |
| `PHASE3L_D_OWNER_DECISION_CHECKLIST.md` | **DETAIL CURRENT** (owner checklist; report-oriented) |
| `PLANNED_TRIP_LIFECYCLE_MODULE_CLOSE.md` | **SHIPPED HISTORICAL RECORD** |
| `DECISION_6_DISPATCHER_LOAD_WORKSPACE_ACTION_MODEL.md` | **SUPERSEDED IN PART** (Save Draft / Save Ready meanings remain; Assign / Assign & Send **action-home on Load Workspace** superseded by Trip-first ops authority — see §18D) |
| `DECISION_7_ACTIVE_EXECUTION_SIGNAL_MODEL.md` | **DETAIL CURRENT** |
| `DECISION_8_DRIVER_DISPATCH_PACKAGE_SCHEMA.md` | **DRAFT** |
| `DECISION_9_LOAD_READINESS_PLANNING_QUEUE.md` | **DETAIL CURRENT** |
| `DECISION_10_FUTURE_ASSIGNMENT_CONFLICT_GUARD.md` | **DETAIL CURRENT** |
| `DECISION_11_LOAD_STATUS_TARGET_BOARD_MIGRATION.md` | **DETAIL CURRENT** |
| `DECISION_12_TERMINAL_YARD_CUSTODY_FOUNDATION.md` | **DETAIL CURRENT** |
| `DECISION_13_TRIP_EXCEPTION_RECOVERY_REPOWER.md` | **DETAIL CURRENT** |
| `DECISION_14_TRIP_ASSIGNMENT_FIRST_SLICE.md` | **DETAIL CURRENT** / shipped-slice record |
| `DISPATCH_TRIP_NUMBER_RULE.md` | **DETAIL CURRENT** (read evolution sections; legacy mint timing is historical) |
| `DISPATCH_TRIP_NUMBER_IMPLEMENTATION_PLAN.md` | **HISTORICAL / TRANSITIONAL** |
| `TRIP_FIRST_DDL_CONTRACT.md` | **DETAIL CURRENT** / target DDL contract (master wins on status vocabulary) |
| `TRIP_CONTAINER_ARCHITECTURE_GAP_REPORT.md` | **SHIPPED HISTORICAL RECORD** (point-in-time gap; not current authority) |
| `TRIP_LIFECYCLE_TERMINAL_ROUTING_YARD_HANDOFF_DISPATCH_LOAD_TRANSFER_FOUNDATION.md` | **DETAIL CURRENT** (custody/terminal background; master + Decision 12 win on header status) |
| `LOAD_INTEGRITY_AUDIT_AND_REMEDIATION_PLAN.md` | **REMEDIATION TRACKER** |
| `LOAD_PAGE_INTAKE_IMPLEMENTATION_TRACKER.md` | **DETAIL CURRENT** for intake/parser safety; Track A status cleanup parked as noted therein |
| `PAYROLL_TRIP_TRACING.md` | **DETAIL CURRENT** for finance tracing caution (do not remove mirrors without audit) |

---

## 17. Known conflicts (reconciled by this master)

### A. `LOAD_LIFECYCLE_AND_OPERATIONAL_EVENTS_LOCK.md`

**Old:** Load Draft → Ready → Assigned → Dispatched → In Transit → Delivered → Closed.

**Current (this master):** `Load.status` = `draft` / `ready` / `cancelled` commercial / readiness only. Execution belongs to Trip.

### B. `trip-foundation.md` older granular `Trip.status` language

**Old:** `dispatched` / `in_transit` / `at_pickup` / `at_delivery` / `delivered` / `problem_hold` as Trip header ladder.

**Current (this master):** `planned` / `assigned` / `in_progress` / `completed` / `cancelled`. Granular road / stop / custody conditions do **not** belong in Trip header status.

### C. `PHASE1_TRIP_FOUNDATION_PLAN.md`

**Old / current-at-that-phase:** `dispatch_trips` live authority; `trips` mirror only.

**Current (this master):** Canonical Trip paths own new work; `dispatch_trips` is legacy compatibility.

### D. Decision 6 / Decision 8 old action-home wording

Where they place **Assign / Assign & Send** on **Load Workspace**, treat that **UI location** as **superseded** by current Trip-first operational authority unless an explicitly retained action is defined later by owner-approved update to this master.

Do **NOT** silently bring Load operational assignment back.

Save Draft / Save Ready commercial meanings remain (Decision 9).

### E. `active_trip_id` as “any open” pointer

**Old (some shipped-close / early notes):** mirror any open TripLoad.

**Current (this master):** mirror of **ACTIVE** Trip only; TripLoad is authority; UI must not repair.

---

## 18. Items that still need owner decision (not invented here)

These are **not** silently resolved by this consolidation:

1. **Assign & Send product home** — whether a future composite “send package” control is Trip Workspace–only, or a deliberate Load Workspace shortcut that still mutates Trip (Decision 8 remains **DRAFT**; Decision 6 action-home is superseded for assignment).
2. **Physical retirement of `/dispatch`** — when Trip Container parity is “good enough” to remove/rename the legacy route (tracked in remediation / Issue 0C; not a new business rule).
3. **Payroll / reporting cutover** — exact reader list and when `Load.trip_number` / `active_dispatch_trip_id` / `dispatch_trips` mirrors may be dropped (Issue 0D posture).
4. **Historical Trip.status contamination cleanup** (`active` / `open` on `trips`) — remediation Issue 0B; migration not approved by this doc alone.
5. **Custody first-write allowlist expansion timing** — Decision 12 foundation vs phased allowlist (3L-D).
6. **Whether `LOAD_LIFECYCLE…` continuity sections** (split / partial / reject / yard) are restated into a new detail doc or left historical with banners only.

Until an owner updates this master, agents must **STOP** rather than invent answers.

---

## 19. Read-before-write checklist (agents)

Before touching Load / Trip / TripLoad / dispatch / custody code, schema, API, UI, migration, or related docs:

1. Read **this file**.
2. Read the **DETAIL CURRENT** decision(s) for the narrow slice (e.g. Decision 7 for execution signal).
3. If another document conflicts with this master → **STOP and report**. Do not pick the older/newer file yourself.
4. Do not implement an architecture change until this master has been **owner-approved and updated**.

---

## 20. Source docs used for this synthesis

Primary locked / current sources:

- `000_TRIP_CONTAINER_IS_DISPATCH_CONTROL_CENTER.md`
- `TRIP_EXECUTION_CUSTODY_MASTER_INDEX.md` §4
- `DECISION_7_ACTIVE_EXECUTION_SIGNAL_MODEL.md`
- `DECISION_9_LOAD_READINESS_PLANNING_QUEUE.md`
- `DECISION_10_FUTURE_ASSIGNMENT_CONFLICT_GUARD.md`
- `DECISION_11_LOAD_STATUS_TARGET_BOARD_MIGRATION.md`
- `DECISION_12_TERMINAL_YARD_CUSTODY_FOUNDATION.md`
- `DECISION_13_TRIP_EXCEPTION_RECOVERY_REPOWER.md`
- `DECISION_14_TRIP_ASSIGNMENT_FIRST_SLICE.md`
- `PHASE3L_B_TRIP_ASSIGNMENT_CONTRACT.md`
- `DISPATCH_TRIP_NUMBER_RULE.md` (evolution / Trip mint)
- `trip-foundation.md` §1A (membership, active_trip_id, four truths — not granular Trip.status ladder)
- `TRIP_CONTAINER_VS_LOAD_FOUNDATION.md`
- `LOAD_INTEGRITY_AUDIT_AND_REMEDIATION_PLAN.md` (0A freeze / remediation facts)
- `LOAD_PAGE_INTAKE_IMPLEMENTATION_TRACKER.md` (parser safety)

Historical / transitional / draft consulted for conflict mapping:

- `LOAD_LIFECYCLE_AND_OPERATIONAL_EVENTS_LOCK.md`
- `PHASE1_TRIP_FOUNDATION_PLAN.md`
- `DECISION_6_DISPATCHER_LOAD_WORKSPACE_ACTION_MODEL.md`
- `DECISION_8_DRIVER_DISPATCH_PACKAGE_SCHEMA.md`
- `TRIP_CONTAINER_ARCHITECTURE_GAP_REPORT.md`
- `PLANNED_TRIP_LIFECYCLE_MODULE_CLOSE.md`
- Phase 3C / 3D / 3L-A / 3L-C / 3L-D docs as listed in §16
