# TruckERP — Trip Lifecycle, Terminal Routing, Yard Handoff, Dispatch, and Load Transfer Foundation

## 0) Purpose

This document combines three important design threads into one implementation-facing foundation note:

1. the Trip-centric redesign
2. the yard handoff / overnight carry / trailer-to-trailer transfer logic
3. the useful boundary rules raised during critique, plus the new terminal-delivery dispatch requirement

This is not a casual product note.
This is a foundational operations model for Cursor before coding.

The goal is to prevent false assumptions such as:

* one load always equals one trip
* one trip always ends only after final customer delivery
* one driver who picked up freight must also be the one to deliver it
* freight never changes trailer after pickup
* the old Load page can simply be extended into a multi-load screen
* terminal delivery is just another free-text stop choice with no dispatch consequence

Those assumptions are wrong in real operations.

---

## 1) Core redesign decision

The primary operational workspace must be a **Trip page**, not a **Load page**.

### Why

A single physical movement may include:

* one driver or team
* one truck
* one trailer
* one trip number
* multiple broker/customer loads
* separate rate confirmations
* separate references
* separate commercial rules
* one shared operational execution flow

So the clean model is:

* **Trip = operational execution container**
* **Load = commercial/broker/customer contract record inside the trip model**

This means the system is moving from:

**load-centric operations**

to

**trip-centric operations with load-based commercial truth**

---

## 2) Foundational separation of concepts

Aligned with **Three Parallel Truths** in [`trip-foundation.md`](./trip-foundation.md) §1A: Load = commercial/revenue; Trip = operational/payable; Audit/Custody = continuity. Separate but reconcilable; no silent disappearance. Detail and invalid/valid examples live there; this section keeps the operational framing used by terminal/yard/handoff rules below.

### 2.1 Load (commercial / revenue truth)

A Load is the commercial/broker/customer record.
It owns:

* broker/customer identity
* rate confirmation
* references
* load-level stops
* load-level billing
* load documents
* commercial rules
* broker-specific paperwork

A load can exist before dispatch, during movement, at yard, through handoff, across multiple trips, and until final delivery/close.

### 2.2 Trip (operational / payable work truth)

A Trip is the operational assignment/execution container.
It owns:

* trip number
* assigned driver/team
* assigned truck
* assigned trailer
* dispatch status
* operational status
* trip timeline/events
* responsibility window
* terminal/yard routing context

A trip may contain one or more loads through explicit TripLoad membership. TripLoad is the membership bridge — **not** the complete custody/audit timeline.

### 2.3 Audit / Custody Timeline (continuity truth)

Freight custody / operational location is separate from Trip and separate from final commercial load delivery.
At any point freight may be:

* on assigned road trailer
* on assigned city trailer
* at yard on trailer
* unloaded and staged at terminal/yard
* transferred to another trailer
* out for delivery
* delivered

This custody/location layer is required. Without it, the system will fake reality.

**Locked distinction (see trip-foundation §1A):** future reservation ≠ current custody ≠ execution eligibility. Planning a next Trip does not transfer custody or start execution.

**Concise valid pattern (Acme → Yard → XYZ):** commercial Load Acme Brick → XYZ Bricks; Trip A (night) moves to company yard on Trailer 13006 and may complete operationally while Load stays commercially active; custody records yard arrival explicitly; Trip B (day) may be planned before Trip A arrives and later runs yard → XYZ on the same or a different trailer. Full wording: [`trip-foundation.md`](./trip-foundation.md) §1A.

---

## 3) Core entity relationship shift

### Old load-centric pattern

* Load ←→ Rate Confirmation (1:1)
* Load ←→ Stops (1:many)
* Trip was effectively a grouping label or convenience field

### New trip-centric pattern

* Trip ←→ Loads (1:many via link)
* Load ←→ Rate Confirmation (1:1)
* Load ←→ Stops (1:many)
* Driver + Truck + Trailer + TripNumber belong to Trip
* Operational execution order belongs to Trip
* Commercial truth remains on Load

