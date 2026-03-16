# Onboarding Multi-Role Implementation Plan

**Version:** 1.0  
**Date:** 2026-03-03  
**Status:** Implementation-ready

---

## A. Revised Target Architecture

### Key Concepts (Do Not Conflate)

| Concept | Purpose | Example |
|---------|---------|---------|
| **application_type** | Intake workflow/form track. Controls which form/steps the applicant sees. | `DRIVER`, `DISPATCHER`, `HR`, `OTHER` |
| **requested_role_code** | Role assigned to Person on approval. Written to `person_roles.role_code`. | `DRIVER`, `DISPATCHER`, `OWNER` |

For MVP, admin may set both to the same value (e.g. application_type=DRIVER → requested_role_code=DRIVER), but the schema and logic must treat them as separate. Future: application_type could be `INTERN` → requested_role_code `DISPATCHER`.

### Data Flow

```
Admin creates invite → application_type + requested_role_code (both set)
                    → PersonApplication created (DRAFT)

Applicant opens link → Reads application_type → Shows matching form
                    → Saves into intake_payload (structured: common, role_specific, review_only, documents)

Admin approves      → Reads requested_role_code → Creates PersonRole(role_code=requested_role_code)
                    → For DRIVER only: creates DriverProfile from role_specific.driver
                    → Promotes only common + role_specific.driver.license (if DRIVER)
```

### MVP Scope

| application_type | Form | Approval Outcome |
|------------------|------|------------------|
| **DRIVER** | Full 4-step workflow (license, personal, work history, documents) | Person + PersonRole(DRIVER) + DriverProfile |
| **DISPATCHER, HR, MECHANIC, PAYROLL, SAFETY, OFFICE_ADMIN, OTHER** | Minimal common intake only (name, contact, address) | Person + PersonRole(requested_role_code) |

Role-specific non-driver forms are deferred.

---

## B. Minimal MVP Implementation Plan

### Phase 1: Schema & Backend (MUST FIX NOW)

1. Add `application_type` and `requested_role_code` columns to `person_applications`.
2. Add `InviteLinkRequest.application_type` and `requested_role_code`; store on create.
3. Enforce structured `intake_payload` shape (document + validate on save).
4. Branch approval logic: create DriverProfile only when `requested_role_code == "DRIVER"`.
5. Use `requested_role_code` for PersonRole.role_code on approval.

### Phase 2: Frontend (SHOULD FIX NEXT)

6. Invite modal: application type dropdown (and requested_role_code, default same).
7. OnboardingApplicantPage: branch by `application_type` — DRIVER = full form; others = minimal common.
8. Admin detail: show application_type and requested_role_code.

### Phase 3: Safeguards (SHOULD FIX NEXT)

9. application_type change: block if intake has meaningful progress; or require explicit reset.
10. API validation: reject invalid application_type / requested_role_code.

### Phase 4: Later Refactor (LATER)

11. Naming cleanup (driver-onboarding → onboarding).
12. Role-specific non-driver forms.
13. Dedicated promotion service.

---

## C. Exact Migration Changes

### New Tenant Migration

**File:** `alembic_tenant/versions/<revision>_add_application_type_and_requested_role.py`

```python
"""Add application_type and requested_role_code to person_applications.

application_type = intake workflow/form track.
requested_role_code = role assigned on approval (person_roles.role_code).
"""
from alembic import op
import sqlalchemy as sa

revision = "<revision_id>"
down_revision = "<current_head>"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "person_applications",
        sa.Column("application_type", sa.String(50), nullable=False, server_default="DRIVER"),
    )
    op.add_column(
        "person_applications",
        sa.Column("requested_role_code", sa.String(50), nullable=False, server_default="DRIVER"),
    )
    op.create_index(
        "ix_person_applications_tenant_application_type",
        "person_applications",
        ["tenant_id", "application_type"],
    )


def downgrade() -> None:
    op.drop_index("ix_person_applications_tenant_application_type", table_name="person_applications")
    op.drop_column("person_applications", "requested_role_code")
    op.drop_column("person_applications", "application_type")
```

