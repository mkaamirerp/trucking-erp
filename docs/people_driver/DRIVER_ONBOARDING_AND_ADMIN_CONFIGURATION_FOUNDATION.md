# Driver Onboarding and Admin Configuration Foundation

**Note for Cursor:** This is a design-only foundation document. Do not implement anything from it without an explicit product/engineering decision. **Do not shorten this file into a vague summary**—keep it **decision-oriented and explicit**. Preserve the logic, examples, distinctions, and matrices when editing. This file must reflect that the company has **many kinds of people**, not only drivers, and that **driver configuration is one role-specific extension** of the broader onboarding system—not the base onboarding model.

**Companion lock (design only):** `docs/ONBOARDING_PHASE1_MULTI_ROLE_FOUNDATION_LOCK.md` — invite workflow matrix, shared vs role-specific section matrix, admin review matrix, canonical onboarding object decision, approval promotion matrix. **Do not implement from these documents without an explicit engineering pass** (no Alembic/backend/UI solely from the matrices).

## Status

Draft foundation document for discussion and refinement only.

This document is intentionally detailed. It is meant to reduce future implementation drift. It should be treated as a planning anchor, not as a loose note.

## Foundational correction: people-first, multi-role, driver as extension

**Onboarding is people-first and multi-role.** The base unit is a **person** entering the company through an **invite and application** flow. **Driver configuration**—license logic, commercial setup, equipment relationships, team and owner-operator rules, and everything else this document details for **drivers**—is a **role-specific extension**. It is **not** the universal onboarding model.

If driver-only questions, driver-only validation, or driver-only admin panels are applied to **every** applicant by default, the product will be wrong for dispatchers, HR, mechanics, payroll, safety, and office staff. The system must treat **workflow / role track** as a first-class decision **before** the applicant sees a form and **before** admin reviews.

## Invite-time workflow selection

When an **admin sends an onboarding link** (or otherwise starts an invite), the admin **chooses the workflow / job type** for that invite. That selection is the **primary routing key** for what the applicant will see.

**Examples of workflow types (align with product and existing role codes):**

- **Driver** — driver intake track (license, compliance, driver documents, etc., as product defines).  
- **Dispatcher** — dispatcher-oriented applicant flow.  
- **HR** — HR-oriented flow.  
- **Mechanic** — mechanic-oriented flow.  
- **Payroll** — payroll-oriented flow.  
- **Safety** — safety-oriented flow.  
- **Office Admin** — office-admin-oriented flow.  
- **Other** — generic or minimal people intake when no specialized track exists yet.  

**Rule:** The **workflow selection** (and/or `application_type` / equivalent in the canonical onboarding record) **decides which applicant form or form variant is shown**. It must not be an afterthought buried only in free text.

## Shared foundation vs role-specific extension

**Shared people foundation (all roles):** Identity and contact, address as needed, general notes, document uploads that apply to **any** hire, application status, review timestamps, and promotion to **`Person`** (and appropriate **`PersonRole`**) on approval—**without** forcing driver-only data.

**Driver extension (driver workflow only):** **`DriverProfile`**, dispatch **`drivers`** roster materialization, and (when built) **driver admin commercial/operational configuration**—only when the workflow is **driver** (or explicitly includes driver extension per product rules).

**Later extensions:** Dispatcher-, HR-, mechanic-, etc.-specific profile or config tables **only** for those workflows—**not** shoehorned into driver tables.

**Explicit rule:** **Non-driver roles must not be forced through driver-only questions** (CDL class, team driving, owner-operator equipment, trailer rent, etc.). If a field is driver-only, it must be **gated** by workflow, not shown globally.

## Admin review must be workflow-aware

Admin review and configuration UI must mirror the same split:

- **Shared admin section** — Applicable to **every** workflow: identity verification, general notes, role confirmation, application status, reject/approve with audit, and any cross-role compliance the company defines.  
- **Driver-only review / config sections** — Shown **only** when the application is on the **driver** workflow: license/commercial, equipment contribution, team/owner-operator, pay relationship **as scoped by later phases** (see locked program order below), etc.

**Examples of what to avoid:**

- A **Dispatcher** applicant’s admin screen should **not** surface AZ/CDL, team mode, owner-operator percentage, or truck/trailer commercial setup **unless** product explicitly adds a driver extension for that person later.  
- **HR** workflow should **not** be required to complete driver license, equipment, or carrier commercial logic by default.  
- **Mechanic** workflow should **not** default to driver pay, equipment contribution, or team configuration **unless** the person is also on a driver track (separate product decision).  

**Principle:** **Workflow drives sections**, not a single mega-form for all people.

## 1. Purpose

This document defines the foundation for **driver-specific** onboarding and **admin driver configuration** in TruckERP—**within** the broader **people-first, multi-role** onboarding system described above.

This is separate from the broader driver operating model discussion. That document explains how different kinds of drivers behave operationally. This document explains where that logic enters the system, how it should be captured, and why it must be configured correctly before dispatch, payroll, settlement, equipment, and team-driver logic go deeper.

The core principle is:

**The driver application is not enough by itself.**  
After application review, admin must configure the approved driver’s real business setup. That admin configuration becomes the source of truth for downstream behavior.

This module should be treated as one of the first base modules in the platform. If it is weak, later logic in dispatch, settlements, payroll, team-driving, owner-operator handling, equipment rules, and liability tracking will become inconsistent.

This document exists to answer these questions:

- what comes from the applicant  
- what must be decided by admin  
- what configuration becomes the source of truth for downstream modules  
- what should be built first  
- what should not be mixed together  
- what must remain flexible for future refinement  

## 2. Why This Module Must Come First

A driver in this system is not just a name, phone number, and license.

Once a driver enters real operations, the system needs to know things like:

- is this a company driver or an owner-operator  
- is this driver single or team-based  
- is this long-haul, city/local, shunt/yard, or another subtype  
- is this person directly paid by the carrier or paid indirectly through an owner-operator relationship  
- is the person paid hourly, per mile, or by commission  
- does this person bring a truck  
- does this person bring a trailer  
- does trailer rent apply  
- do recurring charges such as insurance, parking, or fuel-related charges apply  
- is this person commercially approved and insurance-approved  
- should dispatch treat this driver as dedicated-equipment, owner-bound, or shift-based  

If those questions are not answered in one clean foundation module, then later modules will invent local assumptions and the system will drift.

So this module is not just “driver onboarding.” It is the place where the business decides what kind of operational and commercial entity this driver really is.

## 3. Core Principle

There are two distinct stages and they must remain separate.

### 3.1 Applicant-facing stage

This is the application stage. The applicant submits personal and qualification data.

At this stage, the system is collecting who the person is, what documents they submitted, and what basic information they provided.

### 3.2 Admin configuration stage

This is the approval and setup stage. The company decides how that person will actually operate in the business.

This is where the business truth is created.

The application may say:

- who the person is  
- what license they hold  
- what they uploaded  
- what they claim or intend  

But the admin configuration must define:

- what role the company gives them  
- what kind of driver they are operationally  
- how they are paid  
- whether they are a direct payroll person or an owner-operator settlement relationship  
- whether they are single or team  
- what equipment relationship applies  
- what recurring commercial terms apply  
- whether they are approved to operate  

The system should never assume applicant input alone is enough to run operations.

## 4. Current Direction of the System

The system already has a useful onboarding skeleton:

- an application/intake layer  
- approved person records  
- role assignment  
- a thin driver profile  
- a dispatch-facing driver row  

That is good. It means the project does not need to restart onboarding from zero.

What is missing is the deeper admin configuration layer that turns an approved applicant into a properly configured driver or owner-operator inside the business.

That is what this document is defining.

## Current standing after repo review

The following reflects a **read of the current codebase direction**, not a commitment to freeze implementation details:

- **People-first, multi-role onboarding** is already the architectural direction: tenant **`person_applications`** with **`application_type`** and **`requested_role_code`**, **`APPLICATION_TYPES`** including Driver, Dispatcher, HR, Mechanic, Payroll, Safety, Office Admin, Other, and promotion to **`Person`** / **`PersonRole`** on approval.  
- **Invite workflow selection** and **requested role** are already **important concepts** in the model layer; the product should treat them as the **routing key** for forms and admin sections, not as legacy labels.  
- **Approval already creates `Person` and assigns roles conditionally**; **driver-specific** artifacts (**`DriverProfile`**, operational **`drivers`** row) are **conditional** on driver role—this matches “extension, not universal” and must stay that way as features grow.  
- The repo already has a **substantial payee and compensation** stack (**`payees`**, **`compensation_profiles`**, **`drivers.payee_id`**, pay runs). **Onboarding and driver admin extension must not invent a second, competing compensation truth source** without an explicit reconciliation design (see phased program order: compensation integration comes **after** multi-role foundation and driver extension boundaries are locked).

## 5. Separation of Concerns

The following things must remain separate in design. They must not be collapsed into one vague driver record.

### 5.1 Identity

Who the person is:

- first name  
- last name  
- phone  
- email  
- address  
- notes  
- document uploads  
- license details  

### 5.2 Role

What the person is in the company:

- driver  
- dispatcher  
- mechanic  
- office admin  
- payroll  
- safety  
- other  

### 5.3 Driver operating classification

If the person is a driver, what kind of driver are they operationally:

- long-haul company  
- city/local  
- shunt/yard  
- owner-operator  
- straight-truck specialized later  
- other future subtype later  

### 5.4 Team setup

How the person operates with other drivers:

- single  
- team  
- primary driver  
- co-driver  
- team may be changed by dispatch later  

### 5.5 Compensation model

How the person or operator earns money:

- hourly  
- per mile  
- commission  
- future expansion later  

### 5.6 Commercial deductions and recurring charges

What recurring terms apply:

- fuel-related charge or discount  
- parking charge  
- insurance charge  
- trailer rent  
- future recurring charges later  

### 5.7 Equipment contribution

What the person or operator brings:

- no equipment  
- truck only  
- trailer only if ever needed  
- truck and trailer  

### 5.8 Approval/commercial clearance

Whether the person is actually cleared to operate:

- insurance approved  
- commercially approved  
- blocked pending review later  
- future compliance gating later  

These must not be mixed together.

## 6. What Belongs to the Applicant vs What Belongs to Admin

This section is critical.

### 6.1 Applicant-side information

This is what the applicant may provide during application:

- personal identity  
- contact details  
- address  
- license information  
- uploaded documents  
- qualification or experience information  
- maybe basic intent later, such as owner-operator interest or team interest  

This is intake information. It is not the company’s final operating decision.

### 6.2 Admin-side information

This is what the company must define after review:

- final role in the company  
- final driver subtype  
- final pay relationship  
- final compensation model  
- final single/team setup  
- final equipment contribution  
- final recurring commercial terms  
- final approval and commercial-clearance status  

This is the official business truth.

### 6.3 Design rule

Applicant data may guide admin review, but applicant data should not silently become final operational truth without admin confirmation.

## 7. Admin Configuration Categories

The admin configuration should be organized into clear groups.

### 7A. Role and Operating Classification

This group defines what the person is in the organization and, if they are a driver, what kind of driver they are.

**Concepts to capture**

- primary role  
- driver subtype  
- company driver vs owner-operator  
- long-haul vs city/local vs shunt/yard  
- straight-truck-limited setup later if needed  

