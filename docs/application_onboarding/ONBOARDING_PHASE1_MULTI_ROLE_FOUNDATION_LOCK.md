# Onboarding Phase 1 — Multi-Role Foundation Lock (Design Report)

**Scope:** This file contains the **Phase 1 clarifications**, then the **five locked matrices** below. It is **design-only**.

**Note for Cursor:** **Do not write Alembic, backend, or UI from this report** for the Phase 1 matrices alone. Stop after this document is complete (together with the updated `docs/DRIVER_ONBOARDING_AND_ADMIN_CONFIGURATION_FOUNDATION.md`). **Phase 3B** (§ below) locks **people-level onboarding completion** semantics; a minimal backend foundation for that slice may exist in-repo—behavior must still match this lock. Full HR/payroll/dispatch product build remains **out of scope** here. Keep content **decision-oriented and explicit**—not a vague summary. Canonical detail for approve vs onboard and UI modes: `docs/HR_PAYROLL_ONBOARDING_LOGIC_ANCHOR.md`.

---

## Phase 1 clarifications (approved planning)

These ideas are **explicitly part of this approved matrix artifact**:

1. **`application_type` and `requested_role_code` are separate concepts** and **must not be conflated.** `application_type` drives which **applicant workflow / form** runs; `requested_role_code` is the **role assigned on approval**. They often match operationally, but they answer different questions and must stay distinct in schema and UX.

2. **Phase 1 supports one workflow per application/invite only**; there is **no** combined **dual-role** workflow in Phase 1.

3. **“General documents”** in shared and admin sections means a **shared handling surface** (e.g. upload, review, storage patterns)—**not** that every workflow has **identical** document **requirements**.

4. **Driver commercial / equipment / team / owner-operator admin config** is a **future extension** only; it is **not** a Phase 1 implementation commitment (matrices may show it for **driver** rows as **planning space**).

5. **`drivers`** is an **operational roster projection** materialized on **driver** approval; it is **not** the canonical owner of **onboarding** truth. Canonical onboarding intake/review truth remains **`PersonApplication`** (and promoted **`Person`**), per §4.

---

## 1. Invite workflow matrix

**Rule:** When an admin creates an invite / application, the **workflow type** (`application_type` in the canonical onboarding record, aligned with product naming) **selects which applicant form or form variant** the invitee sees. **Non-driver workflows must not show driver-only steps by default.** Do **not** substitute `requested_role_code` for `application_type` when deciding which form to show—see **Phase 1 clarifications**.

| Invite / workflow type | Applicant workflow / form (what should appear) |
|------------------------|-----------------------------------------------|
| **Driver** | **Driver track:** identity/contact/address (shared), **plus** driver-specific intake—license/CDL (or regional equivalent), medical/expiry where collected, driver document uploads, employment/driver history as product defines, **`intake_payload` shaped for driver schema**. |
| **Dispatcher** | **Dispatcher track:** shared identity/contact/address; **dispatcher-specific** sections only (e.g. dispatch experience, shift expectations, certifications relevant to dispatch—**product-defined**); **no** CDL/team/owner-operator/truck-trailer commercial blocks unless explicitly added later. |
| **HR** | **HR track:** shared foundation; **HR-specific** professional/qualification sections; **no** driver license class, equipment contribution, or carrier commercial driver terms by default. |
| **Mechanic** | **Mechanic track:** shared foundation; **mechanic-specific** skills, certifications, shop safety; **no** driver pay, team driving, or owner-operator equipment setup by default. |
| **Payroll** | **Payroll track:** shared foundation; payroll-relevant employment/compliance fields **as appropriate for office role**; **not** the same as driver CDL or linehaul equipment. |
| **Safety** | **Safety track:** shared foundation; safety program / qualification sections; **no** default driver commercial configuration blocks. |
| **Office Admin** | **Office admin track:** shared foundation; administrative role qualifications; **no** driver-only compliance. *(Dual-role or combined workflows are **out of scope** for Phase 1—see clarifications.)* |
| **Other** | **Generic / minimal track:** shared foundation only, or minimal extra fields; role intent captured for admin to assign **`requested_role_code`** appropriately on review—**avoid** driver mega-form. |

