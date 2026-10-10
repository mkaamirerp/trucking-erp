# Driver Admin Configuration — Phase 1 Field Lock (Design Report)

**Note for Cursor:** This document is a **design-only, decision-oriented** lock for phase 1. Keep it detailed and strict. Do **not** add implementation code, pseudo-code, or vague summaries. Do **not** drift into phase 2 fields. This report must be **strict enough that Alembic can be designed from it next**—without guessing beyond the approved foundation logic.

## 1. Purpose

This report **locks the first implementation slice** for **driver admin configuration** in TruckERP: the exact fields, requiredness, value shapes, table ownership, and foreign-key direction **before** migration, backend contracts, or UI are built.

**Scope boundaries (read carefully):**

- **Phase 1 only.** Anything not listed in the phase-1 field set is **out of scope** for this slice unless explicitly named as a non-goal.
- **No implementation yet.** This file does not prescribe Alembic revisions, SQLAlchemy models, API routes, Pydantic schemas, or UI. It exists so those can be built **without drift**.
- **No guessing beyond foundation logic.** Decisions here align with the onboarding/admin configuration foundation and operating-model documents; do not invent new business rules here.
- **Tenant-safe and person-centered.** All business truth for this slice is scoped by tenant and anchored on the **approved driver person**, not on dispatch roster convenience rows alone.

---

## 2. Exact first-phase field list

The following **thirteen** fields are the **only** fields locked for phase-1 driver admin configuration. Each must be stored on the **new tenant-scoped, person-centered driver admin config record** (see §4), not spread across `people`, `person_roles`, `driver_profiles`, or `drivers` as the authoritative home for commercial/operational setup.

---

### 2.1 `employment_relationship_type`

| Attribute | Lock |
|-----------|------|
| **Business meaning** | The high-level **business relationship** between the carrier and this driver/operator: whether they are compensated as a **company driver** (direct employment-style relationship with the carrier) or as an **owner-operator** (settlement-style relationship). This is the primary branch for downstream pay and settlement behavior—not the same as “role = driver” in RBAC. |
| **Required at approval** | **Yes.** Must be set when admin completes driver business setup at approval (or first admin configuration of that driver). |
| **Editable later** | **Yes, but restricted.** Changes alter pay/settlement semantics; later implementation should treat edits as **high-impact** (audit, confirmation, or controlled workflow). |
| **Allowed value shape** | Coded enum (exact DB/API spelling TBD in a later contract pass). Phase-1 allowed values: see §6. |
| **Must not be confused with** | **Person role** (e.g. “is this person a DRIVER?”). **Compensation type** (hourly vs per mile vs commission). **Payee type** (who gets paid)—related but answers a different question. |

---

### 2.2 `driver_operating_subtype`

| Attribute | Lock |
|-----------|------|
| **Business meaning** | How this driver **operates day to day** for dispatch and equipment assumptions: long-haul company, city/local, shunt/yard, or owner-operator operating pattern. Aligns with operating-model distinctions; drives assignment hints and equipment expectations—not license class alone. |
| **Required at approval** | **Yes.** |
| **Editable later** | **Yes**, with care and audit (dispatch and equipment rules depend on it). |
| **Allowed value shape** | Coded enum. Phase-1 allowed values: see §6. |
| **Must not be confused with** | **Employment relationship** (company vs O/O is separate from long-haul vs city). **Compensation type**. **Person role**. |

---

### 2.3 `is_team_driver`

| Attribute | Lock |
|-----------|------|
| **Business meaning** | Whether this driver is configured to work in **team mode** (vs single) as a **baseline** operational flag—not “is there a co-driver on this specific trip.” |
| **Required at approval** | **Yes.** |
| **Editable later** | **Yes.** |
| **Allowed value shape** | Boolean (or strict two-value enum equivalent). **Recommended:** boolean for phase 1. |
| **Must not be confused with** | **Current trip team pairing**; **permanent teammate link** (no FK in phase 1); **team_role_type** (not in phase-1 field set). |

---

### 2.4 `compensation_type`

