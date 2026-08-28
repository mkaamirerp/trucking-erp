# 001 — Trip Container Accordion Wireframe (Dispatch Control Center)

**Status:** Design / wireframe (not implementation).  
**Purpose:** Define the first **Trip Container = Dispatch Control Center** UI structure: lifecycle filters + accordion drill-down, grounded in current APIs and explicit gaps.

**Related:** `docs/000_TRIP_CONTAINER_IS_DISPATCH_CONTROL_CENTER.md` (product lock), `.cursor/rules/trip-container-dispatch-boundary.mdc`.

---

## 1. Product identity

- **Trip Container = Dispatch Control Center.** One operational page / world — not a separate “dispatch product” or competing surface.
- **Trip page** (e.g. `TripWorkspacePage` at `/trips/:id`) is the canonical home for this world today; future URL aliases (`/dispatch…`) are **the same center**, not a fork.
- **Load workspace** remains **load directory + commercial / readiness / document** work; it is **not** the execution control center.
- **DeprecatedDispatchPage** is **legacy `Load.status` board only** — see §12; it is **not** a data or logic foundation for this wireframe.

---

## 2. Product boundary (comparison)

| | **Trip Container** (Dispatch Control Center) | **Load Workspace** | **DeprecatedDispatchPage** |
|---|---------------------------------------------|----------------------|----------------------------|
| **Primary object** | **Trip** (container + `TripLoad` memberships) | **Load** (commercial record) | **Load** (rows on a board) |
| **Purpose** | Operational control: assignment, execution signals, member loads, future custody/terminal/history/package/payroll signals | Load directory, commercial truth, readiness/documents, deep edit | Legacy **visual** reference for density/layout only; **not** a control plane |
| **Allowed writes** | Trip-scoped APIs only (e.g. assignment, add/remove member load, cancel planned trip, execution signal — see §9) | Load-scoped saves (commercial fields, draft/ready, documents, notes, etc.) | **No new operational writes** for Trip Container; board is read-only for dispatch control evolution |
| **Lifecycle source** | **`Trip.status`** and **trip_loads** / trip APIs | **`Load.status`** and load APIs for **commercial/readiness**, not trip execution authority | **`Load.status`** lanes — **invalid** as lifecycle source for Trip Container |
| **What it must not do** | Must not replace Load Workspace for broker/docs/long-form commercial work; must not use legacy board logic (§12) | Must not become the execution control center or own trip lifecycle; must not drive operator dispatch lanes off `Load.status` alone | Must not supply **state model, write model, lane model, lifecycle logic, metrics, or derived driver/load status** to Trip Container (§12) |

---

## 3. Lifecycle filters (stage bar)

The **top stage / filter bar** drives which trips appear in the list below. Filter semantics:

| Filter | Definition |
|--------|------------|
| **Active** | **`planned` + `assigned` + `in_progress`** — union of trips where `Trip.status` is any of these three and the trip is operationally open (e.g. not `completed`, not `cancelled` per product rules). **Implementation note:** backend `listTrips` today filters by **exact** `status`; **Active** may require **multiple requests merged**, **client-side filter** after a broader fetch, or a **future** API parameter — wireframe does not prescribe implementation. |
| **Planned** | `Trip.status === "planned"` |
| **Assigned** | `Trip.status === "assigned"` |
| **In Progress** | `Trip.status === "in_progress"` |
| **Completed** | `Trip.status === "completed"` |
| **Problem / Hold** | **Future placeholder only — not implemented.** No trip-level filter or API exists in v1; there is **no** `Trip.status` value for this today. Do not imply `Load.status = issue_hold` lanes, DeprecatedDispatchPage grouping, or any shipped “Problem / Hold” trip filtering until explicitly designed and built. |

Constants alignment: `app/constants/trip_dispatch.py` — `TRIP_CONTAINER_STATUS_*` (`planned`, `assigned`, `in_progress`, `completed`, `cancelled`). **`cancelled`** trips are typically excluded from **Active**; exact inclusion/exclusion for cancelled rows in list views is a product detail when implementing.

---

## 4. Accordion hierarchy

Three levels of drill-down (visual / IA contract):

