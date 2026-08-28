# 001 — Trip Container Accordion Wireframe (Dispatch Control Center)

**Status:** **DESIGN CONTRACT + FIRST UI IMPLEMENTATION SLICE SHIPPED**  
**Purpose:** Define the **Trip Container = Dispatch Control Center** list/accordion information architecture and record what the current `TripContainerPage` already implements versus what remains future.  
**Current route:** `/trips/container` → `TripContainerPage`. Detailed Trip work still also exists at `/trips/:id` → `TripWorkspacePage`; `/dispatch` remains the legacy `DeprecatedDispatchPage` during migration.

**Related:** `000_TRIP_CONTAINER_IS_DISPATCH_CONTROL_CENTER.md` (product lock), `TRIP_EXECUTION_CUSTODY_MASTER_INDEX.md` (shipped backend state), `.cursor/rules/trip-container-dispatch-boundary.mdc`.

---

## 1. Product identity

- **Trip Container = Dispatch Control Center.** One operational product world — not a separate “dispatch product.”
- The code is currently in a **route-transition state**: `TripContainerPage` provides the new Trip-backed control-center slice, while `TripWorkspacePage` remains the detailed Trip workspace.
- **Load Workspace** remains load directory + commercial/readiness/document work; it is not the execution control center.
- **DeprecatedDispatchPage** is the legacy `Load.status` board; it is not a data/state foundation for this design.

---

## 2. Product boundary

| | **Trip Container / Dispatch Control Center** | **Load Workspace** | **DeprecatedDispatchPage** |
|---|---|---|---|
| **Primary object** | **Trip** + `TripLoad` memberships | **Load** commercial/readiness record | **Load** rows on legacy status board |
| **Purpose** | Operational control: assignment, execution, member loads, Trip lifecycle; progressively surface custody/history/package/etc. | Commercial truth, readiness, documents, deep edit | Legacy compatibility / visual reference |
| **Allowed writes** | Trip-scoped APIs only | Load-scoped commercial/readiness/document writes | No new Trip-control business logic |
| **Lifecycle source** | `Trip.status` + Trip/TripLoad APIs | `Load.status` for Load commercial/readiness compatibility | Legacy `Load.status` lanes only |
| **Must not do** | Must not depend on legacy board state model | Must not become Trip execution state machine | Must not provide state/write/lifecycle logic to Trip Container |

---

## 3. Lifecycle filters (stage bar)

The top stage/filter bar organizes Trips, not Loads.

| Filter | Definition |
|---|---|
| **Active** | `planned` + `assigned` + `in_progress` operationally open Trips. Current UI may merge/filter client-side because backend status filtering is exact. |
| **Planned** | `Trip.status === "planned"` |
| **Assigned** | `Trip.status === "assigned"` |
| **In Progress** | `Trip.status === "in_progress"` |
| **Completed** | `Trip.status === "completed"` |
| **Problem / Hold** | Placeholder only. No dedicated Trip status/API exists for this label yet. Do not substitute legacy `Load.status = issue_hold`. |

Trip lifecycle constants are `planned`, `assigned`, `in_progress`, `completed`, `cancelled`.

---

## 4. Accordion hierarchy

The design contract is:

```text
Trip row
  └─ Load row(s)
       └─ Stop row(s)
```

- Expanding a Trip reveals member Loads.
- Expanding a Load reveals its Load data/stops.
- Deep commercial/document edits continue in Load Workspace.

### 4.1 No drawer

The control center uses vertical drill-down rather than a narrow right-hand drawer as its primary hierarchy. This preserves operational context as assignment, execution, member loads, custody, history, documents, package, and exceptions grow.

---

## 5. Collapsed Trip row

Current/read-model fields include:

| Field | Source |
|---|---|
| `trip_number` | `TripListItem.trip_number` |
| `status` | `TripListItem.status` |
| driver | nested driver / `driver_id` fallback |
| truck | nested truck / id fallback |
| trailer | nested trailer / id fallback |
| route summary | `first_member?.stop_route_summary` — first-member hint, not a merged multi-load route |
| member load count | `member_load_count` |
| contextual action | Trip-state-dependent action such as Start execution / open / cancel where allowed |

---

## 6. Expanded Trip section

The first implementation slice already uses Trip APIs for core operational actions such as:

- planned Trip creation
- assignment update
- add/remove member Load where allowed
- cancel planned Trip
- execution signal / Start Trip

Expanded Trip UI also owns:

- assignment summary
- member Load rows
- future richer history/timeline integration

Backend completion and custody slices exist elsewhere in the codebase, but the accordion UI does not need to pretend those controls are present until explicitly wired into `TripContainerPage`.

---

## 7. Collapsed Load row

Each member Load row may show:

| Field | Source |
|---|---|
| broker | member-load snapshot / Load detail |
| broker load reference | `broker_load_reference` |
| route | `stop_route_summary` |
| rate | `rate` / optional customer rate where appropriate |
| stop count | from `getLoad` when available |
| document/review status | from Load detail/read model when available |

---

## 8. Expanded Load section

When a Load expands:

- broker/ref details come from `getLoad`
- Trip-scoped membership actions remain Trip actions
- contractual stops come from Load detail
- notes/documents may be shown as supported
- deep commercial editing links to `/loads/:id`

