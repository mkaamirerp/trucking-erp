# Trip execution & custody — master index

**Type:** Navigation map and source-of-truth pointer.  
**Status:** **Approved index.** Does **not** replace any detailed doc below.

---

## 1. Purpose

This document is the **navigation / source-of-truth map** for:

- Trip **execution** and **custody**
- **Terminal** routing and yard context
- **Assignment** (trip vs load)
- The **planned-trip lifecycle** that shipped before execution work

It lists **reading order**, **document classification**, **consolidated locked principles**, **what is still open**, **guardrails**, **current shipped state**, and **next workflow**. **Always open the underlying docs** for full rationale, tables, and API shapes.

---

## 2. Reading order

Read in this order when onboarding or before migrations / implementation:

| Order | Document | Purpose |
|-------|----------|---------|
| **A** | [`TRIP_LIFECYCLE_TERMINAL_ROUTING_YARD_HANDOFF_DISPATCH_LOAD_TRANSFER_FOUNDATION.md`](./TRIP_LIFECYCLE_TERMINAL_ROUTING_YARD_HANDOFF_DISPATCH_LOAD_TRANSFER_FOUNDATION.md) | **Background:** business foundation and real-world operations rules (trip vs load, custody, terminal, handoff, trailer transfer, principles). |
| **B** | [`PLANNED_TRIP_LIFECYCLE_MODULE_CLOSE.md`](./PLANNED_TRIP_LIFECYCLE_MODULE_CLOSE.md) | **Shipped:** planned-trip lifecycle (3D–3K), current APIs/UI, `active_trip_id` mirror, limitations. |
| **C** | [`PHASE3L_A_TRIP_EXECUTION_CUSTODY_DECISION_RECORD.md`](./PHASE3L_A_TRIP_EXECUTION_CUSTODY_DECISION_RECORD.md) | **Decisions:** execution/custody **boundaries** — status ownership, proposed ladder (pre-implementation), dispatch board implications at report level. |
| **D** | [`PHASE3L_B_TRIP_ASSIGNMENT_CONTRACT.md`](./PHASE3L_B_TRIP_ASSIGNMENT_CONTRACT.md) | **Contract:** **effective assignment** / source of truth while on trip membership; sync rules. |
| **E** | [`PHASE3L_C_TRIP_EXECUTION_SCHEMA_API_PLAN.md`](./PHASE3L_C_TRIP_EXECUTION_SCHEMA_API_PLAN.md) | **Plan:** proposed **schema** additions, custody model sketch, **future** API endpoints (`PUT …/assignment`, transitions, custody, timeline). |
| **F** | [`PHASE3L_D_OWNER_DECISION_CHECKLIST.md`](./PHASE3L_D_OWNER_DECISION_CHECKLIST.md) | **Checklist:** owner **locks** vs open items before first migration; sign-off block for remaining topics. |

---

## 3. Document classification

| Classification | Documents |
|----------------|-----------|
| **Background foundation** | `TRIP_LIFECYCLE_TERMINAL_ROUTING_YARD_HANDOFF_DISPATCH_LOAD_TRANSFER_FOUNDATION.md` |
| **Shipped module closeout** | `PLANNED_TRIP_LIFECYCLE_MODULE_CLOSE.md` |
| **Decision records** | `PHASE3L_A_TRIP_EXECUTION_CUSTODY_DECISION_RECORD.md`, `PHASE3L_B_TRIP_ASSIGNMENT_CONTRACT.md` |
| **Implementation planning** | `PHASE3L_C_TRIP_EXECUTION_SCHEMA_API_PLAN.md` |
| **Owner decision checklist** | `PHASE3L_D_OWNER_DECISION_CHECKLIST.md` (includes **locked** decisions in the opening section) |

---

## Supporting references

These docs are **not** part of the required **A–F** reading spine, but should be checked when working near trip numbering, dispatch mirroring, DDL, load parser boundaries, or payroll tracing.