**Implementation note (planning only):** Repo today exposes `APPLICATION_TYPES` including these codes; **this matrix locks intent** so UI and validation **gate** sections by row, not by “one form for all.”

---

## 2. Shared vs role-specific section matrix

**Legend:** **Shared** = shown for every workflow (subject to product). **Role** = shown **only** for that workflow. **—** = not part of that workflow’s default intake. *(Phase 1: **one workflow per invite**—no combined dual-role track; see **Phase 1 clarifications**.)*

| Intake section (conceptual) | Driver | Dispatcher | HR | Mechanic | Payroll | Safety | Office Admin | Other |
|----------------------------|--------|------------|-----|----------|---------|--------|--------------|-------|
| Legal name, contact, address | Shared | Shared | Shared | Shared | Shared | Shared | Shared | Shared |
| General notes / cover letter | Shared | Shared | Shared | Shared | Shared | Shared | Shared | Shared |
| Application status (applicant view) | Shared | Shared | Shared | Shared | Shared | Shared | Shared | Shared |
| Identity documents (generic ID) | Shared* | Shared* | Shared* | Shared* | Shared* | Shared* | Shared* | Shared* |
| **License / CDL / class / endorsements** | **Role** | — | — | — | — | — | — | — |
| **Medical card / expiry (driver regulatory)** | **Role** | — | — | — | — | — | — | — |
| **Driver employment history / MVR path (if product)** | **Role** | — | — | — | — | — | — | — |
| **Driver document bundle (e.g. CDL scan, certs)** | **Role** | — | — | — | — | — | — | — |
| **Team intent / owner-operator intent (driver)** | **Role** | — | — | — | — | — | — | — |
| Dispatcher-specific experience / tools | — | **Role** | — | — | — | — | — | — |
| HR-specific qualifications | — | — | **Role** | — | — | — | — | — |
| Mechanic certifications / shop | — | — | — | **Role** | — | — | — | — |
| Payroll / finance office qualifications | — | — | — | — | **Role** | — | — | — |
| Safety program qualifications | — | — | — | — | — | **Role** | — | — |
| Office admin skills | — | — | — | — | — | — | **Role** | — |

\* *Which* generic documents apply may still vary by workflow; the row means “not inherently driver-only.”

**Explicit lock:** **Non-driver roles must not be forced through driver-only rows** (CDL, team/O-O intent, driver document bundle, etc.). **Phase 1 is one workflow per invite only**; dual-role or combined tracks are a **later** design phase, not Phase 1.

---

## 3. Admin review matrix

**Rule:** Admin sees a **shared review shell** for every application, **plus** **workflow-specific panels** only when the application's workflow type matches.

| Admin review section | Driver | Dispatcher | HR | Mechanic | Payroll | Safety | Office Admin | Other |
|---------------------|--------|------------|-----|----------|---------|--------|--------------|-------|
| Application metadata (invite, dates, status) | Yes | Yes | Yes | Yes | Yes | Yes | Yes | Yes |
| Shared identity verification (name, contact, address) | Yes | Yes | Yes | Yes | Yes | Yes | Yes | Yes |
| General documents (non-driver) † | Yes | Yes | Yes | Yes | Yes | Yes | Yes | Yes |
| Approve / reject / audit trail | Yes | Yes | Yes | Yes | Yes | Yes | Yes | Yes |
| Confirm `requested_role_code` / role assignment | Yes | Yes | Yes | Yes | Yes | Yes | Yes | Yes |
| **Driver license / compliance review** | Yes | — | — | — | — | — | — | — |
| **Driver commercial / equipment / team / O-O admin config** (future extension; not Phase 1 build) | Yes | — | — | — | — | — | — | — |
| **Dispatcher-specific review panel** | — | Yes | — | — | — | — | — | — |
| **HR-specific review panel** | — | — | Yes | — | — | — | — | — |
| **Mechanic-specific review panel** | — | — | — | Yes | — | — | — | — |
| **Payroll-specific review panel** | — | — | — | — | Yes | — | — | — |
| **Safety-specific review panel** | — | — | — | — | — | Yes | — | — |
| **Office admin-specific review panel** | — | — | — | — | — | — | Yes | — |
| **Other / generic role confirmation only** | — | — | — | — | — | — | — | Yes |