**Important rule**

A business role and an operating subtype are not the same thing.

**Example:**

- role = DRIVER  
- subtype = CITY_LOCAL  

**Another example:**

- role = DRIVER  
- subtype = OWNER_OPERATOR  

**Another example:**

- role = DRIVER  
- subtype = LONG_HAUL_COMPANY  

The role alone is not enough.

**Why this matters**

Dispatch behavior, equipment assumptions, compensation rules, and settlement logic may differ even though all of these people are “drivers.”

### 7B. Team Setup

This group defines how the driver participates in team operations.

**Concepts to capture**

- single or team  
- whether the driver can operate as part of a team  
- whether the driver is primary  
- whether the driver is co-driver  
- whether a teammate relationship exists  
- whether dispatch can change pairings later  

**Important rule**

A team can exist as a team, but dispatch must still be able to change that pairing when assigning a load.

**Important rule**

One driver may need to be explicitly designated as the primary driver.

This matters for:

- insurance  
- liability  
- responsibility  
- operational clarity  
- future reporting  

**Important rule**

Even if a second driver is not directly paid by the carrier, that second driver must still exist in the system if they operate.

This is required for:

- insurance  
- liability  
- compliance  
- dispatch visibility  
- trip history  

### 7C. Compensation Model

This group defines how the person or operator is paid by the carrier.

**Main compensation types to support in planning**

- hourly  
- per mile  
- commission  

More types may come later, but these are the main foundation types discussed so far.

**Examples**

- company driver at 58 cents per mile  
- owner-operator at 1.68 per mile  
- owner-operator at a commission percentage  
- city driver hourly  

**Important rule**

The same unit of pay does not mean the same business relationship.

**Example:**

- company driver paid per mile  
- owner-operator paid per mile  

These are not the same thing operationally or financially.

One belongs to company compensation logic.  
The other belongs to owner-operator settlement logic.

**Planning fields in this area**

- compensation type  
- hourly rate  
- per-mile rate  
- commission percentage  

**Important rule**

Only the fields relevant to the chosen compensation type should be active.

For example:

- hourly driver should not need commission percentage  
- commission-based owner-operator should not need hourly rate  

### 7D. Commercial Deductions and Recurring Charges

This group defines recurring charges or adjustments that affect the payout relationship.

**Examples discussed**

- fuel discount charge or adjustment  
- parking charge  
- insurance charge  
- trailer rent  

**Important rule**

These are not base pay fields. These are commercial terms.

**Important rule**

Base compensation and deductions must remain separate.

**Examples:**

- hourly / per mile / commission = how earnings start  
- fuel / parking / insurance / trailer rent = what may reduce or adjust the payout  

**Possible rule methods later**

The system may later need to support:

- none  
- fixed amount  
- percentage  
- cents per mile  
- cents per gallon or per unit  
- weekly  
- monthly  

This does not need to be fully solved now, but the design should leave room for it.

**Why this matters**

If this is not separated early, later settlement and payroll logic will become messy and hard to audit.

### 7E. Equipment Contribution and Ownership

This group defines what the person or operator brings into the relationship.

**Business cases discussed**

- company provides everything  
- owner-operator brings truck only  
- owner-operator brings truck and trailer  
- company trailer is used, so trailer rent applies  

**Concepts to capture**

- provides own truck yes/no  
- provides own trailer yes/no  
- equipment contribution type  
- trailer rent applies yes/no  

**Important rule**

This is not only dispatch logic. It affects:

- settlement  
- recurring deductions  
- operating assumptions  
- trailer-rent logic  
- commercial setup  

**Important examples**

**Example 1 — Company driver:**

- no own truck  
- no own trailer  
- company equipment  

**Example 2 — Owner-operator:**

- own truck  
- own trailer  
- no trailer rent  

**Example 3 — Owner-operator:**

- own truck  
- no own trailer  
- company trailer provided  
- trailer rent applies  

This must be modeled cleanly.

### 7F. Insurance and Commercial Approval

This group defines whether the person is approved to operate in the intended business setup.

**Concepts to capture**

- insurance approved yes/no  
- commercial approval yes/no later  
- blocked pending approval later  
- approval notes later  

**Important rule**

Do not bury important approval state only in notes.

There should be structured approval state.

**Why this matters**

Some drivers may be known to the system but not yet eligible to operate. That distinction must be visible.

## 8. Company Driver vs Owner-Operator Must Stay Separate

This is one of the biggest design rules.

**Company driver**

A company driver is part of the company’s direct compensation structure.

Possible characteristics:

- hourly  
- per mile  
- company equipment or company-assigned equipment  
- payroll relationship directly with the company  
- may be single or team  
- may be city/local or long-haul  

**Owner-operator**

An owner-operator is a different business relationship.

Possible characteristics:

- commission-based or per-mile-based  
- settlement relationship rather than simple company payroll  
- may bring truck only  
- may bring truck and trailer  
- may have recurring charges like insurance, parking, fuel-related adjustments  
- may have a co-driver or team arrangement  
- carrier may pay only the owner-operator while still tracking additional operational drivers  

**Important rule**

Owner-operator logic must never be treated as a simple variation of company-driver payroll logic.

## 9. Operator vs Payee Must Stay Separate

This is another major rule.

The person operating the truck is not always the same person or entity the carrier pays.

**Example**

An owner-operator may have:

- themselves as the main operator  
- another driver working with them  
- maybe a team setup  

But the carrier may still pay only the owner-operator.

That means the system must separate:

- operational participant  
- primary driver  
- direct payee  
- indirect/non-payee operational driver  

**Important rule**

Do not assume that every driver listed in the system is a direct carrier payroll payee.

**Important rule**

Even if a driver is not directly paid by the carrier, they must still exist in the system if they operate.