| Document | When to read / why |
|----------|-------------------|
| `DISPATCH_TRIP_NUMBER_RULE.md` | Read before touching trip number prefix, trip number minting, or any logic involving `Load.status = dispatched` and `dispatch_trips`. |
| `DISPATCH_TRIP_NUMBER_IMPLEMENTATION_PLAN.md` | Read before changing the existing dispatch trip number implementation, shared numbering pool, or load-status-driven dispatch path. |
| `TRIP_FIRST_DDL_CONTRACT.md` | Read before designing tenant migrations or DDL for trip-first execution/custody tables. |
| `TRIP_CONTAINER_VS_LOAD_FOUNDATION.md` | Read when revisiting Trip vs Load boundaries and product ownership. |
| `trip-foundation.md` | Read for earlier trip foundation context and naming/scope history. |
| `TRIP_CONTAINER_OPERATIONAL_RULES.md` | Read before changing operational rules for Trip containers. |
| `PHASE1_TRIP_FOUNDATION_PLAN.md` | Historical phase-1 foundation plan; useful for why current `trips` / `trip_loads` shape exists. |
| `TRIP_CONTAINER_ARCHITECTURE_GAP_REPORT.md` | Read before changing architecture or claiming gaps are closed. |
| `PHASE3C_PLANNED_TRIP_IMPLEMENTATION_PROPOSAL.md` | Pre-ship proposal for planned trips; mostly superseded by module closeout, but useful for rationale. |
| `PHASE3D_TRIP_ACTION_READ_FIRST.md` | Read before changing trip service actions; preserves report-first/action safety discipline. |
| `TRIP_CONTAINER_LOAD_PAGE_PARSER_INTEGRATION_MAP.md` | Read only if Trip work touches LoadWorkspace or parser boundaries. |
| `PAYROLL_TRIP_TRACING.md` | Read before designing payroll, settlement, cancellation-pay, or trip tracing logic. |
| `LOAD_LIFECYCLE_AND_OPERATIONAL_EVENTS_LOCK.md` | Read before coupling Trip transitions to Load.status or operational load events. |

The **A–F** reading order remains the **required spine**; supporting references are **situational**, not replacements for the spine.

---

## 4. Consolidated locked principles

The following are **locked** for V1-oriented execution/custody work as of **3L-A–3L-D** unless explicitly reopened in a later owner decision. (Detail and nuance live in the linked docs.)

- **Trip** is the **operational execution container** (movement, equipment assignment at trip level for active membership).
- **Load** is the **commercial / broker / customer** truth (stops, docs, rates, board `Load.status` today).
- **TripLoad** (`trip_loads`) is **explicit membership** between trip and load.
- **Active membership** = `trip_loads` row with **`removed_at IS NULL`** — **source of truth** for “load on trip.”
- **`loads.active_trip_id`** is a **backend mirror only**; **UI must not “repair” drift** (membership APIs own consistency).
- **Trip completion ≠ load delivery** (trip can end with handoff; loads may remain active).
- **`Trip.status` positive terminal state = `completed`** — **not** `delivered` on the trip container.
- **`Load.status`** may still use **`delivered`** for commercial/final receiver milestones.
- **Custody** event type **`delivered`** may still exist for receiver / proof (distinct from `Trip.status`).
- **No `Trip.status = voided` in V1** — use **`cancelled`** with reason, audit, and future pay-review workflow (see 3L-D).
- **Cancelled** trips: record not deleted; **`cancelled_at`**, **`cancelled_by`**, **`cancel_reason`** (and notes/audit); **`cancel_category` optional later**.
- **Trip numbers are not reused** after cancellation (per 3L-D). Load-number reuse policy is outside this Trip execution/custody index.
- **Cancellation does not automatically mean no pay**; **ELD miles** may be evidence; **dispatch / owner / payroll** decides pay (policy-driven).
- **Terminal table required in V1** for terminal custody: **tenant-scoped** terminal rows (admin-managed **name** + address fields per 3L-D); **dropdown shows name only**; **backend stores `terminal_id`** on custody events — **not** free-text as the identity of “which terminal.”
- **First execution transition slice:** **`planned` → `assigned` only** (then expand later per 3L-C checklist).
- **Assignment** endpoint **`PUT /api/v1/trips/{id}/assignment`** should land **before** broad **transition** endpoint (per 3L-C slices).
- **No `Load.status` auto-updates from `Trip.status` transitions in V1** (default decoupled).
- **No `dispatch_trips` create/update** driven by **`Trip.status`** (including execution `dispatched`) in V1 — avoids collision with **`load.status → dispatched`** mint path (3L-C §7).
- **Custody V1 `event_type` allowlist:** **`picked_up`**, **`handoff`**, **`arrived_terminal`**, **`dropped_at_terminal`**.
- **Defer:** **`picked_up_from_terminal`**, **`trailer_transfer`** (until allowlist extended); **`trip_stops`** (events + projections first).
- **Minimum audit** for assignment / transition / custody: **`actor_user_id`**, **`event_at` / `recorded_at`**, **reason/notes**, **`source`** (central vs local audit store still an open topic — see §5).
- **No default silent sync** of **trip assignment → load assignment** (3L-B); named modes only if explicitly added later.