**†** Per **Phase 1 clarifications** item 3: shared **handling surface** for documents, **not** identical **requirements** for every workflow.

**Examples called out in the foundation doc (must hold in UX):**

- **Dispatcher** must **not** see AZ/CDL, team, owner-operator, truck/trailer commercial setup **by default**.  
- **HR** must **not** see driver license/commercial/equipment logic **by default**.  
- **Mechanic** must **not** see driver pay/equipment/team logic **by default**.

**General documents (non-driver):** a shared **handling surface**, not identical document **requirements** for every workflow (see **Phase 1 clarifications**).

**Driver commercial / equipment / team / O-O admin config** row: **future extension** only—**not** a Phase 1 implementation commitment; the matrix reserves planning/UI space for a later driver admin extension.

---

## 4. Canonical onboarding object decision

**Decision (Phase 1 lock):** The **single source of truth for onboarding intake and review state** going forward is the tenant-scoped **`PersonApplication`** row (`person_applications` table): one record per invite/application instance, carrying **`tenant_id`**, **`application_type`** (which **workflow/form** this invite uses), **`requested_role_code`** (which **role** is assigned on approval), status lifecycle (draft/submitted/approved/rejected as product enumerates), reviewer ids/timestamps, **denormalized identity fields** for convenience, and **`intake_payload` (JSONB)** for workflow-specific answers.

**`application_type` and `requested_role_code` must not be conflated**—see **Phase 1 clarifications**.

- **It is the canonical object** for: “this person’s **application**,” what they submitted, and how far review progressed **before** full operational promotion.  
- **`Person`** is the canonical object for **approved human identity** in the tenant; it is **not** a substitute for application history and payload.  
- **`PersonRole`**, **`DriverProfile`**, and **`drivers`** are **promoted entities** created or updated **only when** approval rules say so—not replacements for `PersonApplication`. **`drivers`** in particular is an **operational roster projection** for dispatch after **driver** approval; it does **not** own onboarding truth (see **Phase 1 clarifications**).  

**Do not** fragment intake truth across unrelated tables without updating this decision in a future design pass.

---

## 5. Approval promotion matrix

**Rule:** On **approve**, the system **always** promotes shared foundation where applicable; **role extensions** are **conditional** on workflow and **`requested_role_code`** (today’s code already follows this pattern for drivers). Use **`application_type`** for which form ran; use **`requested_role_code`** for which **`PersonRole`** to ensure—**do not merge these concepts** (see **Phase 1 clarifications**). The **`drivers`** row is **only** the **operational roster projection** for the driver workflow, **not** onboarding’s canonical store.

| Workflow (`application_type` aligned) | **Person** | **PersonRole** (`requested_role_code`) | **DriverProfile** | **Operational `drivers` row** | **Payee / compensation** (existing system) |
|--------------------------------------|------------|------------------------------------------|-----------------|--------------------------------|---------------------------------------------|
| **Driver** | Create or update | Ensure **DRIVER** (or configured code) active | Create or update | **Upsert** dispatch roster row | **No Phase 1 lock**—**do not** auto-create duplicate compensation truth; **Phase 5** reconciliation (see foundation §14). Existing pay-run paths may create payees **as today** until integration is redesigned. |
| **Dispatcher** | Create or update | Ensure **DISPATCHER** active | **No** | **No** | Same as above |
| **HR** | Create or update | Ensure **HR** active | **No** | **No** | Same |
| **Mechanic** | Create or update | Ensure **MECHANIC** active | **No** | **No** | Same |
| **Payroll** | Create or update | Ensure **PAYROLL** active | **No** | **No** | Same |
| **Safety** | Create or update | Ensure **SAFETY** active | **No** | **No** | Same |
| **Office Admin** | Create or update | Ensure **OFFICE_ADMIN** active | **No** | **No** | Same |
| **Other** | Create or update | Ensure **OTHER** (or product-specific code) active | **No** | **No** | Same |

**Explicit lock:** **Driver-specific promotion** (`DriverProfile`, **`drivers`**) is **only** for the **driver** workflow in Phase 1 (**one workflow per invite**). **Non-driver approvals must not create `drivers` rows or driver profiles.** Later phases may define add-ons (e.g. second role); that is **not** Phase 1.

---

## Phase 3B — Onboarding completion / downstream setup foundation

