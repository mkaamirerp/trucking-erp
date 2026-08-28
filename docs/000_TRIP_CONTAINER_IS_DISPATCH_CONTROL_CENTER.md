# 000 — Trip Container Is the Dispatch Control Center

**Locked identity (no split):** **Trip page = Trip Container = Dispatch Control Center.** One operational surface; vocabulary and URL may vary, but these are **not** separate products or competing pages.

**Status:** Critical pause / restart document  
**Purpose:** Lock the product/UI direction before any more Trip / Load UI work.  
**Do not treat this as implementation.** This is the decision boundary and next-discussion starting point.

---

## 1. Why this document exists

We stopped here because the product direction was at risk of drifting again.

TruckERP already went through this pattern before:

- **Load Lab** started as a useful test/reference surface, then became confusing because temporary logic and product runtime boundaries blurred.
- **Email Intake** had a similar issue where provider/broker-specific logic leaked into architecture.
- The same danger now exists with **DeprecatedDispatchPage** (legacy load-status board), **TripWorkspacePage**, and **LoadWorkspacePage**.

**DeprecatedDispatchPage** looks visually good, but its hidden logic is old load-status logic. The **Trip page** (`TripWorkspacePage`) may look weaker visually today, but it **is** the Trip Container **and** the Dispatch Control Center — the correct operational home.

The lesson:

> Do not choose the page foundation based on how nice the UI looks today. Choose it based on where the correct business truth lives.

---

## 2. Corrected locked direction

### Trip page = Trip Container = Dispatch Control Center

**TripWorkspacePage** at **`/trips/:id`** is the active Dispatch Control Center today — same scope as Trip Container. There is **no** separate, primary “Dispatch page” besides this; **`DeprecatedDispatchPage`** is legacy **`Load.status`** board only (see §3).

Backend/domain language may continue to say:

- `Trip`
- `TripLoad`
- `Trip.status`
- Trip execution signal
- Trip assignment

Frontend/operator language may say **Dispatch**, **dispatch command center**, **dispatch trip**, **active / assigned / in-progress trip** — these labels refer to **this same Trip page / Trip Container surface**, not a different product. Operator language must remain **Trip-backed** (same center), never **`Load.status`**-board-backed (**DeprecatedDispatchPage**).

---

## 3. Page ownership

### Trip page (= Trip Container = Dispatch Control Center)

This is the real operational home (today: **`TripWorkspacePage`** / **`/trips/:id`**).

It owns or will own:

- planned trips
- assigned trips
- in-progress trips
- trip number
- driver / truck / trailer assignment
- member loads
- Start Execution
- future completion
- future exceptions / recovery / repower
- future custody / terminal / handoff
- future dispatch package / send-to-driver flow
- future operational timeline

### LoadWorkspace / Load page (directory + commercial detail)

This remains the **load directory** and **commercial / readiness / document** workspace — not the execution control center.

It owns:

- broker / carrier / customer commercial truth
- rate / gross amount / financial load identity
- broker load reference and other refs
- pickup / delivery contractual stops
- PDF/intake verification
- documents
- Save Draft
- Save Ready
- load directory / search / detail
- create or attach to Trip Container

It must **not** become the execution control center.

### Old Dispatch board (`DeprecatedDispatchPage`)

The existing **DeprecatedDispatchPage** is visually useful but logically legacy (old load-status board).

It currently behaves like:

- load cards
- grouped by `Load.status`
- `unassigned`
- `assigned`
- `dispatched`
- `arrived_pickup`
- `in_transit`
- `arrived_delivery`
- `delivered`
- `issue_hold`

That is old load-status dispatch logic.

**DeprecatedDispatchPage** should be treated as:

- visual reference
- salvage source
- legacy compatibility surface until replaced

It should **not** receive new operational business logic unless explicitly approved.

---

## 4. Current reality discovered on main

From code inspection:

### Old Dispatch backend

`GET /api/v1/dispatch/board` returns loads grouped by dispatch status.

The router uses `LoadResponse` and `loads_service.list_loads_for_board(...)`.

### Old Dispatch service

`list_loads_for_board()` reads `Load` rows, excludes `draft`, and groups by `Load.status`.

This means the board is still load-centric.

### Old Dispatch frontend

`DeprecatedDispatchPage.tsx` uses:

- `getDispatchBoard`
- `DispatchBoard`
- `LoadCard`
- `load.status`
- `load.driver`
- `load.truck`
- `load.trailer`
- `load.trip_number`

