# Phase 3A — Driver Extension Foundation Lock

**Status:** Design-only. **Do not implement** until an explicit implementation slice is opened.

**Purpose:** Define the **driver-only extension layer** that sits **on top of** the locked **people-first, multi-role onboarding foundation** (Phase 1 complete). This document scopes **non-overlapping driver setup concepts**—identity and structure for *how* a driver works for the carrier—not pay math, settlement, or dispatch behavior.

**Audience:** Product, architecture, and implementers planning a **later** schema/API slice. **No code, no Alembic, no payee/compensation redesign** from this document alone.

---

## Relationship to prior locks

- **Onboarding foundation** (`docs/ONBOARDING_PHASE1_MULTI_ROLE_FOUNDATION_LOCK.md`, Phase 1 slice): **`Person`**, **`PersonRole`**, conditional **`DriverProfile`** + operational **`drivers`** on approval. That path stays the **entry** into the tenant’s people model.
- **Phase 3A** adds **structured driver commercial/operational setup** as an **extension**—not a replacement for onboarding intake and not a second source of truth for “who this person is.”

---

## 1. Employment relationship type

**Concept:** The **business relationship** between the driver and the carrier for operational and compliance labeling—not pay rates or payee wiring.

| Value | Meaning (design level) |
|-------|-------------------------|
| **company_driver** | Driver is employed / engaged as a **company** driver (typical W-2–style framing in product language; actual tax treatment is out of scope here). |
| **owner_operator** | Driver operates under **owner-operator** terms (owns or leases equipment and/or authority per product; details belong in extension fields, not in onboarding alone). |
| **contractor** | **Optional future** value—**do not** add to the first implementation unless a distinct need from **company_driver** and **owner_operator** is documented. If added later, define explicitly vs **owner_operator** (e.g. 1099 non-O-O). |

**Lock:** One **primary** employment relationship classification per driver extension record (per person/tenant driver context). Multi-relationship history is **out of scope** for 3A unless a follow-on slice says otherwise.

---

## 2. Driver operating subtype

**Concept:** **How** the driver primarily operates (lane / duty pattern)—orthogonal to **employment relationship** in most cases.

| Value | Meaning (design level) |
|-------|-------------------------|
| **long_haul** | Extended linehaul / OTR-style operation. |
| **city_local** | Local / regional short-radius operation. |
| **shunt_yard** | Yard, shuttle, or similar short specialized movements. |

### Owner-operator: relationship vs subtype — recommended structure

**Problem:** **Owner-operator** is both a **relationship** (who the driver is relative to the carrier) and a **label** users say in the same breath as “long haul.” Putting **owner_operator** in *both* employment type and operating subtype **duplicates semantics** and invites inconsistent data (e.g. relationship = OO, subtype = long_haul vs subtype = owner_operator).

**Recommendation (cleanest):**

1. **`employment_relationship_type`** includes **`owner_operator`** (and **`company_driver`**, optional **`contractor`** later).
2. **`operating_subtype`** includes **only** **`long_haul`**, **`city_local`**, **`shunt_yard`**—**not** `owner_operator`.
3. **Combined meaning** is expressed by **pairing**: e.g. `(owner_operator, long_haul)` = “owner-operator, long haul.” UI may display a **single** human-readable string built from both fields; storage stays **two axes**.

**Rationale:** Relationship answers **commercial/engagement class**; subtype answers **operating pattern**. Owner-operator **long haul** vs **local** is a real distinction; encoding OO only as subtype loses the distinction between OO and company local without extra fields.

**Explicit non-goal:** Do not introduce a second enum value **`owner_operator`** on **`operating_subtype`** unless a future slice proves a case that cannot be represented as relationship + subtype (e.g. product insists on three mutually exclusive radio buttons that are not composable). If that happens, revisit in a **new** design addendum—do not silently duplicate in 3A.

---

## 3. Team structure

**Design level only**—no dispatch pairing implementation in this slice.

| Topic | Lock / guidance |
|-------|------------------|
| **Single vs team** | Extension should support a flag or mode: **single** driver vs **team** operation intent. |
| **Primary vs co-driver** | For **team**, distinguish **primary** vs **co-driver** relative to the **carrier’s** roster record (not necessarily legal co-ownership). Exact FK to another `Person` may belong in a **later** schema slice; 3A only **names** the concepts. |
| **Dispatch changing pairing later** | **Yes, in principle**—dispatch may **reassign** or **end** team pairings operationally. The **driver extension** should **not** assume the onboarding-time team flag is immutable forever; operational truth may live in dispatch domain when built. **3A does not** specify dispatch tables or APIs. |

**Lock:** Document **concepts** and **boundaries**; **implementation** of person-to-person team links and dispatch-owned pairing is **deferred** to implementation slices that touch dispatch or roster rules explicitly.

---

