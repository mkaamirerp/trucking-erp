# HR / Payroll / Onboarding Logic Anchor

## Purpose

This document locks the future **people / onboarding architecture** between manager approval, HR/payroll (and ops) onboarding completion, and the **tenant-level UI mode** that controls where mandatory setup fields are exposed.

This is a **logic/design anchor** for future implementation. It is **not** driver-only: the same patterns apply across onboarding workflows (e.g. driver, dispatcher, other roles).

This anchor does **not** mean HR or Payroll modules must be built right now.

**Preservation:** Any future HR/payroll design doc or implementation plan should align with this document and must **not** narrow the model to “driver only” or rename the tenant toggle back to a driver-scoped flag.

---

## Architecture level (not driver-only)

Model this at the **people / person application / onboarding truth** layer:

- **Approval** is a general people/workflow concept.
- **Onboarding completion** is a general people/workflow concept.
- What **differs by workflow** is the **required downstream setup** (which fields, which modules, which order)—not the existence of approve vs onboard as ideas.

Examples of workflow-specific downstream setup (illustrative, not exhaustive):

- **DRIVER** — may require HR + payroll + driver configuration (and other ops fields as defined).
- **DISPATCHER** — may require HR + payroll + RBAC / dispatch permissions (and other ops fields as defined).
- **Other roles** — each may define its own required setup blocks.

**Rules:**

- Keep the **pattern** general.
- Let **required downstream setup** be **workflow-specific**.
- Do **not** hard-code this logic as driver-only.

---

## Core business distinction: Approve vs Onboard

There is an important business difference between:

1. **Approve**
2. **Onboard**

These are **not** the same action.

### Approve

A manager (or other authorized role) reviews the **person application** and approves the person to move forward **for that workflow**.

This means:

- the application is accepted
- the person may be promoted into the system according to the approved workflow
- required **downstream** setup may still be incomplete

### Onboard

Onboarding is only fully complete when **all required downstream setup** for that workflow is completed by the correct responsible party(ies), and completion is **explicitly finalized** where the product requires it.

Downstream setup may include, depending on workflow and tenant policy:

- role-specific configuration (e.g. driver extension, dispatch/RBAC)
- HR setup
- payroll / compensation setup
- other mandatory operational setup fields

So:

- **Approve = accepted to move forward**
- **Onboard = all required setup completed and explicitly finalized** (per workflow rules)

---

## General truth on person application / onboarding

Store approval and onboarding completion as **general** fields on the **person application / onboarding truth** (not as a driver-only parallel model).

Illustrative general fields:

- `approved_at`
- `approved_by_user_id`
- `onboarded_at`
- `onboarded_by_user_id`

And one **general** setup/completion concept, e.g.:

- `setup_status`

Suggested values (exact enum can be refined later):

- `pending` — not yet approved, or pre-approval state as defined
- `pending_downstream` — approved (or equivalent) but mandatory downstream setup not complete
- `complete` — all required downstream setup done and finalized per product rules

The important business rule:

> **Approval alone does not always mean full onboarding is complete.**

Exact status names and transitions can be finalized later; the **logic** must support distinct phases: approved vs fully onboarded.

---

## Product direction: tenant-level Person Setup UI Mode

A **tenant-level**, **workflow-agnostic** setting is needed so small fleets and departmental companies can both be supported.

### Setting (do not use a driver-only name)

**Do not** use `driver_setup_ui_mode`.

Use a broader tenant-level setting such as:

- `person_setup_ui_mode`

### Allowed values

- `combined` — **default**
- `segmented`

Naming can be refined later, but behavior should follow this model at the **people/onboarding** level, not scoped to drivers only.

### Meaning

- **`combined`:** The onboarding/review experience **may** expose downstream setup fields **for the relevant workflow** so smaller organizations can complete setup from one place when policy allows.
- **`segmented`:** Onboarding/review stays **limited to that stage**; downstream setup is completed later in HR / payroll / ops (and other) workspaces as defined for the workflow.

---

## Mode behavior

### 1. `combined` (default)

Used when one person or a small team often handles review plus downstream setup.

In this mode:

- the onboarding/review surface **can** expose required setup fields needed to finish onboarding **for that application’s workflow**
- the person doing review **may** complete everything from one screen when the product allows it
- default for tenants that do not want to bounce across many modules for routine hires

### 2. `segmented`

Used when responsibilities are split across departments or roles.

In this mode:

- onboarding/review shows only fields **owned by that stage**
- downstream-owned fields are **hidden** from the manager/reviewer on that screen
- HR / payroll / ops complete remaining required setup in **their** workspaces
- onboarding is **not** fully complete until mandatory downstream fields are done and finalized per rules