---

## D. Exact Backend Changes

### 1. `app/models/person_application.py`

- Add columns:
  - `application_type: Mapped[str]` — `String(50)`, default `"DRIVER"`
  - `requested_role_code: Mapped[str]` — `String(50)`, default `"DRIVER"`
- Add index on `(tenant_id, application_type)`.
- Update docstring: distinguish application_type (form) vs requested_role_code (approval role).

### 2. `app/routers/admin_onboarding.py`

- Extend `InviteLinkRequest`:
  - `application_type: str = "DRIVER"`
  - `requested_role_code: str | None = None` — if None, use application_type
- On create:
  - `app.application_type = body.application_type`
  - `app.requested_role_code = body.requested_role_code or body.application_type`
- Validate: application_type and requested_role_code in allowed list (from meta or constant).

### 3. `app/routers/driver_onboarding.py`

- `_ensure_person_entities_for_application`:
  - Use `app.requested_role_code` for PersonRole.role_code (not application_type).
  - Create DriverProfile only when `app.requested_role_code == "DRIVER"`.
  - Read license fields from `intake_payload.get("role_specific", {}).get("driver", {})` (or fallback for legacy shape).
- `_person_application_canonical_data`:
  - For DRIVER: read license from structured intake (`intake.get("role_specific", {}).get("driver", {})`) with fallback to legacy top-level intake keys.
  - For non-DRIVER: no license required; do not fail on missing license.
- `save_applicant_intake` / `update_applicant_application`:
  - Merge payload into structured shape (see payload schema below).
  - Optionally: if admin changes application_type (new endpoint) and intake has progress, return 409 or require reset.

### 4. `app/schemas/driver_onboarding.py`

- Add `InviteLinkRequest` schema (or use shared) with `application_type`, `requested_role_code`.
- Add `PersonApplicationListItem.application_type`, `requested_role_code`.
- Add `ApplicantApplicationOut.application_type`, `requested_role_code`.
- Add constants: `APPLICATION_TYPES`, `ROLE_CODES` (or read from meta).

### 5. Constants / Meta

- Add `APPLICATION_TYPES = ["DRIVER", "DISPATCHER", "HR", "MECHANIC", "PAYROLL", "SAFETY", "OFFICE_ADMIN", "OTHER"]`.
- Add `ROLE_CODES` (can match APPLICATION_TYPES for MVP, or use meta roles).

### 6. Immutability Guard (SHOULD FIX NEXT)

- Define "meaningful progress": `intake_payload` has non-empty `common` or `role_specific` or `documents`.
- If PATCH/PUT to change application_type and progress exists: return 409 with message "Cannot change application type after applicant has started. Use reset to clear application data first."
- Reset endpoint already exists: `resetPersonApplicationDraft` — after reset, application_type could be changeable (optional enhancement).

---

## E. Exact Frontend Changes

### 1. `apps/web/src/api.ts`

- Extend `OnboardingInviteLinkRequest`:
  ```ts
  application_type?: string;  // default "DRIVER"
  requested_role_code?: string | null;  // default to application_type
  ```
- Add `PersonApplicationListItem.application_type`, `requested_role_code`.
- Add `ApplicantApplication.application_type`, `requested_role_code`.

### 2. `apps/web/src/pages/DriverOnboardingAdminListPage.tsx`

- Invite modal: add application type dropdown (APPLICATION_TYPES).
- Optional: requested_role_code dropdown (default = application_type).
- Pass both to `createOnboardingInviteLink`.
- List: optionally show application_type column/badge.

### 3. `apps/web/src/pages/OnboardingApplicantPage.tsx`

- Fetch application; read `application.application_type`.
- **If DRIVER:** Render existing full 4-step form (no change to form content).
- **If non-DRIVER:** Render minimal common form:
  - First name, last name
  - Email, phone
  - Street, city, region, postal, country
  - (Optional) notes
