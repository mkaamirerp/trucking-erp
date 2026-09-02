# TruckERP — Trip Container Operational Rules and Architecture Lock

**Status:** Architecture rule document / implementation anchor  
**Scope:** Trip container, Load relationship, driver assignment, city pickup, cancellation, delivery/completion, audit/accounting relationships  
**Supersedes prior snapshot:** An earlier short “Trip foundation — movement container vs. load” note in this same path. Where any rule differed, **this document wins**. Notable expansions: five pillars, authority map, the shipped simple Trip lifecycle plus future execution-event direction, TripLoad `removed` vs commercial Load `cancelled`, Load `final_delivered` + custody direction, planned Trip may stay empty after sole Load cancels pre-assignment until dispatcher acts, city pickup as same-Load Trip segment, payroll/settlement and board direction.

**Do not treat this as a request to immediately build all features.** This document locks business meaning and implementation direction so future code stays consistent.

---

## Glossary

**Trip** — The operational movement container. It represents what a driver/team, truck, and trailer are doing under one trip number.

**Load** — The commercial broker/customer contract record. It owns broker, rate confirmation, references, documents, commodity, and contractual stops.

**Dispatch Load** — An operator action: commit or send an existing Load through a Trip-backed dispatch workflow. It is not a separate entity, table, or lifecycle. Operational commitment is represented by Trip assignment plus TripLoad membership; execution begins only from an accepted Trip execution signal.

**TripLoad** — The relationship record connecting a Load to a Trip. It tracks whether the Load is planned, active, completed, or removed within that Trip.

**Yard / Terminal** — A company-controlled or operational location where freight/trailers may be dropped, staged, handed off, or picked up for the next Trip.

**City driver** — A driver usually assigned to local pickup/delivery, yard, or short-haul work. Pay treatment comes from driver/pay configuration, not from the Load itself.

**Long-haul driver** — A driver usually assigned to longer-distance movement. Pay treatment comes from driver/pay configuration.

**Custody** — Which Trip/driver currently has operational responsibility for the freight or trailer.

**Handoff** — The transfer of custody from one Trip/driver/location to another.

**TONU** — Truck Ordered Not Used. A cancellation/exception where a truck was ordered or dispatched but the load did not move as planned. It may affect billing, settlement, or expense recovery.

**Delivered** — The Trip reached its assigned destination. For a Load, final delivery means the freight reached the final receiver required by the broker/carrier contract.

**Completed** — Dispatch has closed the Trip file after required documents are uploaded/reviewed. Completed means eligible for payroll/settlement review; it does not mean paid.

**Settlement** — The review/calculation process that determines what a driver, owner-operator, or payee should be paid for completed work.

---

## 1. Core decision

TruckERP is moving from a **load-centric operational model** to a **trip-container operational model**.

The clean model is:

- **Trip = what the truck/driver/team is doing operationally.**
- **Load = what the broker/customer contracted commercially.**
- **TripLoad = the relationship between a Trip and a Load.**

A Load remains the commercial truth. A Trip becomes the operational truth.

This means one commercial Load can be moved by one Trip or by multiple Trips over time. It also means one Trip can carry one Load or multiple Loads.

---

## 1A. Three Parallel Truths (LOCKED)

TruckERP keeps **three separate truths**. They must stay **reconcilable**. This section fails-proofs the existing Load / Trip model; it does **not** replace it.

### A. Load = Commercial / Revenue Truth

- broker/customer contract
- rate/revenue
- contractual pickup/delivery obligation
- documents and billing
- remains alive across one or multiple Trips until final commercial completion

### B. Trip = Operational / Payable Work Truth

- driver/team
- truck
- trailer
- operational movement segment
- execution lifecycle
- creates the work that settlement/payroll will eventually pay

### C. Audit / Custody Timeline = Continuity Truth

- where freight was
- which Trip had responsibility
- which driver/equipment handled it
- pickup
- handoff
- yard/terminal state
- trailer transfer
- next Trip
- final delivery
- correction / void history

### Locked principle

Load, Trip, and Audit/Custody are separate truths but must remain reconcilable.

A commercial Load must have an unbroken operational and custody/audit history from booking through final delivery/close.

Every Trip performing work must remain traceable to the Load(s) it moved and to the custody events caused by that work.

**No line may silently disappear.**

### Invalid continuity examples

