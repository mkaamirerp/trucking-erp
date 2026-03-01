# Implementation Report: Onboarding Requests + Document Requirements

**Date:** 2026-02-26  
**Scope:** Part 1 (implementation brief) + Part 2 (enums + migration skeletons) + Part 3 (review + final adjustments). No breaking changes; tenant DB only; composite FKs; existing approve flow preserved with new guards.

---

## 1. Decisions and Resolutions (Three Parts Merged)

- **DRAFT vs IN_PROGRESS:** Kept **DRAFT** in DB and in enums for backward compatibility. Applicant UI treats DRAFT as IN_PROGRESS (editable state). No data migration.
- **Status gate for approve:** Approve allowed only when `status` is **SUBMITTED** or **IN_REVIEW** (previously only SUBMITTED).
- **Migration order (Part 3):** In one revision: create **document_requirements** → **person_application_requests** → FK requests → document_requirements → add **request_id** to person_application_files + FK.
- **Primary keys:** All new tables use `sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True, nullable=False)`.
- **CHECK constraints:** Added for enum-like columns on both tables (status, request_type, scope_type, applies_at_stage, visibility).
- **created_by_user_id / resolved_by_user_id:** Left as plain BIGINT; comment in migration: platform identity, no FK in tenant DB.
- **UNIQUE(tenant_id, id):** Kept on new tables for consistency with existing tenant patterns.

---

## 2. What Was Implemented

### 2.1 Python enums

- **New file:** `app/schemas/enums.py`  
  - `PersonApplicationStatus` (DRAFT, IN_PROGRESS, SUBMITTED, IN_REVIEW, WAITING_ON_DRIVER, WAITING_INTERNAL, APPROVED, REJECTED)  
  - `PersonApplicationRequestStatus` (OPEN, UPLOADED, ACCEPTED, REJECTED, EXPIRED)  
  - `PersonApplicationRequestType` (CRIMINAL_RECORD, DRUG_TEST, MVR, MEDICAL_CARD, EMPLOYMENT_VERIFICATION, OTHER)  
  - `DocumentRequirementScopeType` (ROLE, FORM)  
  - `DocumentRequirementVisibility` (APPLICANT, ADMIN_ONLY)  
  - `DocumentRequirementStage` (SUBMIT, POST_SUBMIT)  
  - Module docstring documents UI mapping: ACTION_REQUIRED = WAITING_ON_DRIVER; applicant never sees DRAFT.
- **Extended:** `app/schemas/driver_onboarding.py` — `DriverOnboardingStatus` now includes IN_PROGRESS, IN_REVIEW, WAITING_ON_DRIVER, WAITING_INTERNAL (existing DRAFT, SUBMITTED, APPROVED, REJECTED kept).

### 2.2 TypeScript enums

- **New file:** `apps/web/src/types/enums.ts`  
  Same enums as backend; comment documents applicant VIEW mapping (ACTION_REQUIRED = WAITING_ON_DRIVER, etc.).

### 2.3 Alembic tenant migration

- **Revision ID:** `b9c8d7e6f5a4`  
- **File:** `alembic_tenant/versions/b9c8d7e6f5a4_application_requests_and_document_requirements.py`  
- **Down revision:** `f8e353bbc2b9`  
- **Contents:**
  1. **document_requirements** — id (BIGSERIAL), tenant_id, scope_type, scope_key, doc_type, display_name, description, required, applies_at_stage, visibility, sort_order, is_active, created_at, updated_at; UNIQUE(tenant_id, id), UNIQUE(tenant_id, scope_type, scope_key, doc_type); indexes (tenant_id, scope_type, scope_key), (tenant_id, is_active), (tenant_id, doc_type); CHECKs on scope_type, applies_at_stage, visibility.
  2. **person_application_requests** — id (BIGSERIAL), tenant_id, application_id, doc_requirement_id, request_type, message_to_applicant, required, status, due_at, created_by_user_id, resolved_by_user_id, created_at, updated_at; UNIQUE(tenant_id, id); composite FK (tenant_id, application_id) → person_applications(tenant_id, id) ON DELETE CASCADE; indexes (tenant_id, application_id), (tenant_id, status), (tenant_id, request_type); CHECKs on status and request_type.
  3. Index (tenant_id, doc_requirement_id) and composite FK (tenant_id, doc_requirement_id) → document_requirements(tenant_id, id) ON DELETE SET NULL.
  4. **person_application_files:** add column request_id (BIGINT NULL); composite FK (tenant_id, request_id) → person_application_requests(tenant_id, id) ON DELETE SET NULL; index (tenant_id, request_id).
- **Downgrade:** Raises `RuntimeError` (forward-only).

### 2.4 SQLAlchemy models

- **New:** `app/models/document_requirement.py` — `DocumentRequirement` with columns and indexes matching migration (no CHECK in model; DB enforces).
- **New:** `app/models/person_application_request.py` — `PersonApplicationRequest` with composite FKs to person_applications and document_requirements; relationships to `PersonApplication` and `PersonApplicationFile`.
- **Updated:** `app/models/person_application.py` — added `requests` relationship to `PersonApplicationRequest`.
- **Updated:** `app/models/person_application_file.py` — added `request_id` and composite FK to person_application_requests; added `request` relationship.
- **Updated:** `app/models/__init__.py` — export `PersonApplicationRequest`, `DocumentRequirement`.

### 2.5 Approve endpoint behavior

- **File:** `app/routers/driver_onboarding.py`  
- **Changes:**
  - Status gate: approve allowed only when `app.status` is **SUBMITTED** or **IN_REVIEW** (was only SUBMITTED).
  - New guard before existing approval logic: count `PersonApplicationRequest` rows for (tenant_id, application_id) with `required=True` and `status != 'ACCEPTED'`. If count > 0 → **409** with message *"Required documents not completed. Accept or resolve all required document requests before approving."*
  - If there are **no** request rows, approve works as before (no regression).