Trip Container must not duplicate the entire Load Workspace form.

---

## 9. Expanded Stop section

From `getLoad → stops[]`, show available:

- facility
- address
- appointment date/time/type
- reference
- notes

Stop-level contact is not required unless the schema/product slice explicitly supports it.

---

## 10. Supported today

Current APIs/patterns that support the control-center design include:

- `listTrips`
- `getTrip`
- `TripListItem`
- `TripDetail.member_loads`
- `getLoad`
- `addLoadToTrip`
- `removeLoadFromTrip`
- `cancelTrip`
- `updateTripAssignment`
- `postTripExecutionSignal`

Other backend Trip/custody capabilities exist outside the first accordion UI slice; use `TRIP_EXECUTION_CUSTODY_MASTER_INDEX.md` for shipped backend truth.

---

## 11. Missing / deferred in the accordion UI

These are not necessarily absent from all backend code; they are not yet complete control-center UI capabilities unless explicitly wired.

| Item | Current accordion status |
|---|---|
| **True multi-load trip route** | First-member route hint only; merged route model still undefined. |
| **True trip-level stop count** | No dedicated Trip-level aggregate read model. |
| **Problem / Hold** | Placeholder; no dedicated Trip problem/hold state. |
| **Rich Trip history/timeline UI** | Deferred. |
| **Custody / terminal controls in TripContainerPage** | Not part of first accordion slice; backend custody slices exist. |
| **Stop execution UI** | Deferred. |
| **Trip completion control in TripContainerPage** | Not part of first accordion slice; backend completion exists. |
| **Driver dispatch package** | Deferred / Decision 8 remains separate. |
| **Payroll/settlement UI** | Out of scope. |
| **Trailer-to-trailer transfer UI** | Deferred. |
| **Recovery / repower UI** | Deferred. |
| **Multi-load physical Trip-stop model** | Future architecture; current UI reads Load stops. |

---

## 12. Architecture guardrails

These rules constrain both current and future UI.

1. **Trip status, Load readiness/lifecycle, and custody are separate truths.** Never collapse them into one field.
2. **Load persists across Trips.** A Load is commercial continuity; a Trip is an execution container.
3. **Terminal/yard custody is real structured state**, not merely a note. Backend custody foundations already exist; UI should integrate them without inventing alternate state.
4. **Custody transfer is audited.** No silent handoff.
5. **Custody is not equivalent to driver assignment.** Trip assignment, active execution, and custody are distinct.
6. **Future stop execution may exceed pickup/delivery semantics.** Do not hardwire the UI so one physical event can only represent one Load action forever.
7. **One physical Trip stop may serve multiple Load/custody actions** in a future Trip-stop model; the current `Trip → Load → LoadStop` accordion is a read-model limitation, not a final data-model claim.
8. **Trailer transfer / repower must be auditable** and preserve Load continuity.
9. **Load.status must not become the execution ladder.** Per Decision 11, the target for **new Load writes** is commercial/readiness-oriented (`draft`, `ready`, `cancelled` as the target model), while **Trip.status** owns `planned / assigned / in_progress / completed / cancelled` execution lifecycle. Legacy Load statuses may remain on read/compatibility paths during migration.
10. **Reassignment/repower does not create a second commercial Load.** The same Load continues through Trip/custody history.

---

## 13. Must never use as Trip Container state logic

The Trip Container / Dispatch Control Center must not depend on:

- `DeprecatedDispatchPage` state model
- `getDispatchBoard` / `GET /api/v1/dispatch/board`
- legacy `Load.status` lanes as its organizing lifecycle
- `Load.status = dispatched` as a new execution trigger
- new `dispatch_trips` writes from Trip flows
- fake operational metrics presented as truth
- `deriveDriverStatuses` or equivalent logic deriving driver operational state from legacy Load buckets
- fixed `ON_LOAD_STATUSES`-style Load-status sets as Trip execution truth

Pure visual patterns may be salvaged if they do not import the legacy semantics.

---

## 14. First implementation slice — shipped

The initial Trip Container build direction has been implemented in `TripContainerPage`:

- Trip APIs, not `getDispatchBoard`
- Trip lifecycle filters including Active union behavior
- Trip-focused list/control-center layout
- member-load expansion
- Load detail fetch for expanded Load context
- nested Load stop display
- deep link to Load Workspace
- assignment and execution actions where allowed
- placeholders for future operational areas rather than fake data

This does **not** mean every future section in this design is complete.

---

## 15. Current checklist

- [x] One product world: **Trip Container = Dispatch Control Center**
- [x] Trip-backed `/trips/container` first UI slice exists
- [x] Lifecycle filters use Trip semantics, not legacy Load lanes
- [x] Accordion/list drill-down is Trip-backed
- [x] Assignment and execution APIs are wired into Trip UI
- [x] Load details/stops are read from Load APIs when needed
- [x] Legacy `DeprecatedDispatchPage` is excluded as a state-model dependency
- [ ] Problem/Hold Trip model
- [ ] Rich Trip timeline/history UI
- [ ] Mature custody/terminal UI integration in Trip Container
- [ ] Driver dispatch package flow
- [ ] Recovery/repower UI
- [ ] Final route/navigation convergence and legacy `/dispatch` retirement
