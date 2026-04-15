# Phase 3A — Driver Extension Schema Lock (Pre-Implementation Contract)

**Status:** Schema contract only. **No Alembic, no backend, no UI.**

**Depends on:** `docs/DRIVER_EXTENSION_PHASE3A_FOUNDATION_LOCK.md`, `docs/DRIVER_EXTENSION_PHASE3A_IMPLEMENTATION_SLICE.md` (accepted direction).

**Purpose:** Lock the **exact** relational shape, constraints, and validation intent for the **first** driver-extension table **before** any migration is written.

**Proposed physical table name (contract):** `driver_person_extensions` — tenant-scoped, person-centered extension row. Final naming may vary (e.g. prefix/suffix) but **semantics below are fixed**.

---

## A. Exact column-level schema proposal

All string enums use **stable DB values** matching API spelling (snake_case). **Eight business columns** plus identity, scope, and recommended audit columns.

| Column | Nullability | Value shape | Required vs optional (DB) | Notes |
|--------|-------------|-------------|---------------------------|--------|
| `id` | `NOT NULL` | Surrogate PK (e.g. `BIGINT` identity) | **Required** (system) | Primary key. |
| `tenant_id` | `NOT NULL` | `INTEGER` (or tenant FK type used elsewhere) | **Required** | Tenant scope; must match `people.tenant_id` for linked person. |
| `person_id` | `NOT NULL` | `BIGINT` (or person PK type used elsewhere) | **Required** | FK target: `people.id` (composite integrity with `tenant_id`). |
| `employment_relationship_type` | `NOT NULL` | Enum / check: `company_driver`, `owner_operator` only in v1 | **Required** | `contractor` **not** a valid value until a later slice adds it. |
| `driver_operating_subtype` | `NOT NULL` | Enum / check: `long_haul`, `city_local`, `shunt_yard` only | **Required** | **`owner_operator` forbidden** here—see foundation lock. |
| `is_team_driver` | `NOT NULL` | Boolean | **Required** | Default at insert: `false` (if product agrees). |
| `team_role_type` | **Nullable** | Enum / check: `primary`, `co_driver`, or `NULL` | **Optional** | Must be `NULL` when `is_team_driver = false`. |
| `provides_own_truck` | `NOT NULL` | Boolean | **Required** | Default at insert: `false` (if product agrees). |
| `provides_own_trailer` | `NOT NULL` | Boolean | **Required** | Default at insert: `false` (if product agrees). |
| `equipment_contribution_type` | `NOT NULL` | Enum / check: `company_equipment`, `driver_truck_only`, `driver_truck_and_trailer`, `unspecified` (and optionally `other` if product needs escape hatch) | **Required** | Coarse classification only; no rent/charge columns. |
| `insurance_commercial_approved` | **Nullable** OR `NOT NULL` with default | Boolean, or tiny enum later (e.g. `pending` / `approved` / `rejected`) | **Optional in v1** per implementation slice—nullable means “unknown”; if `NOT NULL`, default `false` | Product picks one representation before migrate. |

**Recommended (not counted in the eight business fields):**

| Column | Nullability | Value shape | Notes |
|--------|-------------|-------------|--------|
| `created_at` | `NOT NULL` | `TIMESTAMPTZ` | Server default `now()`. |
| `updated_at` | `NOT NULL` | `TIMESTAMPTZ` | Updated on row change. |

**Uniqueness and indexes (expectations):**

- **Unique constraint:** `(tenant_id, person_id)` — **exactly one** extension row per person per tenant.
- **Primary key:** `id` (or composite PK on `(tenant_id, person_id)` if product prefers—**one** of these patterns; uniqueness of tenant+person is **mandatory** either way).
- **Index:** supporting lookup by `tenant_id` + `person_id` (covered by unique index).
- **Foreign key:** `(tenant_id, person_id)` references **`people`** with composite `FOREIGN KEY (tenant_id, person_id) REFERENCES people(tenant_id, id)` **if** `people` is keyed that way in tenant schema; otherwise match **existing** people-table FK pattern in this codebase **exactly** at implementation time.

**No other columns** in Phase 3A v1 (no compensation, payee, asset FKs, terminal, teammate FK).

---

## B. Exact table contract

| Contract rule | Lock |
|---------------|------|
| **Tenant-scoped** | Every row has **`tenant_id`**; all queries and writes filter by tenant. |
| **Person-centered** | Row **belongs to one person** in that tenant via **`person_id`**; semantic meaning is “driver operational extension for this person,” not “for this roster row.” |
| **Cardinality** | **At most one** row per **`(tenant_id, person_id)`**; **unique** `(tenant_id, person_id)`. |
| **Relation to `people`** | Authoritative link is **`people`** (canonical person). Extension **does not** replace `people` columns. |
| **Separate from `drivers`** | **`drivers`** is the **operational roster projection** (dispatch-facing, minimal). This table is the **canonical store** for the eight Phase 3A fields. **`drivers` is not** the source of truth for these values. |
| **Separate from payee / compensation** | No `compensation_profiles` columns, no payee IDs, no rates. Pay domain remains **downstream** or **parallel**—not merged into this table in Phase 3A. |