This is a real architectural shift, not a UI rename.

---

## 4) The biggest hidden risk: stop sequencing across loads

This must be treated as a first-class design problem.

### Example

Load A (TQL): Pickup Chicago → Drop Detroit

Load B (JB Hunt): Pickup Gary → Drop Cleveland

Real road execution may be:

* Chicago (A pickup)
* Gary (B pickup)
* Detroit (A delivery)
* Cleveland (B delivery)

That means stops can be interleaved across loads.

So the system must **not** assume each load’s stops remain in one contiguous execution block.

### Locked principle

**Contractual stop ownership and operational stop sequencing must be modeled separately.**

### Recommended direction

* `load_stops` = contractual stops belonging to each load
* `trip_stops` or trip execution events = actual operational sequence at trip level
* link/actions between trip execution and load stop intent

Do not assume the old Load page stop list can serve as the full dispatch execution model.

---

## 5) Trip completion is not the same as Load delivered

This is non-negotiable.

A trip may end when:

* all loads on that trip are delivered, **or**
* the assigned operational responsibility for that trip is complete, even if freight remains undelivered

### Example

Owner operator picks freight in Boston and Albany and brings both loads to yard/terminal.
That owner operator’s assignment is complete.
The loads still exist and are not yet delivered.

Therefore:

* Trip = completed
* Load = still active / awaiting handoff / awaiting local delivery / awaiting next trip

This is valid and must be supported.

---

## 6) Trip completion policy must exist

TruckERP must not hardcode only one meaning of trip completion.

Different operations behave differently.

### Example A — City / local P&D

A city driver may:

* leave yard in morning
* deliver multiple stops
* perform pickups later
* return to yard

Some companies treat that as one trip for the whole day.
Some separate it into multiple trip numbers.
Some treat freight continuity on trailer as the trip boundary.

### Example B — Owner operator / linehaul to yard

An owner operator may:

* pick up two loads on east coast
* bring them to yard
* finish his assignment there
* local/city operation later delivers them

That means trip completion is assignment completion, not final load delivery.

### Example C — Overnight loaded trailer

A company driver may:

* bring freight to yard at night
* park trailer loaded
* go home
* next morning the same trailer or a different trailer is used for final delivery

So the system needs **trip completion policy**.

### Recommended policy modes

* `FINAL_DELIVERY` — trip ends only when all freight on trip reaches final receiver
* `ASSIGNMENT_COMPLETE` — trip ends when assigned driver/team responsibility ends
* tenant-configurable local/day-route modes may come later, but do not over-harden one simplistic “empty trailer” rule as a universal system law

### Important note

Do **not** lock a global rule that “trip ends when trailer is empty.”
That may fit some fleets, but it is too narrow as a system-wide principle.

---

## 7) No floating undelivered freight when a trip ends

This is a critical enforcement rule.

If a trip ends while one or more loads remain undelivered, the system must require an explicit operational event such as:

* yard handoff
* terminal drop
* staged at yard/terminal
* trailer transfer
* reassignment pending
* new trip handoff

### Locked rule

**A trip cannot close with active undelivered freight unless an explicit custody/handoff event is recorded.**

No floating orphan freight.

---

## 8) Yard / terminal must be a real custody location

This is not optional.

Between Trip A and Trip B, freight may be:

* at Mississauga terminal
* at Brampton terminal
* at Quebec terminal
* on trailer at terminal
* off trailer and staged inside terminal

That means yard/terminal is not just a note. It is a real operational custody location.

### Locked rule

**Yard/terminal must be representable as a custody location even when freight is not currently on an active trip or trailer.**

This should be modeled using location/terminal references in custody events and/or active custody state.

---

## 9) “At yard” is too vague

A single status called `at_yard` is operationally ambiguous.