- Load remains active with no known Trip and no known custody/location state.
- Trip moves freight without auditable TripLoad membership.
- Trip completes with undelivered freight and no handoff/custody event.
- Load becomes final_delivered without a final-delivery event.
- Load revenue exists but payable Trip work becomes untraceable.
- Driver/truck/trailer responsibility changes without an auditable transition.
- Trailer identity changes through silent overwrite instead of transfer/history.

### Valid operational example

**Commercial Load:** Acme Brick → XYZ Bricks

**Trip A:** US/night driver; Acme Brick → company yard; Trailer 13006.

Trip A may complete its **operational** responsibility at the yard. The Load remains **commercially** active.

**Audit/Custody:** Load/trailer arrives at company yard. Custody/location is recorded explicitly. Load is **not** final delivered.

**Trip B:** local/day driver; company yard → XYZ Bricks; same Trailer 13006 **or** a different trailer.

Trip B may be **PLANNED** before Trip A physically arrives.

### Locked distinction

**Future reservation ≠ current custody ≠ execution eligibility.**

Planning Trip B does **not** mean Trip B currently possesses the freight. Current custody may still belong to Trip A. Execution of Trip B must occur only when the required operational handoff/release conditions are satisfied.

### TripLoad clarification (membership vs continuity)

**TripLoad** is the **membership / relationship bridge** between Load and Trip.

**TripLoad is NOT the complete custody/audit timeline.** Custody events provide continuity/history.

**Slice 1 (foundation shipped):** `terminals`, `load_custody_events`, Load custody snapshot columns, read APIs, bootstrap script.

**Slice 2 (operational transitions):** `POST .../accept-custody`, `.../yard-handoff`, `.../take-custody`. Bare `POST .../activate` and `.../complete` return **409 `MEMBERSHIP_TRANSITION_REQUIRES_CUSTODY`**.

---

### TripLoad membership semantics (LOCKED — V1)

**Authoritative home for open vs active, cardinality, and transitions.** Implementation may lag; code that still treats any `removed_at IS NULL` row as “the” current trip is **legacy behavior to be corrected**, not the product lock.

#### Open ≠ active

| Term | Definition |
|------|------------|
| **Open membership** | `status_within_trip IN ('planned', 'active')` **AND** `completed_at IS NULL` **AND** `removed_at IS NULL`. |
| **Active membership** | `status_within_trip = 'active'` **AND** open (both terminal timestamps NULL) — current operational movement responsibility for that Load. |

**`removed_at IS NULL` alone does NOT mean open.** Completed memberships keep `removed_at IS NULL` and set `completed_at`. An open **`planned`** row is a future reservation only.

Older docs that said **“open = `removed_at IS NULL`”** or **“active membership = `removed_at IS NULL`”** are **superseded** by this section.

#### Status meanings

| Status | Meaning |
|--------|---------|
| `planned` | Future membership / reservation. **No custody. No execution.** Does **not** make that Trip the Load’s active/current Trip. `completed_at`/`removed_at` NULL. |
| `active` | Current operational movement responsibility. `completed_at`/`removed_at` NULL. |
| `completed` | This Trip’s responsibility for the Load finished **normally**. `completed_at` set; **`removed_at` remains NULL**. Historical membership preserved. Load may still remain **commercially** active. |
| `removed` | Membership cancelled / removed / replanned. `removed_at` set; `completed_at` NULL. Historical membership preserved. |

#### V1 cardinality (one Load)

- Maximum **ONE** open **`active`** membership.
- Maximum **ONE** open **`planned`** membership (the next future reservation).
- Unlimited **`completed`** history.
- Unlimited **`removed`** history.

**Reason:** Until an explicit trip-chain / future-sequence model exists, multiple open planned memberships would create ambiguous competing next Trips.

#### Valid overlap (required)

Trip A / Load 123 = **`active`**  
Trip B / Load 123 = **`planned`**

Required for the yard handoff scenario (Acme → Yard → XYZ).

#### Invalid overlap (V1)

- Two open **`active`** memberships for the same Load — never two current movement owners.
- Two open **`planned`** memberships for the same Load — invalid until explicit future-trip sequencing exists.

#### `loads.active_trip_id` (intended meaning)

Compatibility / read-model pointer to the Load’s current **ACTIVE** Trip only.

It must **NOT**:

- point to a **PLANNED** Trip
- select an arbitrary open TripLoad
- represent future reservation

**TripLoad remains source of truth** for membership. `active_trip_id` is a mirror, not authority.

#### Explicit transitions

| From → To | Rule |
|-----------|------|
| `planned` → `active` | Explicit activation only. |
| `active` → `completed` | Normal end of this Trip’s responsibility for the Load. |
| `planned` → `removed` | Cancel / replan reservation. |
| `active` → `removed` | Explicit exception / cancellation workflows only. |