```text
Trip Container bar          ← stage list: one row per trip
  └─ Load bar               ← one row per member load (active trip_loads)
       └─ Stop bar          ← one row per load stop (from Load payload)
```

- **Expand/collapse** at each level; expanding a trip reveals its **member load bars**; expanding a load reveals **stop bars** and load body sections (see §9).
- **Navigation:** deep links to full **Load Workspace** remain available from expanded load (§9).

### 4.1 No drawer

The Trip Container **must** use **vertical accordion drill-down**, **not** a right-hand drawer.

**Reason:** The future operational surface will include assignment, driver/truck/trailer, execution, member loads, stops, terminal/custody, exceptions, history, documents, driver package, and future payroll/settlement signals. A drawer will **become cramped** and will **recreate preview-board behavior** instead of a **real control center**. Accordion keeps hierarchy visible, supports deep context without hiding the trip list, and scales with many sections without fighting fixed drawer width.

---

## 5. Collapsed Trip bar (fields)

Each **collapsed** row in the trip list shows:

| Field | Source (today) |
|--------|-----------------|
| **trip_number** | `TripListItem.trip_number` / `TripDetail.trip_number` |
| **status** | `TripListItem.status` |
| **driver** | Nested `driver` (name) or `driver_id` display fallback |
| **truck** | `truck.unit_number` or id fallback |
| **trailer** | `trailer.unit_number` (+ optional type) or id fallback |
| **route summary** | **`TripListItem.first_member?.stop_route_summary`** — **first member load** route only; not a true merged multi-load route (see §10). |
| **member load count** | `TripListItem.member_load_count` |
| **allowed primary action** | Contextual CTA mirroring trip rules: e.g. **Start execution** when `status === "assigned"` and rules allow; **Cancel trip** when planned and open; **Open** / expand for detail — exact buttons are implementation detail; **rules** must match existing trip APIs (§9). |

---

## 6. Expanded Trip section

When a **Trip Container** row expands:

1. **Trip actions** — Operations already supported by trip APIs: cancel (planned), add/remove member loads (when membership open), post **execution signal** (when assigned and allowed), etc.
2. **Assignment summary** — Driver / truck / trailer summary + `assigned_at`; editable assignment when product rules allow (same as current trip workspace gates).
3. **Member load bars** — One **collapsed load bar** per active member (§7); user expands individual loads.
4. **Recent history** — **Placeholder only** in v1: “Trip timeline / audit — future.” No requirement to invent UI data; **trip history API** is deferred (§10).

---

## 7. Collapsed Load bar (fields)

Each **member load** row under an expanded trip:

| Field | Source (today) |
|--------|-----------------|
| **broker** | `TripMemberLoad` / summary: `broker_name_snapshot` |
| **broker load reference** | `broker_load_reference` |
| **route** | `stop_route_summary` (may be empty) |
| **rate** | `rate` (and optionally `customer_rate` in expanded section) |
| **stop count** | **If available** — not on `TripMemberLoad` today; supply via **`getLoad`** on expand / prefetch, or defer display until load expanded (§10). |
| **document / review status** | **If available** — not on member summary; from **`getLoad`** (`Load` / `LoadResponse` fields such as `review_required` and document-related flags per codebase). |

---

## 8. Expanded Load section

When a **Load** row expands:

- **Broker / ref details** — Full snapshot + related broker/contact fields from **`getLoad`**.
- **Load actions** — Trip-scoped actions (e.g. remove from trip when allowed) + **link to full Load Workspace** for commercial/edit flows (Save Ready, documents, etc.).
- **Stop bars** — Collapsed **stop bars** per `load.stops`; expand to §9.
- **Documents** — As supported by load workspace / load APIs (embed vs link is implementation).
- **Notes** — e.g. `internal_notes`, load notes API if applicable.
- **Link to full Load Workspace** — Canonical deep work: `/loads/:id` (or equivalent `OPS.LOAD_DETAIL`).

---

## 9. Expanded Stop section

When a **Stop** row expands (data from **`getLoad` → `stops[]`**):

- **Facility** — `facility_name` (and related display fields).
- **Address** — Street, city, state/province, postal, country as available on stop model.
- **Appointment** — `appointment_date`, `appointment_time_text`, `appointment_type` as available.
- **Reference** — `reference_number` (and any stop-level ref fields in schema).
- **Notes** — Stop `notes` / related text fields.

