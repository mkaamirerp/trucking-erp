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
- **Dispatcher load workspace** actions (**Decision 6**) — canonical verification screen, action bar, dispatch package concept
- **Trip number in the driver dispatch package** — **Trip Number** is the **primary operational identifier**; one number for the **whole** trip (not per stop); see §4
- **Active execution signal** (**Decision 7**) — execution starts at **first real signal**, not assignment/package send
- **Driver dispatch package & financial visibility** (**Decision 8**, **DRAFT**) — versioned package from **Assign & Send**, operational content vs driver-visible view, disclosure — see [`DECISION_8_DRIVER_DISPATCH_PACKAGE_SCHEMA.md`](./DECISION_8_DRIVER_DISPATCH_PACKAGE_SCHEMA.md)
- **Load readiness & planning queue** (**Decision 9**, **LOCKED**) — **Save Draft / Save Ready** are load preparation, not trip execution; **Ready / Unassigned** planning queue semantics — see [`DECISION_9_LOAD_READINESS_PLANNING_QUEUE.md`](./DECISION_9_LOAD_READINESS_PLANNING_QUEUE.md)
- **Future assignment vs active execution** (**Decision 10**, **LOCKED**) — queued **assigned** trips allowed, but **impossible** schedule overlap vs **`in_progress`** trip guarded; supervisor override with audit — see [`DECISION_10_FUTURE_ASSIGNMENT_CONFLICT_GUARD.md`](./DECISION_10_FUTURE_ASSIGNMENT_CONFLICT_GUARD.md)
- **`Load.status` target & board migration** (**Decision 11**, **LOCKED**) — commercial/readiness **`draft` / `ready` / `cancelled`** for **new writes**; legacy **`Load.status`** read-side; **trip** board vs **load** planning queue — see [`DECISION_11_LOAD_STATUS_TARGET_BOARD_MIGRATION.md`](./DECISION_11_LOAD_STATUS_TARGET_BOARD_MIGRATION.md)
- **Terminal / yard / custody foundation** (**Decision 12**, **LOCKED**) — consolidates [`TRIP_LIFECYCLE_TERMINAL_ROUTING_YARD_HANDOFF_DISPATCH_LOAD_TRANSFER_FOUNDATION.md`](./TRIP_LIFECYCLE_TERMINAL_ROUTING_YARD_HANDOFF_DISPATCH_LOAD_TRANSFER_FOUNDATION.md) onto the decision spine; structured terminal, handoff, auditable trailer transfer, trip close with undelivered only with custody — see [`DECISION_12_TERMINAL_YARD_CUSTODY_FOUNDATION.md`](./DECISION_12_TERMINAL_YARD_CUSTODY_FOUNDATION.md)
- **Trip exception / recovery / repower + payroll guard** (**Decision 13**, **LOCKED**) — preserve original trip + new recovery trip number; no silent assignment swap; planned handoff vs failed assignment; **`review_required`** payroll block on incomplete trip responsibility — see [`DECISION_13_TRIP_EXCEPTION_RECOVERY_REPOWER.md`](./DECISION_13_TRIP_EXCEPTION_RECOVERY_REPOWER.md)

It lists **reading order**, **document classification**, **consolidated locked principles**, **what is still open**, **guardrails**, **current shipped state**, and **next workflow**. **Always open the underlying docs** for full rationale, tables, and API shapes.