This section is the **people-level bridge** between (a) Phase 1 multi-role onboarding + canonical **`PersonApplication`**, (b) Phase 3A-style **workflow-specific operational setup** (e.g. driver extension on the person), and (c) **later** dispatch, compensation/payee, and full HR/payroll product slices. **Do not** infer that **manager approval** alone means **full onboarding**, **HR/payroll completeness**, or **dispatch eligibility**—those are **separate** concerns governed below.

This pattern is **workflow-wide** (Driver, Dispatcher, HR, Mechanic, Payroll, Safety, Office Admin, Other)—**not** driver-only. Driver extension and **`drivers`** roster promotion remain **driver-path** artifacts; **approve vs onboard** and **`person_setup_ui_mode`** apply to **any** `application_type`.

### 1. Approve vs onboard (separate concepts)

* **Approve** — A manager (or delegated reviewer) accepts the **application**; the person may be **promoted** per **§5** (`Person`, `PersonRole`, and workflow-conditional artifacts such as `DriverProfile` / **`drivers`** for the driver track). **Required downstream setup** (HR, payroll, ops, role-specific configuration blocks) may still be **incomplete**.
* **Onboard (fully)** — All **mandatory** downstream setup for that **workflow** is **complete**, and an authorized actor has performed an **explicit onboarding completion** action (distinct from approval).

**Lock:** Approval truth and onboarding-completion truth use **separate** concepts (e.g. `approved_*` vs `onboarded_*`, and a **`setup_status`**-style lifecycle on **`PersonApplication`**). **Do not** overload the application **`status`** field (e.g. `APPROVED`) to mean “every downstream mandatory field is satisfied.”

### 2. Tenant `person_setup_ui_mode` (`combined` / `segmented`)

* **`combined`** (default) — Onboarding/review surfaces **may** expose downstream setup fields **when product allows**, so smaller fleets can finish setup **without** bouncing across many modules.
* **`segmented`** — Onboarding/review stays **limited to that stage**; HR/payroll/ops (and similar) complete remaining mandatory setup in **their** workspaces.

This is a **tenant-level** (platform) setting—**not** stored on driver-only tables. Naming and full rules: **`docs/HR_PAYROLL_ONBOARDING_LOGIC_ANCHOR.md`**.

### 3. Segmented mode: hidden fields must not block manager save

If fields are **hidden** from the manager because they belong to a **downstream** stage, they must **not** cause **validation errors** on actions the manager **can** take (e.g. approve). **Never** show a user an error for fields they **cannot** access on that screen.

### 4. Pending downstream setup state

After **approval**, until **explicit completion**: the record should reflect that downstream mandatory work may remain (e.g. **`setup_status` = `pending_downstream`** in implementation). **`pending`** (pre-approval / not yet in downstream phase) and **`complete`** (onboarding finalized) complete the mental model; exact enum names may evolve in code.

### 5. Explicit final onboarding completion

A **separate** action (admin or otherwise authorized) marks **onboarding completion** (`onboarded_*`, **`setup_status = complete`**). That action means “required setup for this workflow is finished,” **not** merely “the manager approved the invite.”

### 6. Workflow-specific downstream setup (later slices)

**What** must be completed downstream is **workflow-specific** (e.g. Driver vs Dispatcher vs HR): driver configuration extension, RBAC/dispatch permissions, HR records, payroll/compensation hooks, etc. The **pattern** is general; the **checklist** is per workflow. **Phase 4 dispatch behavior** and **Phase 5-style compensation/payee reconciliation** remain **downstream** of this bridge—do **not** skip this completion model when designing those phases.

### 7. Visibility vs truth ownership

**Configurable:** where fields appear, which role/workspace completes them, and when in the journey they are edited. **Not configurable:** that mandatory business fields **exist**, that they must **eventually** be satisfied before **full onboarding**, and that there is a **single canonical source of truth** per concern (no duplicate “shadow” ownership of the same business fact).

---

**End of Phase 1 multi-role foundation lock** (including **Phase 3B**). **Do not write Alembic, backend, or UI** for net-new product beyond what is already explicitly adopted in repo for this foundation—later passes must **preserve** §1–§5 matrices and **Phase 3B** semantics when extending dispatch, HR/payroll, and compensation.