Because of:

- insurance  
- liability  
- compliance  
- dispatch visibility  
- historical trip records  

## 10. Team Driver Logic in This Module

Team logic belongs here because onboarding/admin configuration must tell the system whether the person is operating as single or team.

**Important distinction**

Team logic is not only an operational issue. It also affects:

- insurance  
- liability  
- dispatch  
- trip visibility  
- future pay allocation  
- owner-operator vs company-driver relationships  

**Two broad team business cases**

**Company-driver team**

Both drivers are company-side drivers. The company pays them directly according to company rules.

**Owner-operator team**

The owner-operator may have another driver, but the carrier may still pay only the owner-operator. The other driver still matters operationally and legally.

**Important rule**

Team participation and direct pay relationship must remain separate.

**Important rule**

Primary-driver identity must remain visible.

## 11. Example Business Cases

This section exists to keep the logic grounded.

**Case 1: Company long-haul solo driver**

- role = driver  
- subtype = long-haul company  
- single  
- per mile  
- company equipment  
- no trailer rent  
- direct company pay  

**Case 2: Company city driver**

- role = driver  
- subtype = city/local  
- single  
- hourly or per mile depending on company  
- company equipment  
- truck may be shift-assigned  
- direct company pay  

**Case 3: Owner-operator with truck and trailer**

- role = driver  
- subtype = owner-operator  
- single or team  
- commission or per mile  
- provides truck  
- provides trailer  
- no trailer rent  
- carrier pays owner-operator  

**Case 4: Owner-operator with truck only**

- role = driver  
- subtype = owner-operator  
- single or team  
- commission or per mile  
- provides truck  
- no own trailer  
- company trailer used  
- trailer rent applies  
- carrier pays owner-operator  

**Case 5: Owner-operator with co-driver**

- owner-operator is payee  
- second driver exists in the system  
- second driver participates operationally  
- carrier still pays owner-operator  
- co-driver is still important for liability and compliance  

These examples should be kept in the document because they protect against oversimplified implementation later.

## 12. Candidate Field Groups

This section is still planning-only, but it is intentionally concrete.

### 12.1 Operating classification group

**Purpose:** define the operational identity of the person.

**Candidate fields:**

- primary role  
- driver subtype  
- company driver vs owner-operator  
- single vs team  
- primary driver flag later  
- dispatch eligibility later  
- long-haul eligible later  
- city/local eligible later  
- shunt eligible later  
- straight-truck-only later  
- tractor-trailer eligible later  

### 12.2 Team setup group

**Purpose:** define single/team participation.

**Candidate fields:**

- team mode  
- team role  
- linked teammate later  
- dispatch can change team pairing yes/no  
- team notes later  

### 12.3 Compensation group

**Purpose:** define how the carrier pays this person or operator.

**Candidate fields:**

- compensation type  
- hourly rate  
- per-mile rate  
- commission percentage  

### 12.4 Commercial terms group

**Purpose:** define recurring deductions or adjustments.

**Candidate fields:**

- fuel discount rule type  
- fuel discount value  
- parking charge rule type  
- parking charge value  
- insurance charge rule type  
- insurance charge value  
- trailer rent rule type  
- trailer rent value  

### 12.5 Equipment contribution group

**Purpose:** define what equipment the person or operator brings.

**Candidate fields:**

- provides own truck  
- provides own trailer  
- equipment contribution type  
- trailer rent applies  
- trailer-rent notes later  

### 12.6 Approval group

**Purpose:** define whether the person is commercially cleared to operate.

**Candidate fields:**

- insurance approved  
- insurance approval note later  
- commercially approved later  
- blocked from dispatch until approved later  

This section should remain concrete enough to guide later implementation discussion.

## 13. What Must Not Be Mixed Up

This section should stay in the document exactly because this is where implementation drift starts.

### 13.1 Do not mix role with operating subtype

Driver is not enough. The person may be long-haul, city/local, shunt, or owner-operator.

### 13.2 Do not mix operator with payee

The person operating is not always the direct payee.

### 13.3 Do not mix base compensation with deductions

Hourly/per mile/commission is one thing. Fuel, parking, insurance, and trailer rent are separate.

### 13.4 Do not mix equipment contribution with current assignment

Bringing a truck or trailer is a business setup fact. Current truck/trailer assignment on a load is an operational event.

### 13.5 Do not assume applicant input is final truth

Applicant data may guide review, but admin configuration is the official company decision.

### 13.6 Do not bury important business state only in notes

Structured fields are needed for key operating and commercial facts.

## 14. Locked program phase order (multi-role first)

**This order supersedes** the earlier “build driver admin first” layering **for program sequencing**. Driver commercial configuration remains important but is **not** Phase 1 of the **overall onboarding program**. Phase 1 is the **multi-role, people-first foundation lock**.

### Phase 1 — Multi-role onboarding foundation lock

Lock, in **design and product**, before writing schema or UI for specialized extensions:

- **Invite workflow matrix** — For each invite/workflow type, which applicant track and form variant applies?  
- **Shared vs role-specific section matrix** — Which intake sections are **common to all people** vs **driver-only**, **dispatcher-only**, **HR-only**, **mechanic-only**, etc.?  
- **Admin review matrix** — Which admin sections appear for each workflow on review/approve?  
- **Canonical onboarding object decision** — Single source of truth for “this application” (see `docs/ONBOARDING_PHASE1_MULTI_ROLE_FOUNDATION_LOCK.md`).  
- **Approval promotion boundaries** — For each workflow, exactly what rows are created or updated on approve (`Person`, `PersonRole`, optional extensions only when applicable).  

**Deliverable:** `docs/ONBOARDING_PHASE1_MULTI_ROLE_FOUNDATION_LOCK.md` (matrices only, design report—no code).

