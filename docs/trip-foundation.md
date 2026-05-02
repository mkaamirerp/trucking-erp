# TruckERP — Trip Container Operational Rules and Architecture Lock

**Status:** Architecture rule document / implementation anchor  
**Scope:** Trip container, Load relationship, driver assignment, city pickup, cancellation, delivery/completion, audit/accounting relationships  
**Supersedes prior snapshot:** An earlier short “Trip foundation — movement container vs. load” note in this same path. Where any rule differed, **this document wins**. Notable expansions: five pillars, authority map, granular Trip statuses (`in_transit` / `at_pickup` / `at_delivery` / `delivered` / `problem_hold`), TripLoad `removed` vs commercial Load `cancelled`, Load `final_delivered` + custody direction, planned Trip may stay empty after sole Load cancels pre-assignment until dispatcher acts, city pickup as same-Load Trip segment, payroll/settlement and board direction.

**Do not treat this as a request to immediately build all features.** This document locks business meaning and implementation direction so future code stays consistent.

---

## Glossary

**Trip** — The operational movement container. It represents what a driver/team, truck, and trailer are doing under one trip number.

**Load** — The commercial broker/customer contract record. It owns broker, rate confirmation, references, documents, commodity, and contractual stops.

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

### TripLoad owns relationship truth

TripLoad owns:

- this Load is on this Trip
- the status of that relationship
- added/removed/completed timestamps
- sequence/order hint
- future reason/audit metadata

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

Recommended V1 Trip statuses:

| Status | Meaning |
|--------|---------|
| `planned` | Trip container exists. Trip number is minted. Driver/truck/trailer may be blank. Trip may temporarily have zero Loads. |
| `assigned` | Driver and/or equipment assignment has been planned, but the movement is not yet released/dispatched. |
| `dispatched` | Driver has been sent/released for the work. |
| `in_transit` | Driver/equipment is moving. |
| `at_pickup` | Driver/equipment is at a pickup location. |
| `at_delivery` | Driver/equipment is at a delivery/drop location for the Trip. |
| `delivered` | The Trip reached its assigned operational destination. This does not always mean the commercial Load is finally delivered. |
| `completed` | Dispatcher has closed the Trip file after required documents/review. This makes the Trip eligible for payroll/settlement review. |
| `cancelled` | Trip was cancelled. Trip number remains permanently for audit. |
| `problem_hold` | Operational exception/hold state. |

Future-compatible statuses may include:

- `arrived_terminal`
- `handed_off`

These should be added when terminal/custody workflows are implemented.

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

A Trip may be marked completed only after:

- required documents are uploaded
- dispatch reviews/confirms the Trip file
- dispatch explicitly marks the Trip complete

Completed means:

> Dispatch file complete / ready for payroll or settlement review.

Completed does **not** mean payroll is paid. Payroll/settlement remains a later workflow.

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

Recommended `trip_loads.status_within_trip` values:

| Status | Meaning |
|--------|---------|
| `planned` | Load is planned to be on this Trip. |
| `active` | Load is currently active on this Trip. |
| `completed` | This Load’s role in this Trip is complete. This may be terminal drop, handoff, or final delivery depending on Trip purpose. |
| `removed` | Load is no longer on this Trip. Commercial Load may or may not be cancelled. |

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
7. **Trip status transitions**: planned → assigned → dispatched → in_transit → at_pickup/at_delivery → delivered → completed.
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
5. TripLoad is the explicit relationship and audit bridge between Trip and Load.
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

> A Load is the broker/customer contract. A Trip is the operational/payable movement. A Load may be moved by one Trip or multiple Trips. City pickup is a Trip segment for the same Load, not a second Load. Trip numbers belong to Trips, can be created during planning, and are never reused. Trip completion means dispatch file closeout and payroll eligibility; Load final delivery means the commercial freight reached the broker/customer receiver. TruckERP must relate Load revenue to all connected Trips, settlements, and expenses to show true profit.
