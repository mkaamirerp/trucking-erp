# Phase 3L-D — Owner decision checklist (before migration/schema)

**Purpose:** Lock choices from **3L-A**, **3L-B**, and **3L-C** so the first migration and API slices do not drift.  
**Status:** Report-only. Implementation still **not** started.

---

## 1. Trip terminal status naming

| | |
|--|--|
| **Decision needed** | For a **closed** trip **container**, should `Trip.status` use **`completed`**, **`delivered`**, or something else? |
| **Recommended answer** | **`completed`**. |
| **Why** | Matches **3L-A / 3L-C**: **`delivered`** belongs on **loads** and custody events; using **`delivered`** on the trip blurs “all freight commercially delivered” vs “assignment / responsibility ended.” |
| **Risk if undecided** | Inconsistent APIs, wrong UI labels, and accidental coupling to **`Load.status == delivered`**. |
| **Impact on schema/API** | Allowlist / CHECK / constants must include **`completed`** as terminal positive state; **`delivered`** omitted from `Trip.status` unless product overrides. |

---

## 2. Voided

| | |
|--|--|
| **Decision needed** | Introduce **`voided`** as a distinct `Trip.status` now, or **defer** and use **`cancelled`** + reason/category? |
| **Recommended answer** | **Defer `voided`** unless operational or legal requires a hard separation **immediately**. |
| **Why** | **3L-A** treats **`voided`** as optional; **`cancelled`** + **`cancelled_at`** + notes often suffice for v1. |
| **Risk if undecided** | Two “cancel-like” states without rules → bad reports and confused transitions. |
| **Impact on schema/API** | Deferring avoids extra enum value, migration branching, and permission rules; if **`voided`** is added later, expand allowlist and state machine in one focused change. |

---

## 3. Terminal table

| | |
|--|--|
| **Decision needed** | Add **`terminals`** (or **`yard_locations`**) in the **first** tenant migration that introduces custody, or **defer** and store free-form / payload only? |
| **Recommended answer** | **Add a small tenant-scoped terminal table** if **custody at terminal** is in **v1** (e.g. **`arrived_terminal`**, **`dropped_at_terminal`**). |
| **Why** | **3L-C** flags no first-class terminal today; structured **`terminal_id`** improves reporting, deduplication, and RBAC. Defer only if v1 is **road-only** events with no terminal routing. |
| **Risk if undecided** | Painful backfill from JSON blobs; inconsistent terminal identity across events. |
| **Impact on schema/API** | New table + FK on **`load_custody_events.terminal_id`**; optional seed/migrate; **`GET`** filters by terminal. |

---

## 4. First execution transition edges

| | |
|--|--|
| **Decision needed** | Which **`Trip.status`** transitions ship in the **first** execution slice? |
| **Recommended answer** | **`planned` → `assigned`** **only** first; **`assigned` → `dispatched`** (and beyond) **later**, with custody/guards when ready. |
| **Why** | Smallest behavioral change; exercises state machine + audit without touching **load dispatch** or **`dispatch_trips`** semantics. |
| **Risk if undecided** | Shipping **`dispatched`** or **`in_transit`** too early invites accidental **`Load.status`** coupling or mint bugs (**3L-C §7**). |
| **Impact on schema/API** | Transition endpoint initially allows **one** edge; expand allowlist per release; tests stay narrow. |

---

## 5. Assignment endpoint first?

| | |
|--|--|
| **Decision needed** | Implement **`PUT /api/v1/trips/{id}/assignment`** **before** **`POST …/transition`**, or the reverse? |
| **Recommended answer** | **Yes — assignment first** (per **3L-C** slice **C** before **D**). |
| **Why** | **3L-B**: movement authority lives on the trip; operators need stable driver/truck/trailer before status transitions mean much; simpler RBAC and audits. |
| **Risk if undecided** | Transitions bundled with assignment payloads → fat endpoints and unclear audit. |
| **Impact on schema/API** | Ship **PUT assignment** with validation + actor metadata; transition body stays **`to_status` + reason** only. |

---

## 6. Load.status coupling