**Legacy dispatch cutover (Slice 1, code — e.g. `7012f40a`):** **Generic `Load` PATCH** cannot create a **new** transition into **`Load.status = dispatched`** ( **`409`**, **`LEGACY_LOAD_STATUS_DISPATCH_DEPRECATED`** ). **Read**/**board** compatibility and **legacy cancel** paths for **already-dispatched** loads remain; **new** execution uses **Trip**/**`TripLoad`**/**planned trip** flows per locked decisions. **Target `Load.status` and board direction** are **LOCKED** in **`DECISION_11_LOAD_STATUS_TARGET_BOARD_MIGRATION.md`**.

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
| **Decision records** | `PHASE3L_A_TRIP_EXECUTION_CUSTODY_DECISION_RECORD.md`, `PHASE3L_B_TRIP_ASSIGNMENT_CONTRACT.md`; **terminal/custody spine** — `DECISION_12_TERMINAL_YARD_CUSTODY_FOUNDATION.md` (**LOCKED**); **exception/recovery/repower spine** — `DECISION_13_TRIP_EXCEPTION_RECOVERY_REPOWER.md` (**LOCKED**) |
| **Implementation planning** | `PHASE3L_C_TRIP_EXECUTION_SCHEMA_API_PLAN.md` |
| **Owner decision checklist** | `PHASE3L_D_OWNER_DECISION_CHECKLIST.md` (includes **locked** decisions in the opening section) |
| **Dispatcher load workspace (Decision 6)** | `DECISION_6_DISPATCHER_LOAD_WORKSPACE_ACTION_MODEL.md` |
| **Active execution signal (Decision 7)** | `DECISION_7_ACTIVE_EXECUTION_SIGNAL_MODEL.md` |
| **Driver dispatch package & financial visibility (Decision 8)** — **DRAFT / NOT LOCKED** | `DECISION_8_DRIVER_DISPATCH_PACKAGE_SCHEMA.md` |
| **Load readiness / planning queue (Decision 9)** — **LOCKED** | `DECISION_9_LOAD_READINESS_PLANNING_QUEUE.md` |
| **Future assignment / conflict guard (Decision 10)** — **LOCKED** | `DECISION_10_FUTURE_ASSIGNMENT_CONFLICT_GUARD.md` |
| **Load.status target / board migration (Decision 11)** — **LOCKED** | `DECISION_11_LOAD_STATUS_TARGET_BOARD_MIGRATION.md` |
| **Terminal / yard / custody foundation (Decision 12)** — **LOCKED** | `DECISION_12_TERMINAL_YARD_CUSTODY_FOUNDATION.md` |
| **Trip exception / recovery / repower + payroll guard (Decision 13)** — **LOCKED** | `DECISION_13_TRIP_EXCEPTION_RECOVERY_REPOWER.md` |

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
| `DECISION_6_DISPATCHER_LOAD_WORKSPACE_ACTION_MODEL.md` | Read before changing **Load Workspace** dispatcher actions (**Save Draft / Ready / Assign / Assign & Send**) or **dispatch package** design. |
| `DECISION_7_ACTIVE_EXECUTION_SIGNAL_MODEL.md` | Read before defining **when a trip is “actively executing”**, **`Trip.status = in_progress`**, execution signals, or overlap guards vs **assignment**. |
| `DECISION_8_DRIVER_DISPATCH_PACKAGE_SCHEMA.md` — **draft** | Read when designing **Assign & Send** package **content**, **versioning**, **internal vs driver-visible** views, **financial disclosure**, or **driver-type** visibility (**not locked** until owner sign-off). |
| `DECISION_9_LOAD_READINESS_PLANNING_QUEUE.md` | Read before mapping **Save Draft / Save Ready** to **boards**, **queues**, or **`Load.status`** — **locked** semantics: readiness vs execution (**Decision 9**). |
| `DECISION_10_FUTURE_ASSIGNMENT_CONFLICT_GUARD.md` | Read before **assigning** a **future** trip to **driver/truck/trailer** already **`in_progress`** elsewhere — **locked** scheduling conflict + override rules (**Decision 10**). |
| `DECISION_11_LOAD_STATUS_TARGET_BOARD_MIGRATION.md` | Read before changing **`Load.status`** **new-write** allowlists, **dispatch board** migration, or conflating **load readiness** with **trip execution** — **Decision 11** + Slice 1 compatibility. |
| `DECISION_12_TERMINAL_YARD_CUSTODY_FOUNDATION.md` | Read before custody/terminal/trailer-transfer design — **LOCKED** consolidation of [`TRIP_LIFECYCLE_TERMINAL_ROUTING_YARD_HANDOFF_DISPATCH_LOAD_TRANSFER_FOUNDATION.md`](./TRIP_LIFECYCLE_TERMINAL_ROUTING_YARD_HANDOFF_DISPATCH_LOAD_TRANSFER_FOUNDATION.md) on the decision spine (**Decision 12**). |
| `DECISION_13_TRIP_EXCEPTION_RECOVERY_REPOWER.md` | Read before exception/repower/recovery flows, **original vs recovery trip** rules, **payroll review** / **`review_required`** guard, or **planned handoff vs failed assignment** — **LOCKED** (**Decision 13**). |

The **A–F** reading order remains the **required spine**; supporting references are **situational**, not replacements for the spine.

---

## 4. Consolidated locked principles

The following are **locked** for V1-oriented execution/custody work as of **3L-A–3L-D**, **Decision 6** (load workspace / dispatch package), **Decision 7** (active execution signal), **Decision 9** (load readiness / planning queue), **Decision 10** (future assignment scheduling vs active execution), **Decision 11** (`Load.status` target + board migration direction), **Decision 12** (terminal/yard/custody foundation), and **Decision 13** (trip exception/recovery/repower + payroll guard — plus **3L-D Decision 3** terminal table) unless explicitly reopened in a later owner decision. (Detail and nuance live in the linked docs.)

- **Trip** is the **operational execution container** (movement, equipment assignment at trip level for active membership).
- **Load** is the **commercial / broker / customer** truth (stops, docs, rates); **`Load.status`** **target** for **new writes** is **commercial/readiness** only — **`draft`**, **`ready`**, **`cancelled`** (**Decision 11**) — **not** trip execution state.
- **TripLoad** (`trip_loads`) is **explicit membership** between trip and load.
- **Active membership** = `trip_loads` row with **`removed_at IS NULL`** — **source of truth** for “load on trip.”
- **`loads.active_trip_id`** is a **backend mirror only**; **UI must not “repair” drift** (membership APIs own consistency).
- **Trip completion ≠ load delivery** (trip can end with handoff; loads may remain active).
- **`Trip.status` positive terminal state = `completed`** — **not** `delivered` on the trip container.
- **Legacy `Load.status`** values (**`dispatched`**, **`in_transit`**, **`delivered`**, etc.) **may persist** on **old rows** and **read** paths (**Decision 11**); **target new-write** set is **`draft` / `ready` / `cancelled`**. **`Load.status = dispatched`** is **not** a **new** execution trigger (Slice 1 + **Decision 11**).
- **Custody** event type **`delivered`** may still exist for receiver / proof (distinct from `Trip.status`).
- **No `Trip.status = voided` in V1** — use **`cancelled`** with reason, audit, and future pay-review workflow (see 3L-D).
- **Cancelled** trips: record not deleted; **`cancelled_at`**, **`cancelled_by`**, **`cancel_reason`** (and notes/audit); **`cancel_category` optional later**.
- **Trip numbers are not reused** after cancellation (per 3L-D). Load-number reuse policy is outside this Trip execution/custody index.

### Trip number rule — driver dispatch package (**locked**)

- The **driver dispatch package** must display the **Trip Number** as the **primary operational identifier**.
- **Trip number** belongs to the **Trip** only.
- **Do not** mint or display a **new** trip number for each pickup, delivery, stop, or second pickup.
- If the trip has **multiple pickups or deliveries**, **all stops** remain under the **same** trip number.
- Each stop may have its own **stop sequence number**, **pickup number**, **delivery number**, **PO number**, **appointment date/time**, **facility address**, and **notes/instructions** — those are **stop / load** references, **not** trip numbers.

(See **`DISPATCH_TRIP_NUMBER_RULE.md`** and **`DISPATCH_TRIP_NUMBER_IMPLEMENTATION_PLAN.md`** when changing numbering or minting.)

- **Cancellation does not automatically mean no pay**; **ELD miles** may be evidence; **dispatch / owner / payroll** decides pay (policy-driven).
- **Terminal table required in V1** for terminal custody: **tenant-scoped** terminal rows (admin-managed **name** + address fields per **3L-D Decision 3** and **Decision 12 §E**); **dropdown shows name only**; **backend stores `terminal_id`** on custody events — **not** free-text as the identity of “which terminal.”
- **Canonical `Trip.status` ladder (Decision 7):** **`planned` → `assigned` → `in_progress` → `completed`**, **`cancelled`** terminal negative — see **3L-D §4** + **`DECISION_7_ACTIVE_EXECUTION_SIGNAL_MODEL.md`**. **Do not** use **`Trip.status = dispatched`** after **`assigned`**; **`dispatched`** on **`Load.status`** / board remains **legacy** vocabulary for mint/board, not the trip header step after commitment.
- **First execution transition slice (phasing):** **`planned` → `assigned` only** first; then **`assigned` → `in_progress`** when execution signals exist — **not** `assigned → dispatched`.
- **Assignment** endpoint **`PUT /api/v1/trips/{id}/assignment`** should land **before** broad **transition** endpoint (per 3L-C slices).
- **No `Load.status` auto-updates from `Trip.status` transitions in V1** (default decoupled).
- **No `dispatch_trips` create/update** driven by **`Trip.status`** (including **`in_progress`** or any future trip execution state) in V1 — avoids collision with **legacy** **`load.status → dispatched`** mint path (3L-C §7).
- **Custody / terminal foundation (Decision 12):** Principles from [`TRIP_LIFECYCLE_TERMINAL_ROUTING_YARD_HANDOFF_DISPATCH_LOAD_TRANSFER_FOUNDATION.md`](./TRIP_LIFECYCLE_TERMINAL_ROUTING_YARD_HANDOFF_DISPATCH_LOAD_TRANSFER_FOUNDATION.md) — structured terminal routing, **auditable** trailer transfer, **trip** may complete with undelivered loads **only** with recorded custody/handoff, **append-only** history with **void/correct** — **`DECISION_12_TERMINAL_YARD_CUSTODY_FOUNDATION.md`**. Terminal/yard state must be **more granular** than a single vague “at yard” label (**Decision 12 §H**).
- **Trip exception / recovery / repower (Decision 13):** **Preserve** **original** **`Trip`** + **trip number**; **recovery** = **new** **`Trip`** + **new** number — **no** silent in-place driver/truck/trailer **swap** on original trip. **Five** base dispatcher options (repower, terminal handoff, planning queue, broker cancel, hold). **`Load.status = cancelled`** only for **true** commercial cancel (**Decision 11**). **Payroll:** incomplete **trip** responsibility → **`review_required`** — **no** auto full pay, **no** auto zero; **planned terminal linehaul complete** ≠ **failed final delivery** (**Decision 13 §G**). Recovery trip payroll **separate** from original (**Decision 13 §I**). **Custody chain** for recovery — **Decision 12** + **Decision 13 §J**.
- **Custody first *write* allowlist slice (implementation phasing):** **3L-D §8** may still ship a **narrow** first set (e.g. **`picked_up`**, **`handoff`**, **`arrived_terminal`**, **`dropped_at_terminal`**) — **not** because **`trailer_transfer`** or **`picked_up_from_terminal`** are optional **forever**; the **foundation** (**Decision 12**) **requires** them for full terminal/transfer stories. **Expand** allowlist and UI in **later** slices.
- **Defer (implementation):** **`trip_stops`** table CRUD — prefer **custody events** + **timeline** projections first (**3L-C §2.2**).
- **Minimum audit** for assignment / transition / custody: **`actor_user_id`**, **`event_at` / `recorded_at`**, **reason/notes**, **`source`** (central vs local audit store still an open topic — see §5).
- **No default silent sync** of **trip assignment → load assignment** (3L-B); named modes only if explicitly added later.

- **Save Draft / Save Ready (Decision 9)** are **load preparation / readiness** — **not** trip-execution states. **Save Ready** (without a **trip** action) implies **Ready / Unassigned Load Planning Queue** semantics: dispatch may plan, combine, split, or hold; **no** automatic trip, assignment, package, **`in_progress`**, **`Load.status = dispatched`**, custody, payroll, or board rewrite — see **`DECISION_9_LOAD_READINESS_PLANNING_QUEUE.md`**.
- **Future assignment scheduling (Decision 10):** **Assigned** **future** trips on the **same** driver/truck/trailer are **allowed** while another trip is **`in_progress`**, but **next** trip **first pickup / planned start** must **not** be **before** current trip **final delivery / expected completion** — **scheduling conflict**; default **block** or **hard warning**; **supervisor override** with audit — **`DECISION_10_FUTURE_ASSIGNMENT_CONFLICT_GUARD.md`**. **Assignment** still **does not** set **`in_progress`** (**Decision 7**).

### Decision 6 — Load workspace action model: Save Draft / Save Ready / Assign / Assign & Send (**locked**)

**Cross-check Decision 9:** **Save Draft / Save Ready** = load **readiness** only; **Assign** / **Assign & Send** remain the path to **trip commitment** and **package send** per **Decision 6**.

**Cross-check Decision 10:** **Future** **assignment** must respect **scheduling conflict** rules vs **`in_progress`** trips on the **same** resource — see **`DECISION_10_FUTURE_ASSIGNMENT_CONFLICT_GUARD.md`**.

**Cross-check Decision 11:** **`Load.status`** **new writes** align with **`draft` / `ready` / `cancelled`** — **not** **`dispatched`** as execution (**Slice 1**).

Full specification: [`DECISION_6_DISPATCHER_LOAD_WORKSPACE_ACTION_MODEL.md`](./DECISION_6_DISPATCHER_LOAD_WORKSPACE_ACTION_MODEL.md). **Sits after** the **Assignment endpoint first** slice (§4 bullet above). Summary:

- **Canonical Load Workspace** for dispatcher verification; top **action bar** (or primary + menu): **Save Draft**, **Save Ready**, **Assign**, **Assign & Send**.
- **Assign** = trip **assignment / commitment** only (may set **`Trip.status = assigned`** from **`planned`** per policy); **does not** imply driver **send**.
- **Assign & Send** = **composite** backend facts (save load, ready if needed, trip + membership, assignment, **versioned dispatch package**, send, **audit**) even if UI is one control.
- **Out of scope** for these actions: pickup complete, en route (unless separate execution action), **custody start**, **`Load.status = delivered`**, payroll, false movement/ELD events, **`dispatch_trips`** from **`Trip.status` in V1**, **silent trip→load assignment sync**, dispatch board rewrite.
- **Queued** future **assigned** trips per driver/equipment **allowed** subject to **scheduling conflict guard** (**Decision 10**); **overlapping active execution** (impossible dates) blocked or **supervisor override** with audit — see **`DECISION_10_FUTURE_ASSIGNMENT_CONFLICT_GUARD.md`**.
- **Dispatch package** = proof of **sent / viewed** beyond **`Trip.status = assigned`**; terminology: avoid overloading **“Dispatched”** until execution vocabulary is fixed.
- **Dispatch package content — trip number:** Follow the **§4** subsection **Trip number rule — driver dispatch package** (one **Trip Number** for the whole trip; stop-level fields are **not** trip numbers).

### Decision 7 — Active execution starts from first real execution signal, not assignment (**locked**)

Full specification: [`DECISION_7_ACTIVE_EXECUTION_SIGNAL_MODEL.md`](./DECISION_7_ACTIVE_EXECUTION_SIGNAL_MODEL.md).

**Summary:**

- **Assignment** / **Assign & Send** = commitment + optional **package send**; they **do not** start movement, pickup, custody, delivered, payroll, or board rewrite.
- **Active execution** begins at the **first accepted execution signal** (driver app, dispatcher manual, **future** geofence with override — **geofence not implemented now**).
- **Simple `Trip.status` product model:** `planned` → `assigned` → **`in_progress`** (first signal) → `completed` → `cancelled` (number not reused).
- **Queued future assigned trips** allowed during a current trip **if** **not** a **scheduling conflict** per **Decision 10**; **overlapping active execution** (impossible **first pickup** vs **current expected completion**) blocked or **supervisor override** — **without** blocking planning/assignment when dates are valid.
- **Cross-check Decision 6:** package send **≠** `in_progress`; only **first execution signal** sets **in progress**.
- **Cross-check Decision 10:** **`assigned`** ≠ **`in_progress`**; conflict guard is **schedule sanity**, not execution start.

### Decision 8 — Driver dispatch package & financial visibility (**DRAFT / NOT LOCKED**)

**Full draft:** [`DECISION_8_DRIVER_DISPATCH_PACKAGE_SCHEMA.md`](./DECISION_8_DRIVER_DISPATCH_PACKAGE_SCHEMA.md).

**Summary:** Decision 8 defines the **Driver Dispatch Package**: the **versioned** package sent from **Load Workspace** / **Assign & Send**, including **trip number**, **driver/truck/trailer** header, **stop** details, **references**, **documents/instructions**, **driver-type disclosure** rules, and **financial visibility** boundaries (internal snapshot vs driver-visible view; broker rate hidden by default; future **two pay branches** preserved — **no** O/O settlement implementation in this draft).

**Until locked:** treat §§ B–M as **design preservation** only; implementation slices remain gated on owner review (see also **§5** — dispatch package persistence).

### Decision 9 — Load readiness and planning queue mapping (**locked**)

Full specification: [`DECISION_9_LOAD_READINESS_PLANNING_QUEUE.md`](./DECISION_9_LOAD_READINESS_PLANNING_QUEUE.md).

**Summary:** **Save Draft / Save Ready** are **load-preparation** states, **not** **trip-execution** states. **Save Ready** without assigning places the load in **Ready / Unassigned Load Planning Queue** meaning: clean enough to plan; **not** committed to equipment; may be combined/split across trips; explicit **trip** actions create **`TripLoad`** — **not** automatic on Save Ready. **Does not** create trip, assign, send package, **`in_progress`**, **`Load.status = dispatched`**, custody, payroll, or rewrite board. Coexists with **legacy** board until deliberate migration.

### Decision 10 — Future assignment and active execution conflict guard (**locked**)

Full specification: [`DECISION_10_FUTURE_ASSIGNMENT_CONFLICT_GUARD.md`](./DECISION_10_FUTURE_ASSIGNMENT_CONFLICT_GUARD.md).

**Summary:** **Future assigned** trips on the **same** driver/truck/trailer are **allowed** while a trip is **`in_progress`**, but **next** trip **first pickup / planned start** must **not** precede current trip **final delivery / expected completion** — else **scheduling conflict** (default **block** or **hard warning**; **no** silent allow). **Per-resource** checks. **Supervisor override** with reason, actor, time, trips, resource, audit. **Assignment** still **does not** start execution, custody, **`Load.status = dispatched`**, payroll, or board rewrite (**Decisions 6–7**). **Assign & Send** does **not** bypass this guard when implemented.

### Decision 11 — Load.status target model and board migration (**locked**)

Full specification: [`DECISION_11_LOAD_STATUS_TARGET_BOARD_MIGRATION.md`](./DECISION_11_LOAD_STATUS_TARGET_BOARD_MIGRATION.md).

**Summary:** **`Load.status`** = **commercial/readiness**, **not** trip execution. **Target new-write** values: **`draft`**, **`ready`**, **`cancelled`**; **`ready`** aligns with **Decision 9** planning queue. **Legacy** `Load.status` values remain for **read**/history — **`dispatched`** **not** a **new** execution trigger (Slice 1 `7012f40a` + **`LEGACY_LOAD_STATUS_DISPATCH_DEPRECATED`**). **Trip** `Trip.status` / **`TripLoad`** / package / custody own **operational** state. **Target boards:** **load** planning queue + **trip** workspace — **no** immediate schema strip or board rewrite required by this doc alone.