---

## Critical rule: mandatory fields remain mandatory in both modes

The toggle does **not** change whether fields are **required** for that workflow.

The toggle changes:

- **where** those fields are exposed
- **who** completes them
- **at which step** they are completed

So:

- fields hidden from a manager in `segmented` mode are still **mandatory business fields** for that workflow
- they must still exist in the appropriate downstream workspaces
- they must still be completed before onboarding is **fully** complete

---

## Critical UX rule: hidden fields must not block the wrong user’s save

If fields are hidden due to UI mode or role ownership, they must **not** cause hidden-field validation errors on that user’s screen.

### In `combined`

- required setup fields **may** be shown on onboarding/review
- save/finalize **may** validate them there

### In `segmented`

- the reviewer can still approve/save **their** stage without seeing downstream-owned fields
- hidden fields must **not** block that save
- the record should move into a **pending downstream** setup state (see `setup_status` above)

Strict UX rule:

> Never show a user an error for fields they cannot access on that screen.

---

## Workflow model (general)

### Manager (or stage owner) approval

Authorized user approves the **person application** for the workflow.

Result:

- application accepted (general approval truth: timestamps / actor ids)
- person may progress per workflow rules
- downstream setup may still be pending (`setup_status` e.g. `pending_downstream`)

### Downstream completion (HR / payroll / ops)

Responsible parties complete mandatory setup owned by their stage **for that workflow**.

After all mandatory downstream setup is complete:

- an authorized user performs an explicit final action (naming TBD), e.g. **Complete onboarding** / **Mark onboarded**

That action means:

- required setup is complete for that workflow
- the person is **fully onboarded** per product rules
- `onboarded_at` / `onboarded_by_user_id` (and `setup_status` → `complete`) reflect that truth

---

## Operational readiness (general)

Future behavior should distinguish, **per person / application / workflow**:

- approved but not fully onboarded
- fully onboarded / ready for downstream operations (dispatch, payroll, settlement, compliance, etc.) **according to workflow-specific gates**

In `segmented` mode especially:

- approval can happen first
- downstream completion happens later
- the person must not be treated as **fully operationally ready** until mandatory setup is done

---

## Architecture rule

### What is configurable

- screen exposure
- workflow ownership
- which workspace completes which setup **for a given workflow**

### What is not configurable

- business truth ownership
- whether mandatory fields exist for a workflow
- whether required setup must **eventually** be completed

So:

> **Visibility / edit location** is configurable.  
> **Data ownership** is not.

Do not duplicate canonical business truth because a field appears on more than one screen.

---

## Current practical direction

- HR and Payroll modules do not need to be fully designed in this doc.
- **Do** keep this people-level model so future work does not collapse **Approve** and **Onboard**, and does not paint the tenant toggle as driver-only.

Default product expectation:

- `person_setup_ui_mode = combined` is the default.
- `segmented` must support departmental completion **without** breaking validation clarity or blocking the wrong user.

---

## Roadmap: richer pay recipient / payout (deferred)

Pay recipient / payout routing beyond single-driver payee (O/O, team, co-driver) — **deferred**; v1 uses implicit `drivers.payee_id` only and is **not** the final payout architecture.

---

## Implementation guardrails for future Cursor work

1. Do **not** collapse **Approve** and **Onboard** into one concept.
2. Do **not** let hidden downstream fields block a user who cannot see them.
3. Do **not** make the UI mode toggle change whether fields are **required** for the workflow.
4. Do **not** duplicate business truth across screens; one canonical source per concern.
5. Use **`person_setup_ui_mode`** (or agreed successor name)—**not** `driver_setup_ui_mode`.
6. Model approval/onboarding/setup state on **person application / onboarding truth** with general fields (e.g. `approved_*`, `onboarded_*`, `setup_status`).
7. Keep **required downstream setup** **workflow-specific** (driver vs dispatcher vs other)—not a single hard-coded driver path.
8. Ensure an explicit downstream completion/finalization path when the product requires it.

---

## Locked direction summary

- Think at **people / onboarding architecture**, not driver-only.
- Tenant toggle: **`person_setup_ui_mode`** (`combined` | `segmented`); not `driver_setup_ui_mode`.
- **Approve** vs **Onboard** are general; live on **person application / onboarding** truth with general fields and **`setup_status`** (e.g. `pending` / `pending_downstream` / `complete`—refinable).
- Mandatory fields stay mandatory; the toggle only changes **where** they are completed.
- Hidden fields must not block the wrong user’s save.
- **Downstream requirements** are **workflow-specific** (driver, dispatcher, other).
- Visibility is configurable; data ownership is not.