These are not the same:

* trailer parked loaded at yard
* freight unloaded and staged at yard
* freight transferred to another trailer but still at terminal waiting dispatch

So V1 should not rely on one broad `at_yard` status.

### Better direction

Use more precise operational states such as:

* `AT_TERMINAL_ON_TRAILER`
* `AT_TERMINAL_STAGED`
* `AT_TERMINAL_TRANSFERRED_WAITING_DISPATCH`

The exact naming can be finalized later, but the principle is locked:

### Locked rule

**Yard/terminal freight state must be more granular than a single `at_yard` label.**

---

## 10) Trailer-to-trailer transfer must be first-class

This is not an edge case.
It is a core requirement.

### Real example

Two loads arrive on one trailer at night.
In the morning:

* a company adds another partial to the same trailer for city delivery, or
* one of the existing loads is moved to a different trailer, or
* city/local delivery is built using a different trailer from the inbound trailer

So the system must support:

* moving an undelivered load from one trailer to another
* moving multiple loads together if required
* recording who authorized it
* recording where it happened
* recording whether it happened at terminal/yard or elsewhere

### Locked rule

**Trailer-to-trailer transfer must be an explicit auditable event, never a silent overwrite of current trailer fields.**

---

## 11) Loads may continue across multiple trips

This is required.

A load may:

* begin on Trip A
* arrive at terminal/yard
* be handed off
* continue on Trip B
* later, in rare cases, move again

So a load must survive across trip boundaries until final delivery.

### Locked rule

**A load may remain active across multiple trips until final delivery/close.**

---

## 12) Dispatch screen requirement: terminal routing after pickup

This is a new operational requirement and should be included in the design.

### User requirement

Once a load is picked up from Boston (example), the system should support an immediate dispatch decision through a dropdown or dispatch action such as:

* Deliver
* Dispatch to Terminal

If dispatch to terminal is chosen, the terminal may be selected from more than one terminal, for example:

* Mississauga
* Brampton
* Quebec

This is a very important operational pattern because freight may be linehauled to a terminal first and only later sent on final/local delivery.

### Meaning

After pickup, the next destination is not always the final receiver.
Sometimes the next destination is a company terminal.

Therefore the system must support terminal-directed movement as a normal, planned operational branch.

### Locked rule

**After pickup, dispatch workflow must support routing freight either toward final delivery or toward a selected terminal/yard.**

### UI implication

On Trip page or dispatch workspace, there must be a visible operation/action that allows dispatcher to choose:

* Final Delivery
* Terminal Delivery / Dispatch to Terminal

and if terminal dispatch is selected, require terminal choice.

### Data implication

This should create or update trip execution intent and later custody/location state, not just store a free-text note.

---

## 13) Dispatch board and dispatch UI implication

The dispatch screen must eventually pivot from loads to trips.

### Why

The dispatcher needs to manage:

* which driver/team is doing the movement
* which truck/trailer is assigned
* which loads are on board
* whether the freight is going to final receiver or terminal
* handoff / transfer / staging states

A load-centric dispatch board will break as soon as multiple loads share a single operational movement.

### Required UI directions

The new Trip/Dispatch workspace should include:

#### A. Trip header

* trip number
* trip status
* driver/team
* truck
* trailer
* trip completion policy
* origin / current terminal context if relevant

#### B. Loads inside trip

Each load card should show:

* broker/customer
* references
* pickup / delivery summary
* revenue / rate summary
* current custody state
* terminal/delivery intent summary

#### C. Execution / dispatch decisions

Dispatcher must be able to:

* assign trip
* mark pickup complete
* choose next movement: Deliver vs Dispatch to Terminal
* select terminal if terminal route is chosen
* transfer load to another trailer
* create handoff
* dispatch undelivered load into a new trip

#### D. Timeline / event history

Trip timeline should show events such as:

* pickup complete
* terminal selected
* arrived Mississauga terminal
* staged at terminal
* transferred to trailer X
* assigned to city delivery trip

#### E. What should stay off the main Trip page

Do not overload the Trip page with every deep commercial detail.
The following remain primarily on Load page:

* full broker contact details
* full rate con detail
* full commercial document workspace
* detailed billing/invoicing controls

---

## 14) Load page role after redesign

The Load page still matters, but its role changes.

It becomes the **commercial/detail workspace** for:

* broker/customer identity
* rate confirmation
* references
* load financials
* load-specific rules
* load documents
* contractual stop plan
* history across trips and transfers

So the Load page is not deleted.
It simply stops being the top dispatch root.

---

## 15) Need for explicit link table between Trip and Load

Use a real linking structure.

### Recommended direction

`trip_loads`

* id
* tenant_id
* trip_id
* load_id
* status_within_trip or operational state within trip
* sequence/order hints if useful
* added_at
* removed_at nullable
* notes

### Why

This protects future logic such as:

* load reassigned from one trip to another
* handoff between trips
* trip-specific state for a load
* audit trail of which load belonged to which trip when

### Locked rule

**Use an explicit TripLoad link model; do not reduce the relationship to a simplistic convenience field only.**

---

## 16) Need for custody / movement event history

To support yard drop, terminal routing, overnight carry, and trailer transfer, the system needs append-style history.

### Recommended concept

`load_custody_events` or `load_movements`

Each record captures an operational transition such as:

* picked up onto trailer
* arrived at terminal on trailer
* unloaded / staged at terminal
* transferred from trailer A to trailer B
* assigned to city delivery trip
* delivered
* handoff from Trip A to yard/terminal custody

### Suggested fields

* id
* tenant_id
* load_id
* event_type
* from_trip_id nullable
* to_trip_id nullable
* from_trailer_id nullable
* to_trailer_id nullable
* from_truck_id nullable
* to_truck_id nullable
* from_driver_id nullable
* to_driver_id nullable
* terminal_id / yard_id / location_id nullable
* location_type
* quantity nullable
* quantity_unit nullable
* event_time
* notes
* created_by
* voided_flag / voided_reason / voided_by / voided_at if correction model is used

### Important future-proofing

Even if V1 only supports full-load transfer, add optional quantity fields now so later partial skid/quantity transfer is possible without breaking history design.

### Locked rule

**Schema must leave room for future quantity-based transfers even if V1 uses only full-load moves.**

---

## 17) Event correction policy

Real operations make mistakes.
For example:

* someone recorded transfer to Trailer 902, but it was really Trailer 901

The system should not solve this by silently rewriting history.

### Recommended rule

* no hard delete of custody history
* no silent edits as the truth model
* use void + correction event pattern

### Locked rule

**Custody/movement history must be audit-safe: void/correct rather than erase history.**

---

## 18) Trip completion with active loads: role / workflow control

Exact role design can be finalized later, but the system must not allow nonsense operations.

### Locked rule

**A driver should not be able to unilaterally complete a trip with active undelivered freight unless the required handoff/custody event workflow is satisfied.**

Dispatcher approval / override rules can be finalized later, but the event discipline must be enforced.

---

## 19) New trip assignment for undelivered loads

When a load finishes one trip but is not delivered, it may be attached to a new trip.

### Example

* Owner operator brings two loads to Mississauga terminal
* Owner operator trip completes
* next morning city driver takes one or both loads for local delivery

That means the system should support new trip assignment for an existing undelivered load.

### Recommended V1 behavior

When creating the new trip from an undelivered load, do not rely on magical silent inheritance.
Instead:

* show remaining undelivered stops
* offer explicit carry-forward/copy behavior for remaining stop intent

### Locked rule

**Trip-to-trip continuation should use explicit remaining-stop carry logic, not silent automatic inheritance.**

---

## 20) Status separation

### Trip status examples