| Attribute | Lock |
|-----------|------|
| **Business meaning** | The **primary earning model** for base calculation: hourly, per mile, or commission. Controls which **rate** fields are active. Does **not** include deductions or recurring charges (phase-1 non-goals). |
| **Required at approval** | **Yes.** |
| **Editable later** | **Yes**, with care and audit (which rate fields apply changes). |
| **Allowed value shape** | Coded enum. Phase-1 allowed values: see §6. |
| **Must not be confused with** | **Employment relationship type**; **payee type**; **deductions** (fuel, parking, insurance, trailer rent rules). |

---

### 2.5 `hourly_rate`

| Attribute | Lock |
|-----------|------|
| **Business meaning** | Base **hourly** rate when `compensation_type` is hourly. |
| **Required at approval** | **Yes if and only if** `compensation_type = hourly`. Otherwise must be **null / not applicable** (see §3). |
| **Editable later** | **Yes** when applicable. |
| **Allowed value shape** | Non-negative monetary decimal (precision TBD at implementation); **null** when not applicable. |
| **Must not be confused with** | **Parking or other recurring charges**; **per-mile rate**; **commission**. |

---

### 2.6 `per_mile_rate`

| Attribute | Lock |
|-----------|------|
| **Business meaning** | Base **per-mile** rate or settlement rate per mile when `compensation_type` is per mile. **Note:** per mile can apply to both company drivers and owner-operators, but **employment relationship** and **payee** still determine which **downstream module** owns the calculation (payroll vs settlement)—this field only captures the **stated base rate** for phase 1. |
| **Required at approval** | **Yes if and only if** `compensation_type = per_mile`. Otherwise **null / not applicable**. |
| **Editable later** | **Yes** when applicable. |
| **Allowed value shape** | Non-negative monetary decimal; **null** when not applicable. |
| **Must not be confused with** | **Fuel deduction “cents per mile”** (phase-1 non-goal); **trailer rent per mile** (non-goal). |

---

### 2.7 `commission_percent`

| Attribute | Lock |
|-----------|------|
| **Business meaning** | **Commission percentage** when `compensation_type` is commission (typical owner-operator pattern; could apply elsewhere only if product expands—phase 1 does not expand beyond the locked enums). |
| **Required at approval** | **Yes if and only if** `compensation_type = commission`. Otherwise **null / not applicable**. |
| **Editable later** | **Yes** when applicable. |
| **Allowed value shape** | Non-negative percentage (0–100 or 0–1 internal representation TBD at implementation—**this report locks semantics, not storage format**); **null** when not applicable. |
| **Must not be confused with** | **Insurance or fuel percentage deductions** (non-goals in phase 1). |

---

### 2.8 `payee_type`

| Attribute | Lock |
|-----------|------|
| **Business meaning** | **Who the carrier pays** in this configuration: the **driver directly** vs the **owner-operator as payee**. Protects against conflating **operator** (who drives) with **payee** (who receives settlement)—especially when a co-driver exists in operations but is **not** paid by the carrier (that co-driver is **out of phase-1 config** but the principle must hold). |
| **Required at approval** | **Yes.** |
| **Editable later** | **Yes**, with strong caution—this is a structural pay relationship change. |
| **Allowed value shape** | Coded enum. Phase-1 allowed values: see §6. |
| **Must not be confused with** | **Primary vs co-driver** (not in phase-1 field set); **is_team_driver**; **employment_relationship_type** (related but not identical). |

---

### 2.9 `provides_own_truck`

| Attribute | Lock |
|-----------|------|
| **Business meaning** | Whether this driver/operator **brings their own truck** as a **business setup fact**—not “which truck is assigned on today’s load.” |
| **Required at approval** | **Yes.** |
| **Editable later** | **Yes.** |
| **Allowed value shape** | Boolean. |
| **Must not be confused with** | **Default or current dispatch truck assignment**; **truck FK** (phase-1 non-goal). |

---

### 2.10 `provides_own_trailer`