### Decision 12 — Terminal / yard / custody foundation consolidation (**locked**)

Full specification: [`DECISION_12_TERMINAL_YARD_CUSTODY_FOUNDATION.md`](./DECISION_12_TERMINAL_YARD_CUSTODY_FOUNDATION.md).

**Source (detailed background):** [`TRIP_LIFECYCLE_TERMINAL_ROUTING_YARD_HANDOFF_DISPATCH_LOAD_TRANSFER_FOUNDATION.md`](./TRIP_LIFECYCLE_TERMINAL_ROUTING_YARD_HANDOFF_DISPATCH_LOAD_TRANSFER_FOUNDATION.md) — **not** superseded; **Decision 12** is the **concise lock** on the decision spine.

**Summary:** **Trip** = operational execution container; **Load** = commercial truth; **trip completion ≠ load delivered**; **yard/terminal** = structured custody location (**`terminal_id`**, not free-text identity); **after pickup**, dispatcher may choose **del final** or **dispatch to terminal**; **trip** cannot close with active undelivered freight **without** recorded custody/handoff; custody history **append-only** with **void/correct**; **trailer-to-trailer transfer** is **auditable**, never silent **`trailer_id` overwrite**; terminal freight state **more granular** than one vague “at yard”; **quantity-based transfer** reserved for later. **Breakdown/repower/recovery** model (original vs recovery trip, payroll guard): **`DECISION_13_TRIP_EXCEPTION_RECOVERY_REPOWER.md`** (**Decision 13**). **Decision 12 §J** bridges custody requirements; **Decision 12 §K**: minimum custody **`event_type`** candidates + slice discipline.

