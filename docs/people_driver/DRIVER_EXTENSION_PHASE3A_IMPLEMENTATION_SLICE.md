# Phase 3A — Driver Extension Implementation Slice (Planning Report)

**Status:** Planning only. **No Alembic, no backend, no UI** from this document alone.

**Depends on:** `docs/DRIVER_EXTENSION_PHASE3A_FOUNDATION_LOCK.md` (accepted direction).

**Purpose:** Lock the **first schema-safe** driver-extension slice: exact candidate fields, table boundaries, requiredness, FK cautions, non-overlap with existing systems, and **recommended implementation order**—so a later implementation pass does not drift into pay, dispatch, or onboarding duplication.

---

## A. Exact Phase 3A field list (first schema-safe slice)

Only **non-overlapping** driver setup fields aligned with the foundation lock. **Excluded by definition:** compensation rates, payee wiring, `compensation_profiles`, trailer rent, dispatch pairing implementation, settlement integration.

| # | Logical field name | Type (conceptual) | Foundation § |
|---|-------------------|-------------------|--------------|
| 1 | `employment_relationship_type` | Enum: `company_driver`, `owner_operator` | Foundation §1 |
| 2 | `driver_operating_subtype` | Enum: `long_haul`, `city_local`, `shunt_yard` | Foundation §2 |
| 3 | `is_team_driver` | Boolean | Foundation §3 |
| 4 | `team_role_type` | Enum: `primary`, `co_driver` — **nullable** when not team | Foundation §3 |
| 5 | `provides_own_truck` | Boolean | Foundation §4 |
| 6 | `provides_own_trailer` | Boolean | Foundation §4 |
| 7 | `equipment_contribution_type` | Coarse enum (see below) | Foundation §4 |
| 8 | `insurance_commercial_approved` | Boolean (or tiny status enum: e.g. pending / approved / rejected — **product choice in implementation**) | Foundation §5 |

**`equipment_contribution_type` (recommended allowed values for first slice):**

- `company_equipment` — carrier provides tractor + trailer (driver uses company assets).
- `driver_truck_only` — driver provides tractor; trailer from company or not modeled here.
- `driver_truck_and_trailer` — driver provides both.
- `other` or `unspecified` — optional escape hatch if product needs it without opening rent math.

Exact spellings for DB/API are **implementation contract** details; semantics above are locked.

**Explicitly NOT in Phase 3A first slice (even if other docs once listed them):**

- `contractor` as `employment_relationship_type` — **later**, only if distinct from `company_driver` / `owner_operator` (foundation).
- `owner_operator` as a value of `driver_operating_subtype` — **forbidden** (foundation); use `employment_relationship_type = owner_operator` + `driver_operating_subtype = long_haul` | `city_local` | `shunt_yard`.
- Any **rate**, **percent**, **payee** pointer, **compensation_type**, **deduction**, **trailer rent** field — **out of scope** for this slice.

**Relationship note — older driver admin field lock:** `docs/DRIVER_ADMIN_CONFIG_PHASE1_FIELD_LOCK.md` describes a broader **driver admin configuration** set including **compensation and payee** fields. **Phase 3A first slice** intentionally implements **only** the foundation-aligned **setup/compliance** layer above. Compensation/payee fields from that document remain **deferred** to a **payee/compensation reconciliation** slice unless product explicitly merges scopes later.

---

## B. Ownership / table-boundary recommendation

### Conceptual home

- **Anchor:** **`Person`** (canonical human in tenant). Extension is **per** `(tenant_id, person_id)` for drivers who have **driver extension** meaning—typically where **`PersonRole.role_code = DRIVER`** and operational **`drivers`** row may exist.
- **Tenant scope:** Every row **must** include **`tenant_id`** consistent with composite tenant isolation elsewhere (`(tenant_id, person_id)` uniqueness for this extension).

### Recommended physical placement (later implementation)

- **Preferred:** A **dedicated tenant-scoped table** (name TBD, e.g. `driver_operational_extensions` or `driver_person_extensions`) with:
  - **PK:** surrogate `id` **or** composite uniqueness on `(tenant_id, person_id)`.
  - **FK:** `(tenant_id, person_id)` → **`people`** (or equivalent people table) with **ON DELETE** behavior defined in implementation (likely restrict or soft-handling—TBD).
- **Alternative (weaker):** Add columns to **`driver_profiles`** if product insists on a single “driver facts” table. **Caution:** `driver_profiles` today skews **license/compliance**; overloading with **commercial setup** without discipline blurs boundaries. If merged, **document** which columns are “intake/license” vs “3A extension” in the same table.

### Why this must **not** be authoritative on **`drivers`**

- **`drivers`** is the **operational roster projection** for dispatch (minimal, synced): putting **full** commercial/setup truth there makes the roster row a **second master** and invites drift from **`Person`**.
- **Thin projection rule:** `drivers` may **mirror** a few display fields for performance **only if** a written sync rule exists; **authoritative** setup belongs on **person-centered extension**, not on roster alone.

