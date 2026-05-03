# Phase 3L-A — Trip execution / custody foundation (decision record)

**Type:** Report-first / implementation-facing decision record.  
**Scope:** Option A only. **No code, migrations, or dispatch/load workspace changes** in this phase.  
**Supersedes nothing:** Builds on `docs/TRIP_LIFECYCLE_TERMINAL_ROUTING_YARD_HANDOFF_DISPATCH_LOAD_TRANSFER_FOUNDATION.md` (large foundation) and `docs/PLANNED_TRIP_LIFECYCLE_MODULE_CLOSE.md` (3D–3K shipped).

---

## Executive summary of the existing foundation doc

`TRIP_LIFECYCLE_TERMINAL_ROUTING_YARD_HANDOFF_DISPATCH_LOAD_TRANSFER_FOUNDATION.md` establishes:

- **Trip** as the operational execution container (driver, truck, trailer, execution order); **Load** as commercial/broker truth (rates, docs, contractual stops).
- **Custody / operational location** as a third concern: freight is not always “on a trip” or “delivered”—it can be on trailer, staged at terminal, transferred trailer-to-trailer, etc.
- **Contractual stops** (`load_stops`) vs **operational sequencing** (trip-level stops or events)—must not be conflated; stops can interleave across loads on one trip.
- **Trip completion ≠ load delivered**; closing a trip with undelivered freight requires an **explicit handoff/custody** path (no “floating” freight).
- **Yard/terminal** must be a real custody location with **granular states** (not one vague `at_yard`).
- **Trailer-to-trailer transfer** must be an **auditable event**, not silent field overwrites.
- **Append-only (or void/correct) custody history** is recommended (`load_custody_events` / similar).
- **After pickup**, dispatch must support **final delivery vs dispatch to a selected terminal** as first-class branches.
- **Future schema sketch:** `trip_loads` (explicit link—now partially shipped), custody events, optional `trip_stops` / execution model.

This 3L-A record **sharpens** that narrative into **current vs future boundaries**, **recommended ownership** of status fields, a **proposed trip status ladder** (proposal only), **custody semantics**, **assignment rules**, **transition thoughts**, and **implementation ordering**—without implementing custody/terminal/handoff.

---

## 1. Current system boundary

### 1.1 What Trip supports today

- **Container lifecycle (tenant `trips` table):** `status` is effectively **`planned`** or **`cancelled`** for the planned-trip module (`app/constants/trip_dispatch.py`: `TRIP_CONTAINER_STATUS_PLANNED`, `TRIP_CONTAINER_STATUS_CANCELLED`).
- **Fields present:** `trip_number`, `job_type`, `driver_id`, `truck_id`, `trailer_id`, `assigned_at`, `cancelled_at`, plus legacy/debug `legacy_dispatch_trip_id`.
- **API (typical):** create planned trip, list, detail, add/remove load membership, cancel trip. **No** general PATCH for execution progression, **no** custody APIs.
- **Integration with legacy dispatch mirror:** Separate path (`dispatch_trips`, `TRIP_ALLOCATED_AT_LOAD_STATUS`, mirror sync rules)—still **load-status-driven** for when a **dispatch** trip row is minted/cleared; not the same as the new **planned container** lifecycle.

### 1.2 What `Load.status` still controls today

- **Authoritative operational states for the load row** used across intake, workspace, and board grouping:  
  `draft`, `ready`, `unassigned`, `assigned`, `dispatched`, `arrived_pickup`, `in_transit`, `arrived_delivery`, `delivered`, `issue_hold` (`app/schemas/load.py` `DISPATCH_STATUSES`).
- **Dispatch board columns** are keyed off **`Load.status`** (see §1.3).
- **Trip number on load / active trip mirror:** Legacy rules tie **minting** of dispatch-trip behavior to load entering **`dispatched`** (`TRIP_ALLOCATED_AT_LOAD_STATUS`); cancellation of **active** dispatch trip when load returns to pre-dispatch pool statuses is **load-status-driven** (`PRE_DISPATCH_TRIP_CANCEL_STATUSES`).

### 1.3 What the dispatch board still uses today