### Phase 2 — Finalize canonical onboarding object and review surface

Solidify the **onboarding record** contract, admin read/write boundaries, and review UX patterns **across roles**—still **without** duplicating payee/compensation engines in onboarding.

### Phase 3 — Driver-specific extension foundation

Implement or extend **driver-only** structures: conditional **`DriverProfile`** / roster / future **driver admin config** as already documented in this file and in `docs/DRIVER_ADMIN_CONFIG_PHASE1_FIELD_LOCK.md`—**only after** Phase 1–2 prevent driver-only leakage into other workflows.

### Phase 4 — Connect driver extension to dispatch behavior

Dispatch hints, assignment policy, equipment assumptions—**read from** driver extension truth, not from ad hoc duplication.

### Phase 5 — Compensation / payee integration review

**Explicit reconciliation** with existing **`payees`**, **`compensation_profiles`**, and related payroll flows so driver admin configuration **feeds** or **aligns with** one compensation truth—**not** a parallel unmaintained rate store.

### What should not be first right now

Until Phase 1–2 are locked:

- **Do not** start with **driver compensation schema** as the first migration priority.  
- **Do not** start with **owner-operator percentage fields** as the first onboarding change.  
- **Do not** start with **per-mile / hourly / commission duplication** alongside `compensation_profiles` without a reconciliation plan.  
- **Do not** start with **payee duplication** (second payee model keyed only off onboarding).  
- **Do not** start with **truck/trailer assignment logic** as a substitute for workflow-aware onboarding.  
- **Do not** start with a **full driver commercial rule engine** (deductions, trailer rent rules, etc.) before multi-role boundaries are clear.  

## 15. First Real Implementation Slice Recommendation

**Program context:** The **first implementation slice for the overall onboarding program** is **Phase 1 — multi-role foundation** (matrices and boundaries), **not** the driver commercial field list below. The following **driver admin configuration slice** remains the recommended **first driver-specific** build **after** Phase 1–2 are satisfied—i.e. **program Phase 3** in §14, not “step one” for the whole product.

The safest **driver-extension** slice is still the minimum that has real business value **once driver-only extension is in scope**.

**Recommended driver-extension first slice (Phase 3 program):**

- company driver vs owner-operator  
- long-haul / city-local / shunt / owner-operator subtype  
- single vs team  
- compensation type  
- hourly/per-mile/commission value  
- own truck yes/no  
- own trailer yes/no  
- trailer rent applies yes/no  
- insurance approved yes/no  

**Why this slice first:**

- it is small enough to build  
- it gives real structure  
- dispatch can later read from it  
- settlement/payroll can later read from it  
- it prevents the most dangerous ambiguities early  

## 16. Non-Goals for This Document

This document does not yet lock:

- final database schema  
- final API contracts  
- final enum names  
- final validation rules  
- final payroll formulas  
- final settlement formulas  
- final team pay allocation rules  
- final dispatch UI details  

Those should come after the field model is agreed.

## 17. Immediate Next Discussion

**Before** tagging every driver admin field (applicant vs admin-only vs derived vs future), complete **`docs/ONBOARDING_PHASE1_MULTI_ROLE_FOUNDATION_LOCK.md`** so workflow boundaries are fixed.

After Phase 1–3 driver extension fields are in scope, the next discussion should take each **driver** candidate field and tag it as one of:

- applicant field  
- admin-only field  
- derived field  
- future field  

That step turns the driver extension into an implementation plan **without** prematurely coding it.

## 18. Working Summary

The project should now proceed in **this order**:

1. **Lock multi-role, people-first onboarding foundation** — workflow-aware invites, shared vs role-specific intake, no driver-only gates on non-drivers.  
2. **Lock workflow-aware applicant and admin section mapping** — matrices in `docs/ONBOARDING_PHASE1_MULTI_ROLE_FOUNDATION_LOCK.md`.  
3. **Confirm canonical onboarding object and approval boundaries** — one clear intake truth; promotion rules per workflow.  
4. **Then build driver-specific admin extension** — profiles, roster, future driver admin config as in this document and `docs/DRIVER_ADMIN_CONFIG_PHASE1_FIELD_LOCK.md`, **only for driver workflow**.  
5. **Only later reconcile** the driver extension with **existing payee and compensation systems** — Phase 5 in §14, explicitly avoiding a second compensation truth source.  

Within **driver** work specifically, the enduring takeaways of **this** document remain:

- application data identifies the person and collects **role-appropriate** intake  
- **driver** admin configuration defines the **driver** business truth for operations and commercial setup  
- downstream modules must read from that truth **without** mixing operator and payee, base pay and deductions, or equipment setup and dispatch assignment  
- company-driver and owner-operator logic must remain separate  
- team participation and direct pay relationship must remain separate  

This document remains the **driver-extension** planning anchor; the **program** anchor for onboarding order is §14 plus `docs/ONBOARDING_PHASE1_MULTI_ROLE_FOUNDATION_LOCK.md`.

## Field inventory framing

The safest way is to break the field inventory into:

- where the field lives  
- what the field means  
- whether it is required at approval  
- whether it is editable later  
- what it should reference  
- what it must not be confused with  

Below is the detailed field-by-field planning section.

## Field-by-Field Inventory and Relationship Planning

### Goal of this section

This section exists to define the field inventory for the admin driver configuration layer in a way that is safe for future implementation.

It is intentionally careful about:

- field ownership  
- table boundaries  
- foreign key direction  
- what should be structured versus free-text  
- what should be first-phase versus later-phase  
- what must not be mixed together  

This section is still design-only. It does not lock final schema names yet, but it should strongly guide the schema and relationship design later.

### 1. First principle: do not overload existing tables blindly

The current system already has:

- application records  
- person records  
- person role records  
- driver profile records  
- dispatch-facing driver records  

The new admin configuration work should not be shoved randomly into all of those tables.

A cleaner direction is:

- keep application for intake/review  
- keep person for identity  
- keep person role for role membership  
- keep driver profile for core driver identity/license basics  
- add a separate **admin driver configuration record** for operational and commercial setup  

That separate config record is important because the new fields you want are not just “driver profile” fields. They include:

- operating subtype  
- team mode  
- pay model  
- owner-operator commercial setup  
- equipment contribution  
- recurring commercial charges  
- insurance approval  

Those are really business configuration fields, not raw identity fields.

### 2. Recommended ownership model

#### 2.1 people

Use for **identity only**.

Should continue to own:

- first_name  
- last_name  
- phone  
- email  
- address  
- notes  
- active/inactive identity state  

Should **not** become the place for:

- compensation setup  
- trailer rent  
- insurance commercial approval  
- owner-operator percentage  
- team pay logic  

#### 2.2 person_roles

Use for **role membership only**.

Should continue to answer:

- is this person a DRIVER  
- is this person also DISPATCHER  
- is this person also MECHANIC  
- which role is primary  

Should **not** become the place for:

- long-haul vs city  
- owner-operator percentage  
- fuel discount rule  
- own trailer flag  

#### 2.3 driver_profiles

Use for **core driver-specific identity/compliance basics**.

This is the right home for:

- license identity  
- issuing region/country  
- expiry  
- maybe later raw endorsements/restrictions  
- maybe later normalized capability references  

This is **not** the ideal place for:

- pay model  
- recurring deductions  
- owner-operator percentage  
- trailer rent  
- team commercial setup  

#### 2.4 New admin driver configuration record

This is the right place for the **new business setup**.

This record should belong to one approved driver person and hold the company’s operational/commercial truth.

That means this record should be the home for:

- driver subtype  
- company driver vs owner-operator  
- single vs team  
- compensation type  
- compensation values  
- equipment contribution flags  
- recurring commercial terms  
- insurance approval  
- similar admin-only operational/business setup  

This is the cleanest direction.

### 3. Recommended core relationship shape

At planning level, the relationships should look like this:

- one **Person**  
- one or more **PersonRole**  
- zero or one **DriverProfile**  
- zero or one **DriverAdminConfig** for driver-role people  
- one dispatch-facing **Driver** row materialized for operational roster use  

#### 3.1 Person is the root person entity

This remains the human identity root.

#### 3.2 PersonRole says the person is a DRIVER

This remains how the system knows the person holds the driver role.

#### 3.3 DriverProfile says this driver has driver-specific identity/compliance info

This remains tied to the person.

#### 3.4 DriverAdminConfig says how this driver behaves in the business

This should also tie to the same person, tenant-scoped.

#### 3.5 Driver row is operational roster / dispatch-facing projection

This can continue to exist for dispatch convenience, but it should not become the only source of truth for deep business config.

**Important principle:** Person / Role / Profile / Config are the truth. Driver row is the operational surface.

### 4. Foreign key direction principles

Be very careful here.

#### 4.1 Tenant-scoped always

Every business row in this area must remain tenant-scoped.

That means all these records should continue to be tied to `tenant_id`.

#### 4.2 Root FK should be person-centered

The strongest anchor is still the person.

So the new admin config should likely point to:

- `tenant_id`  
- `person_id`  

Not just to the dispatch `drivers.id`.

**Why:**

- the config is about the real person/business relationship  
- the dispatch row is more like an operational projection  
- if dispatch row behavior changes later, the business truth should still remain person-centered  

#### 4.3 Do not key business truth only off drivers.id

That would make dispatch roster shape the owner of deeper business configuration, which is the wrong dependency direction.

#### 4.4 Optional references to teammate/payee/equipment must be carefully separated

Later, some fields may need foreign keys to:

- teammate person  
- payee  
- truck  
- trailer  
- terminal/home base  

But those should not all be forced into phase 1.

Phase 1 should keep the record stable without overcomplicating it.

### 5. Recommended new conceptual table: Driver Admin Configuration

This is still a **planning name**, not a locked schema name.

**Purpose:** A tenant-scoped, person-centered record storing the company-defined operational and commercial setup for a driver.

**Recommended root keys**

- id  
- tenant_id  
- person_id  

**Relationship rule**

- one config per tenant per person for driver-role people  
- unique `(tenant_id, person_id)`  

**Why this is good:**

- stable  
- easy to load  
- person-centered  
- avoids drift into duplicate configs  

### 6. Field groups and field-by-field planning

Now the actual field inventory.

#### Group A. Role and operating classification

These fields describe what kind of driver this person is in operations.

**A1. employment_relationship_type**

- **Meaning:** Describes the high-level business relationship between the carrier and this driver/operator.  
- **Planning values:** `company_driver`, `owner_operator`, maybe later `contractor_driver`  
- **Required at approval:** yes  
- **Editable later:** only carefully, because changing this affects pay logic and settlement logic  
- **FK:** none, enum/code style field  
- **Must not be confused with:** role code; compensation type  
- **Why it matters:** This is one of the most important fields because many downstream rules branch from it.  

**A2. driver_operating_subtype**

- **Meaning:** Describes how the driver operates day to day.  
- **Planning values:** `long_haul_company`, `city_local`, `shunt_yard`, `owner_operator`, maybe later `straight_truck_local`  
- **Required at approval:** yes  
- **Editable later:** yes, but carefully and audited  
- **FK:** none, enum/code style field  
- **Must not be confused with:** person role; compensation type  
- **Why it matters:** Dispatch logic and equipment assumptions depend on this.  

**A3. is_team_driver**

