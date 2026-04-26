# TruckERP — Trip Container vs Load Foundation

## 0) Purpose

This document isolates the core architectural redesign behind TruckERP’s move from a load-centric operational model to a trip-centric operational model.

This file is intentionally narrower than the larger trip lifecycle / custody / terminal-routing note.
Its purpose is to define:

* what a Trip is
* what a Load is
* why they are not the same thing
* which one is the operational root
* which one holds commercial truth
* what belongs to Trip vs what belongs to Load
* what relationship exists between them
* what the UI/workspace implication is
* what the schema direction must respect before implementation

This is the foundation note that should guide the schema design next.

---

## 1) The old assumption that no longer works

The old mental model was effectively:

* one load
* one main page
* one dispatch flow
* one trip number
* one operational movement

That works only when one broker load maps neatly to one physical movement.

But real trucking operations break that assumption very quickly.

### Example

A single driver with one truck and one trailer may carry:

* half load from TQL
* half load from JB Hunt
* one trip number
* one real movement
* two separate broker contracts
* two separate rate confirmations
* two separate reference sets
* one shared operational execution flow

At that point, a Load can no longer be both:

* the commercial record, and
* the top-level operational execution container

That is the core reason for the redesign.

---

## 2) The foundational redesign decision

### Locked principle

**The primary operational workspace should be a Trip page, not a Load page.**

### Meaning

Trip becomes the dispatch / execution container.
Load remains the commercial / broker / customer contract record.

So the clean model is:

* **Trip = what the truck is doing**
* **Load = what the broker/customer contracted**

This is not just a UI decision.
It is a core architecture decision.

---

## 3) What a Trip is

A **Trip** is the operational execution container representing one real-world movement assignment under one trip number.

A Trip answers questions like:

* who is moving
* with what equipment
* under which trip number
* in what operational sequence
* what the driver/team is actually doing on the road

### Trip owns operational truth such as:

* trip number
* assigned driver or team
* truck
* trailer
* dispatch lifecycle / operational status
* actual trip execution flow
* trip-level timeline/events
* trip-level notes
* trip-level route/deadhead/execution summary

Trip is the thing dispatch primarily works on.

---

## 4) What a Load is

A **Load** is the commercial/broker/customer contract object.

A Load answers questions like:

* who booked it
* what freight belongs to that broker/customer contract
* what rate confirmation applies
* what references and paperwork belong to it
* how it should be billed and financially tracked

### Load owns commercial truth such as:

* broker
* broker contact
* customer/party references
* rate confirmation
* commodity / weight / temp / equipment requirements
* load-level documents
* load-level rules / alerts
* load-level financial identity
* contractual stop plan

Load is a first-class business record and must remain so.

---

## 5) Why Trip and Load must be separate

Because a single real-world movement can contain multiple commercial loads.

### Example

One truck/trailer movement may include:

* Load A from TQL
* Load B from JB Hunt
* one trip number
* one driver/team
* one truck
* one trailer
* one actual dispatch flow

But those loads still need separate:

* broker relationships
* rate confirmations
* references
* documents
* billing treatment
* commercial history

So if the system keeps Load as the top operational root, it will eventually confuse:

* dispatch logic
* stop sequence logic
* equipment assignment logic
* trip number ownership
* billing assumptions
* settlement assumptions

### Locked principle

**Trip and Load must remain separate because operational execution and commercial contract truth are not always the same container.**

---

## 6) The correct relationship between them

### High-level relationship

A Trip may contain one or more Loads.
A Load may, over its lifetime, be associated with one or more Trips until final delivery in more advanced operational scenarios.

At minimum, the system must support:

* one Trip → many Loads

### Strong recommendation

Use an explicit link model between Trip and Load.

#### Suggested concept

`trip_loads`

* id
* tenant_id
* trip_id
* load_id
* status or state within trip
* sequence/order hint if useful
* added_at
* removed_at nullable
* notes

### Why not just store trip_id on load?

Because a real explicit link model gives room for:

* reassignment
* auditing when a load entered/left a trip
* future cross-trip continuity
* trip-specific state per load
* better operational history

### Locked principle

**Use an explicit TripLoad relationship model, not a simplistic assumption that Load itself is always the container.**

---

## 7) What belongs to Trip vs what belongs to Load

This separation must stay clean.

### Trip-owned concerns

Trip should own:

* trip number
* driver/team assignment
* truck assignment
* trailer assignment
* dispatch execution state
* operational timeline
* trip-level progress
* actual execution order / operational sequence
* trip-level notes

### Load-owned concerns

Load should own:

* broker/customer identity
* rate confirmation
* references
* commercial documents
* commodity/weight/temp requirements
* load-specific rules
* billing/invoice identity
* contractual stop intent
* broker-facing paperwork

### Important design rule

Do not move commercial truth onto Trip just because the Trip is the main operational page.
Do not move dispatch execution truth onto Load just because the Load still matters.

### Locked principle

**Trip owns execution; Load owns commercial truth.**

---

## 8) UI and workspace implication

This redesign means the old “one canonical Load page as the main workspace” is no longer enough.

### Old model

Load page was doing too many jobs at once:

* commercial record
* dispatch record
* equipment assignment container
* operational timeline
* trip identity

### New model

The system should become two-layered:

#### A. Trip Workspace (primary operational root)

This is where dispatch works.
It should show:

* trip header
* driver/team
* truck/trailer
* trip status
* loads inside trip
* merged operational execution flow
* trip-level dispatch actions

#### B. Load Workspace (commercial/detail workspace)

This is where commercial truth lives.
It should show:

* broker/customer details
* rate confirmation
* references
* documents
* financials
* load-specific stop/contract detail
* load history across trips if needed

### Locked principle

**Trip page is the primary operational workspace; Load page remains the first-class commercial/detail workspace.**

---

## 9) Why a “Load page v2 with multi-load toggle” is the wrong direction

This is an important warning.

Do not take the old Load page and simply add:

* multiple load tabs
* multi-load mode
* add-another-load button
* a few trip fields at the top

That would still leave the page mentally and structurally load-first.

But the dispatcher’s real questions are now:

* which driver/team is assigned
* which truck/trailer is assigned
* what trip number is active
* which loads are on board
* what is the actual execution sequence
* what belongs to which load

Those are Trip-root questions, not Load-root questions.

### Locked principle

**Do not build a patched “Load page v2” that pretends to support trips. Build a true Trip-root operational workspace.**

---

## 10) Stop modeling warning

This document is not the full stop/custody design note, but one principle must be stated here because it directly affects Trip vs Load architecture.

### Problem

Load stops are contractual by nature.
Trip execution order is operational by nature.
Those are not always the same thing.

Example:

* Pickup Load A
* Pickup Load B
* Deliver Load A
* Deliver Load B

So execution order belongs to the Trip, while stop ownership still belongs to each Load.

### Locked principle

**Contractual stop ownership and operational execution sequencing must be kept conceptually separate.**

The later schema/workflow note should define exactly how.

---

## 11) Trip number ownership

Trip number belongs to the Trip, not the Load.

### Why

One trip number may cover:

* one driver/team
* one truck/trailer movement
* multiple loads carried together

If trip number remains load-owned, the system will create confusion as soon as one trip carries more than one load.

### Locked principle

**Trip number is Trip-owned, not Load-owned.**

Legacy convenience display fields on Load may still exist as read-model/snapshot fields if needed, but the authority should be Trip.

---

## 12) Dispatch board implication

The dispatch board should ultimately pivot from loads to trips.

### Why

Dispatchers dispatch:

* equipment
* driver/team
* operational movement
* trip number
* not just isolated commercial contracts

Loads still matter, but dispatching a real-world movement is a Trip concern.

### Locked principle

**Dispatch operates primarily on Trips, not Loads.**

---

## 13) Financial/accounting implication

This redesign does **not** mean Load stops matter financially less.
It means the system must separate two truths:

### Operational truth

* trip movement
* equipment assignment
* driver/team work
* trip execution

### Commercial truth

* broker contract
* references
* billing entity
* rate confirmation
* accessorial identity
* invoice/AR identity

This is actually a better fit for the broader TruckERP financial philosophy because:

* billing can remain load-based
* documents remain load-based
* broker records remain load-based
* dispatch execution becomes trip-based

### Locked principle

**Dispatch becomes Trip-based while billing, broker documentation, and commercial truth remain Load-based.**

---

## 14) Canonical definition block

Use this as the clean canonical wording:

### Trip

A Trip is the primary dispatch/execution container representing one real-world movement by a driver/team with assigned equipment under one trip number.

### Load

A Load is the first-class commercial/broker/customer contract record with its own references, documents, stops, and financial identity.

### Relationship