- **`GET /api/v1/dispatch/board`** returns a **dictionary of status keys → lists of `LoadResponse`** (`app/routers/dispatch.py`, `loads_service.list_loads_for_board`).
- **UI** (`DispatchPage.tsx`): ribbon tabs map to subsets of **`Load.status`** (e.g. unassigned, assigned, dispatched, in_transit, delivered, issue_hold). **Trip number** on cards is **read-only** context from the load row, not a trip-first grouping key.

### 1.4 What `trip_loads` means today

- **Source of truth** for **which loads are actively members of which planned trip container**: active membership = row with **`removed_at IS NULL`** (and consistent `status_within_trip` for active planned vs legacy paths).
- **`status_within_trip` today:** **`planned`** for memberships created in the planned-trip module; legacy/mirror paths use **`active`** / **`removed`** (`dispatch_trips` integration). Soft-remove sets membership to **`removed`** (and `removed_at`).
- **Not yet:** per-load execution progress inside a trip (e.g. “picked on this trip,” “delivered on this trip”) as distinct from load-level commercial status.

### 1.5 What `active_trip_id` means today

- **Backend-maintained mirror** on `loads`: points to the **planned trip** the load is actively attached to, derived from **active `trip_loads` membership** (not something the UI should “repair” or treat as authoritative over membership).
- **Product rule of thumb:** **`trip_loads` wins**; `active_trip_id` is for **read convenience** and pickers (see module-close doc).

---

## 2. Execution state ownership (recommended decisions)

| Question | Recommendation |
|----------|------------------|
| Does **execution status** for the **movement container** live on **`Trip.status`**? | **Yes, progressively.** `Trip.status` should become the **canonical container execution ladder** (planned → … → delivered / completed / cancelled) for the **new trip container**. It must **not** blindly duplicate every **`Load.status`** value 1:1, but it **summarizes** where the **trip’s operational responsibility** is in the lifecycle. |
| Does **commercial / dispatch row state** remain on **`Load.status`**? | **Yes, for the medium term.** Today's board, billing-adjacent workflows, and broker-facing language stay anchored on **load-level** statuses until a **controlled migration** introduces trip-first read-models. **Load.status** remains **commercial + operational truth for the contract row**; trip status is **container** truth. |
| Does **membership-specific** state belong on **`trip_loads.status_within_trip`**? | **Partially.** Today it encodes **membership phase** (planned vs active vs removed). **Recommended future use:** **membership role / progression relative to the trip** (e.g. still on trip, staged off trip at terminal, formally delivered on this trip) **where it is trip-relative** and should not overwrite **commercial** load state. **Do not** store **physical custody** as only a mutable string—pair with **events** (§4, §5). |
| What belongs in **future event / custody tables** instead of only mutable columns? | **Anything that must be auditable and time-ordered:** pickups, arrivals, terminal drops, staging, trailer A→B transfers, handoffs between trips, void/corrections. **Mutable columns** on trip/load may hold **current snapshot** for UI performance, but **events** are the **proof** and **history** (aligned with foundation doc §16–§17). |

**Non-decision (explicit):** Exact split between **`trip_stops`** vs **only custody events** for sequencing can stay **open** until schema design phase; this record only requires **do not conflate** `load_stops` with execution sequence.

---

## 3. Proposed future `Trip.status` ladder (proposal only — do not implement)

**Purpose:** Give a **shared vocabulary** for API/UI design later. Names can be adjusted; semantics matter.

