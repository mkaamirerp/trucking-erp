# TruckERP — Decision 12 / Terminal, yard, and custody foundation consolidation

**Status:** **LOCKED** — consolidation of existing business rules onto the **active trip execution / custody decision spine**; **not** a replacement for the full background document.

**Source foundation (detailed background):** [`TRIP_LIFECYCLE_TERMINAL_ROUTING_YARD_HANDOFF_DISPATCH_LOAD_TRANSFER_FOUNDATION.md`](./TRIP_LIFECYCLE_TERMINAL_ROUTING_YARD_HANDOFF_DISPATCH_LOAD_TRANSFER_FOUNDATION.md)

**Related:** `TRIP_EXECUTION_CUSTODY_MASTER_INDEX.md`, **Decisions 6–11**, `PHASE3L_D_OWNER_DECISION_CHECKLIST.md`, `PHASE3L_C_TRIP_EXECUTION_SCHEMA_API_PLAN.md`, **Decision 3** (terminal table — 3L-D locked owner decisions).

---

## A. Purpose

**Decision 12** consolidates the **existing** terminal / yard / custody / handoff / transfer **foundation** into the **active** trip execution and custody **decision spine**.

**This document does not replace** [`TRIP_LIFECYCLE_TERMINAL_ROUTING_YARD_HANDOFF_DISPATCH_LOAD_TRANSFER_FOUNDATION.md`](./TRIP_LIFECYCLE_TERMINAL_ROUTING_YARD_HANDOFF_DISPATCH_LOAD_TRANSFER_FOUNDATION.md). That file remains the **detailed** source for routing, yard handoff, dispatch, and load-transfer **business logic**.

**Reason:** The foundation already captured the **real-world operations model**. The **master index** and **owner checklist** must **explicitly** show which rules are **locked** so implementation does not treat them as vague future ideas.

---

## B. Source-of-truth relationship

| Document | Role |
|----------|------|
| **`TRIP_LIFECYCLE_TERMINAL_ROUTING_YARD_HANDOFF_DISPATCH_LOAD_TRANSFER_FOUNDATION.md`** | **Detailed background** — terminal routing, yard handoff, dispatch, load transfer. |
| **Decision 12 (this doc)** | **Concise locked record** on the **implementation spine** — summarizes **locked** principles and **links** to the source. |

**Do not** duplicate the entire foundation doc here.

---

## C. Locked principles (drawn from existing foundation)

The following are **LOCKED** for product and documentation alignment:

1. **Trip** is the **operational execution** container.
2. **Load** is the **commercial / broker / customer** truth.
3. **Trip completion** is **not** the same as **Load delivered**.
4. A **Trip** may **complete** while one or more **Loads** remain **undelivered**, **only if** explicit **custody/handoff** state is **recorded**.
5. A **Load** may remain **active** across **multiple Trips** until final delivery/close.
6. **Yard/terminal** is a **real custody location**, not merely a note.
7. **“At yard”** is **too vague**; terminal/yard state needs **more granular** meaning.
8. **Trailer-to-trailer transfer** must be **explicit** and **auditable** — **never** silent overwrite of trailer identity.
9. **Terminal routing after pickup** must support either: **deliver to final receiver**, or **dispatch to selected terminal / yard**.
10. If **dispatch to terminal** is chosen, terminal choice must be **structured** — **not** free-text-only identity.
11. **Custody/movement history** must be **append-only** / **audit-safe**.
12. **Corrections** use **void/correct** pattern — **not** silent hard-delete or overwrite of history.
13. A **driver** must **not** unilaterally **complete** a trip with **active undelivered freight** unless **required** handoff/custody **workflow** is satisfied (product/RBAC details TBD).
14. **Trip-to-trip continuation** uses **explicit** remaining-stop / carry logic — **not** silent automatic inheritance of operational state.
15. **Schema direction** leaves room for **future quantity-based** transfers, even if **V1** is **full-load** transfer only.
16. **Load**, **Trip**, and **custody/audit** timelines are **separate** but must remain **reconcilable** (no silent disappearance) — architecture home: [`trip-foundation.md`](./trip-foundation.md) §1A; Decision 12 stays focused on terminal/custody enforcement of that continuity.
17. **TripLoad** open **planned** may coexist with open **active** for the same Load (yard next-leg reservation). Completing / handing off Trip A’s membership does **not** auto-activate Trip B; custody/handoff is recorded separately; activation of B is explicit. Membership cardinality and open≠active: [`trip-foundation.md`](./trip-foundation.md) §1A.

