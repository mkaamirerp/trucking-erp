# Phase 3L-D — Owner decision checklist (before migration/schema)

**Purpose:** Lock choices from **3L-A**, **3L-B**, and **3L-C** so the first migration and API slices do not drift.  
**Status:** Report-only. Implementation still **not** started.

---

## Locked owner decisions so far

### Decision 1 — Trip terminal status name

Locked:

- Use `Trip.status = completed` as the positive terminal state for a trip container.
- Do not use `Trip.status = delivered`.

Reason:

- Trip completion is not the same as load delivery.
- A trip may complete when driver/equipment responsibility ends, even if freight is handed off to terminal/custody/another trip.
- `Load.status = delivered` remains the commercial/final receiver truth.
- Custody event `delivered` may still exist for receiver delivery proof.
- `Trip.status = completed` means the operational trip responsibility is finished.

### Decision 2 — Voided vs cancelled

Locked:

- Do not add `Trip.status = voided` in V1.
- Use `Trip.status = cancelled` for operational cancellations, mistakes, duplicate/accidental trips, broker/customer cancellations, driver unavailable, abandoned plans, and any cancellation before or after movement.

Cancellation history rules:

- Trip number is not reused.
- Record is not deleted.
- Store `cancelled_at`.
- Store `cancelled_by`.
- Store `cancel_reason`.
- Optional future `cancel_category`.
- Notes and audit trail required.

Cancellation/pay rules:

- Cancellation does not automatically mean no pay.
- If the truck moved before cancellation, ELD miles are evidence.
- Dispatch/owner/payroll must make a pay decision.
- Decision depends on company policy and driver type.

Driver/pay cases to support later:

1. Company driver paid by miles.
2. Owner-operator paid by miles.
3. Owner-operator paid by commission/percentage.

Future cancellation workflow should support:

- `movement_started` yes/no.
- `eld_miles_before_cancel`.
- `manual_miles_override`.
- pay decision options:
  - `no_pay`
  - `pay_eld_miles`
  - `pay_manual_miles`
  - `flat_amount`
  - `payroll_review`
- `pay_decision_reason` / note.
- `pay_decision_by_user_id`.
- `pay_decision_at`.

Important:

- No automatic pay decision should be encoded in `Trip.status`.
- Payroll/settlement policy handles money later.

### Decision 3 — Terminal table

Locked:

- Add a tenant-scoped terminal / yard location table in V1.
- Do not use free text as the custody terminal identity.
- Admin can create and manage terminals.
- Dispatch/custody UI should show a dropdown of terminal names.
- Backend should store `terminal_id` on custody events.

Minimum terminal fields:

- `id`
- `tenant_id`
- `name`
- `street`
- `city`
- `state_or_province`
- `postal_code`
- `country`
- `is_active`
- `created_at`
- `updated_at`

Dropdown display:

- Show terminal name only.

Examples:

- Mississauga
- Brampton
- Boston
- Quebec

Reason:

- Prevents duplicate/misspelled terminal identities.
- Supports clean custody history.
- Supports reporting by terminal.
- Supports future terminal/yard board.

---

### Decision 6 — Load workspace action model: Save Draft / Save Ready / Assign / Assign & Send

**Locked:** Dispatchers use a **canonical Load Workspace** with a top action model: **Save Draft**, **Save Ready**, **Assign**, **Assign & Send** (buttons or primary + menu). **Assign** = trip assignment / commitment only; **Assign & Send** = composite backend steps including **versioned dispatch package** to driver + audit. **Hard boundaries** and **queuing rules** per full doc.

**Full specification:** [`DECISION_6_DISPATCHER_LOAD_WORKSPACE_ACTION_MODEL.md`](./DECISION_6_DISPATCHER_LOAD_WORKSPACE_ACTION_MODEL.md)

---

## 1. Trip terminal status naming

| | |
|--|--|
| **Status** | **LOCKED** |
| **Decision needed** | For a **closed** trip **container**, should `Trip.status` use **`completed`**, **`delivered`**, or something else? |
| **Locked answer** | **`Trip.status = completed`** only; **do not** use **`Trip.status = delivered`**. |
| **Why** | Trip completion ≠ load delivery; operational responsibility can end with handoff. **`Load.status = delivered`** and custody **`delivered`** event handle commercial/receiver proof. |
| **Risk if undecided** | *(Resolved for V1 — see **Locked owner decisions §1**.)* |
| **Impact on schema/API** | Allowlist / CHECK / constants must include **`completed`** as terminal positive state; **`delivered`** must **not** appear on `Trip.status`. |

---

## 2. Voided vs cancelled

| | |
|--|--|
| **Status** | **LOCKED** |
| **Decision needed** | Introduce **`voided`** as a distinct `Trip.status` now, or use **`cancelled`** + audit/reason? |
| **Locked answer** | **No `voided` in V1.** Use **`cancelled`** for all cancellation cases; capture **`cancelled_at`**, **`cancelled_by`**, **`cancel_reason`** (+ optional **`cancel_category`**), notes, and audit. Future pay/cancellation workflow fields as in **Locked owner decisions §2**. |
| **Why** | Single cancel path reduces ambiguity; **`voided`** deferred unless legal/operational requires it later. |
| **Risk if undecided** | *(Resolved for V1 — see **Locked owner decisions §2**.)* |
| **Impact on schema/API** | No **`voided`** in trip status allowlist for V1; migrations/API eventually add **`cancelled_by`**, **`cancel_reason`**, etc., as specified — **not** automatic pay encoding on **`Trip.status`**. |

---

## 3. Terminal table

| | |
|--|--|
| **Status** | **LOCKED** |
| **Decision needed** | Add **`terminals`** (or **`yard_locations`**) in V1, or defer / use free text? |
| **Locked answer** | **Tenant-scoped terminal table required in V1** — not free-text custody identity; **`terminal_id`** on custody events; admin-managed rows; UI dropdown (**name** only); minimum fields per **Locked owner decisions §3**. |
| **Why** | Stable identity for custody, reporting, and future yard board; avoids misspellings/duplicates. |
| **Risk if undecided** | *(Resolved for V1 — see **Locked owner decisions §3**.)* |
| **Impact on schema/API** | New **`terminals`** (or equivalent) table with listed columns; FK **`load_custody_events.terminal_id`**; admin CRUD + list for dropdown; custody **`POST`** validates `terminal_id` belongs to tenant. |

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
| 1 | Terminal status name | **LOCKED** — `completed` only; not `delivered` on trip. |
| 2 | Voided vs cancelled | **LOCKED** — no `voided` in V1; `cancelled` + audit (`cancelled_by`, `cancel_reason`, …) per **Locked owner decisions §2**. |
| 3 | Terminal table | **LOCKED** — V1 tenant terminal table + `terminal_id` on custody; admin + name-only dropdown; no free-text terminal identity. |
| 4 | First transition edges | |
| 5 | Assignment before transition | |
| 6 | Load.status coupling | |
| 7 | dispatch_trips | |
| 8 | Custody v1 types | |
| 9 | trip_stops | |
| 10 | RBAC / audit minimum | |
| **11** | **Decision 6** — Load workspace (Draft/Ready/Assign/Assign&Send) | **LOCKED** — [`DECISION_6_DISPATCHER_LOAD_WORKSPACE_ACTION_MODEL.md`](./DECISION_6_DISPATCHER_LOAD_WORKSPACE_ACTION_MODEL.md) |

---

*End of Phase 3L-D checklist.*