**No automatic transition:** completing active membership A must **NOT** automatically activate planned membership B. Activation of B is **explicit**.

At yard (reference): Trip A → **`completed`**; custody/handoff recorded **separately**; Trip B remains **`planned`** until later explicit activation → **`active`**.

#### Reference scenario (LOCKED)

**Commercial Load:** Acme Brick → XYZ Bricks

- **Trip A:** US/night driver; Acme → Yard; TripLoad **`active`**
- **Trip B:** local/day driver; Yard → XYZ; TripLoad **`planned`** while Trip A is still **`active`**
- **At yard:** Trip A → **`completed`**; custody/handoff recorded separately; Trip B stays **`planned`**
- **Later:** explicit Trip B activation → **`active`**

Same Trailer 13006 or a different trailer both remain valid for Trip B.

Preserve: **future reservation ≠ current custody ≠ execution eligibility**; TripLoad ≠ full custody timeline; Load / Trip / TripLoad / Audit-Custody remain four distinct truths (§1A A–C + membership).

#### Reference scenario — many-to-many Trip/Load continuity (LOCKED)

TruckERP must preserve a **true many-to-many** relationship:

- One Trip can carry **multiple Loads**.
- One Load can move through **multiple Trips**.
- **TripLoad** is the membership bridge between them.
- **Audit/Custody** history explains what physically happened between and during Trips.

**Example — two Loads, one inbound Trip, split outbound:**

| Commercial Loads | |
|------------------|---|
| **Load A** | Boston → Brampton |
| **Load B** | Albany → Toronto |

**Inbound Trip 10001** (long-haul / US driver; one truck/trailer):

- Picks up Load A in Boston
- Picks up Load B in Albany
- Brings both Loads to the company yard

**At the yard:**

- Trip 10001 may **complete** its operational responsibility
- Load A and Load B remain **commercially active**
- Both Loads are unloaded/staged at the yard
- Custody/audit history must record the yard state

**Outbound split:**

- **Trip 10002:** House Driver A takes one Load from yard → final destination
- **Trip 10003:** House Driver B takes the other Load from yard → final destination
- Each outbound Trip may use the **same** trailer or a **different** trailer as operationally required

**Architecture reminder:** Load = commercial/revenue; Trip = operational/payable; TripLoad = which Loads participated in which Trips; Audit/Custody = continuity (pickup, movement, yard handoff/staging, trailer transfer if any, next Trip, final delivery). Do **not** duplicate a commercial Load merely because it moves through multiple Trips. Every Trip that performs work must remain traceable to the Load(s) it moved.

**Fail-proof acceptance (eventual):** 2 Loads → 1 inbound Trip → both staged at yard → 2 separate outbound Trips → 2 different drivers → same or different trailers → each Load keeps its own commercial revenue → every Trip remains separately traceable for driver/pay → complete custody/audit history for both Loads.

---

## 2. Five pillars

All future implementation must follow these five pillars.

### Pillar 1 — Establish the Trip container foundation

Trip is the operational root/container.

Trip owns:

- trip number
- driver/team assignment
- truck assignment
- trailer assignment
- dispatch status/lifecycle
- operational movement/execution
- trip-level notes/events/audit
- future terminal, custody, handoff, and execution sequence

### Pillar 2 — Define Load membership into the container

Loads belong to Trips through an explicit relationship table, conceptually `trip_loads`.

TripLoad owns:

- which Load belongs to which Trip
- whether that membership is planned, active, completed, or removed
- when the Load entered or left the Trip
- sequence/order hint if needed
- future relationship-specific audit context

Do not replace this relationship with only `loads.trip_id` or `loads.active_trip_id`.

### Pillar 3 — Keep `LoadWorkspacePage` as load preparation / commercial confirmation

`LoadWorkspacePage` stays alive. It should not be deleted.

Its long-term role changes from operational root to:

- load intake
- load verification
- PDF/email/manual field review
- broker/commercial confirmation
- contractual stop review
- document review
- commercial load preparation

### Pillar 4 — Move operational assignment / dispatch into `TripWorkspacePage`

Driver, team, truck, trailer, trip number, dispatch lifecycle, terminal routing, handoff, and operational execution belong to the Trip workspace.

`LoadWorkspacePage` may show trip-related snapshots or links, but it should not remain the final operational dispatch surface.

### Pillar 5 — Build the full Trip page / board / UI on top