---

## D. V1 custody model (conceptual — not final DDL)

**Locked concept:** Custody / location changes are recorded as **append-only events**.

A custody event **may reference** (conceptual fields — **do not implement** as mandatory columns yet):

- `tenant_id`, `load_id`, `trip_id`, `from_trip_id`, `to_trip_id`
- `terminal_id` / yard / structured location id
- `from_trailer_id` / `to_trailer_id`
- `from_driver_id` / `to_driver_id`, `from_truck_id` / `to_truck_id`
- `event_type`, `event_time`, `actor_user_id`, `source`, `notes`
- void/correction fields
- optional **quantity** / **quantity_unit** placeholders for **future**

---

## E. Terminal / yard location rule

**Locked:**

- A terminal/yard must be a **real structured location**.
- **Tenant-scoped terminal table** direction (aligned with **3L-D Decision 3**):  
  `id`, `tenant_id`, `name`, `street`, `city`, `state_or_province`, `postal_code`, `country`, `is_active`, `created_at`, `updated_at`
- **UI:** dropdown shows **terminal name**; **backend** custody events store **`terminal_id`** — **not** free-text as the identity of “which terminal.”

**Examples (names):** Mississauga, Brampton, Quebec, Boston.

---

## F. Trip completion with undelivered freight

**Locked:** A trip **cannot close** with **active undelivered freight** unless an **explicit custody/handoff** event exists that **accounts** for the freight’s **custody/location**.

**Valid examples** (non-exhaustive):

- Dropped **loaded trailer** at terminal  
- **Unloaded/staged** at terminal  
- **Handed off** to terminal custody  
- **Transferred** to another trailer  
- **Attached** to a new trip / reassignment **with** explicit custody state  

**Invalid:**

- **`Trip.status = completed`** while freight is **active** and **no** custody/handoff chain exists  
- Load “**lost**” or **floating** with **no** custody owner  

**Plain example:** O/O picks up two loads in Boston, brings them to **Mississauga terminal**, assignment ends. **Trip A = completed.** Loads **not** commercially **delivered**. **Custody event** records terminal handoff/drop. Later **Trip B/C** continues final delivery.

---

## G. Terminal routing after pickup

**Locked:** After pickup, dispatcher can choose **next movement intent**:

1. **Deliver to final receiver**, or  
2. **Dispatch to terminal / yard**

If **dispatch to terminal**:

- Dispatcher selects terminal from **configured** list  
- Creates **structured** execution/custody intent — **not** only free-text  

**Normal branch**, not only “exception.”

**Example:** Load picked up Boston → either **direct to Toronto receiver** or **dispatch to terminal: Mississauga**. Trip may **complete** at terminal while final receiver still **pending**.

---

## H. Terminal/yard state granularity

**Locked:** Do **not** rely on one vague label such as **`at_yard`**.

Prefer **more precise** concepts, e.g.:

- `at_terminal_on_trailer`  
- `at_terminal_staged`  
- `at_terminal_transfer_pending`  
- `transferred_waiting_dispatch`  
- `attached_to_next_trip`  

**Exact enum names** can be finalized in implementation — **principle** is **locked**: terminal/yard freight state must be **more granular** than a single vague **at yard** label.

---

## I. Trailer-to-trailer transfer

**Locked:**

- **Trailer-to-trailer transfer** is a **first-class auditable** concept.
- Must record conceptually: `load_id`, `from_trailer_id`, `to_trailer_id`, terminal/location, `event_time`, actor/user, reason/notes; optional quantity **later**.
- **Must not** be modeled by **silently overwriting** `trailer_id`.
- **V1** may support **whole-load** only; schema **direction** allows **future** partial quantity / skid / pallet transfer.