- Save into structured intake: `{ common: {...}, role_specific: { driver: {...} | {} }, review_only: {...}, documents: {...} }`.
- DRIVER form continues to populate `role_specific.driver` and `documents`; minimal form only populates `common`.

### 4. `apps/web/src/pages/DriverOnboardingAdminDetailPage.tsx`

- Display `application_type` and `requested_role_code` in header or info section.
- For non-DRIVER: show only common section (no license, work history, DOT docs).
- For DRIVER: keep current full display.

---

## F. Promotion Rules per application_type

Promotion is driven by **requested_role_code**, not application_type.

| requested_role_code | Person | PersonRole | DriverProfile |
|---------------------|--------|------------|---------------|
| DRIVER | first_name, last_name, phone, email, address, notes from `common` | role_code=DRIVER, is_active=True | Create/update from `role_specific.driver.license_*` |
| DISPATCHER, HR, MECHANIC, etc. | same | role_code=requested_role_code, is_active=True | Do not create |

### Exact promotion map

```
Person (always):
  first_name  ← common.first_name  or app.first_name
  last_name   ← common.last_name   or app.last_name
  phone       ← common.phone       or app.phone
  email       ← common.email       or app.email
  street_address ← common.address_street or app.street_address
  city        ← common.address_city or app.city
  region      ← common.address_region or app.region
  postal_code ← common.address_postal or app.postal_code
  country     ← common.address_country or app.country
  notes       ← common.notes       or app.notes

PersonRole (always):
  role_code   ← app.requested_role_code
  is_active   ← True

DriverProfile (only if requested_role_code == "DRIVER"):
  license_number  ← role_specific.driver.license_number (with fallbacks)
  license_region  ← role_specific.driver.license_region
  license_expiry  ← role_specific.driver.license_expiry
```

**Never promote:** review_only, documents metadata, jobs, refs, SSN, agreements.

---

## G. Recommended Payload Schema

### intake_payload structure

```ts
interface IntakePayload {
  common?: {
    first_name?: string;
    last_name?: string;
    phone?: string;
    email?: string;
    address_street?: string;
    address_city?: string;
    address_region?: string;
    address_postal?: string;
    address_country?: string;
    notes?: string;
  };

  role_specific?: {
    driver?: {
      license_number?: string;
      license_region?: string;
      license_expiry?: string;
      cdl_class?: string;
      endorsements?: string;
      restrictions?: string;
      license_issue_date?: string;
      // FMCSA / experience fields — review only, in driver sub-object for organization
      years_experience?: string;
      total_miles?: string;
      equipment_types?: string;
      accidents_last_3_years?: string;
      violations_last_3_years?: string;
      dot_medical_card_expiry?: string;
      emergency_contact_name?: string;
      emergency_contact_relationship?: string;
      emergency_contact_phone?: string;
      jobs?: WorkHistoryEntry[];
      refs?: ReferenceEntry[];
    };
    // Future: dispatcher?, hr?, mechanic?
  };

  review_only?: {
    date_of_birth?: string;
    ssn?: string;
    sex?: string;
    nationality?: string;
    height?: string;
    agree_info_accurate?: boolean;
    agree_background_check?: boolean;
    agree_dot_compliance?: boolean;
    // Jobs/refs can live here instead of role_specific.driver for shared audit; or in role_specific.driver for DRIVER-only.
    // Recommendation: keep in role_specific.driver for DRIVER; add to review_only only if shared across roles.
  };

  documents?: Record<string, {
    original_filename?: string;
    storage_key?: string;
    file_id?: string;
    uploaded_at?: string;
  }>;

  // Legacy / backward compatibility: allow flat keys at top level for existing DRIVER apps
  // Migration path: on save, normalize into common/role_specific/review_only/documents
  [key: string]: unknown;
}
```

### Normalization rules (backend on save)