- **Meaning:** Whether this driver is configured to operate in team mode rather than single mode.  
- **Required at approval:** yes  
- **Editable later:** yes  
- **FK:** none, boolean or enum  
- **Must not be confused with:** current trip has co-driver; permanent team pairing  
- **Why it matters:** This is a base operational behavior flag.  

**A4. team_role_type**

- **Meaning:** Whether this driver is generally treated as primary or co-driver in a team setup.  
- **Planning values:** `primary`, `co_driver`, maybe `either` later  
- **Required at approval:** only when team mode is enabled  
- **Editable later:** yes  
- **FK:** none  
- **Must not be confused with:** direct payee; teammate link  
- **Why it matters:** Insurance, liability, and UI clarity.  

**A5. dispatch_team_pairing_flexible**

- **Meaning:** Whether dispatch may change team pairing at assignment time.  
- **Required at approval:** optional early; recommended eventually  
- **Editable later:** yes  
- **FK:** none  
- **Must not be confused with:** whether driver is team-capable  
- **Why it matters:** Teams exist but dispatch can still change pairings when assigning a load.  

#### Group B. Compensation model

These fields define how the carrier calculates base pay or settlement.

**B1. compensation_type**

- **Meaning:** The primary earning model.  
- **Planning values:** `hourly`, `per_mile`, `commission`  
- **Required at approval:** yes  
- **Editable later:** yes, but carefully and audited  
- **FK:** none  
- **Must not be confused with:** employment relationship type; deductions  
- **Why it matters:** This controls which rate fields matter.  

**B2. hourly_rate**

- **Meaning:** Base hourly rate.  
- **Required at approval:** only when compensation type is hourly  
- **Editable later:** yes  
- **FK:** none, numeric/money/decimal  
- **Must not be confused with:** parking charge; deduction amounts  

**B3. per_mile_rate**

- **Meaning:** Base pay per mile or settlement per mile.  
- **Required at approval:** only when compensation type is per mile  
- **Editable later:** yes  
- **FK:** none  
- **Must not be confused with:** fuel cents deduction; trailer rent per mile later  
- **Important note:** A per-mile field can apply to both company driver and owner-operator, but the business relationship remains different.  

**B4. commission_percent**

- **Meaning:** Commission percentage for owner-operator or other commission-based setup.  
- **Required at approval:** only when compensation type is commission  
- **Editable later:** yes  
- **FK:** none  
- **Must not be confused with:** fuel percentage deduction; insurance percentage deduction  

**B5. payee_type**

- **Meaning:** Who the carrier intends to pay in this relationship.  
- **Planning values:** `direct_driver`, `owner_operator_payee`, maybe later `external_payee_entity`  
- **Required at approval:** yes  
- **Editable later:** carefully  
- **FK:** probably none in phase 1 if using code only; later may reference payee/pay-to entity  
- **Must not be confused with:** team role; primary driver  
- **Why it matters:** This is the field that protects against confusing operator with payee.  

#### Group C. Equipment contribution

These fields describe what equipment the person/operator brings.

**C1. provides_own_truck**

- **Meaning:** Whether the driver/operator brings their own truck.  
- **Required at approval:** yes  
- **Editable later:** yes  
- **FK:** none  
- **Must not be confused with:** current assigned truck  

**C2. provides_own_trailer**

- **Meaning:** Whether the driver/operator brings their own trailer.  
- **Required at approval:** yes  
- **Editable later:** yes  
- **FK:** none  
- **Must not be confused with:** currently attached trailer  

**C3. equipment_contribution_type**

- **Meaning:** Summarizes the commercial equipment setup.  
- **Planning values:** `company_equipment`, `truck_only`, `truck_and_trailer`  
- **Required at approval:** yes  
- **Editable later:** yes  
- **FK:** none  
- **Must not be confused with:** dispatch assignment mode  
- **Why it matters:** This is the cleanest way to model the business examples discussed elsewhere in this document.  

**C4. company_trailer_rent_applies**

- **Meaning:** Whether company trailer rent should apply because company trailer is used.  
- **Required at approval:** yes when operator does not provide own trailer and trailer use is part of setup; otherwise optional or false  
- **Editable later:** yes  
- **FK:** none  
- **Must not be confused with:** actual trailer assignment on a specific load  

#### Group D. Recurring commercial charges

These fields define recurring business deductions or offsets.

**Important design note:** These are likely better modeled later as child rows or rule rows, not as endless flat columns. But for phase 1 planning, we can still name the important business concepts clearly.

**D1. fuel_charge_rule_type**

- **Meaning:** How fuel-related deduction/adjustment is applied.  
- **Planning values:** `none`, `fixed_amount`, `percentage`, maybe later `cents_per_unit`  
- **Required at approval:** optional, default none  
- **Editable later:** yes  
- **FK:** none  
- **Must not be confused with:** compensation type  

**D2. fuel_charge_value**

- **Meaning:** Numeric value for the fuel rule.  
- **Required at approval:** only if rule type is not none  
- **Editable later:** yes  
- **FK:** none  

**D3. parking_charge_rule_type**

- **Meaning:** How parking deduction is applied.  
- **Planning values:** `none`, `fixed_amount`, `percentage`  
- **Required at approval:** optional  
- **Editable later:** yes  

**D4. parking_charge_value**

- **Meaning:** Numeric value for parking rule.  
- **Required at approval:** only when applicable  
- **Editable later:** yes  

**D5. insurance_charge_rule_type**

- **Meaning:** How insurance charge is applied.  
- **Planning values:** `none`, `fixed_amount`, `percentage`, maybe later `weekly`, `monthly`  
- **Required at approval:** optional  
- **Editable later:** yes  

**D6. insurance_charge_value**