| Attribute | Lock |
|-----------|------|
| **Business meaning** | Whether this driver/operator **brings their own trailer** as a **business setup fact**—not “which trailer is on the load right now.” |
| **Required at approval** | **Yes.** |
| **Editable later** | **Yes.** |
| **Allowed value shape** | Boolean. |
| **Must not be confused with** | **Trailer rent rules or amounts** (non-goals); **current trailer assignment**; **trailer FK** (non-goal). |

---

### 2.11 `equipment_contribution_type`

| Attribute | Lock |
|-----------|------|
| **Business meaning** | A **single structured summary** of equipment contribution for commercial setup: company equipment vs operator truck only vs operator truck and trailer. Must stay **consistent** with `provides_own_truck` / `provides_own_trailer` where possible (see §3 for suspicious combinations). |
| **Required at approval** | **Yes.** |
| **Editable later** | **Yes.** |
| **Allowed value shape** | Coded enum. Phase-1 allowed values: see §6. |
| **Must not be confused with** | **Dispatch assignment mode** or **load-level equipment**; **trailer rent applies** (separate boolean). |

---

### 2.12 `company_trailer_rent_applies`

| Attribute | Lock |
|-----------|------|
| **Business meaning** | Whether **company trailer rent** is part of the **commercial setup** because the operator uses a **company trailer** (e.g. operator has truck but not trailer). This is a **boolean business flag** for phase 1—not a rent **amount**, **schedule**, or **rule engine** (non-goals). |
| **Required at approval** | **Yes** as a field (always set true/false). **Semantic expectation:** should be **true** when company trailer usage implies rent; **false** when not applicable. When the operator provides their own trailer, this should normally be **false** (see §3). |
| **Editable later** | **Yes.** |
| **Allowed value shape** | Boolean. |
| **Must not be confused with** | **Trailer rent numeric rules** (non-goal); **current trailer on dispatch**; **`provides_own_trailer`** (related but distinct). |

---

### 2.13 `insurance_approved`

| Attribute | Lock |
|-----------|------|
| **Business meaning** | Whether the driver/operator is **approved from an insurance/commercial clearance** perspective **for this business setup**—structured **approval state**, not free-text notes. Distinct from “an insurance **charge** applies” (deduction rules are phase-1 non-goals). |
| **Required at approval** | **Yes** (explicit true/false at configuration time). *Process note:* for company drivers some carriers may default true; the field must still exist and be set deliberately—**no silent default without product decision** at implementation time. |
| **Editable later** | **Yes.** |
| **Allowed value shape** | Boolean. |
| **Must not be confused with** | **`insurance_charge_*` rules** (non-goal); **person active flag**; **application approved** without operational clearance. |

---

## 3. Requiredness rules

### 3.1 Always required at admin configuration (when saving phase-1 config)

These fields are **always required** (non-null / must be set):

- `employment_relationship_type`
- `driver_operating_subtype`
- `is_team_driver`
- `compensation_type`
- `payee_type`
- `provides_own_truck`
- `provides_own_trailer`
- `equipment_contribution_type`
- `company_trailer_rent_applies`
- `insurance_approved`

### 3.2 Conditionally required (compensation rates)

- **`hourly_rate`:** required **only when** `compensation_type = hourly`. Otherwise must be **absent / null / not applicable** (implementation must enforce mutual exclusivity of rate fields).
- **`per_mile_rate`:** required **only when** `compensation_type = per_mile`. Otherwise **null / N/A**.
- **`commission_percent`:** required **only when** `compensation_type = commission`. Otherwise **null / N/A**.

**Rule:** Exactly **one** of the three rate fields should be populated, matching `compensation_type`. The other two must be null.

### 3.3 `company_trailer_rent_applies` — meaningful when

- Must always be **true or false**.
- **Expected true** when: operator does **not** provide own trailer **and** uses a **company trailer** such that rent is a business term (per foundation docs).
- **Expected false** when: operator **provides own trailer**, or equipment is fully company-provided in a way that does not imply operator trailer rent (product may refine messaging later—phase 1 locks the **field** and **boolean**, not the accounting engine).