After the foundation and membership are stable, the operational UI should pivot from load rows to trip containers.

The current Loads list can remain for commercial load work. The future dispatch board should operate primarily on Trips.

---

## 3. Load vs Trip authority map

### Trip owns operational truth

Trip owns:

- trip number
- trip status
- driver/team
- truck
- trailer
- operational origin/destination for that Trip segment
- actual movement execution
- dispatch instructions
- trip-level completion
- trip-level cancellation
- future terminal/custody/handoff events
- settlement/payroll eligibility for the assigned work

### Load owns commercial truth

Load owns:

- broker
- broker contact
- broker/customer references
- rate confirmation
- commodity
- weight
- temperature requirement
- equipment requirement
- commercial/contractual pickup and receiver stops
- documents
- billing/invoice identity
- broker revenue
- commercial cancellation/final delivery state

### TripLoad owns relationship / membership truth

TripLoad owns:

- this Load is on this Trip
- the status of that relationship (`planned` / `active` / `completed` / `removed`)
- added/removed/completed timestamps
- sequence/order hint
- future reason/audit metadata

**Do not collapse TripLoad into Audit/Custody.** TripLoad is the membership bridge. Continuity history (pickup, handoff, yard/terminal, trailer transfer, final delivery, void/correct) belongs to the **Audit / Custody Timeline** (see §1A). Membership rows are necessary for reconcilability; they are not a substitute for custody events.

**Open ≠ active:** see §1A TripLoad membership semantics. Open = planned|active with both terminal timestamps NULL; current movement owner = open **`active`**.

### Audit / Custody owns continuity truth

Audit/Custody owns (conceptually; schema/API timing is separate):

- where freight was and is
- which Trip had responsibility
- which driver/equipment handled it
- handoff / yard / terminal / trailer-transfer events
- final-delivery continuity and correction/void history

---

## 4. Do not build a patched “Load page v2”

Do not solve multi-load operations by adding tabs or a multi-load toggle to the old Load page.

Bad direction:

- Load page with multiple load tabs
- Load page as final dispatch root
- a few Trip fields added at the top of Load page
- treating `load_stops` as the whole operational execution sequence

Correct direction:

- Trip page is the operational root.
- Load page is commercial/preparation workspace.
- TripLoad connects them.
- Future trip execution sequence is modeled separately from contractual load stops.

---

## 5. Planned Trip creation and trip number rule

### New rule

A Trip can exist before driver/truck/trailer assignment.

A Trip number may be minted when the Trip container is created/planned, not only when a Load enters dispatched.

This supports scheduling and future planning.

### Numbering rules

Trip numbers are:

- generated only by the backend
- tenant-scoped
- taken from the tenant dispatch numbering sequence
- immutable after creation
- never reused
- retained even if the Trip is cancelled, abandoned, or ends up empty

Gaps in sequence are acceptable.

### Important implication

The old rule “trip number is born only when a load enters dispatched” is no longer the final architecture rule. It may remain as a legacy compatibility path during migration, but the target model is:

> Trip number is born when the Trip container is created/planned.

---

## 6. Trip statuses

Trip status should represent operational movement status, not commercial load status.

### Current shipped lifecycle

| Status | Meaning |
|--------|---------|
| `planned` | Trip container exists. Trip number is minted. Driver/truck/trailer may be blank. Trip may temporarily have zero Loads. |
| `assigned` | Complete driver/truck/trailer assignment has been committed. Assignment or package send does not start execution. |
| `in_progress` | The first accepted execution signal started operational execution. |
| `completed` | Dispatcher has closed the Trip file after required documents/review. This makes the Trip eligible for payroll/settlement review. |
| `cancelled` | Trip was cancelled. Trip number remains permanently for audit. |

Current transition spine:

```text
planned -> assigned -> in_progress -> completed
                         \
                          -> cancelled where product rules allow
```

### Future execution detail

Concepts such as `dispatched`, `in_transit`, `at_pickup`, `at_delivery`, `delivered`, `problem_hold`, `arrived_terminal`, and `handed_off` are useful operational detail, but they are **not current `Trip.status` values**. Model them through explicit execution/custody events or a separately approved sub-state design. Do not expand the core Trip lifecycle or revive legacy `Load.status` lanes without an explicit architecture decision.

---

## 7. Delivered vs completed

Delivered and completed are not the same.

### Delivered

`delivered` means the Trip reached its assigned operational destination.

Examples:

- Long-haul Trip reached final receiver.
- City pickup Trip reached the yard/terminal assigned by dispatch.

### Completed