It is visually strong but logically old.

### Current Trip logic

Trip logic is where the new operational model is being built:

- `Trip`
- `TripLoad`
- planned trip creation
- add/remove member load
- cancel trip
- assignment driver/truck/trailer
- assigned → in_progress execution signal

This is the correct foundation.

---

## 5. What must not happen

Do **not** move all TripWorkspace logic into **DeprecatedDispatchPage**.

Do **not** build new business logic on top of old `Load.status` lanes.

Do **not** revive:

- `Load.status = dispatched` as new execution trigger
- `dispatch_trips` writes from new Trip execution flow
- load-status board as the new operational truth

Do **not** copy **DeprecatedDispatchPage** logic into TripWorkspace.

Do **not** copy TripWorkspace wholesale into **DeprecatedDispatchPage**.

Instead:

> Evolve **one** surface — **Trip page = Trip Container = Dispatch Control Center** — while salvaging useful **visual** patterns only from **DeprecatedDispatchPage** (no second “dispatch product”).

---

## 6. What can be salvaged from DeprecatedDispatchPage

The legacy dispatch page is useful visually.

Potential salvage:

- driver rail idea
- dense card layout
- board columns
- ribbon/tabs
- route display
- mileage/rate display style
- card badge treatment
- scroll behavior
- operator-friendly density
- "open detail" interaction pattern

Do not blindly salvage:

- `Load.status` lanes
- `dispatched` as execution truth
- `arrived_pickup`, `in_transit`, `arrived_delivery` as Load-status board truth
- driver availability derived from load statuses
- `/dispatch/board` as final read model
- old assignment-through-load behavior

---

## 7. Current uncommitted / parked Decision 7 state

Decision 7 execution-signal slice has been implemented and runtime-proven, but not committed.

Pending code slice files:

```text
app/constants/trip_dispatch.py
app/routers/trips.py
app/schemas/trip_read.py
app/services/trips.py
tests/test_trip_execution_signal_slice7.py
```

Frontend wiring files:

```text
apps/web/src/api.ts
apps/web/src/pages/TripWorkspacePage.tsx
```

Separate pending non-feature item:

```text
.cursor/rules/documentation-decision-tracker-discipline.mdc
```

Runtime proof showed:

- assigned trip moved to `in_progress`
- `Load.status` unchanged
- `dispatch_trips` count unchanged
- `audit_events` wrote one `trip_execution_started`
- repeat signal was idempotent
- frontend bundle had Start Execution button and warning copy

Operational issue found and fixed during proof:

- disk was 100% full
- Postgres could not insert audit row
- Docker pruning restored disk space
- after that, proof passed

---

## 8. Correct architecture statement

Use this wording going forward:

> **Trip page = Trip Container = Dispatch Control Center** (one operational surface).  
> Load workspace is load directory + commercial/readiness/document truth.  
> Trip (API/domain) is operational execution truth; TripLoad is membership truth.  
> **DeprecatedDispatchPage** is deprecated legacy **`Load.status`** board and visual salvage only — **not** an active Dispatch Control Center.

---

## 9. Proposed phased path

### Phase 0 — Pause and document

- Create this critical MD file.
- Create a Cursor rule to prevent coding in the wrong page.
- Stop accidental **DeprecatedDispatchPage** business logic.

### Phase 1 — Deep audit of DeprecatedDispatchPage

Report only.

Classify every part of **DeprecatedDispatchPage** as:

- visual salvage
- legacy load-status logic
- business logic worth preserving
- delete/retire later
- unknown / needs owner decision

### Phase 2 — Trip page / Dispatch Control Center wireframe

Before coding, define IA and layout for **the Trip page** (same surface as Trip Container and Dispatch Control Center).

Basic possible wireframe:

```text
Trip page = Trip Container = Dispatch Control Center

Top header:
- Trip number
- Trip status
- driver / truck / trailer
- primary actions

Left rail:
- drivers / equipment / available resources

Center:
- member loads
- route sequence
- execution status
- timeline

Right rail:
- selected load details
- documents
- notes
- audit/history
- exceptions

Tabs or sections:
- Loads
- Assignment
- Execution
- History
- Documents
- Exceptions
```

### Phase 3 — Rebrand / reroute carefully

Do not rush route changes. **`/trips/:id`** is the Dispatch Control Center today; any later **`/dispatch...`** paths would be **aliases or preferred URLs for the same Trip-backed surface** — not a separate app or competing “dispatch product.”