### Why this must **not** live in **payee / compensation** tables

- **Payee/compensation** answers **who gets paid** and **how much / which profile**—different domain.
- Mixing **employment relationship** and **equipment flags** into **`compensation_profiles`** couples **ops setup** to **pay runs** and blocks clear audit when pay rules change but setup does not (or vice versa).
- **Phase 3A extension** may **inform** future pay configuration **by reference** in a later slice; it does **not** store rates or payee keys in this slice.

---

## C. Required vs optional vs later

| Field | First slice — required? | Notes |
|-------|-------------------------|--------|
| `employment_relationship_type` | **Required** | Default at create may be product-defined; null not allowed once record is “committed.” |
| `driver_operating_subtype` | **Required** | Same. |
| `is_team_driver` | **Required** | Boolean; default `false` if product allows. |
| `team_role_type` | **Optional** | Required **only when** `is_team_driver = true`; must be **null** when single. |
| `provides_own_truck` | **Required** | Booleans with safe defaults (e.g. `false`) acceptable if product agrees. |
| `provides_own_trailer` | **Required** | Same. |
| `equipment_contribution_type` | **Required** | Can default to `company_equipment` or `unspecified` per product. |
| `insurance_commercial_approved` | **Optional in first slice** | If product wants a slimmer v1, ship nullable / “unknown”; else **required** with default `false`. |

**Later (not in first schema slice):**

- **`employment_relationship_type = contractor`** — add enum value only after distinct definition vs `company_driver` / `owner_operator`.
- **FK to co-driver `person_id`** — team pairing to another person.
- **FK to equipment assets** (truck/trailer units).
- **FK to payee** — belongs to compensation domain.
- **FK to terminal / dispatch home base** — when dispatch/ops model is locked.
- **History/audit tables** for high-impact edits — recommended before wide production use but can follow MVP.

---

## D. Relationship / FK cautions (what NOT to link yet)

Unless a **separate** slice locks the target entity and **delete/integrity** rules:

| Target | Link in Phase 3A first slice? | Rationale |
|--------|----------------------------------|-----------|
| **Teammate (other Person)** | **No** | Pairing is **operational** and may change in dispatch; onboarding-time “co-driver” without dispatch rules invites bad data. Optional **later** with dispatch-owned or HR-owned rules. |
| **Truck (equipment unit)** | **No** | Asset registry may not exist or differ by tenant; booleans + coarse type suffice for 3A. |
| **Trailer (equipment unit)** | **No** | Same. |
| **Payee** | **No** | Pay domain; violates boundary with `compensation_profiles` / payee ownership. |
| **Terminal / yard** | **No** | Unless terminal master is already a locked FK across the product for drivers—if not, **defer**. |

**Strong reason exception:** If the codebase **already** has a stable, tenant-scoped **`person_id`** FK pattern and product **only** needs a nullable “default co-driver” pointer in a **later** sub-slice—still **not** part of **Phase 3A first** schema slice as locked here.

---

## E. No-overlap check against existing systems

| System | What it owns | Why Phase 3A fields do not duplicate it |
|--------|----------------|----------------------------------------|
| **Onboarding (`PersonApplication`, intake)** | **Applicant-time** truth: what was submitted pre-hire; historical record. | 3A fields describe **post-approval / ongoing** driver **setup**, not the application PDF/intake snapshot. Promotion may **seed** defaults once; **authoritative** ongoing values live on extension. |
| **Payee / compensation (`compensation_profiles`, rates, payee)** | **Who is paid**, **how calculated**, **settlement lines**. | 3A has **no rates**, **no payee FK**, **no profile merge**—only structural labels (relationship, subtype, equipment contribution, insurance gate) for **ops/compliance**. |
| **Dispatch assignment truth** | **Current** load assignment, pairing on trip, equipment assignment. | 3A does not store **assignments**; `is_team_driver` / `team_role_type` are **configuration baselines**, not “who is on this load.” |

---

## F. Recommended implementation order (planning only)

1. **Field lock** — Product sign-off on §A + §C (this document + foundation lock); freeze enum values and requiredness.
2. **Table boundary lock** — Choose dedicated table vs `driver_profiles` extension (§B); document FK to `people` and uniqueness `(tenant_id, person_id)`.
3. **Schema slice** — Single Alembic (tenant) migration in a **future** PR, after the two locks above; still **not** part of this report’s deliverable.
4. **Backend** — Model, service, API for CRUD or patch of extension by `person_id` / driver context; validation enums; no payee writes.
5. **UI** — Admin driver setup screen (or section) bound to extension; no compensation panels in 3A slice unless scope explicitly expands (it should not).

---

## Stop rule

**Stop after this report.** No migration, no Python, no React until an explicit **“implement Phase 3A schema”** (or similarly scoped) task is opened.