`completed` is a dispatcher-controlled closeout state.

**API (V1 shipped):** `POST /api/v1/trips/{trip_id}/complete` transitions **`in_progress` → `completed`** only when the Trip has **zero OPEN** TripLoad memberships (`planned|active` with both timestamps NULL). Sets **`trips.completed_at`** once (immutable on idempotent retry). Does **not** mutate TripLoads, `Load.status`, `active_trip_id`, custody, payroll, or `dispatch_trips`. Does **not** auto-activate another Trip.

Product closeout may later also require documents / file review; those gates are **not** enforced by this endpoint yet.

Completed means:

> Dispatch file complete / ready for payroll or settlement review (operational Trip responsibility ended).

Completed does **not** mean payroll is paid. Payroll/settlement remains a later workflow.
Completed does **not** mean commercial Load final delivery.

---

## 8. Load final delivery vs Trip delivery

Trip delivery and Load final delivery are separate.

A Trip can be delivered/completed even when the commercial Load is not finally delivered.

Example:

- Load: Mississauga pickup → Boston final receiver
- Trip 1: city driver picks up in Mississauga and drops at Terminal A
- Trip 2: long-haul driver takes the same Load from Terminal A to Boston

In this example:

- Trip 1 can be `delivered` or `completed` at Terminal A.
- The Load is **not** finally delivered yet.
- The Load remains active and should be available for the next Trip.
- Trip 2 later performs the final delivery to Boston.

Rule:

> Trip completed means the assigned movement is complete. Load final delivered means the broker/customer contract reached its final receiver.

---

## 9. Cancellation rules

Load cancellation and Trip cancellation are separate.

### Load cancellation

A Load is cancelled when the broker/customer commercial job is cancelled.

When a Load is cancelled:

- `loads.status` should become `cancelled` or an equivalent explicit commercial terminal state.
- The relevant `trip_loads` membership should be closed/removed if that Load is no longer on the Trip.
- The Trip should **not** automatically cancel if other active Loads remain.

### Trip cancellation

A Trip is cancelled when the operational movement itself is cancelled.

When a Trip is cancelled:

- `trips.status = cancelled`
- `cancelled_at` should be set when available
- trip number remains forever
- active TripLoad memberships are closed/removed
- commercial Loads are **not** automatically cancelled unless the dispatcher explicitly performs a commercial cancellation action

### One Load cancels on a multi-load Trip

If a Trip has multiple Loads and one Load cancels:

- cancelled Load becomes commercially cancelled
- that Load’s TripLoad membership is removed/closed
- Trip continues with remaining active Loads

### Only Load cancels before assignment

If the only Load on a planned Trip cancels before assignment:

- Load becomes commercially cancelled
- TripLoad membership is removed/closed
- Trip remains as a planned empty Trip until dispatcher cancels it or adds another Load
- trip number is not reused

### Only Load cancels after driver is dispatched/on the way

If the driver has already been sent and the only Load cancels:

- Load becomes commercially cancelled
- TripLoad membership is removed/closed
- Trip remains an audit/operational record
- dispatcher decides whether to cancel the Trip, complete it with exception, or add another Load

This protects future TONU, deadhead, driver pay, and audit logic.

---

## 10. TripLoad statuses

Recommended `trip_loads.status_within_trip` values (meanings locked in §1A):

| Status | Meaning |
|--------|---------|
| `planned` | Future membership / reservation — no custody, no execution; does not set current Trip. |
| `active` | Current movement responsibility — max **one** open `active` per Load (V1). |
| `completed` | That Load’s responsibility within that Trip finished normally; historical; Load may stay commercially active. |
| `removed` | Membership cancelled / removed / replanned; historical. |

**Open membership** = `status_within_trip IN ('planned', 'active')` AND `completed_at IS NULL` AND `removed_at IS NULL`.  
**Active membership** = `status_within_trip = 'active'` AND open.  
`completed_at` = normal completion timestamp; `removed_at` = removed/cancelled/replanned only (not a generic closed stamp).

V1: max one open `planned` and max one open `active` per Load; unlimited `completed` / `removed` history. Valid: active A + planned B. Invalid: two open actives, or two open planneds, until future sequencing exists.

These are **membership** statuses on TripLoad, not the full custody/audit timeline (see §1A).

Do not confuse `trip_loads.status_within_trip = removed` with `loads.status = cancelled`.

- `removed` is membership status.
- `cancelled` is commercial Load status.

If more detail is needed later, use a reason field or event log, not many statuses immediately.

Possible future reason codes:

- `dispatcher_removed`
- `load_cancelled`
- `reassigned`
- `terminal_handoff`
- `yard_staged`

---

## 11. Load statuses and custody/location

Long-term, Load status should not carry the whole operational trip lifecycle.

Load should eventually support commercial/custody concepts such as:

- `draft`
- `ready`
- `active`
- `cancelled`
- `final_delivered`

For yard/terminal workflows, avoid overloading `delivered`.

A Load may need custody/location fields or events such as:

- current location type: shipper / in_transit / yard / terminal / receiver
- current location id/name
- custody status: at_yard, staged_for_next_trip, on_trip, final_delivered
- load custody event history

When a city Trip drops freight at a yard, the Load’s current location should update to that yard, but the Load is not finally delivered unless the broker contract’s final receiver is that yard.

---

## 12. Broker Load assignment rules

A broker Load is not classified as city or long-haul by itself.

A broker can ask for a 5-mile move or a 5,000-mile move. The dispatcher decides which driver and Trip should handle it.

Driver type/pay logic already lives in driver configuration.

Therefore:

- A city driver can be assigned directly to a broker Load.
- A long-haul driver can be assigned directly to a broker Load.
- An owner-operator can be assigned directly to a broker Load.
- Driver profile/pay setup determines payroll treatment.

Do not create special logic that says “if local city load, create a different commercial Load.”

The Load remains the commercial contract. The Trip is the operational/payable movement.

---

## 13. Normal assignment vs City Pickup action

### Normal assignment

For a normal broker Load, dispatcher can assign a driver/Trip directly.

This may be:

- city driver
- long-haul driver
- company driver
- owner-operator
- team driver

The system should rely on driver configuration and pay rules to determine payroll/settlement behavior. This is already present in Driver Onboarding, where an admin configures that before approving the driver.

### City Pickup / Send City Driver

Use `Send City Pickup` only when the dispatcher wants to create a separate pickup-to-yard or pickup-to-terminal movement for the same Load.

This is not a separate commercial Load.

It creates an operational Trip segment for the same Load.

Example:

- Load: Mississauga pickup → Boston final receiver
- City Pickup Trip: Mississauga pickup → Terminal A
- Long-haul Trip: Terminal A → Boston

### Required rule

> “Send City Pickup” creates an operational Trip for the same Load. It does not create another commercial Load unless there is a separate broker/customer contract.

---

## 14. Load handoff to city driver

When a Load has been created from broker PDF/email/manual entry and is ready for pickup, dispatcher should be able to hand it to a city driver by creating a City Pickup Trip.

The action should ask operational questions only:

- pickup stop from the Load
- drop yard/terminal
- city driver
- truck/trailer if needed
- planned vs assign/dispatch now

The system then creates:

- a Trip with a new trip number
- TripLoad membership to the same Load
- origin from selected pickup stop
- destination as selected yard/terminal
- driver/equipment if selected

When city driver completes the Trip:

- Trip can become delivered/completed according to its destination and document rules
- Load remains commercially active if final receiver is elsewhere
- Load current location/custody becomes the yard/terminal
- Load becomes available for the next Trip

---

## 15. Direct delivery by city driver

No special product path is needed for local/city-distance Loads.

If a Load is Mississauga to Mississauga, or 100–150 miles, dispatcher can simply assign a city driver through normal Trip assignment.

Do not create a separate “Create City Delivery Trip” product type only because the distance is short.

The driver’s configuration determines that the driver is hourly/city/etc.

---

## 16. Accounting and profit relationship

The reason this architecture matters is accounting and relationship tracing.

A single broker Load has revenue.

That revenue may be served by one or multiple Trips.

Example:

- Load revenue: broker pays for Mississauga → Boston
- Trip 1 cost: city driver pickup to yard, hourly pay
- Trip 2 cost: long-haul driver to Boston, mileage/percentage/owner-operator pay
- Additional expenses: fuel, tolls, yard, accessorials, deductions

Profit analysis should connect:

- Load revenue
- all related Trips
- all driver/payee settlements generated by those Trips
- all expenses allocated to those Trips/Load

So TruckERP must support:

> Load revenue minus related Trip costs and expenses = true profit.

This is why Load and Trip must be separate but related.

---

## 17. Settlement and payroll boundary

Settlement/payroll should eventually be based on Trip work, assigned driver/payee, and compensation profile.

A single Load may produce multiple payable Trips.

Examples:

- city pickup Trip creates hourly city driver pay
- long-haul Trip creates long-haul/owner-operator/company driver pay
- direct Trip creates one driver settlement path