---

## J. Repower / breakdown / recovery (bridge to Decision 13)

Breakdown, **driver unavailable**, trailer issue, accident, border delay, **repower** — **must not** be modeled **only** as **`Load.status`**.

These are **Trip exception / recovery** workflows. **Business model and payroll guard** are **LOCKED** in **`DECISION_13_TRIP_EXCEPTION_RECOVERY_REPOWER.md`** (**Decision 13**). **Decision 12** still requires **explicit custody/handoff** facts for any handoff or recovery chain (**Decision 13 §J**).

Illustrative responses (aligned with Decision 13):

- **Commercial load** may stay **active**  
- **Original** **Trip** is **preserved**; **recovery** uses a **new** **Trip** + **new trip number**  
- **Custody/handoff/recovery** events  
- **Reassign/repower** to another trip; return load to **planning queue**; **`Load.status = cancelled`** only if broker load **truly** cancelled  

**Decision 12** does **not** replace **Decision 13** for exception/repower/repay rules.

---

## K. Event types — principle vs first allowlist slice

**Principle (locked):** Custody events are **required** for truthful location/custody; chain is **append-only**; final **write-path** **`event_type` allowlist** is finalized during schema/API work and **cannot violate** this foundation.

**Minimum V1 *candidate* types** (names may adjust in implementation):

- `picked_up`, `arrived_terminal`, `dropped_at_terminal`, `staged_at_terminal`, `handoff`, `trailer_transfer`, `picked_up_from_terminal`, `delivered`

**Problem/recovery candidates (later):** e.g. `breakdown`, `repower_requested`, `repower_completed`, `recovery_started`, `recovery_completed`

**Slice discipline:** **3L-D §8** may still recommend shipping a **narrow first allowlist** (e.g. four types) for a **thin** first release — **not** because **`trailer_transfer`** or **`picked_up_from_terminal`** are **optional forever**; the foundation **requires** them for full terminal and transfer stories. **Expand** the allowlist in **later** slices with validation/UI. See **Decision 12** + **`PHASE3L_D`** §8 reconciliation note.

---

## L. Relationship to `Load.status` and `Trip.status`

| Cross-check | Rule |
|-------------|------|
| **Decision 11** | **`Load.status`** = commercial/readiness — **not** sole carrier of terminal/custody location. |
| **Decision 7** | **`Trip.status = completed`** = trip **responsibility ended** — **not** “all loads commercially delivered.” |
| **Decision 9** | Return load to **planning queue** after handoff/recovery is an **explicit** workflow — **not** automatic from **`Trip.status` alone**. |
| **Slice 1** | **`Load.status = dispatched`** is **not** a custody/execution **trigger** for **new** writes. |

---

## M. What Decision 12 does **NOT** do

Decision 12 **does not**:

- Implement terminal table, custody table, routing UI, trailer transfer UI  
- Implement trip exception/repower workflow  
- Rewrite dispatch board  
- Change **`Load.status`** / **`Trip.status`** in code  
- Create migrations  
- Delete old docs  

It **only** **consolidates** and **locks** foundation rules on the **current decision spine**.

---

## N. Open items (after Decision 12 — implementation detail)

Remain **open** (non-exhaustive):

- Exact custody **`event_type` enum** strings and CHECK/allowlist  
- **First** custody implementation slice (which types ship first)  
- Terminal table **migration** details  
- Terminal **dropdown / admin UI**  
- Trip completion **gating** and required event **count**  
- **RBAC** for closing trips with undelivered freight  
- Trailer transfer **UX**  
- Repower/breakdown/recovery **workflow** (**separate decision**)  
- Quantity transfer behavior  
- Timeline/read-model **projection**  
- Board **integration**  

**No longer “open” as principles** (now **locked** by Decision 12 + foundation):

- Whether terminal/yard is a **real** custody location  
- Whether trip completion can **differ** from load delivery  
- Whether **handoff/custody** is required to complete a trip with undelivered freight  
- Whether trailer transfer must be **auditable**  
- Whether a load can **span** multiple trips  

---

*End of Decision 12 — terminal / yard / custody foundation consolidation.*