A Trip may contain one or more Loads. Dispatch operates primarily on Trips, while billing, broker documentation, and commercial truth remain Load-based.

---

## 15) What should be locked before schema work starts

Before schema implementation, the following statements should be treated as locked:

1. **Trip is the primary operational/dispatch container.**
2. **Load remains the first-class commercial contract record.**
3. **A Trip may contain one or more Loads.**
4. **Trip owns execution truth; Load owns commercial truth.**
5. **Trip page becomes the primary operational workspace.**
6. **Load page remains the commercial/detail workspace.**
7. **Trip number belongs to Trip, not Load.**
8. **Dispatch board must eventually pivot from loads to trips.**
9. **Do not build a patched “Load page v2” that pretends to support trips.**
10. **Contractual stop ownership and operational execution sequencing must be kept conceptually separate.**
11. **Use an explicit TripLoad relationship model.**
12. **Dispatch becomes Trip-based while billing and broker/commercial truth remain Load-based.**

---

## 16) What happens to `LoadWorkspacePage` after the Trip redesign

This needs to be stated clearly because a lot of valuable work already exists on the real `LoadWorkspacePage`.

The correct decision is not to delete it immediately and not to keep it as the final operational root.

### Locked principle

`LoadWorkspacePage` should be kept, but its role must change.

It should be repositioned from:

* main operational/dispatch root

to:

* load intake / verification / preparation / commercial confirmation workspace

This protects the heavy logic already built into the page while preventing the system from staying accidentally load-rooted after the Trip redesign.

---

## 17) Why `LoadWorkspacePage` should be kept

The real `LoadWorkspacePage` is not just a random old page. A lot of meaningful logic already lives there.

That logic includes things like:

* parsed field hydration
* document/PDF review
* verification against source documents
* operator correction of extracted values
* broker/load detail confirmation
* preparation of one clean load candidate from raw intake

### Why keeping it is the right move

#### A. It preserves the investment already made

A lot of real logic exists there already. Throwing it away would waste working design and implementation.

#### B. It still fits the redesigned architecture

Even in a Trip-first system, there is still a real need for a place where one load is:

* reviewed
* corrected
* verified
* normalized
* prepared before operational commitment

#### C. It creates a clean bridge from inbox to operations

The page can sit naturally between:

* `InboxIngestionPage`
* `TripWorkspacePage`

So the workflow becomes:

* inbox/intake
* load verification/preparation
* trip assignment/dispatch/save

#### D. It helps prevent premature operational commits

If parsing, verification, and operational dispatch all happen in one page, the system becomes muddy again. Keeping `LoadWorkspacePage` as a verification/preparation workspace helps keep boundaries clean.

### Better permanent meaning of the page

Do not think of it as “the old load page.” Do not reduce it to “just a parsing page.”

Its better long-term role is:

* load verification / preparation / commercial confirmation workspace

That is much more accurate.

---

## 18) What `LoadWorkspacePage` should become conceptually

### New role

`LoadWorkspacePage` should become the place where an operator:

* reviews parsed load data
* verifies extracted information against email/PDF/source text
* corrects fields
* confirms commercial/load details
* prepares one load candidate for operational use

It should become a pre-operational workspace, not the final operational container.

### Relationship to other pages

#### `InboxIngestionPage`

Owns:

* intake queue
* email threads
* attachments
* candidate routing/review queue
* duplicate review and ingestion status

#### `LoadWorkspacePage`

Owns:

* parse review
* source verification
* normalization
* commercial/load-level confirmation
* preparation of a load candidate

#### `TripWorkspacePage`

Owns:

* actual operational save/commit
* trip creation
* assignment to driver/truck/trailer
* add load to existing trip
* dispatch actions
* trip number ownership
* terminal routing / handoff / transfer logic
* final audited operational state

### Locked principle

`LoadWorkspacePage` becomes the bridge between intake and operations, while `TripWorkspacePage` becomes the true operational root.

---

## 19) What final actions should come out of `LoadWorkspacePage`

After review/verification, the operator should not be forced to fully dispatch from `LoadWorkspacePage`.

Instead the final actions should move toward trip-oriented actions such as:

* Create New Trip with This Load
* Add This Load to Existing Trip
* Save as Draft Load Only (if needed)
* Return to Inbox / Keep in Review

This preserves the page’s usefulness without leaving it as the place where operational truth is finalized.

### Example workflow

