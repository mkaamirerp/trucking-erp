# Onboarding Phase 1 — Design-to-Implementation Planning Slice

**Purpose:** Translate the locked matrix documents (`docs/ONBOARDING_PHASE1_MULTI_ROLE_FOUNDATION_LOCK.md`, `docs/DRIVER_ONBOARDING_AND_ADMIN_CONFIGURATION_FOUNDATION.md`) into the **smallest safe implementation slice**—without drifting into **Phase 3 driver commercial config**, payee/compensation work, or dispatch behavior changes.

This document is the **Phase 1 implementation contract**; implementation notes and proof may be appended after deploy (§7–§9).

**Slice status:** **CLOSED** (2026-04-11). Manual QA passed; Phase 1 onboarding for this slice is **complete**. Further work waits on an **explicitly opened** follow-on slice—do not extend this slice ad hoc.

**Report status:** Refined per Phase 1 lock; **accepted** for implementation **only** under the guardrails in **§8** and the order in **§9**.

### Final Phase 1 lock (implementation)

- Phase 1 **may keep** the MVP default where **`requested_role_code` = `application_type`** on invite, but **implementation must not hardcode** them as **the same concept**—use **two fields**, **two assignments**, and **distinct** semantics (workflow vs role on approval).  
- **Non-driver workflows remain shared-foundation only in Phase 1** unless a **specific role extension** is **explicitly approved**.  
- **Backend changes in Phase 1 are behavior-alignment only**, **not** schema redesign.  
- **Hard guardrails (no exceptions without revising this doc):** **no migrations** · **no new tables** · **no driver commercial config** · **no compensation/payee changes** · **no dispatch logic changes**.  
- **Do not drift** into Phase 3, payee/compensation, or dispatch—stay strictly inside this slice.

---

## 1. Current-state alignment

Map from **approved Phase 1 design** to **what exists in the repo today**.

### 1.1 What already supports invite workflow selection

| Design intent | Current codebase |
|---------------|------------------|
| Admin chooses workflow when creating invite | **`POST /api/v1/admin/onboarding/invite-link`** (`app/routers/admin_onboarding.py`) accepts **`application_type`**, validated against **`APPLICATION_TYPES`** in `app/models/person_application.py`. |
| Invite creates canonical application row | Creates **`PersonApplication`** with `application_type`, `requested_role_code`, `intake_payload` seed (`step`: `dl_upload` for DRIVER, else `common`). |

### 1.2 What already supports `application_type`

| Area | Current |
|------|---------|
| Persistence | Column on **`person_applications`**; indexed `(tenant_id, application_type)` (tenant migration history). |
| API / schemas | Returned on applicant and admin payloads (`app/routers/driver_onboarding.py`, `app/schemas/driver_onboarding.py`). |
| Frontend invite | **`DriverOnboardingAdminListPage.tsx`**: `inviteApplicationType` + `createOnboardingInviteLink({ application_type })`. |
| Frontend applicant | **`OnboardingApplicantPage.tsx`**: `isDriver = (application_type === "DRIVER")` gates **full driver wizard** vs **minimal contact/address** flow. |
| Frontend admin detail | **`DriverOnboardingAdminDetailPage.tsx`**: `isDriver` gates license panel, work history, references, documents, agreements. |

### 1.3 What already supports `requested_role_code`

| Area | Current |
|------|---------|
| Persistence | Column on **`person_applications`** (separate from `application_type` per model docstring). |
| Invite creation | **`admin_onboarding.py`** sets **`requested_role_code = application_type`** (“MVP: same as application_type”). |
| Approval promotion | **`_ensure_person_entities_for_application`** uses **`requested_role_code`** (normalized) for **`PersonRole.role_code`** and **only** creates **`DriverProfile` + operational `drivers`** when that code is **`DRIVER`**. |

**Gap vs matrix:** Design locks **`application_type`** and **`requested_role_code`** as **non-conflated** concepts. Invite creation today sets **`requested_role_code = application_type`** (MVP default).

**Phase 1 refinement:** Phase 1 **may keep** that MVP default (same values on create), but **implementation must not hardcode** them as **one concept**—code, comments, and APIs should treat **`application_type`** (which **workflow/form** ran) and **`requested_role_code`** (which **role** is assigned on approval) as **distinct fields** so a later invite or admin edit can diverge without a refactor.