**Cross-check Decision 13:** Exception/repower flows **must** use **explicit custody** links (**Decision 13 §J**).

**Cross-check Decision 7:** **`Trip.status = completed`** = trip responsibility ended; **not** proof all member loads are commercially **delivered**.

**Cross-check Decision 9:** Return to **planning queue** after handoff/recovery is an **explicit** workflow; **not** automatic from **`Trip.status`**.

**Cross-check Decision 11:** **`Load.status`** = commercial/readiness; **not** terminal/custody location; **not** trip execution.

**Cross-check Slice 1:** **Do not** reintroduce **`Load.status = dispatched`** as custody/execution trigger.

### Decision 13 — Trip exception, recovery, repower workflow and payroll guard (**locked**)

Full specification: [`DECISION_13_TRIP_EXCEPTION_RECOVERY_REPOWER.md`](./DECISION_13_TRIP_EXCEPTION_RECOVERY_REPOWER.md).

**Summary:** Separates **trip exception truth**, **load commercial truth**, **custody**, and **payroll review**. **Trip exception ≠ automatic load cancel.** **Preserve** original **`Trip`** + **trip number**; **recovery** = **new** **`Trip`** + **new** number — **no** silent in-place assignment swap. **Five** base dispatcher options (**§C**). **Albany breakdown** + **planned terminal handoff vs failed final delivery** (**§G**). **Payroll guard:** incomplete **trip** responsibility → **`review_required`**; **no** automatic full or zero settlement until admin resolution (**§F**). **Recovery trip payroll** separate from original (**§I**). **Decision 10:** recovery assignment + **emergency override** still audited (**§L**). **Decision 8:** O/O agreed amount not blindly paid if assignment incomplete (**§M**). **Decision 12:** custody chain mandatory (**§J**).