**Note:** Stop-level “contact” is not required in this wireframe v1; add only if schema supports without stretching.

---

## 9. Supported today (APIs / patterns)

These exist and align the wireframe to **current** backend + frontend patterns (no DeprecatedDispatchPage):

- **`listTrips`** — Pagination, `search`, **exact** `status` filter (`planned`, `assigned`, `in_progress`, `completed`, `cancelled`).
- **`getTrip`** — Full `TripDetail` including `member_loads`, assignment, cancellation fields, execution-related state after signals.
- **`TripListItem`** — Trip directory row: `trip_number`, `status`, equipment, `member_load_count`, `first_member` (route summary snippet).
- **`TripDetail.member_loads`** — Active and historical memberships for load bars and “previously on trip.”
- **`getLoad`** — On load expand: stops, notes, review/document signals, commercial fields.
- **Add / remove load** — `addLoadToTrip`, `removeLoadFromTrip` (membership), with existing error codes.
- **Cancel trip** — `cancelTrip` (planned container).
- **Update assignment** — `updateTripAssignment` (driver / truck / trailer).
- **Execution signal** — `postTripExecutionSignal` (e.g. start execution from assigned when allowed).

---

## 10. Missing / deferred (explicit)

Not blocking wireframe **definition**, but **not** represented as shipped product truth without further work:

| Item | Notes |
|------|--------|
| **True multi-load trip route** | List uses **first member** route summary only; merged trip route is undefined in API. |
| **True trip-level stop count** | Not on `TripListItem` / `TripDetail`; aggregate from loads or new read-model. |
| **Problem / Hold** | **Not implemented** — UI filter placeholder only until a **trip-level** (or explicitly scoped) model and API exist; no behavior to ship under this label in v1. |
| **Trip history API** | Audit / execution timeline for “recent history” — placeholder until API + UX spec. |
| **Custody / terminal** | Out of scope for accordion v1. |
| **Stop execution** | Operational execution per stop — deferred. |
| **Completion** | Trip completion UX/API beyond current slices — deferred. |
| **Driver package** | Send-to-driver / package flows — deferred. |
| **Payroll** | Explicitly out of scope. |
| **Load custody state** | Distinct from **`Trip.status`** and from high-level **load lifecycle**; not modeled in accordion v1 — see §11. |
| **Terminal / yard custody** | Terminal/yard as real stop/event + custody holder — deferred; see §11. |
| **Handoff workflow** | Driver-initiated vs dispatcher/receiver confirmation; audited transfer — deferred; see §11. |
| **Trailer-to-trailer transfer event** | Audited event (from/to trailer, time, actor, loads, custody) — deferred; see §11. |
| **Load continuity across multiple trips** | Same **Load** across trip memberships; UI must not assume one-trip-only commercial identity — see §11. |
| **Trip stop model with multiple load actions** | Physical stop may fan out to many load/custody actions — future; v1 uses `load.stops` via `getLoad` only; see §11. |
| **Partial delivery / rejection / return-to-yard / reassignment event handling** | Operational sub-events vs simple lifecycle — deferred; see §11. |

---

## 11. Future Architecture Guardrails — Must Not Be Designed Against

**This section does not assert that these features exist today.** It records **final architecture decisions** so the **first accordion UI** is not shaped in a way that **blocks** a future **custody-aware, terminal-aware, multi-trip continuity** platform.

1. **Three separate state machines** — **Trip status**, **Load custody**, and **Load lifecycle** are related but **never the same field**. Do not collapse them in UI or API assumptions.

2. **Load persists across trips** — A **Load** is continuous **commercial / operational** truth. A **Trip** is a **temporary execution container**. A **Load does not end when a Trip ends.**

3. **Terminal / yard is real** — Terminal/yard is **not** “just a note.” It can be a **real stop/event**, can **receive custody**, and **dispatch-to-terminal** is a **real future decision point.**

4. **Handoff is audited** — A driver may **initiate/request** handoff; **dispatcher or receiving party must confirm**. **No silent custody transfer.**