### 1.4 What already supports applicant detail loading

| Area | Current |
|------|---------|
| Token-based load | Applicant APIs in **`app/routers/driver_onboarding.py`** load **`PersonApplication`** by onboarding token; **`intake_payload`** (JSONB) holds step + form data. |
| Hydration | **`apps/web/src/core/hydrateOnboardingFormFromIntake.ts`** maps intake → form (driver-oriented field set). |
| Non-driver path | Minimal form writes a **subset** of fields to intake on save/submit. |

### 1.5 What already supports admin review

| Area | Current |
|------|---------|
| List | **`DriverOnboardingAdminListPage.tsx`** lists applications; shows `application_type` in rows. |
| Detail | **`DriverOnboardingAdminDetailPage.tsx`**: status, approve/reject, file viewer; **workflow-gated** driver panels via `isDriver`. |
| Backend | Admin list/detail/approve/reject routes under driver onboarding / person application (same router module). |

### 1.6 What already supports approval promotion

| Area | Current |
|------|---------|
| Driver workflow | **`approve_person_application`** → **`_ensure_person_entities_for_application`**: **`Person`**, **`PersonRole`**, conditional **`DriverProfile`**, **`_upsert_operational_driver_for_person`**. |
| Non-driver | Same path creates/updates **`Person`** + **`PersonRole`**; **no** `DriverProfile` / **`drivers`** when role code is not DRIVER (see tests in **`tests/test_driver_onboarding_operational_driver.py`**). |

### 1.7 What still reflects old driver-only assumptions

These are **implementation risks** for Phase 1 polish—not necessarily blockers:

| Issue | Where / note |
|-------|----------------|
| **Naming & routes** | UI strings and routes still say **“Driver”** onboarding review in places; matrix expects **multi-role** language where product wants it. |
| **Admin “Contact” panel for non-driver** | **`DriverOnboardingAdminDetailPage`**: shared panel still shows **DOB, SSN, sex, height**, etc., even when **`isDriver`** is false—fields are often empty for minimal applicants but **layout** still looks like a driver packet. Phase 1 may **trim** non-driver “Basic Info” to what non-driver intake actually collects. |
| **Applicant non-driver form** | Only **one** minimal flow for all non-driver types. **Non-driver workflows remain shared-foundation only in Phase 1** unless a **specific role extension** is **explicitly approved** outside this slice. |
| **`requested_role_code` tied to `application_type` on invite** | Cannot yet express “dispatcher form but approve as OTHER” without a small API/UI change. |
| **Hydration / EMPTY_FORM** | **`OnboardingApplicantPage`** / **`hydrateOnboardingFormFromIntake`** are **driver-field-heavy**; non-driver path bypasses most of it—OK, but any new role-specific steps will need **extension**, not more `if (!isDriver)` sprawl long-term. |
| **Legacy submissions** | Admin copy references **`DriverOnboardingSubmission`** compatibility; Phase 1 should **not** expand legacy path—only keep as-is or retire per separate decision. |

---

## 2. Exact Phase 1 scope (lock)

Implement **only** what is needed to **honor the approved matrices**, staying inside **one workflow per invite** and **no** driver commercial config.

**In scope:**