### 3.4 Invalid or suspicious combinations (for later backend validation)

Backend validation is **not implemented in this report**; these are **design flags** for the first contract:

1. **`payee_type = owner_operator_payee` but `employment_relationship_type = company_driver`**  
   - **Suspicious / likely invalid.** Owner-operator payee normally aligns with owner-operator employment relationship. Require explicit product exception if ever allowed.

2. **`payee_type = direct_driver` but `employment_relationship_type = owner_operator`**  
   - **Suspicious.** May occasionally occur in edge cases; treat as **warning or hard error** pending product decision. Default stance: **do not allow** without override.

3. **`equipment_contribution_type = company_equipment` but `provides_own_truck = true` or `provides_own_trailer = true`**  
   - **Inconsistent.** Company equipment implies operator is not bringing owned truck/trailer.

4. **`equipment_contribution_type = truck_and_trailer` but `provides_own_truck = false` or `provides_own_trailer = false`**  
   - **Inconsistent.**

5. **`equipment_contribution_type = truck_only` but `provides_own_truck = false`**  
   - **Inconsistent.**

6. **`provides_own_trailer = true` but `company_trailer_rent_applies = true`**  
   - **Suspicious.** If operator owns trailer, company trailer rent normally does not apply. Likely invalid unless documented exception.

7. **`compensation_type` populated rates mismatch**  
   - e.g. `hourly` + non-null `per_mile_rate` → **invalid**.

8. **`driver_operating_subtype = owner_operator` vs `employment_relationship_type`**  
   - Generally should align: if subtype is owner-operator, employment relationship is usually owner-operator. Misalignment should be **flagged** for review.

9. **Team baseline without phase-1 team detail**  
   - `is_team_driver = true` is allowed, but **no** teammate FK or primary/co-driver fields in phase 1—downstream UX must not assume those exist yet.

---

## 4. Table ownership decision

**Locked direction:**

| Table / surface | Phase-1 ownership |
|-----------------|-------------------|
| **`people`** | **Identity only** (name, contact, address, notes, identity lifecycle). **Does not** own compensation, trailer rent flags, insurance commercial setup, or owner-operator commercial fields. |
| **`person_roles`** | **Role membership only** (e.g. person holds DRIVER role). **Does not** own operating subtype, pay model, equipment contribution, or deductions. |
| **`driver_profiles`** | **Core driver identity / license / compliance basics** (license identifiers, region, expiry, future capability normalization). **Does not** own commercial setup, pay rates, or recurring charge logic. |
| **`drivers`** | **Dispatch-facing operational roster projection** (convenience for dispatch screens and operational joins). **Not** the authoritative store for this business configuration. **Do not** make `drivers.id` the only anchor for phase-1 business truth. |
| **NEW: driver admin config record** | **Authoritative home for all thirteen phase-1 fields.** Tenant-scoped, person-centered business configuration created/updated in admin approval flow. |

### 4.1 New record anchor (locked)

The new configuration row **must** be anchored by:

- **`tenant_id`**
- **`person_id`** → references the **approved driver person** in that tenant

**Cardinality:**

- **At most one** config row per **`(tenant_id, person_id)`** for drivers who receive this configuration.
- Enforce **`UNIQUE (tenant_id, person_id)`** when the schema is written.

**Existence rule (for implementation planning):** Config row is created when admin completes phase-1 setup for that driver person (typically at approval). Exact workflow is product/UI detail; **this report locks data ownership and uniqueness only.**

---

## 5. Foreign key direction

**Locked principles:**

1. **Person-centered:** The new config record **`person_id`** points to **`people`** (or equivalent tenant person table). Business truth follows the **person**, not the dispatch row.
2. **Not owned by `drivers`:** Do **not** make `drivers.id` the **primary** parent of this configuration. If a link from `drivers` to config exists later for convenience, it must be **derived or secondary**—not the sole key for business truth.
3. **Tenant-safe:** Every config row carries **`tenant_id`**; all validation assumes tenant scope (no cross-tenant references).
4. **Phase-1 explicit exclusions:**  
   - **No** `linked_teammate_person_id` (or equivalent) in phase 1.  
   - **No** `default_truck_id` / truck FK in phase 1.  
   - **No** `default_trailer_id` / trailer FK in phase 1.  
   - **No** `payee` / external payee entity FK in phase 1.  