- **Meaning:** Numeric value for insurance rule.  
- **Required at approval:** only when applicable  
- **Editable later:** yes  

**D7. trailer_rent_rule_type**

- **Meaning:** How trailer rent is applied.  
- **Planning values:** `none`, `fixed_amount`, `weekly`, `monthly`, maybe later `per_mile`  
- **Required at approval:** when company trailer rent applies  
- **Editable later:** yes  
- **Must not be confused with:** base per-mile compensation  

**D8. trailer_rent_value**

- **Meaning:** Numeric value for trailer rent rule.  
- **Required at approval:** when trailer rent applies  
- **Editable later:** yes  

#### Group E. Approval / commercial clearance

These fields govern whether the person is approved to operate.

**E1. insurance_approved**

- **Meaning:** Whether insurance/commercial review for this business setup has been approved.  
- **Required at approval:** yes for owner-operator style relationships; maybe optional early for company drivers depending on process, but better as explicit  
- **Editable later:** yes  
- **FK:** none  
- **Must not be confused with:** insurance charge rule  

**This is very important:** One field says whether insurance costs apply. Another field says whether the operator is approved from an insurance/commercial standpoint. These are not the same thing.

**E2. operationally_cleared**

- **Meaning:** Whether the person is cleared for active operational use.  
- **Required at approval:** optional early; recommended later  
- **Editable later:** yes  
- **Must not be confused with:** person `is_active`; application approved  

**Why:** A person can be approved as a record but still not be cleared for dispatch.

#### Group F. Relationship fields that need extra care

These are fields that likely need foreign keys eventually, but should be phased carefully.

**F1. linked_teammate_person_id**

- **Meaning:** Reference to another person who is a normal teammate/co-driver pairing.  
- **Required at approval:** no  
- **Editable later:** yes  
- **FK:** should point to `people.id` within same tenant; tenant-safe validation required  
- **Must not be confused with:** current trip teammate; payee  
- **Important note:** This should likely not be required in phase 1.  

**F2. default_payee_id**

- **Meaning:** Reference to the payee entity the carrier pays.  
- **Required at approval:** maybe later, depending on payee architecture  
- **Editable later:** yes  
- **FK:** likely to payee/pay-to entity, not person necessarily  
- **Important note:** Do not force this too early unless payee architecture is already ready.  

**F3. default_truck_id**

- **Meaning:** The usual/default truck relationship for this driver/operator.  
- **Required at approval:** no in phase 1  
- **Editable later:** yes  
- **FK:** should point to truck/asset table later  
- **Must not be confused with:** current dispatch assignment  
- **Important note:** Good future field, not required for first slice.  

**F4. default_trailer_id**

- **Meaning:** The usual/default trailer relationship.  
- **Required at approval:** no in phase 1  
- **Editable later:** yes  
- **FK:** should point to trailer/asset table later  
- **Must not be confused with:** current attached trailer on a dispatch event  

**F5. home_terminal_id**

- **Meaning:** Reference to terminal or base.  
- **Required at approval:** no in phase 1  
- **Editable later:** yes  
- **FK:** terminal/location table later  
- **Important note:** Keep future-facing.  

### 7. Required at approval vs optional vs later

Now the important practical cut.

**Required at approval in first slice**

These are the best candidates for first build:

- employment_relationship_type  
- driver_operating_subtype  
- is_team_driver  
- compensation_type  
- hourly_rate or per_mile_rate or commission_percent as applicable  
- payee_type  
- provides_own_truck  
- provides_own_trailer  
- equipment_contribution_type  
- company_trailer_rent_applies  
- insurance_approved  

**Optional at approval in early phase**

- team_role_type  
- fuel_charge_rule_type / value  
- parking_charge_rule_type / value  
- insurance_charge_rule_type / value  
- trailer_rent_rule_type / value  
- operationally_cleared  

**Later / future**

- linked_teammate_person_id  
- default_payee_id (if payee system not ready)  
- default_truck_id  
- default_trailer_id  
- home_terminal_id  
- advanced rule engines  
- effective-dated historical term tracking  

### 8. Recommended implementation-safe relationship rule

If this goes into schema later, the safest first version is:

- One person-centered config row: `tenant_id`, `person_id` unique, driver-role required, holds the operational/commercial configuration.  

Then later, if needed:

- child rows for deduction rules  
- child rows for history/audit  
- child rows for linked teammate or assignment preferences  

This is safer than overloading `drivers` or stuffing everything into JSON too early.

### 9. Strong warnings for implementation later

Cursor should keep these rules in mind:

#### 9.1 Do not use drivers as the only truth source

`drivers` is dispatch-facing. Business configuration should be person-centered.

#### 9.2 Do not attach everything directly to person_roles

Role membership is not the same as operational/commercial configuration.

#### 9.3 Do not mix “has own truck” with “currently assigned truck”

One is a business setup fact. The other is an operational event.

#### 9.4 Do not mix “insurance approved” with “insurance charge applies”

One is approval state. The other is a recurring commercial term.

#### 9.5 Do not force teammate, truck, trailer, or payee FKs too early

Those are good future relationships, but phase 1 should avoid overcoupling if the target modules are not stable yet.

### 10. Next practical step

The next implementation planning step after this field inventory should be:

- decide the new config record/table boundary  
- tag each field as: phase 1 required, phase 1 optional, or later  
- decide which fields are: flat columns, child-rule rows later, FK references later  
- only then design API and admin UI  

That order will reduce future rework.

### Next move after this section

The smartest next move is to turn these into a **three-column build matrix**:

- field  
- first-phase decision  
- table ownership / FK direction  

---

**Note for Cursor (this section):** Keep this field-inventory material as a detailed section in this foundation document. Keep the relationship and foreign-key cautions intact. Do not simplify it into a short summary.
