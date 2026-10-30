# People / Onboarding — current behavior (authoritative for implemented behavior)

**Status:** describes the code on `gpt-review` as of the 2026-10-30 remediation. Where an older
design doc disagrees with this file about **implemented** behavior, this file wins and the older doc
is marked superseded below. Design docs remain the authority for **future** work they describe.

**Not deployed.** Schema changes below live in `alembic_tenant/pending/pc01/` and are not applied to
any real tenant database.

## D1 — Ownership

| Thing | Owner | Notes |
|---|---|---|
| Person identity (name, contact, address, active flag) | `people` | Canonical master. Edited from the People page. |
| Role held | `person_roles` | `role_code` + `is_active`. |
| Driver license facts | `driver_profiles` | One per person per tenant. |
| Driver classification | `driver_person_extensions` | `company_driver` or `owner_operator` only. |
| Dispatch roster | `drivers` | Operational projection: one canonical row per person (lowest id). Referenced by trips. Never the identity master. |
| Who gets paid | `payees` | Separate from Person. A driver links to one via `drivers.payee_id`. |
| Rates and their history | `compensation_profiles` | Effective-dated versions owned by a payee. |
| Application / review state | `person_applications` | Intake and review only. Never the roster and never the payroll source. |

Rules that follow:

- Approval materializes the projection. Re-approval changes nothing (no reactivation, no contact
  overwrite). Review edits after approval change the application only.
- Combined-mode setup before approval creates the projection **inactive**, so it cannot be dispatched.
- A terminated `drivers` row is never reactivated by approval or re-approval. Rehire is a separate
  workflow that does not exist yet.
- Rejecting an application leaves any pre-existing independent `drivers` row untouched.

## D3 — States and transitions

Three stored fields, each with one job:

- `person_applications.status`: `DRAFT -> SUBMITTED -> APPROVED` or `REJECTED`.
- `person_applications.setup_status`: `pending` -> `pending_downstream` on approval -> `complete` only
  when an admin explicitly marks onboarding complete. **Approval never completes onboarding.**
- `person_applications.current_workflow_lane`: queue/ownership hint for the admin list. Not a lifecycle.

Tenant UI mode (`platform` DB, `person_setup_ui_mode`):

- `combined` (default): driver classification and compensation are saved on the application page, and
  approval is blocked until both are saved.
- `segmented`: approval has no in-page prerequisites; classification and compensation happen later on
  the People page.

Assignment eligibility (new trip or plan assignment only; existing assignments are kept):

- `drivers.is_active`, no `termination_date` on or before today, linked Person active if any, and
  either an `APPROVED` driver application or **no driver application at all** (grandfathered roster).
- Pay readiness is **not** part of assignment eligibility.

## Payroll (modern vs legacy)

- `payees` + `compensation_profiles` are the modern rate system. `percent_rate` is a fraction
  (`0.75` = 75%), greater than 0 and at most 1. `cpm_loaded` must be greater than 0; `cpm_empty` may
  be 0. Versions are effective-dated (`effective_to` inclusive), never overlap, and past dates cannot
  be rewritten.
- `pay_profiles` is the legacy rate table. It is still readable; nothing here migrates or deletes it.
- Pay entries store `DEDUCTION` as a positive amount that reduces net. Pay-run generation maps it to
  source type `DEDUCTION` with a negative signed amount. `GROSS` and `ADJUSTMENT` stay earnings.
- A driver with no payee gets one only when their classification is known (`company_driver` ->
  employee driver, `owner_operator` -> owner-operator). Otherwise generation stops with
  `PAYRUN_PAYEE_CLASSIFICATION_REQUIRED`. No employee payee is ever assumed.
- A finalized pay run cannot be regenerated.

**Stop-gate:** installed tenant databases have `pay_runs`/`pay_run_items` columns that differ from the
ORM and have no `pay_documents` table. Pay-run generation cannot run on them until a reviewed
migration exists. See the remediation report.

## Admin gates (interim)

Tenant admin (`require_tenant_admin`; owner, admin, tenant admin, tenant owner) is required for:
driver create/update, driver phone writes, legacy license confirm, pay-profile writes, and every
admin onboarding route. Reads of drivers stay open to members. `FULL_ACCESS` is a separate helper and
is not the same as tenant admin even where the role lists currently match.

## D2 — Role coverage and backlog

Implemented end to end: **DRIVER** only.

`application_type` also allows DISPATCHER, HR, MECHANIC, PAYROLL, SAFETY, OFFICE_ADMIN, OTHER. The
invite dialog lists them as **disabled — not available yet**. Do not build those workflows without a
separate approval. Backend routes that call `_require_driver_workflow` already refuse them.

Backlog (not scheduled):

1. Non-driver applicant forms and admin review per role.
2. Rehire workflow for a terminated driver.
3. Pay-readiness as an explicit, separate gate (assignment eligibility deliberately excludes it).
4. Retiring legacy `pay_profiles` after a compatibility review.
5. Clearing stored plaintext invite tokens after the hash backfill is verified per tenant.

## D5 — Superseded documents

Superseded **for implemented behavior** by this file (kept as design history; do not delete):

- `docs/payroll_settlements/HR_PAYROLL_ONBOARDING_LOGIC_ANCHOR.md` — its approve-vs-complete and
  combined/segmented model is what shipped; its "future design" framing is outdated.
- `docs/application_onboarding/ONBOARDING_PHASE1_MULTI_ROLE_FOUNDATION_LOCK.md` — the separation of
  `application_type` and `requested_role_code` shipped; the multi-role workflows did not.
- `docs/people_driver/DRIVER_ONBOARDING_AND_ADMIN_CONFIGURATION_FOUNDATION.md` and
  `docs/people_driver/Driver_Onboarding_Architecture_2026-03-05.md` — early architecture; ownership in
  the table above replaces them where they differ.