---

## 3. Revision and Migration Run

- **Tenant head:** `b9c8d7e6f5a4` (confirmed with `alembic -c alembic_tenant.ini heads`).
- **Migration not run in this environment:** `ALEMBIC_TENANT_DATABASE_URL` was not available (password-protected tenant DB). You must run the migration with your tenant URL.

**Run the migration (with your tenant DB URL):**

```bash
docker exec truckerp-api sh -lc 'set -a && . /run/secrets/truckerp.env && set +a && cd /app && alembic -c alembic_tenant.ini upgrade head'
```

If your secrets do not set `ALEMBIC_TENANT_DATABASE_URL`, set it explicitly (e.g. for tenant_demo):

```bash
# Example (replace with your real URL/password):
export ALEMBIC_TENANT_DATABASE_URL="postgresql+asyncpg://postgres:YOUR_PASSWORD@truckerp-postgres:5432/tenant_demo"
docker exec -e ALEMBIC_TENANT_DATABASE_URL truckerp-api sh -lc 'cd /app && alembic -c alembic_tenant.ini upgrade head'
```

---

## 4. Proof Output (run after migration)

After `alembic -c alembic_tenant.ini upgrade head` on **tenant_demo** (or any tenant DB), run:

```bash
docker exec truckerp-postgres psql -U postgres -d tenant_demo -c "\d+ document_requirements"
docker exec truckerp-postgres psql -U postgres -d tenant_demo -c "\d+ person_application_requests"
docker exec truckerp-postgres psql -U postgres -d tenant_demo -c "\d+ person_application_files"
```

**Expected:**

- **document_requirements:** Columns id (bigint default nextval), tenant_id, scope_type, scope_key, doc_type, display_name, description, required (default true), applies_at_stage (default 'SUBMIT'), visibility (default 'APPLICANT'), sort_order (default 0), is_active (default true), created_at, updated_at. Constraints: pkey on id, uq_document_requirements_tenant_id_id, uq_document_requirements_tenant_scope_doc, ck_document_requirements_scope_type, ck_document_requirements_stage, ck_document_requirements_visibility. Indexes: ix_document_requirements_tenant_scope, ix_document_requirements_tenant_active, ix_document_requirements_tenant_doc_type.
- **person_application_requests:** Columns id (bigint default nextval), tenant_id, application_id, doc_requirement_id, request_type, message_to_applicant, required (default true), status (default 'OPEN'), due_at, created_by_user_id, resolved_by_user_id, created_at, updated_at. FK fk_person_application_requests_tenant_app_to_applications to person_applications(tenant_id, id) ON DELETE CASCADE; FK fk_person_application_requests_tenant_docreq_to_requirements to document_requirements(tenant_id, id) ON DELETE SET NULL. CHECKs ck_person_application_requests_status, ck_person_application_requests_request_type. Indexes: ix_person_application_requests_tenant_application_id, ix_person_application_requests_tenant_status, ix_person_application_requests_tenant_request_type, ix_person_application_requests_tenant_doc_requirement_id.
- **person_application_files:** Existing columns plus **request_id** (bigint NULL). FK fk_person_application_files_tenant_request_to_requests to person_application_requests(tenant_id, id) ON DELETE SET NULL. Index ix_person_application_files_tenant_request_id.

---

## 5. Files Touched (Summary)

| Path | Change |
|------|--------|
| `app/schemas/enums.py` | **New** — onboarding enums + UI mapping comment |
| `app/schemas/driver_onboarding.py` | Extended DriverOnboardingStatus (IN_PROGRESS, IN_REVIEW, WAITING_ON_DRIVER, WAITING_INTERNAL) |
| `apps/web/src/types/enums.ts` | **New** — TS enums matching backend |
| `alembic_tenant/versions/b9c8d7e6f5a4_application_requests_and_document_requirements.py` | **New** — migration |
| `app/models/document_requirement.py` | **New** — DocumentRequirement model |
| `app/models/person_application_request.py` | **New** — PersonApplicationRequest model |
| `app/models/person_application.py` | Added `requests` relationship |
| `app/models/person_application_file.py` | Added request_id, FK, index, `request` relationship |
| `app/models/__init__.py` | Export PersonApplicationRequest, DocumentRequirement |
| `app/routers/driver_onboarding.py` | Approve: status in (SUBMITTED, IN_REVIEW); block if required requests not all ACCEPTED |

---

## 6. What’s Left (Not in This Change)

- **APIs:** Applicant GET/POST requests, admin create/resolve requests, document-requirements CRUD (Part 1 §4) — not implemented.
- **UI:** Driver intake submit lock, ACTION_REQUIRED request list + upload, admin “Request documents” and checklist (Part 1 §5) — not implemented.
- **Submit transition:** IN_PROGRESS → SUBMITTED (and any renames from DRAFT to IN_PROGRESS in new flows) — existing submit already sets SUBMITTED; no change in this PR.
- **Automatic status moves:** e.g. when all required requests are ACCEPTED, set application to IN_REVIEW — to be implemented with the new request/upload/resolve endpoints.

---

## 7. Acceptance (from Part 1)

- Approve only when status in (SUBMITTED, IN_REVIEW) and all required requests ACCEPTED — **done** (guard in place; no request rows ⇒ approve allowed).
- Existing approve flow (person_id, commit) — **unchanged**; new guard only adds a condition.
- Tenant DB only; composite FKs; no platform DB changes — **done**.
- Enums and migration match spec; CHECK constraints and idempotent-style single-run migration — **done**.

End of report.