| Proposed status | Container-level? | Notes |
|-----------------|------------------|--------|
| **`planned`** | Yes | Trip exists; membership may be edited (under policy). Matches today. |
| **`assigned`** | Yes | Driver/truck/trailer (or team) **committed** to this trip **for upcoming execution**; not necessarily rolling yet. |
| **`dispatched`** | Yes | **Released to execute** (may align with “rolled” / left gate—define in implementation). |
| **`in_transit`** | Yes | **Primary linehaul / road movement** phase (may subsume multiple load pickups/drops—detail in events). |
| **`at_terminal`** | Yes | **Trip-level** anchor: equipment/freight **at a company terminal/yard context** (granular **custody** still in events—not one ambiguous label). |
| **`delivered`** | Yes | **Recommended naming nuance:** Prefer **`completed`** for “assignment over” vs **`delivered`** meaning “all member loads commercially delivered”—**pick one convention** in open questions (§10). Foundation doc allows **trip complete while loads undelivered** if custody/handoff satisfied. |
| **`cancelled`** | Yes | **Planner cancellation** (matches today’s **`cancelled_at`** semantic). Distinct from … |
| **`voided`** | Yes (optional) | **Administrative never-happened** (wrong trip number minted, **no execution started**). Use **only** if legal/audit requires **hard separation** from **`cancelled`**. If not needed, **cancelled + reason** may suffice. |

**What should not directly mutate commercial loads**

- **Container-only transitions** (e.g. **`assigned` → `dispatched`** on **Trip**) should **not** auto-write broker rate, invoice state, or **contractual** stop list on **Load**.
- **Commercial milestones** (**POD**, **delivered** for billing, customer signature) remain **load-driven** unless a later **explicit rule** copies trip events into load status **via defined services** (future work).
- **Custody phases** (**on trailer vs staged**) should **`not`** be crammed into **`Trip.status` alone**—use **events** + possibly **load-level or membership-level** flags as **denormalized cache** only.

---

## 4. Custody / terminal model (report-only)

Definitions align with the foundation doc; **no implementation** here.

### 4.1 What is a **custody event**?

An **append-only operational fact** (or void/correct pair) that records a **change in who holds the freight or where it sits physically**: e.g. picked up onto trailer X, arrived terminal T on trailer X, unloaded/staged at T, transferred trailer X→Y, handed off from trip A to trip B or to terminal custody, delivered to consignee.

### 4.2 What is a **terminal / yard location**?

A **first-class location** (configurable **terminal/yard id**) representing company-controlled or contracted space where freight may **rest without an active road trip**, or **transfer between equipment**. **Not** a free-text stop note for this purpose.

### 4.3 Dispatch to terminal **after pickup**

Operations: after **commercial pickup** is recognized (load-level and/or event), dispatcher chooses **next movement intent**: **toward final receiver** vs **toward a selected terminal**. That choice should produce **trip execution intent updates** and eventually **custody events**, not only UI state.

### 4.4 Freight **dropped at terminal**

Record **arrival** and then either **remain on trailer at terminal**, **unload/stage**, or **transfer**—each is a **distinct custody state** (foundation doc: avoid single vague “at yard”).

### 4.5 **Another trip picks it up later**

**Active `trip_loads`** membership moves to a **new trip** (or **reactivated**) only with **explicit** workflow: prior trip **completed/handled**, custody shows **available for outbound**, new trip **assigned**—no silent reassignment.

### 4.6 **Trailer-to-trailer transfer**

**Explicit event**: from trailer A to B, with **who/when/where**, optional **authorization**. **Never** only overwrite **`trailer_id`** fields without history.

### 4.7 **Chain of custody proof**

Recommended proof bundle: **ordered custody events** per **load** (and references to **from_trip** / **to_trip**, **terminal**, **trailer**, **actor**, **timestamps**), plus **void/correct** records. **Trip timeline** can be a **projection** of these events + key trip milestones.

---

## 5. Load vs Trip vs TripLoad vs future custody — responsibilities

| Entity | Responsibility |
|--------|----------------|
| **Load** | **Commercial contract / broker truth:** broker identity, rate, references, **contractual** `load_stops`, documents, **commercial** lifecycle, **`Load.status`** for **today’s** dispatch board and intake. **Customer/broker deliverables** stay here. |
| **Trip** | **Operational movement container:** trip number, **assigned** driver/team, truck, trailer, **container execution** (`Trip.status` ladder when implemented), **trip completion policy** (future), **responsibility window**. **Does not replace** rate con or invoice. |
| **TripLoad** | **Membership and trip-relative state:** which loads are on the trip, order hints, **`removed_at`** / removal audit, **future:** progress vs this trip (e.g. delivered-on-trip flags **if** kept denormalized). **Source of truth** for **active membership** today. |
| **Future custody event** | **Audit trail of physical possession / location / transfers** tying **load** (and trips/trailers/terminals) to **time-ordered** facts; supports terminal, handoff, and trailer transfer **without** silent edits. |