**Cross-check Decision 11:** **`Load.status = cancelled`** only for **true** commercial cancel — **not** trip exception alone.

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
- **Exact custody `event_type` enum names** and **allowlist per implementation slice** — **Decision 12 §K** locks **principle** + **minimum candidates**; a **narrow** first slice is allowed, but **`trailer_transfer`** / **`picked_up_from_terminal`** are **required** by foundation for full terminal stories (**not** “optional forever” — see §4).
- **Exact trip completion gating**, **required custody event sequences**, and **RBAC** for closing trips with undelivered freight (**Decision 12** locks that gating **exists**).
- **Trip exception / recovery / repower — implementation** (**Decision 13** locks **principles**): exact **exception** table/schema, **reason-code** enum, **recovery** API + UI, **payroll review** table and **`review_required` block** mechanism, admin adjustment UX, **RBAC** for override/recovery/payroll decision, **custody** linkage for recovery events, **ELD/miles** evidence, **settlement/payrun** integration, driver **notifications**, **board/timeline** for issue/recovery (**Decision 13 §O**).
- **Future `assigned_responsibility_type` / completion-expectation** field (or equivalent) — **Decision 13 §H** preserves the concept; exact naming/schema TBD.
- **Dispatch package** persistence (tables, versioning, resend, stale-after-edit) — per **Decision 6**; **detailed design draft** in **`DECISION_8_DRIVER_DISPATCH_PACKAGE_SCHEMA.md`** (**Decision 8**, **NOT LOCKED**); schema/API TBD after sign-off.
- **Definition of “active execution”** for overlap / queuing guards — **partially locked** in **Decision 7** (`in_progress` from first signal); **scheduling conflict** vs **future assignment** **locked** in **Decision 10**; exact **date fields**, **timezone**, and **supervisor override UX** remain TBD.
- **Reconcile** **3L-C** granular trip-status proposal (`dispatched`, `in_transit`, `at_terminal`, etc.) with **Decision 7** **simple** `in_progress` model (mapping, sub-states, or deprecation).
- **Save Ready / Save Draft + `Load.status` + boards:** **Planning-queue semantics** **LOCKED** in **`DECISION_9_LOAD_READINESS_PLANNING_QUEUE.md`**; **target new-write `Load.status` values** (`draft` / `ready` / `cancelled`) and **load vs trip board direction** **LOCKED** in **`DECISION_11_LOAD_STATUS_TARGET_BOARD_MIGRATION.md`**; **legacy** read paths and **phased** migration remain **implementation**.

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
- Implement **Load Workspace** dispatcher actions per **`DECISION_6_DISPATCHER_LOAD_WORKSPACE_ACTION_MODEL.md`**; **do not** treat **Assign** as legacy **`Load.status = dispatched`** or as **custody** / **payroll**.
- **Do not** set **`Trip.status = in_progress`** (or treat trip as **actively executing**) from **assignment** or **dispatch package send** alone — **`DECISION_7_ACTIVE_EXECUTION_SIGNAL_MODEL.md`**.
- **Do not** mint or surface a **new Trip Number** per stop, pickup, delivery, or second pickup — **one** trip number per **Trip**; driver **dispatch package** uses that number as **primary** operational ID (**§4**, **Trip number rule**, + **Decision 6**).
- **Save Ready** (without explicit **trip** / **assign** / **Assign & Send** actions) **must not** be treated as creating a **trip**, **`TripLoad`** rows, **assignment**, **dispatch package send**, **`Trip.status = assigned`/`in_progress`**, **`Load.status = dispatched`**, **custody**, **payroll**, or **board rewrite** — **`DECISION_9_LOAD_READINESS_PLANNING_QUEUE.md`**.
- **Do not** **silently** accept **impossible** **future assignment** schedules when **Decision 10** applies (**first pickup** before **current expected completion** on **same** driver/truck/trailer) — **`DECISION_10_FUTURE_ASSIGNMENT_CONFLICT_GUARD.md`** (implementation **deferred**).
- **`Load.status` migration:** target **new-write** semantics and **boards** per **`DECISION_11_LOAD_STATUS_TARGET_BOARD_MIGRATION.md`**; **do not** treat **`Load.status = dispatched`** as a **new** execution trigger (**Slice 1**).
- **Exception / repower / recovery:** **do not** silently replace **original** trip **driver/truck/trailer** in place for **recovery** — **new** **`Trip`** + **new** trip number per **`DECISION_13_TRIP_EXCEPTION_RECOVERY_REPOWER.md`**. **Do not** auto-settle **full** or **zero** pay on **incomplete trip responsibility** without **`review_required`** / admin resolution (**Decision 13**).

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