The Load remains the commercial revenue record.

Trip completion makes the Trip eligible for payroll/settlement review, but does not mean the driver has been paid.

Payroll remains a separate future workflow.

---

## 18. Operational boards and queues

There should eventually be different views for different questions.

### Loads list / Load board

Commercial/preparation view.

Shows:

- broker Loads
- readiness
- commercial references
- rate/doc info
- maybe current trip link
- maybe current custody/location

### Trips list / Trip board

Operational execution view.

Shows:

- Trip number
- driver/team
- truck/trailer
- Trip status
- loads inside Trip
- movement state

### Needs Next Trip / At Yard board

Future operational planning/custody view.

Shows Loads that are not finally delivered and are sitting at a yard/terminal ready for another Trip.

For each row:

- Load number
- broker
- current location/yard
- final receiver/destination
- required equipment
- commodity/weight/temp
- documents
- ready for next Trip status

This board should derive current origin from custody/location and final destination from the original Load contract.

---

## 19. Current implementation state to preserve

The current system already has:

- `trips` table foundation
- `trip_loads` membership
- `loads.active_trip_id` mirror
- live bridge from dispatch path into trips/trip_loads
- catch-up repair for missing mirrors
- read-only Trip detail page
- read-only Trips list
- `LoadWorkspacePage` still working as commercial/prep surface

Do not break these.

Until the full writer flip is done, current legacy compatibility may still include:

- `dispatch_trips`
- `loads.active_dispatch_trip_id`
- `loads.trip_number`

But the target authority is Trip + TripLoad.

---

## 20. Implementation direction from here

### Do next only after rules are locked

The next implementation should not jump into board pivot immediately.

First lock/update docs for:

- trip number minted on Trip create/planned
- zero-load planned Trips allowed
- Trip cancellation vs Load cancellation
- delivered vs completed
- city pickup as Trip segment, not duplicate Load
- driver type/pay determined by driver configuration
- Load revenue vs Trip cost relationship

### Then implement in small phases

Recommended sequence:

1. **Doc lock update** for the new rules.
2. **Planned Trip creation API** that mints trip number on Trip creation.
3. **Trip membership APIs**: add existing Load to Trip, remove Load from Trip.
4. **City Pickup action**: create Trip for same Load from pickup stop to yard/terminal.
5. **Trip cancellation endpoint** separate from Load cancellation.
6. **Load cancellation endpoint/state** separate from Trip cancellation.
7. **Trip status transitions**: planned → assigned → in_progress → completed, with cancelled as the terminal negative state. Granular movement details belong to execution/custody events, not new Trip header statuses.
8. **Load custody/location events** for yard/terminal handoff and Needs Next Trip board.
9. **Move assignment controls from LoadWorkspacePage to TripWorkspacePage.**
10. **Trip-based dispatch board.**
11. **Payroll/settlement integration.**

---

## 21. Non-goals for immediate next slice

Do not implement all of this at once.

Do not immediately:

- replace the current dispatch board
- delete or rewrite `LoadWorkspacePage`
- build full custody/terminal system
- build payroll/settlement calculations
- create duplicate Loads for city pickup
- force every Trip to have a Load at creation
- auto-cancel Trip when one Load cancels
- auto-complete Trip when delivered
- treat completed as payroll paid

---

## 22. Final locked rules

1. Trip is the operational execution container.
2. Load is the commercial broker/customer contract record.
3. Trip may contain one or more Loads.
4. A Load may move through multiple Trips before final delivery.
5. TripLoad is the explicit membership/relationship bridge between Trip and Load (not the complete custody/audit timeline).
6. Trip number belongs to Trip, not Load.
7. Trip number may be minted when a planned Trip is created.
8. Trip numbers are never reused.
9. A planned Trip may temporarily have zero Loads.
10. Load cancellation and Trip cancellation are separate.
11. Cancelling one Load does not automatically cancel the Trip.
12. Cancelling a Trip does not automatically commercially cancel the Loads unless explicitly requested.
13. Trip delivered and Load final delivered are separate.
14. Trip completed means dispatcher closed the Trip file after required docs/review; it becomes payroll/settlement eligible.
15. A city pickup is a Trip segment for the same Load, not a duplicate Load.
16. A local broker Load does not need special “city load” logic; dispatcher chooses driver and Trip, and driver configuration determines pay treatment.
17. Load revenue must be connected to all related Trips, settlements, and expenses for profit reporting.
18. `LoadWorkspacePage` stays as load preparation/commercial confirmation.
19. `TripWorkspacePage` becomes the operational assignment/dispatch root.
20. Dispatch board eventually pivots from Loads to Trips.
21. Three parallel truths: Load = commercial/revenue; Trip = operational/payable; Audit/Custody timeline = continuity — separate but reconcilable (§1A).
22. No line may silently disappear: unbroken operational and custody/audit history from booking through final delivery/close; every Trip’s work remains traceable to Load(s) and custody events.
23. TripLoad is membership/relationship only — not the complete custody/audit timeline.
24. Future reservation ≠ current custody ≠ execution eligibility.
25. Open ≠ active: open membership requires `status_within_trip IN ('planned', 'active')` AND `completed_at IS NULL` AND `removed_at IS NULL`; active membership additionally requires `status_within_trip = 'active'` (§1A).
26. V1 per Load: max one open active + max one open planned; unlimited completed/removed history; active A + planned B is valid; two open actives or two open planneds are invalid.
27. `loads.active_trip_id` points only to the current ACTIVE Trip (compatibility mirror); must not point at planned or arbitrary open membership.
28. Completing active A must not auto-activate planned B; activation is explicit.

