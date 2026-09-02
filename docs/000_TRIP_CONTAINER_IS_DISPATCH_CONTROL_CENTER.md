# 000 — Trip Container Is the Dispatch Control Center

**Status:** **CURRENT PRODUCT / UI LOCK — transition state in code**  
**Locked identity (no split):** **Trip = Trip Container = Dispatch Control Center.** These are names for one operational product world, not separate products.  
**Current implementation reality (2026-08-28 inspection branch):** the UI is still in migration: `/trips/container` runs the new Trip-backed `TripContainerPage`, `/trips/:id` runs the detailed `TripWorkspacePage`, and `/dispatch` still runs `DeprecatedDispatchPage`, the legacy `Load.status` board. The one-surface rule is the **product destination and ownership boundary**; it does not mean the three routes have already been physically collapsed.

**Related:** `001_TRIP_CONTAINER_ACCORDION_WIREFRAME.md`, `TRIP_EXECUTION_CUSTODY_MASTER_INDEX.md`, `.cursor/rules/trip-container-dispatch-boundary.mdc`.

---

## 1. Why this lock exists

TruckERP has repeatedly seen temporary/reference surfaces grow into accidental architecture. Load Lab and email-intake work both showed the risk: a useful local implementation can become a competing source of truth if product boundaries are not explicit.

The same risk exists around:

- `DeprecatedDispatchPage` — visually useful, but backed by legacy `Load.status` board semantics
- `TripContainerPage` — the new Trip-backed operational control-center slice
- `TripWorkspacePage` — detailed Trip workspace that already owns Trip mutations
- `LoadWorkspacePage` — commercial/readiness/document workspace

The rule is therefore:

> Choose the product foundation based on where the correct business truth lives, not on which page currently looks better.

Operational truth lives on **Trip / TripLoad / custody**, not on legacy Load-status dispatch lanes.

---

## 2. Locked product identity

### Trip = Trip Container = Dispatch Control Center

Backend/domain language may say:

- `Trip`
- `TripLoad`
- `Trip.status`
- Trip assignment
- Trip execution signal
- Trip completion
- Trip/custody transitions

Frontend/operator language may say:

- Dispatch
- Dispatch Control Center
- Trip Container
- active / assigned / in-progress trip

Those labels refer to the **same Trip-backed operational world**.

They must never imply a second product whose lifecycle comes from `Load.status` lanes.

### Current route transition

Today the code still exposes:

| Route | Current page | Meaning |
|---|---|---|
| `/trips/container` | `TripContainerPage` | New Trip-backed Dispatch Control Center slice; list/accordion/operator view. |
| `/trips/:id` | `TripWorkspacePage` | Detailed Trip workspace and mutation surface. |
| `/dispatch` | `DeprecatedDispatchPage` | Legacy `Load.status` board compatibility / visual salvage. Not the future state model. |

This is a **migration state**, not three product identities.

---

## 3. Page ownership

### Trip-backed Dispatch Control Center

The Trip operational world owns:

- planned trips
- assigned trips
- in-progress trips
- completed/cancelled Trip lifecycle
- trip number
- driver / truck / trailer assignment
- `TripLoad` memberships
- Start Execution / execution signals
- Trip completion
- custody transitions and continuity where shipped
- future recovery / repower UX
- future driver dispatch package / send flow
- future richer operational timeline

Some of these behaviors already exist in backend/API slices even if the new `TripContainerPage` has not surfaced all of them yet. UI incompleteness does **not** move ownership back to `Load.status`.

### Load Workspace

`LoadWorkspacePage` remains **load directory + commercial/readiness/document truth**.

It owns:

- broker/customer commercial fields
- rate / revenue identity
- broker load reference and related refs
- contractual pickup/delivery stops
- PDF/intake verification
- documents and notes
- Save Draft / Save Ready
- load search/detail
- create/attach-to-trip entry points

It must **not** become the Trip execution state machine.

### Deprecated Dispatch board

`DeprecatedDispatchPage` is the old Load-centric board. It may still display lanes such as:

- unassigned
- assigned
- dispatched
- arrived_pickup
- in_transit
- arrived_delivery
- delivered
- issue_hold

Those lanes remain compatibility/read-side behavior only. They are **not** the lifecycle source for new Trip execution work.

Treat the page as:

- legacy compatibility surface
- visual reference / salvage source
- retire-later code

Do not add new operational business logic there unless an explicit owner decision reopens that boundary.

---

## 4. Code-backed current reality

### Legacy board still exists

`GET /api/v1/dispatch/board` still groups `Load` rows by legacy dispatch status for `DeprecatedDispatchPage`.

This is expected compatibility debt during migration. Its existence does not make `Load.status` the new execution authority.

### Trip lifecycle is already real

The working `trips.status` lifecycle is:

```text
planned → assigned → in_progress → completed
                    ↘
                     cancelled (where allowed by product rules)
```

Current shipped slices include:

- planned Trip creation
- add/remove `TripLoad` membership
- cancel planned Trip
- Trip assignment (`PUT /trips/{id}/assignment`)
- active execution signal (`POST /trips/{id}/execution-signal`)
- Trip completion (`POST /trips/{id}/complete`)
- custody foundation and read APIs
- custody transitions including accept custody, yard handoff, and Trip takeover