| | |
|--|--|
| **Decision needed** | Should **trip** transitions **automatically** update **`Load.status`** for member loads in **v1**? |
| **Recommended answer** | **No** in v1 (default **decoupled**). |
| **Why** | Board is **load-keyed**; hidden updates confuse dispatch; risks unintended **`dispatch_trips`** interactions (**3L-C §7**). |
| **Risk if undecided** | Silent board moves, double-mint, or contradicting **3L-B** effective-assignment expectations. |
| **Impact on schema/API** | Transition service **must not** call load status updates unless a **future** explicit flag/feature documents the mapping; tests assert **no** `Load.status` change by default. |

---

## 7. `dispatch_trips` interaction

| | |
|--|--|
| **Decision needed** | When **`Trip.status`** becomes **`dispatched`** (future slice), should the system **create or update** **`dispatch_trips`** (today driven largely by **`Load.status` → `dispatched`**)? |
| **Recommended answer** | **No** in v1 — **do not** auto-wire new trip execution **`dispatched`** to the existing load-status **`dispatch_trips`** path. |
| **Why** | **3L-C §7**: today **`load.status` → `dispatched`** triggers trip number behavior on the **legacy** path; automatic linkage risks **double-mint** or competing rows. |
| **Risk if undecided** | Data corruption, duplicate trip numbers, broken mirror logic. |
| **Impact on schema/API** | Execution transition code paths stay **separate** from **`dispatch_trips`** until a **designed** unification (explicit **3L-A** follow-up). |

---

## 8. Custody event v1 scope

**Decision needed:**  
Which **`event_type`** values are in the first custody write path and validation?

**Recommended answer:**  
Use only these four in v1:

- **`picked_up`**
- **`handoff`**
- **`arrived_terminal`**
- **`dropped_at_terminal`**

**Defer:**

- **`picked_up_from_terminal`**
- **`trailer_transfer`**

**Why:**  
This keeps the first custody slice small while covering the main terminal/handoff story. Trailer transfer needs extra trailer-pair validation and clearer UI. Picked-up-from-terminal can be phase 1b when outbound terminal workflow is implemented.

**Risk if undecided:**  
Schema/API may allow too many event types before product flow and validation rules are clear.

**Impact on schema/API:**  
`event_type` allowlist or CHECK should include only the v1 types at first. **`POST`** custody event should reject unknown event types until intentionally enabled. Timeline can still be designed to support later event types.

---

## 9. Trip stops

| | |
|--|--|
| **Decision needed** | Introduce **`trip_stops`** table in the **first** execution migration, or **defer**? |
| **Recommended answer** | **Defer**; use **custody events** + **timeline projections** first (**3L-A** open question, **3L-C §2.2**). |
| **Why** | Operational sequencing vs **contractual** `load_stops` must not be rushed; events give an audit trail without committing to stop-row CRUD. |
| **Risk if undecided** | Premature **`trip_stops`** may duplicate events or fight custody model. |
| **Impact on schema/API** | Smaller first migration; **`GET /timeline`** merges status events + custody only; **`trip_stops`** is a later additive migration if needed. |

---

## 10. RBAC / audit

| | |
|--|--|
| **Decision needed** | What **minimum** audit fields are required for **assignment** and **transition** (and custody writes) in v1? |
| **Recommended answer** | **`actor_user_id`**, **`event_at`** / server **`recorded_at`**, **`reason`** or **`notes`**, **`source`** (e.g. `dispatcher_ui`, `api`); optional **`trip_status_events`** row per transition. Central audit log integration **later**. |
| **Why** | Meets **3L-A** audit expectations without blocking on a global audit service; **3L-B** implies assignment changes must be traceable before payroll. |
| **Risk if undecided** | Disputes and compliance gaps; no way to reconstruct who closed a trip. |
| **Impact on schema/API** | Columns on **`trip_status_events`** and **`load_custody_events`**; request bodies accept **`reason`** / **`source`**; responses echo persisted metadata. |

---

## Sign-off block (for owner)

| # | Topic | Owner choice (agree / override) |
|---|--------|-----------------------------------|
| 1 | Terminal status name | |
| 2 | Voided | |
| 3 | Terminal table | |
| 4 | First transition edges | |
| 5 | Assignment before transition | |
| 6 | Load.status coupling | |
| 7 | dispatch_trips | |
| 8 | Custody v1 types | |
| 9 | trip_stops | |
| 10 | RBAC / audit minimum | |

---

*End of Phase 3L-D checklist.*