1. **Workflow-aware applicant form routing** — Ensure **`application_type`** from loaded **`PersonApplication`** consistently drives **driver full flow** vs **non-driver shared-foundation flow**; no driver-only steps on non-driver types.  
2. **Shared vs role-specific section gating** — Applicant UI and admin detail UI **hide** driver-only sections unless `application_type === "DRIVER"` (or equivalent product rule). **Non-driver workflows remain shared-foundation only in Phase 1** unless a **specific role extension** is **explicitly approved**; **do not** build dispatcher/HR/mechanic-specific questionnaires in Phase 1 without that approval.  
3. **Workflow-aware admin review surface** — Admin sees **shared** metadata + **driver panels only** for driver applications; align **sidebar / labels** with multi-role where cheap.  
4. **Correct approval promotion by workflow** — Verify and test: **DRIVER** → `Person` + `PersonRole` + `DriverProfile` + `drivers`; **non-DRIVER** → `Person` + `PersonRole` only **no** `drivers` / **no** `DriverProfile**.

**Explicitly part of Phase 1 if gaps found:**

- Tighten **non-driver admin panel** so “Basic Info” does not imply driver compliance fields when empty.  
- **Product copy** / page titles: “Onboarding review” vs “Driver onboarding” where the list is mixed-role.  
- **Tests** proving matrix behaviors (see §7).

---

## 3. Exact non-goals (Phase 1)

**Do not implement in this slice:**

- **Driver commercial / operational admin config** (employment type, payee flags, equipment contribution, trailer rent, team/O-O admin, insurance charge **rules**, etc.) — **Phase 3+** per program order.  
- **Compensation fields** on onboarding or new config tables.  
- **Owner-operator pay logic**, percentages, settlement rules.  
- **Trailer rent rule engine** or any recurring deduction engine.  
- **Team-driver deep logic** (primary/co-driver, pairing FKs, pay split).  
- **Dispatch integration changes** (assignment hints, load strip, `drivers`-centric behavior).  
- **Payee / `compensation_profiles` reconciliation** — **Phase 5**; do not duplicate pay data in onboarding.  
- **New tenant migrations**, **new tables**, or **schema redesign** (see §5 and §8).  
- Any **compensation / payee** or **dispatch** change (also restated in §8).

---

## 4. File-by-file implementation plan (Phase 1 only)

**No code—only where work would land.**

### 4.1 Backend

**Phase 1 backend work is behavior-alignment only**—routing, validation, response shape clarity, and comments—**not** schema redesign, new tables, or migrations.

| File | Likely change |
|------|----------------|
| `app/routers/admin_onboarding.py` | Keep MVP default **`requested_role_code = application_type`** on create if unchanged; **do not** treat the two as one concept in code—assign explicitly to both fields. Optional: separate invite field for `requested_role_code` **only** if product approves divergent values (still **no** new tables/migrations for Phase 1 unless §5 exception—**not expected**). |
| `app/routers/driver_onboarding.py` | Audit public/admin endpoints so **no driver-only mutation** is required for non-driver apps; ensure responses always include **`application_type`** / **`requested_role_code`** for gating. |
| `app/schemas/driver_onboarding.py` | Clarify field descriptions for **`application_type`** vs **`requested_role_code`** in OpenAPI/docs (no new commercial fields). |
| `app/models/person_application.py` | Likely **no change**; reference only. |

### 4.2 Frontend

| File | Likely change |
|------|----------------|
| `apps/web/src/pages/OnboardingApplicantPage.tsx` | Harden **`isDriver`** / **`application_type`** gating; **non-driver stays shared-foundation only** unless an **explicitly approved** role extension adds fields; avoid duplicating driver steps. |
| `apps/web/src/pages/DriverOnboardingAdminDetailPage.tsx` | **Non-driver**: reduce or hide driver-only **Basic Info** subfields (DOB/SSN/etc.) when not applicable; improve titles/labels; ensure **no** license/work-history panels for non-driver. |
| `apps/web/src/pages/DriverOnboardingAdminListPage.tsx` | Copy/filter: optional filter by **`application_type`**; rename labels to **onboarding** vs driver-only if desired. |
| `apps/web/src/core/hydrateOnboardingFormFromIntake.ts` | Only if new non-driver fields need hydration; keep **driver** logic isolated. |
| `apps/web/src/api.ts` | Types/comments if invite API gains optional `requested_role_code`; otherwise unchanged. |
| `apps/web/src/routes.ts` (or route config) | Optional path rename **only** if product wants `/operations/onboarding-review`—cosmetic; coordinate with links. |

### 4.3 Docs

| File | Likely change |
|------|----------------|
| `docs/ONBOARDING_PHASE1_IMPLEMENTATION_SLICE.md` | Updated after slice completes (proof checklist results)—this file. |
| Optional | Short **RUNBOOK** snippet for QA (link from §7)—**only if** the team wants it; user did not require new doc sprawl. |

### 4.4 Tests

| File | Likely change |
|------|----------------|
| `tests/test_driver_onboarding_operational_driver.py` | Add or extend cases: **non-driver** `application_type` end-to-end approve → **no** `drivers` row; **driver** → has roster row. |
| `tests/test_driver_onboarding.py` | Applicant token load + `application_type` propagation if gaps. |
| Frontend | Optional E2E or Playwright **later**; Phase 1 can stay **API-heavy** for proof. |

---

## 5. Migration decision

**Under the accepted Phase 1 slice: no migrations and no new tables.**

Rationale:

- **`application_type`** and **`requested_role_code`** already exist on **`person_applications`**.  
- Approval logic already **conditionally** creates **`DriverProfile`** / **`drivers`**.  
- Phase 1 is **behavioral and UI gating** only (see §4.1).

If a **true blocker** appears that **only** a schema change can fix, **stop** and **re-open** this planning doc—do **not** slip in migrations under Phase 1 without explicit slice revision.

---

## 6. Sequence of implementation

1. **Backend gating / alignment** — Confirm approve path and public read paths for all `APPLICATION_TYPES`; adjust only if a hole is found.  
2. **Frontend workflow-aware rendering** — Applicant page: verify routing; admin detail: trim non-driver panels.  
3. **Admin review alignment** — List/detail copy, optional filters, consistent display of `application_type` vs `requested_role_code`.  
4. **Approval-path verification** — Manual or automated: driver vs non-driver promotion matrix.  
5. **Tests** — Lock behaviors in `tests/test_driver_onboarding_operational_driver.py` (and siblings).  
6. **Deploy proof** — Rebuild API/nginx per project rules; run proof checklist (§7); capture logs/screenshots as team prefers.

---

## 7. Proof checklist

| # | Verify | Expected |
|---|--------|----------|
| 1 | **Driver** invite → applicant opens link | Full **driver** steps (license upload, etc.) appear. |
| 2 | **Dispatcher** (or any non-DRIVER) invite → applicant | **No** CDL upload step, **no** driver work-history/refs/documents wizard; **shared-foundation** flow only (unless an **explicitly approved** non-driver role extension is in scope). |
| 3 | **HR** / **Mechanic** invite → applicant | Same as #2: **no** driver-only sections. |
| 4 | Approve **driver** application | **`Person`**, **`PersonRole` DRIVER**, **`DriverProfile`**, operational **`drivers`** row present (per existing behavior). |
| 5 | Approve **non-driver** application | **`Person`** + **`PersonRole`** for that code; **no** new **`DriverProfile`** for that person if not driver; **no** operational **`drivers`** row for that approval path. |
| 6 | Admin detail for **non-driver** | **No** “Step 1 — Driver’s License” panel; **no** work history / driver documents panels. |
| 7 | Admin detail for **driver** | Full driver panels present. |
| 8 | **Regression** | Existing driver onboarding **submit** and **DL** flows still work for DRIVER type. |

---

## 8. Stop rule and acceptance

**This slice is accepted** as the Phase 1 implementation boundary when the team agrees to **all** of the following guardrails for any Phase 1 PR:

- **No migrations** (unless the slice doc is formally revised for a documented blocker—see §5).  
- **No new tables**.  
- **No driver commercial config** (Phase 3+).  
- **No compensation / payee / settlement changes** (Phase 5+).  
- **No dispatch logic changes** (assignment hints, load strip, etc.).  

Do **not** expand scope beyond §2 or violate §3. Treat **`application_type`** and **`requested_role_code`** as **distinct** semantics in code even when the MVP default sets them equal on invite (see §1.3).

---

## 9. What comes next (implementation order)

**Phase 1 implementation** should proceed **only** in this order (matches §6; use this as the execution checklist):

1. **Backend alignment / gating** — behavior-only; **no** schema redesign (§4.1).  
2. **Applicant workflow-aware rendering** — shared-foundation for non-driver unless an **explicitly approved** extension says otherwise.  
3. **Admin review cleanup for non-driver roles** — hide driver-only panels and trim misleading “driver packet” fields where appropriate.  
4. **Approval-path verification** — driver vs non-driver promotion (§7).  
5. **Tests** — lock matrix behavior in automated tests.  
6. **Deploy proof** — rebuild/restart per project rules; run §7 in the target environment.

After deploy proof, update this document (or an appendix) with **what was verified** so the slice stays auditable.