---

## 6. Dispatch board implications (report only)

### 6.1 Why the **current** board must **not** be rewritten yet

- **All operational users** still navigate **load columns** keyed by **`Load.status`**; ripping or dual-writing would **break** trained workflows and **risk** inconsistent **trip vs load** truth before execution model exists.
- **Trip-first grouping** requires **agreed** read-model (§2–§3) and likely **new APIs**; doing UI first would **encode wrong assumptions**.

### 6.2 What a **future trip-first board** would need

- **Aggregate model:** trip header + nested active loads + **container status** + **custody summary** per load.
- **Policies** for **multi-load cards**, **terminal intent**, and **handoff** visibility.
- Possibly **dual view**: **classic load board** + **trip board** during transition (foundation doc §13).

### 6.3 **Read-model / API gaps** (current)

- Board: **`dict[load_status → LoadResponse[]]`** only; **no** `GET /dispatch/board-by-trip` or equivalent.
- Trips: **list/detail** by container; **no** execution transition endpoints; **no** custody projection.

### 6.4 **Avoid breaking** `/dispatch` flow

- Any new surfaces should be **additive** (new endpoints, optional tabs) until **explicit cutover**.
- **Do not** change **`list_loads_for_board`** grouping keys **without** a migration plan for **`Load.status`** vs **`Trip.status`**.
- **Load workspace** and **assignment strip** remain **load-centric** until assignment contract (§7) and **product sign-off**.

---

## 7. Assignment implications

### 7.1 Where **driver / truck / trailer** should live

- **Canonical for the trip container:** **`Trip.driver_id`**, **`Trip.truck_id`**, **`Trip.trailer_id`** (already on model) for **“who is running this movement.”**
- **Load row** may still hold assignment **for unplanned / legacy / single-load** flows until migration completes.

### 7.2 Should **Trip** assignment **sync back** to **Load** fields?

**Recommended default for future execution phase:** **One-way or explicit sync rules only:**

- When a load is **actively on a trip** and that trip **owns execution**, **prefer showing trip assignment** in read APIs; **avoid** silently overwriting **Load** assignment fields on every trip save **unless** a **documented rule** says loads on trip **must** mirror trip equipment for **board compatibility**.
- **Risk of bidirectional sync:** **Last-write-wins** bugs, dispatch board showing **different** driver than trip page.

### 7.3 Risks if **both** Load and Trip can assign equipment

- **Split brain:** board uses load, trip page uses trip **→** operational errors and payroll edge cases later.
- **Audit:** unclear who **authorized** equipment change.

### 7.4 **Source-of-truth rule (recommendation)**

- **During active planned trip membership:** **Trip assignment is authoritative for “movement.”**  
- **Load assignment fields** remain **authoritative for pre-trip / unassigned pool** and **commercial** contexts until a **later phase** explicitly **deprecates** dual storage or **denormalizes** read-models only.  
- **Document** this in a short **trip assignment contract** before large UI work (see §9).

---

## 8. State transition rules (possible future — not implemented)

**Legend:** States refer to **§3 proposal**. **Custody** gates in **italics** are placeholders for “required events recorded.”

### 8.1 Suggested **allowed** transitions (trip container)

| From | To | Guard / note |
|------|-----|----------------|
| `planned` | `assigned` | Resources committed; membership may still be constrained by policy. |
| `assigned` | `dispatched` | Release to execute. |
| `dispatched` | `in_transit` | Pickup / movement started (define vs load pickup event). |
| `in_transit` | `at_terminal` | Arrival at terminal context (details in custody). |
| `at_terminal` | `in_transit` | Depart terminal (reload / outbound). |
| `in_transit` | **`delivered` or `completed`** | **Only if policy satisfied:** either all loads delivered **or** **assignment complete +** *handoff/custody complete* (foundation §7). |
| `planned` | `cancelled` | Matches today’s cancel path. |
| `assigned` | `cancelled` | Allowed if **no irreversible execution** (define: e.g. not past first pickup event). |