## 4. Equipment contribution

**Concept:** What equipment the driver **brings** vs what the **company** provides—**without** defining lease payments, charge rules, or settlement.

| Element | Design intent |
|---------|----------------|
| **Provides own truck** | Boolean (yes/no). |
| **Provides own trailer** | Boolean (yes/no). |
| **Equipment contribution type** | Coarse classification, e.g. **company equipment** (driver uses company truck/trailer), **truck only** (driver brings tractor), **truck and trailer** (driver brings both), or **other** product-defined bucket—**enumerated in implementation slice**, not here as final enum names. |
| **Company vs driver asset mix** | Supports ops and insurance narrative **at extension level**; does **not** calculate rent, deductions, or contributions in dollars. |

**Lock:** No **trailer rent rule engine**, no **recurring charge** definitions—see §6.

---

## 5. Insurance / commercial approval (driver extension only)

**At driver-extension level only:**

| Field / concept | Meaning |
|-------------------|---------|
| **Insurance approved** | Boolean (yes/no) or equivalent workflow state: carrier has **cleared** this driver for **commercial / insurance** purposes **as tracked in this extension**. |
| **What this means here** | A **gate** for “allowed to be dispatched / on the road under our program” from an **admin compliance** perspective—not a full policy object, not premium math, not payee integration. |

**Lock:** Detailed **policy numbers**, **carrier policy documents**, and **integration with external insurance systems** are **out of scope** for 3A unless a later slice says otherwise. This slice only **anchors** that such a flag **belongs** on the driver extension, not on raw onboarding intake alone.

---

## 6. Boundaries — what Phase 3A does NOT include

The following are **explicitly excluded** from Phase 3A foundation lock (no sneaking them in as “just one more column” without a new slice):

| Excluded area | Why |
|---------------|-----|
| **Compensation rates** | Belongs to pay / compensation domain. |
| **Per-mile, hourly, commission math** | Same. |
| **Payee ownership changes** | Payee model and ownership of pay data. |
| **`compensation_profiles` redesign** | Separate reconciliation slice. |
| **Trailer rent rule engine** | Recurring charge / settlement logic. |
| **Dispatch implementation changes** | Assignment, load strip, pairing implementation—not 3A. |
| **Payee / settlement integration** | Wiring extension fields to pay runs is a **later** integration contract. |

**Lock:** Phase 3A defines **what the driver extension talks about** at a **setup/compliance/ops** level; it does **not** subsume **pay** or **dispatch**.

---

## 7. Ownership and relationships (conceptual model)

**Recommendations:**

1. **Driver extension** is a **driver-only** augmentation of the **people-first** model:
   - Anchors on **`Person`** (and **`PersonRole`** with `DRIVER` where applicable).
   - Sits alongside or extends **`DriverProfile`** conceptually—**implementation** may extend `driver_profiles`, add a dedicated **driver extension / admin config** table, or follow the pattern in `docs/DRIVER_ONBOARDING_AND_ADMIN_CONFIGURATION_FOUNDATION.md`—**decide in an implementation slice**, not here.

2. **Not** the base onboarding model: **`PersonApplication`** / intake remains **historical applicant truth**; promotion creates **Person**; **driver extension** is **post-hire or post-approval configuration** (or seeded defaults at approval), not a duplicate of every onboarding field.

3. **Not** a duplicate compensation system: extension may **reference** or **align with** payee selection **later**; it does **not** store rate tables or replace **`compensation_profiles`**.

4. **Operational `drivers` row** remains a **dispatch roster projection**—minimal and **synced** from person/extension as today’s architecture describes; **heavy** commercial setup belongs on **extension/config** records, not scattered ad hoc on `drivers` without a written rule.

---

## 8. Implementation readiness

### Safe for a later schema slice (subject to naming review)

- Employment relationship type (enumerated).
- Operating subtype (long_haul / city_local / shunt_yard) **without** duplicating owner-operator as subtype.
- Team mode (single vs team) and **conceptual** primary/co-driver (fields or FKs as designed in implementation slice).
- Equipment contribution booleans and coarse contribution type enum.
- Insurance / commercial approval boolean (or small status enum).

These are **structurally** about **driver setup** and **compliance gating**, not about **money movement**.

### Must be deferred to payee / compensation reconciliation

- Any **rate**, **deduction schedule**, **charge rule**, or **settlement line** driven by equipment or O-O status.
- **Who gets paid** and **how** splits work for teams.
- **Trailer rent** amounts, **escrow**, **recurring** deductions tied to equipment.
- **Dispatch-time** logic that consumes extension fields for **assignment** or **pay export**—integrate only when those domains have an explicit slice.

**Stop:** This document is complete for **Phase 3A — Driver Extension Foundation Lock**. **No code, no Alembic, no changes to existing payee/compensation design** until a separate implementation slice is approved.