---

## C. Validation rules (first slice, plain English)

1. **`employment_relationship_type`** must be **`company_driver`** or **`owner_operator`**. The value **`contractor`** is **not allowed** until implemented in a later slice.

2. **`driver_operating_subtype`** must be **`long_haul`**, **`city_local`**, or **`shunt_yard`**. The value **`owner_operator`** is **forbidden** on this column—owner-operator identity is expressed **only** via **`employment_relationship_type = owner_operator`**.

3. **`team_role_type`:**  
   - If **`is_team_driver`** is **false**, then **`team_role_type`** must be **null**.  
   - If **`is_team_driver`** is **true**, then **`team_role_type`** must be **`primary`** or **`co_driver`** (not null)—unless product explicitly allows “team but role TBD” as a temporary state (if so, document as an exception; default rule is **required when team**).

4. **`equipment_contribution_type`** must **align** with **`provides_own_truck`** and **`provides_own_trailer`** in a way the product defines, for example:  
   - **`company_equipment`** → normally **`provides_own_truck = false`** and **`provides_own_trailer = false`** (driver uses company assets).  
   - **`driver_truck_and_trailer`** → normally **`provides_own_truck = true`** and **`provides_own_trailer = true`**.  
   - **`driver_truck_only`** → normally **`provides_own_truck = true`** and **`provides_own_trailer = false`**.  
   If a write would create an **obvious contradiction** (e.g. `company_equipment` with both provides flags true), **reject** or **normalize** per product rule chosen at implementation—**no silent drift**.

5. **No FK** to teammate, truck unit, trailer unit, payee, or terminal in this slice—validation does not reference those entities.

---

## D. Projection rule (`drivers`)

- **`drivers`** remains a **thin roster projection**: identity/contact sync, operational flags as **already** designed for dispatch—not the **canonical** home for Phase 3A extension data.

- **If** anything is **projected** from `driver_person_extensions` into **`drivers`** in a later step, it must be **read-only mirror** for **display or dispatch hints** (e.g. a denormalized label), with **authoritative** values always read from **`driver_person_extensions`** (or via a single service that starts from extension).

- **Canonical extension truth** = **`driver_person_extensions`** row for `(tenant_id, person_id)`. **`drivers`** must not become the **editor** of Phase 3A fields.

- **No requirement** in Phase 3A to add columns to **`drivers`**; projection is **optional** and **downstream**.

---

## E. Non-goals (Phase 3A schema lock)

- **No** compensation fields (rates, types, percentages, deductions).
- **No** payee fields or FKs to payee.
- **No** FKs to equipment assets (truck/trailer units).
- **No** dispatch assignment or pairing behavior in this table.
- **No** settlement or pay-run logic.
- **No** Alembic migrations, **no** application code, **no** UI in this document—**contract only**.

---

## F. Ready-to-build checklist

Before opening an implementation task (migration + code), confirm:

- [ ] Product accepts **nullable vs NOT NULL** for `insurance_commercial_approved` (and boolean vs small status enum).
- [ ] Product accepts **defaults** for booleans and `equipment_contribution_type` on first insert (e.g. new driver seed).
- [ ] **Team rule** locked: is `team_role_type` **required** whenever `is_team_driver = true`, or is a temporary null allowed?
- [ ] **Equipment alignment** rule: exact matrix of allowed `(equipment_contribution_type, provides_own_truck, provides_own_trailer)` triples—or “reject on contradiction.”
- [ ] **Final table name** chosen (`driver_person_extensions` or approved alias).
- [ ] **FK definition** matches **actual** `people` table composite key pattern in tenant DB.
- [ ] **ON DELETE** policy chosen for person delete (restrict vs cascade vs soft-delete alignment with `people`).
- [ ] Overlap review: no duplicate of onboarding, payee, or dispatch truth—**§B** and **§D** acknowledged by implementer.

**Stop after this report.** Next step is implementation **only** when explicitly opened—not from this document alone.

---

## Implementation decisions locked (Phase 3A first slice)

The following were **resolved** at implementation time (see `docs/DRIVER_EXTENSION_PHASE3A_IMPLEMENTATION_REPORT.md`):

| Open item | Locked choice |
|-----------|----------------|
| `insurance_commercial_approved` | `NOT NULL`, default **`false`** |
| `team_role_type` | **Required** when `is_team_driver` is true (`primary` \| `co_driver`); **NULL** when not team; non-null forbidden when single-driver |
| Equipment vs flags | Strict matrix for `company_equipment`, `driver_truck_only`, `driver_truck_and_trailer`; **`unspecified`** unconstrained |
| Table name | **`driver_person_extensions`** |
| FK / ON DELETE | **`(tenant_id, person_id)` → `people(tenant_id, id)`** **`ON DELETE CASCADE`** |