---

## 5. Open decisions / still pending

Items **not** fully locked remain in **`PHASE3L_D_OWNER_DECISION_CHECKLIST.md`** (sections 4–10) and **3L-A/B/C** open-question lists. Notable gaps:

- **Exact cancellation reason categories** (`cancel_category` taxonomy).
- **Exact cancellation pay-review fields and workflow** (beyond the future-field sketch in 3L-D — UX, RBAC, payroll integration).
- **Terminal address field details** (validation, normalization, multi-line vs single, country rules).
- **Audit storage:** **`trip_status_events` / local tables first** vs **central `audit_events`** immediately.
- **Assignment endpoint** detailed **request/response**, validation edge cases, and idempotency headers.
- **Dispatch board trip-first read model** — API shape, dual-view strategy, timeline vs columns (3L-C §8 / 3L-A §6).
- **Long-term `dispatch_trips` retirement** or unification with trip container (3L-A/C open questions).
- **Terminal sub-states** in custody: on trailer / staged / transfer pending (granularity vs trip `at_terminal`).
- **When** **`picked_up_from_terminal`** and **`trailer_transfer`** enter the custody allowlist.

---

## 6. Implementation guardrails

Before writing migrations or product code:

- **No tenant migrations** for execution/custody until **owner decisions** needed for that slice are **locked** (continue from 3L-D).
- **No backend/UI implementation** of execution/custody should start without **reading this index** and the **ordered docs** in §2.
- **Do not** modify **`Load.status`** from **`Trip.status`** transitions in V1 (unless a future explicit, tested coupling feature is approved).
- **Do not** auto-**create/modify `dispatch_trips`** from **`Trip.status`** in V1.
- **Do not** **silently sync** trip assignment to load assignment (3L-B).
- **Do not** let the **UI repair `active_trip_id`**.
- **Do not hard-delete** custody history — void/correct patterns per foundation docs.
- **Do not rewrite** the **dispatch board** as part of the first execution/custody slices.
- **Do not** mix **stashed unrelated work** into trip execution workstreams (triage stash separately).

---

## 7. Current shipped state

- **Planned-trip lifecycle** is **complete through 3K** in product (list/detail, create from load, add/remove/cancel, active + historical members, labels per module-close + later commits; see `PLANNED_TRIP_LIFECYCLE_MODULE_CLOSE.md` for inventory — commit hashes in that file may be older than current `main`).
- **3L-A through 3L-D** docs exist in the current project state as **planning / contract docs** (paths above).
- **Execution/custody implementation** (new statuses, custody tables, transition APIs) **has not started** in code.
- **Working product model** for trip **container** remains **`planned` / `cancelled` only**; **`Load.status`** still drives the **load-centric dispatch board**.

---

## 8. Next recommended workflow

1. **Finish review** of this **master index** (and fix any drift vs underlying docs).
2. **Commit** this file **only after** maintainer approval (draft until then).
3. **Resume owner decisions** from **`PHASE3L_D_OWNER_DECISION_CHECKLIST.md`** (items still **not** LOCKED).
4. Produce **3L-E implementation readiness plan** (migrations order, feature flags, cutover checks) — **documentation phase**, not code.
5. **Only after owner approval** of readiness: **start migrations** and implementation slices per **3L-C** (A→H) with guardrails in §6.

---

*End of trip execution & custody master index.*