---

## 23. Cursor implementation guardrail

Before coding any future Trip/Load/dispatch feature, Cursor must check the work against these questions:

1. Does this keep Trip as operational root?
2. Does this keep Load as commercial truth?
3. Does this use TripLoad instead of shortcutting through only `loads.active_trip_id`?
4. Does this avoid duplicating commercial Loads for operational Trip segments?
5. Does this preserve trip number immutability and audit?
6. Does this separate Trip cancellation from Load cancellation?
7. Does this separate Trip delivered/completed from Load final delivery?
8. Does this preserve `LoadWorkspacePage` as preparation/commercial confirmation?
9. Does this move operational assignment toward `TripWorkspacePage`?
10. Does this support future relationship/accounting/profit reporting?
11. Does this keep Load, Trip, and Audit/Custody reconcilable (no silent gaps or silent overwrites)?
12. Does this keep TripLoad as membership only and custody events as continuity history?
13. Does this respect future reservation ≠ current custody ≠ execution eligibility?
14. Does this use the complete open-membership predicate (`planned|active` with both terminal timestamps NULL) and distinguish it from active (`status_within_trip = active` and open)?
15. Does this enforce V1 max one open active and max one open planned per Load?
16. Does completing a membership avoid auto-activating the next planned membership?

If the answer is no, the implementation is drifting.

---

## 24. Recommended next Cursor instruction

Use this when ready:

```text
DOC LOCK UPDATE ONLY — DO NOT CODE FEATURES

Update the TruckERP Trip/Load architecture docs to lock the following rules:

- Trip number may be minted when a planned Trip container is created.
- Trip may exist before driver/truck/trailer assignment.
- Planned Trip may temporarily have zero Loads.
- Trip numbers are never reused.
- Trip cancellation and Load cancellation are separate.
- Trip delivered/completed and Load final delivered are separate.
- Trip completed means dispatcher file closeout after required documents, ready for payroll/settlement review.
- City pickup creates a Trip segment for the same Load, not a duplicate Load.
- Local broker Loads do not need special city-load classification; dispatcher chooses driver, and driver configuration/pay profile determines pay treatment.
- Load revenue must relate to all Trips, settlements, and expenses for profit reporting.

Update docs only. Do not add migrations, code, UI, parser/Lab changes, or board changes.

After docs are updated, produce a short Phase 3C implementation proposal for planned Trip creation and membership actions.
```

---

## 25. Short canonical wording

> A Load is the commercial/revenue truth. A Trip is the operational/payable work truth. Audit/Custody is the continuity truth. TripLoad is membership only. Open (`planned|active` with `completed_at` and `removed_at` both NULL) ≠ active (`status_within_trip = active` AND open). V1: at most one open active and one open planned per Load; active A + planned B is valid for yard handoff; completing A does not auto-activate B. `active_trip_id` mirrors the active Trip only. The three continuity truths plus membership must remain reconcilable — no line may silently disappear. Future reservation ≠ current custody ≠ execution eligibility. “Dispatch Load” is an action, not a third entity. City pickup is a Trip segment for the same Load, not a second Load. Trip numbers belong to Trips, can be created during planning, and are never reused. Trip completion means dispatch file closeout and payroll eligibility; Load final delivery means the commercial freight reached the broker/customer receiver. TruckERP must relate Load revenue to all connected Trips, settlements, and expenses to show true profit.