5. **Custody is not driver-only** — Future custody holder types must include at least: **driver**; **terminal / yard**; **trailer at yard**; **facility**; **customs hold**; **unknown / disputed**.

6. **Future stop model must evolve beyond pickup/delivery** — Operational stop/event types may include: **pickup**; **delivery**; **terminal arrival**; **yard arrival**; **relay**; **trailer drop**; **trailer pickup**; **trailer-to-trailer transfer**; **handoff**; **hold**.

7. **One physical trip stop can serve multiple load actions** — The current accordion uses **Trip → Load → Stop** because **supported data today** is **`load.stops`** via **`getLoad`**. Future architecture **must not** assume each physical stop belongs to only one load. Target: **Trip stop = physical event/location**; **under that stop = one or more load actions and custody actions.**

8. **Trailer-to-trailer transfer is audited** — A future transfer event must capture: **from trailer**; **to trailer**; **date/time**; **actor**; **loads affected**; **custody impact**.

9. **Load lifecycle stays simple** — Do **not** overload lifecycle with every operational exception. High-level load lifecycle remains: **Draft → Ready → Assigned → Dispatched → In Transit → Delivered → Closed**. Operational events / sub-statuses handle: **split load**; **partial delivery**; **rejected delivery**; **return to yard**; **reassignment**; **terminal hold**; **custody dispute** (and similar).

10. **Reassignment does not create a new load** — If freight continues on **another trip**, the **same Load** continues; **only trip execution** changes. **Do not** create a second commercial load solely because operational responsibility moved to another trip.

---

## 12. Must never use (for this design)

The Trip Container / Dispatch Control Center **must not** depend on:

- **DeprecatedDispatchPage** — **Visual inspiration only** (density, spacing, accordion rhythm, card chrome). It **must not** provide **state model, write model, lane model, lifecycle logic, metrics, or derived driver/load status logic** to Trip Container.
- **`getDispatchBoard`** / **`GET /api/v1/dispatch/board`**.
- **`Load.status` lanes** as the **organizing model** for this operational view.
- **`Load.status = dispatched`** as an **execution trigger** for new trip flow (locked elsewhere).
- **`dispatch_trips` writes** originating from **new Trip** flows (locked elsewhere).
- **Fake metrics** (e.g. **`uiDeadMiles`**-style placeholders) presented as operational truth.
- **`deriveDriverStatuses`** (or any equivalent) — **derived “availability” or on-load state from load-status board buckets** — **forbidden** for Trip Container.
- **`ON_LOAD_STATUSES`** (or any fixed set of **`Load.status`** values used to infer driver/trip operational state) — **forbidden** as logic input for this design.

Pure **visual** patterns from DeprecatedDispatchPage (e.g. pill density, column spacing) are allowed **only** when they do **not** import the legacy board’s **data model or semantics**.

---

## 13. First implementation slice guidance

Exact direction for the first build slice (when implementation is approved):

- Create **Trip Container** page from **trip APIs** (not from `getDispatchBoard`).
- **Lifecycle filters** based on **`Trip.status`** (including **Active** as union of `planned` + `assigned` + `in_progress` per §3).
- Render **trip accordion rows** (collapsed trip bar per §5).
- **Expand trip** to show **`member_loads`** from **`getTrip`**.
- **Expand load** by calling **`getLoad`**.
- Show **nested stops read-only** from `getLoad` payload.
- Add **“Open in Load Workspace”** for deep commercial/document work.
- Keep **execution / custody / history / package / payroll** as **placeholders** until respective APIs and scope land.
- **Do not** implement **old dispatch board logic** (lanes, board refresh model, load-status execution, DeprecatedDispatchPage data paths).

---

## 14. Summary checklist

- [ ] One world: **Trip Container = Dispatch Control Center**.  
- [ ] **Product boundary** understood (§2); **no drawer** (§4.1).  
- [ ] Lifecycle bar: **Active** = planned ∪ assigned ∪ in_progress; **Problem/Hold** = **placeholder only, not implemented**.  
- [ ] Accordion: **Trip → Load → Stop**.  
- [ ] Collapsed/expanded fields per §5–§9.  
- [ ] Build on §9; acknowledge §10; **guardrails §11**; forbid §12; first slice per §13.