### Phase 4 — Retire DeprecatedDispatchPage

Only after the **Trip page / Dispatch Control Center** is stable at the desired maturity:

- hide **DeprecatedDispatchPage** / remove `/dispatch` legacy route when replaced
- rename old file to legacy if needed
- delete old load-status board logic
- keep migration notes and tests

---

## 10. Required next step

Before any more frontend coding:

### Create Cursor rule

Recommended file:

```text
.cursor/rules/trip-container-dispatch-boundary.mdc
```

Rule should say:

```text
# Trip page / Trip Container / Dispatch Control Center — boundary

Locked identity: Trip page = Trip Container = Dispatch Control Center (one surface). No separate active DispatchPage; legacy board is DeprecatedDispatchPage only.

Definitions:
- Load workspace = load directory + commercial/readiness/document truth.
- Trip (API/domain) = operational execution truth; TripLoad = membership truth.
- Trip page = Trip Container = Dispatch Control Center (TripWorkspacePage today).
- DeprecatedDispatchPage = deprecated legacy Load.status board and visual reference only.

Rules:
1. Do not add new operational business logic to **DeprecatedDispatchPage** unless explicitly approved.
2. Do not build new workflows on Load.status execution values.
3. Do not reintroduce Load.status = dispatched as a new trigger.
4. Do not write dispatch_trips from new Trip execution flows.
5. Do not move TripWorkspace logic wholesale into **DeprecatedDispatchPage**.
6. Do not copy **DeprecatedDispatchPage** logic into TripWorkspace.
7. Use **DeprecatedDispatchPage** only for visual salvage unless explicitly approved.
8. LoadWorkspace remains load directory + commercial/readiness/document workspace.
9. Do not describe Trip Container and Dispatch Control Center as separate products or pages.
10. Before touching Trip / Load / legacy-board UI, report whether the change is:
    - visual salvage
    - Trip read-model integration
    - operational mutation
    - legacy cleanup
11. Do not mix parser/email-intake/dependency cleanup with Trip page / legacy-board UI work.
12. No custody, terminal, payroll, package/send, or completion logic unless explicitly scoped.
```

---

## 11. Cursor instruction for next time

Use this as the next prompt:

```text
Stop coding and preserve the current direction.

We are locking this decision:

Trip page = Trip Container = Dispatch Control Center (one surface). Frontend/operator may say Dispatch; backend/domain may say Trip — same center, not a separate product.
There is no separate active DispatchPage; legacy board is DeprecatedDispatchPage (Load.status only).
LoadWorkspace is load directory + commercial/readiness/document workspace.

Do not add new business logic to DeprecatedDispatchPage.
Do not move TripWorkspace logic into DeprecatedDispatchPage.
Do not revive Load.status=dispatched.
Do not write dispatch_trips from new Trip flows.
Do not touch parser/email-intake.
Do not touch dependency cleanup.
No commit.
No push.

Task:
1. Create/update docs/000_TRIP_CONTAINER_IS_DISPATCH_CONTROL_CENTER.md.
2. Create/update .cursor/rules/trip-container-dispatch-boundary.mdc.
3. Do not touch app logic or frontend pages.
4. Report changed files only.
```

---

## 12. Open decisions for owner discussion

Before further Trip page / Dispatch Control Center work, decide:

1. Should **`/dispatch`** (or similar) become a URL alias to the same Trip-backed surface while **DeprecatedDispatchPage** is retired?
2. Does **`/trips/:id`** remain the canonical route, with optional friendlier aliases only?
3. Should the Trip page show one trip at a time, or a board of trips plus selected detail?
4. How much of **DeprecatedDispatchPage** visual layout should be reused on **that same Trip page**?
5. Should ready loads appear inside the Trip page, or remain in the Load list/planning queue?
6. How should drivers/equipment be shown without relying on old Load.status board logic?
7. Should completion be delayed until the UI ownership is locked?
8. When do we formally deprecate `/dispatch/board`?

---

## 13. Final locked takeaway

Do not build the future on the old page just because it looks good.

Build on the **Trip page (= Trip Container = Dispatch Control Center)** because operational truth lives there; polish and operator language (“Dispatch”) apply to **that same surface**.

```text
Trip page = Trip Container = Dispatch Control Center (one surface, evolve in place).
DeprecatedDispatchPage retired when replaced.
```