- If payload has top-level `first_name`, `last_name`, etc. (legacy): merge into `common`.
- If payload has top-level `driver_license_number`, `license_region`, etc.: merge into `role_specific.driver`.
- If payload has `jobs`, `refs`: merge into `role_specific.driver` (DRIVER) or `review_only`.
- If payload has `documents`: ensure shape is `Record<string, DocMeta>`.
- Preserve `step`, `form_country_default`, `form_region_default`, `field_sources`, `user_edited_fields` at top level (operational, not promoted).

---

## H. File-by-File Execution Plan

### MUST FIX NOW

| Order | File | Action |
|-------|------|--------|
| 1 | `alembic_tenant/versions/<new>_add_application_type_and_requested_role.py` | Create migration. Run after generating revision. |
| 2 | `app/models/person_application.py` | Add `application_type`, `requested_role_code` columns and index. |
| 3 | `app/schemas/driver_onboarding.py` | Add `APPLICATION_TYPES`, `ROLE_CODES`; extend `InviteLinkRequest` (or create in admin_onboarding); add fields to `PersonApplicationListItem`, `ApplicantApplicationOut`. |
| 4 | `app/routers/admin_onboarding.py` | Add `application_type`, `requested_role_code` to InviteLinkRequest; validate; set on PersonApplication create. |
| 5 | `app/routers/driver_onboarding.py` | In `_ensure_person_entities_for_application`: use `requested_role_code` for PersonRole; create DriverProfile only when `requested_role_code == "DRIVER"`. In `_person_application_canonical_data`: support structured intake; for non-DRIVER, do not require license. |
| 6 | Run migration | `docker exec truckerp-api bash -lc '... tenant_upgrade_head.sh'` |
| 7 | Rebuild & restart API | Per workspace rules |

### SHOULD FIX NEXT

| Order | File | Action |
|-------|------|--------|
| 8 | `apps/web/src/api.ts` | Extend `OnboardingInviteLinkRequest`, `PersonApplicationListItem`, `ApplicantApplication` with application_type, requested_role_code. |
| 9 | `apps/web/src/pages/DriverOnboardingAdminListPage.tsx` | Add application type (and optional requested_role_code) dropdown to invite modal; pass to API. |
| 10 | `apps/web/src/pages/OnboardingApplicantPage.tsx` | Branch by `application_type`: DRIVER = existing form; else = minimal common form. Ensure save writes into structured intake. |
| 11 | `apps/web/src/pages/DriverOnboardingAdminDetailPage.tsx` | Display application_type, requested_role_code; for non-DRIVER hide license/work/docs sections. |
| 12 | `app/routers/driver_onboarding.py` | Add immutability guard: if changing application_type and intake has progress, return 409. (Requires PATCH endpoint for application_type if not yet present.) |
| 13 | `app/routers/driver_onboarding.py` | Normalize intake_payload on save into common/role_specific/review_only/documents where possible. |
| 14 | Frontend build & nginx restart | `npm run build` → `restart truckerp-nginx` |

### LATER REFACTOR

| Order | File | Action |
|-------|------|--------|
| — | Router prefix | Rename `driver-onboarding` → `onboarding` (breaking; coordinate frontend) |
| — | Schema/module names | Rename `driver_onboarding.py` → `onboarding.py` |
| — | Page names | Rename `DriverOnboardingAdmin*` → `OnboardingAdmin*` |
| — | Role-specific non-driver forms | Add DISPATCHER, HR, etc. intake sections when needed |
| — | Promotion service | Extract `_ensure_person_entities_for_application` into dedicated service |

---

## Summary Checklist

- [ ] Migration adds `application_type`, `requested_role_code` to person_applications
- [ ] PersonApplication model has both columns
- [ ] Invite creation accepts and stores both
- [ ] Approval uses `requested_role_code` for PersonRole.role_code
- [ ] DriverProfile created only when requested_role_code == DRIVER
- [ ] Canonical data reads from structured intake with legacy fallback
- [ ] Invite modal has application type dropdown
- [ ] Applicant page branches: DRIVER = full form, others = minimal
- [ ] Admin detail shows application_type, requested_role_code; conditional sections
- [ ] intake_payload documented and normalized on save
- [ ] Immutability guard (optional in MVP)