See `TRIP_EXECUTION_CUSTODY_MASTER_INDEX.md` for the authoritative shipped-state decision spine.

### Load status is not Trip execution truth

New generic writes into legacy operational `Load.status` values are blocked by the legacy-dispatch cutover. Legacy Load status values remain for compatibility/read-side behavior while migration continues; unchanged values may be re-sent when editing historical rows.

---

## 5. What must not happen

Do **not**:

- move the future Trip control model onto `DeprecatedDispatchPage`
- build new operational lanes from `Load.status`
- revive `Load.status = dispatched` as the execution trigger
- write `dispatch_trips` from new Trip execution flows
- infer driver operational state from legacy Load-status buckets
- copy old dispatch-board business logic into `TripContainerPage` / `TripWorkspacePage`
- turn Load Workspace into the execution control center

Instead:

> Evolve the **Trip-backed Dispatch Control Center** while salvaging only useful visual/operator patterns from the legacy board.

---

## 6. What may be visually salvaged from DeprecatedDispatchPage

Potential visual salvage:

- driver rail concept
- dense cards / compact rows
- route display treatment
- badge/pill styling
- operator-friendly density
- scrolling patterns
- quick-open interactions
- board-like grouping as a **visual** pattern where Trip semantics support it

Do not salvage as logic:

- `Load.status` execution lanes
- `dispatched` as Trip execution truth
- `/dispatch/board` as the final operational read model
- `deriveDriverStatuses`-style status inference from Load buckets
- old assignment-through-Load behavior

---

## 7. Shipped execution / custody state

Earlier versions of this document described Decision 7 as parked/uncommitted. That is historical.

Current code already contains:

- **Decision 14A assignment:** `planned` → `assigned` when the required Trip assignment is committed
- **Decision 7 execution signal:** `assigned` → `in_progress`
- **Trip completion:** `in_progress` → `completed` when completion guards pass
- **Custody Slice 1:** terminal/custody tables + read APIs
- **Custody Slice 2:** accept-custody / yard-handoff / take-custody transition workflows

These slices intentionally keep `Load.status`, Trip lifecycle, and custody as separate truths.

---

## 8. Architecture statement to use going forward

> **Trip = Trip Container = Dispatch Control Center** — one Trip-backed operational product world.  
> **Load Workspace** = load directory + commercial/readiness/document truth.  
> **Trip / TripLoad** = execution + membership truth.  
> **Custody/Audit** = continuity truth.  
> **DeprecatedDispatchPage** = legacy `Load.status` board compatibility and visual salvage only.

---

## 9. Migration path

### Phase 0 — product boundary lock

**Complete.** This document and `.cursor/rules/trip-container-dispatch-boundary.mdc` establish the boundary.

### Phase 1 — legacy board classification

**In progress / historical analysis available.** Continue to classify legacy code as visual salvage, compatibility logic, or retire-later debt. Do not make it the new foundation.

### Phase 2 — Trip Container operator surface

**First implementation slice shipped.** `TripContainerPage` exists at `/trips/container` and is backed by Trip APIs, not `getDispatchBoard`.

Continue adding Trip-backed capability only when its API/state ownership is explicit.

### Phase 3 — converge navigation/routes

Still open. Decide how `/trips/container`, `/trips/:id`, and future `/dispatch` aliasing converge without creating competing products.

### Phase 4 — retire legacy `/dispatch`

Only after the Trip-backed control center covers the required operator workflow:

- remove/hide legacy navigation
- retire `/dispatch` legacy route
- retire `/api/v1/dispatch/board` when no remaining compatibility consumers need it
- delete legacy board logic only after references/tests are checked

---

## 10. Cursor / agent boundary rule

The rule exists at:

```text
.cursor/rules/trip-container-dispatch-boundary.mdc
```

Before changing Trip, Load, or legacy-board UI, classify the work as one of:

1. visual salvage
2. Trip read-model integration
3. operational mutation
4. legacy cleanup

Do not mix unrelated parser/email/dependency work into the same Trip/legacy-board slice.

---

## 11. Historical restart prompt

Older versions of this file included a copy/paste prompt instructing Cursor to stop coding and create the boundary rule. That step has now been completed. The durable instruction is the repository rule itself plus this document; do not treat an old chat-style prompt as current project state.

---

## 12. Open owner decisions

1. Should `/dispatch` eventually become an alias/preferred URL for the same Trip-backed control center?
2. Should `/trips/:id` remain the canonical deep-detail route while `/trips/container` is the list/accordion command surface?
3. When should legacy `Dispatch` navigation disappear from TopNav?
4. How much visual structure from `DeprecatedDispatchPage` should be reused without importing its state model?
5. How should Ready loads feed the Trip planning workflow while remaining Load/readiness truth?
6. When can `/api/v1/dispatch/board` be formally deprecated and removed?
7. Which shipped custody/completion capabilities belong in the first mature `TripContainerPage` operator workflow?

---

## 13. Final locked takeaway

Do not build the future on the legacy Load-status board merely because it is visually mature.

Build on the **Trip-backed operational world** and converge the current Trip routes into one operator experience over time.

```text
Trip = Trip Container = Dispatch Control Center.
Load Workspace = commercial/readiness/document truth.
DeprecatedDispatchPage = legacy compatibility until retired.
```