* DRAFT
* PLANNED
* ASSIGNED
* DISPATCHED
* IN_PROGRESS
* ARRIVED_TERMINAL
* HANDED_OFF
* COMPLETED
* CANCELLED

### Load status examples

* DRAFT
* READY
* PICKED_UP
* IN_TRANSIT
* AT_TERMINAL_ON_TRAILER
* AT_TERMINAL_STAGED
* OUT_FOR_DELIVERY
* DELIVERED
* CLOSED
* CANCELLED

These are separate because trip may complete while load remains active.

---

## 21) Terminal delivery flow concept

This needs explicit business support.

### Example flow

1. Load picked up in Boston
2. Dispatcher chooses next action:

   * Deliver directly
   * Dispatch to Terminal
3. If Dispatch to Terminal:

   * choose terminal: Mississauga / Brampton / Quebec / others
4. Trip continues toward selected terminal
5. On arrival, one of these happens:

   * freight remains on trailer at terminal
   * freight is staged at terminal
   * freight is transferred to another trailer
   * freight is attached to new city/local delivery trip

This should not be improvised through notes.
It should be modeled as real operational state.

---

## 22) V1 scope recommendation

Do not build every advanced yard-management feature immediately.

### V1 should include

* Trip as operational root
* TripLoad link table
* Load remains commercial truth
* trip completion separate from load delivery
* explicit handoff requirement when trip ends with active freight
* yard/terminal as real custody location
* terminal routing choice after pickup (Deliver vs Dispatch to Terminal)
* terminal selection from configured terminals
* trailer-to-trailer transfer event
* new trip assignment for undelivered load after handoff
* granular terminal states beyond simple `at_yard`
* audit-safe custody history
* optional quantity fields reserved for future

### V2 later

* detailed dock/door/slot modeling
* pallet/skid-level quantity transfer logic
* advanced yard board / terminal staging board
* route optimization for city/local delivery
* more advanced trip policy automation by operation type

---

## 23) Implementation warning

Do **not** build a “Load page v2” that pretends to support trips.

That would be the wrong direction.

The correct direction is:

* Trip page becomes operational/dispatch root
* Load page remains first-class commercial detail workspace
* custody/movement history becomes the bridge between trip completion and load continuity
* terminal routing becomes an explicit dispatch workflow branch

---

## 24) Final locked principles for Cursor

Use these as the foundation block:

1. **Trip is the primary dispatch/execution container.**
2. **Load remains the commercial/broker contract record.**
3. **A trip may contain one or more loads through an explicit TripLoad relationship.**
4. **Execution order belongs to the trip, not to any single load.**
5. **Contractual stop ownership and operational stop sequencing must be modeled separately.**
6. **Trip completion is separate from load delivery.**
7. **A trip cannot close with active undelivered freight unless an explicit handoff/custody event is recorded.**
8. **Yard/terminal is a real custody location, not a note.**
9. **Yard/terminal freight state must be more granular than a single `at_yard` label.**
10. **Trailer-to-trailer transfer must be an explicit auditable event, never a silent overwrite.**
11. **A load may remain active across multiple trips until final delivery.**
12. **Dispatch workflow after pickup must support either final delivery or dispatch to a selected terminal.**
13. **Custody/movement history must be audit-safe: void/correct rather than erase.**
14. **Schema should leave room for future quantity-based transfers even if V1 is whole-load only.**
15. **Trip-to-trip continuation should use explicit remaining-stop carry logic, not silent automatic inheritance.**

---

## 25) Next follow-up design docs after this one

After Cursor absorbs this file, the next follow-up note should focus only on:

* exact schema proposal (`trips`, `trip_loads`, `trip_stops`, `load_stops`, `load_custody_events`)
* exact event types for custody/handoff/transfer/terminal routing
* exact Trip page wireframe and action model
* exact rule for when a new trip number is created
* exact role permissions for trip closure with active freight