These FKs are **explicitly deferred** until related modules and payee architecture are stable.

---

## 6. Phase-1 value shapes

**Coded fields** use **closed sets** in phase 1. Do **not** expand enums beyond this list without a new design pass.

### 6.1 `employment_relationship_type`

- `company_driver`
- `owner_operator`

*(Optional future values such as `contractor_driver` are **out of scope** for phase 1.)*

### 6.2 `driver_operating_subtype`

- `long_haul_company`
- `city_local`
- `shunt_yard`
- `owner_operator`

*(Future subtypes such as `straight_truck_local` are **out of scope** for phase 1.)*

### 6.3 `compensation_type`

- `hourly`
- `per_mile`
- `commission`

### 6.4 `payee_type`

- `direct_driver`
- `owner_operator_payee`

*(Future: `external_payee_entity` — **out of scope** for phase 1.)*

### 6.5 `equipment_contribution_type`

- `company_equipment`
- `truck_only`
- `truck_and_trailer`

### 6.6 Booleans

- `is_team_driver` — true/false  
- `provides_own_truck` — true/false  
- `provides_own_trailer` — true/false  
- `company_trailer_rent_applies` — true/false  
- `insurance_approved` — true/false  

### 6.7 Monetary / numeric

- `hourly_rate`, `per_mile_rate`, `commission_percent` — shapes as in §2; mutual exclusivity per §3.

---

## 7. Explicit non-goals for phase 1

Phase 1 **does not** include (no fields, no engines, no FKs for these in this slice):

- Fuel charge rules (`fuel_charge_rule_type` / value, etc.)
- Parking charge rules
- Insurance **charge** rules (as distinct from **`insurance_approved`** boolean)
- Trailer rent **numeric** rules or schedules
- `linked_teammate_person_id` or teammate linkage
- Default **truck** FK
- Default **trailer** FK
- Home **terminal** FK
- Effective-dated **history** of terms
- Deduction **rule engine**
- Advanced **team** logic (primary/co-driver fields, pairing flexibility flag, etc.)
- **Payroll formulas**
- **Settlement formulas**

If a stakeholder asks for any of the above, the answer is: **phase 2+ / separate design report**—not phase 1.

---

## 8. Build order recommendation

**Exact next build order** (after this report is accepted):

1. **Lock phase-1 field set** — this document is that lock; any change requires revising this report first.  
2. **Lock table ownership** — new tenant-scoped, person-centered **driver admin config** table (name TBD) with `UNIQUE (tenant_id, person_id)`.  
3. **Write Alembic** — tenant migration only, per project rules; follow uniqueness and FK to `people` + `tenant_id`.  
4. **Add model / schema / backend contract** — SQLAlchemy model, Pydantic (or equivalent) request/response shapes, validation rules reflecting §3 and §6.  
5. **Build UI** — admin approval/configuration surfaces that edit **only** these fields on the config record.

Do **not** start step 3 until steps 1–2 are acknowledged by the team.

---

## 9. Strong warnings

1. **Do not mix operator with payee.** A person may operate without being the carrier’s direct payee; `payee_type` exists to prevent that mistake.  
2. **Do not mix base compensation with deductions.** Hourly/per mile/commission are **earnings shape**; fuel/parking/insurance/trailer rent **rules** are not in phase 1.  
3. **Do not mix equipment contribution with current dispatch assignment.** Owning vs company equipment is **setup**; load assignment is **operations**.  
4. **Do not overload `drivers` as the only source of truth** for this configuration. **Person-centered config** is authoritative.  
5. **Do not bury core setup only in notes or unstructured JSON** if phase 1 is meant to be **structured and auditable**—these thirteen fields are **first-class columns** on the config record (JSON blobs are not part of this lock).

---

**After this report is complete, stop. Do not create migration or code yet.**