* Email arrives in `InboxIngestionPage`
* Operator opens the candidate in `LoadWorkspacePage`
* Operator verifies and corrects extracted load data
* Operator clicks one of:
  * Create New Trip with This Load
  * Add This Load to Existing Trip
* `TripWorkspacePage` becomes the place where the operational container is committed and audited

### Important boundary

`LoadWorkspacePage` may prepare data for a load. `TripWorkspacePage` should own the operational commitment of that load into live trip execution.

---

## 20) What logic should stay on `LoadWorkspacePage`

The page should continue to own logic that is load-specific, intake-specific, or verification-specific.

### Keep on `LoadWorkspacePage`

* parsed field hydration
* document/PDF/source-text review
* extraction verification
* manual correction of parsed values
* broker/contact/reference confirmation
* commodity/weight/temp/equipment confirmation
* load-specific notes derived from intake
* load document review
* one-load commercial preparation
* draft load preparation before trip assignment

### Why

All of this logic is naturally centered on preparing and confirming one load as a business/commercial object.

---

## 21) What logic should be stripped from `LoadWorkspacePage` over time

Anything that makes the page behave like the final operational root should gradually move out.

### Logic that should move to `TripWorkspacePage` / Trip container

* driver assignment
* team assignment
* truck assignment
* trailer assignment
* trip number authority/creation
* dispatch progression as operational truth
* multi-load trip composition
* add/remove/manage multiple loads in one operational movement
* trip-level execution flow
* terminal routing choices (Deliver vs Dispatch to Terminal)
* handoff/yard/transfer operational actions
* final operational save/commit and audit root

### Why

These things are no longer properties of one isolated load page. They are properties of the Trip as the operational container.

### Locked principle

Any logic that answers “what is this truck/driver/trailer doing operationally right now?” belongs to `TripWorkspacePage`, not `LoadWorkspacePage`.

---

## 22) What should not happen

The system should not follow either of these bad patterns:

### Bad pattern A — Delete `LoadWorkspacePage` immediately

This would waste valuable verification/preparation logic and force too much complexity directly into Trip workspace too early.

### Bad pattern B — Keep `LoadWorkspacePage` as the final dispatch root

This would preserve the old load-centric architecture under a new name and cause confusion later.

### Locked principle

Do not delete `LoadWorkspacePage` now, and do not let it remain the final dispatch root. Reposition it.

---

## 23) Migration strategy for the page

### Phase 1

Keep `LoadWorkspacePage` alive and useful. Do not break existing verification/parsing/preparation logic.

### Phase 2

Introduce `TripWorkspacePage` as the new operational/dispatch root.

### Phase 3

Change the final actions of `LoadWorkspacePage` so they point into Trip actions rather than trying to fully dispatch there.

### Phase 4

Gradually strip dispatch-root logic from `LoadWorkspacePage` and keep it focused on:

* intake
* verification
* preparation
* commercial confirmation

### Phase 5

Later, the product/UI naming can be simplified if desired, for example:

* Load Verification
* Review Load
* Prepare Load

Internal route/component naming can remain stable until a safer refactor window.

---

## 24) Product wording recommendation

To reduce user confusion, the business meaning of the page should eventually be described more clearly.

Instead of thinking of it as:

* the final load dispatch page
* the main operational workspace

Think of it as:

* load verification workspace
* load preparation workspace
* load commercial confirmation workspace

This wording better matches the redesigned architecture.

---

## 25) Final locked principles for `LoadWorkspacePage` after redesign

1. `LoadWorkspacePage` should be kept.
2. Its role must change from operational root to verification/preparation workspace.
3. It should sit between `InboxIngestionPage` and `TripWorkspacePage`.
4. It should continue to own parsing, verification, correction, and load-level commercial confirmation logic.
5. It should stop being the place where live trip operations are ultimately committed.
6. Driver/truck/trailer/trip-number/dispatch-root logic must move to `TripWorkspacePage`.
7. Its final actions should become trip-oriented actions such as Create New Trip or Add to Existing Trip.
8. Do not delete the page now, and do not let it remain the final dispatch root.

---

## 26) Next document after this one

This note is intentionally architectural and conceptual.

The next design note should be strictly technical and should define:

* core schema direction for `trips`, `trip_loads`, `loads`, and stop relationships
* which existing Load fields move or stop being authoritative
* which Trip fields are required in V1
* exact Trip page sections/actions
* exact dispatch board migration approach
* exact trip number lifecycle and creation rule

That next note should be the schema-facing implementation contract.