### 8.2 **Forbidden / needs explicit handling**

- **`cancelled` →** any forward execution state (no “uncancel” without admin **void** path).
- **`delivered`/`completed` →** `dispatched` / `in_transit` without **corrective / admin** workflow.
- **Trip → `completed` with undelivered member loads** **without** *terminal/stage/transfer/handoff* events (foundation **locked** rule).
- Direct jumps **skipping** `dispatched` if business requires **dispatch** as legal checkpoint.

### 8.3 **Audit needs**

- **Who** transitioned trip state **when** (user id, optional reason).
- **Link** to **custody events** for terminal and transfer.
- **Correlation** with **`Load.status` changes** when **intentionally** coupled (logged side effects).

---

## 9. Minimum future implementation order (after this doc)

**Strictly sequential recommendation; each step can be shipped in small slices.**

| Step | Deliverable |
|------|-------------|
| **A** | **This decision record** (3L-A) — reviewed & **committed** when owners approve. |
| **B** | **Trip assignment contract** — short doc: authoritative fields, sync rules, UI expectations **before** PATCH trip assignment APIs. |
| **C** | **DB migrations** — `Trip.status` enum expansion + **custody event** table (minimal columns first) + indexes; **no** board rewrite. |
| **D** | **API transition endpoints** — guarded state machine for trip; **internal** consistency with `trip_loads` + mirror rules. |
| **E** | **Trip workspace execution UI** — read transitions + **timelines** when events exist; still **no** mandatory board change. |
| **F** | **Dispatch board read-model** — **additive** trip aggregation / second tab; **classic** load board remains until cutover. |

**Custody/terminal/handoff behavior** rolls out **inside C–E** in **thin slices** (event types one at a time), not as a big-bang.

---

## 10. Open questions (need owner approval before implementation)

1. **`delivered` vs `completed` on Trip:** Should **`delivered`** mean **all member loads commercially delivered**, and **`completed`** mean **assignment ended** (possibly with freight at terminal)? Or single terminal state with **policy enum**?
2. **`voided` vs `cancelled`:** Is **`voided`** required for **audit**, or is **`cancelled` + category/reason** enough?
3. **Trip completion policy default** per tenant: **`FINAL_DELIVERY`** vs **`ASSIGNMENT_COMPLETE`** (foundation §6)—what is **system default** at first ship?
4. **`Load.status` vs trip execution coupling:** When trip enters **`in_transit`**, **must** member loads auto-transition certain **`Load.status`** values, or **event-driven** only with **explicit** mapping table?
5. **Granularity of `at_terminal`:** Minimum **custody sub-states** for v1 (on trailer / staged / transfer pending)?
6. **`trip_stops` table vs events-only:** Do we need **materialized trip stop sequence** in v1, or **only custody events + projections**?
7. **Role permissions:** Who may **close trip with undelivered freight** (dispatcher only? **Two-person** rule?)—affects §8 guards.
8. **Legacy `dispatch_trips` / mirror:** Long-term **deprecation** plan vs **parallel** operation—when does **new trip container** subsume old trip number minting at **`dispatched`**?
9. **Multi-stop interleaving:** v1 scope—**display-only** merged timeline vs **editable** trip stop list?
10. **Payroll/settlements touchpoints:** Confirm **no** payroll changes in execution phases until **separate** sign-off (this doc assumes **out of scope** for implementation).

---

## References

- `docs/TRIP_LIFECYCLE_TERMINAL_ROUTING_YARD_HANDOFF_DISPATCH_LOAD_TRANSFER_FOUNDATION.md` — extended principles and sketches.
- `docs/PLANNED_TRIP_LIFECYCLE_MODULE_CLOSE.md` — shipped 3D–3K behavior and **`active_trip_id`** caveat.
- `app/constants/trip_dispatch.py`, `app/models/trip.py`, `app/routers/dispatch.py`, `app/services/loads.py` (`list_loads_for_board`), `app/schemas/load.py` (`DISPATCH_STATUSES`).

---

*End of Phase 3L-A decision record. **Not committed** until explicitly approved by maintainer.*
