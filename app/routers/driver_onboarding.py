# ACTIVE_ONBOARDING_2026Q1
# Canonical onboarding pipeline:
#   PersonApplication -> applicant submit -> admin review -> admin approve/reject
# Legacy compatibility only:
#   DriverOnboardingSubmission routes below remain temporarily for older flows and
#   must not be treated as the future approval source-of-truth.
#
# Tenant policy (enforced in TenantContextMiddleware before handlers):
#   - Platform tenant must be status ACTIVE and db_status READY, or all routes get 403 "Tenant not ready".
#   - Applicant invite-token routes (/applicant/*) skip JWT/membership; auth is the token query param.
#   - Applicant routes also require TRIAL_ACTIVE/ACTIVE subscription (require_tenant_subscription_active).
#   - Authenticated routes here require membership + JWT like other tenant APIs (middleware).
#   - Router does not use Depends(require_active_tenant) because middleware already blocks non-ACTIVE tenants.

from __future__ import annotations

import asyncio
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.storage import (
    readable_path,
    save_applicant_dl_upload,
    save_applicant_doc_upload,
    serve_file,
)

from app.deps.auth import CurrentUser, get_current_user
from app.deps.tenant import require_tenant, require_tenant_slug
from app.deps.tenant_db import get_tenant_db
from app.models.application_access_token import ApplicationAccessToken
from app.models.driver_onboarding_submission import DriverOnboardingSubmission
from app.models.person import Person, PersonRole, DriverProfile
from app.models.person_application import APPLICATION_TYPES, PersonApplication
from app.schemas.driver_onboarding import (
    ApplicantApplicationOut,
    ApplicantIntakeRequest,
    ApplicantApplicationUpdate,
    DriverOnboardingApproveResponse,
    DriverOnboardingCreateResponse,
    DriverOnboardingRejectRequest,
    DriverOnboardingSubmissionCreate,
    DriverOnboardingSubmissionOut,
    DriverOnboardingStatus,
    PersonApplicationRejectRequest,
    PersonApplicationListItem,
    PersonOut,
)
from app.deps.admin import is_tenant_admin
from app.deps.entitlements import require_tenant_subscription_active
from app.services.dl_pdf417 import extract_pdf417_fields

router = APIRouter(prefix="/api/v1/driver-onboarding", tags=["driver-onboarding"])

# Token-based applicant flows: subscription gate matches admin invite (no JWT on these routes).
_APPLICANT_SUBSCRIPTION = [Depends(require_tenant_subscription_active)]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)




def _merge_field_sources(existing: dict | None, incoming: dict | None) -> dict:
    merged = dict(existing or {})
    for key, value in (incoming or {}).items():
        if value:
            merged[key] = value
    return merged


async def _best_effort_pdf417_extract(
    intake: dict, storage_key: str | None, tenant_slug: str
) -> dict:
    if not storage_key:
        return intake

    try:
        with readable_path(storage_key, "applicant_dl", tenant_slug) as path:
            if not path.is_file():
                return intake
            extracted = await asyncio.wait_for(
                asyncio.to_thread(extract_pdf417_fields, path),
                timeout=4.0,
            )
    except Exception:
        return intake

    if not extracted:
        return intake

    field_sources = _merge_field_sources(intake.get("field_sources"), extracted.pop("field_sources", None))
    for key, value in extracted.items():
        if value not in (None, ""):
            intake[key] = value
    if field_sources:
        intake["field_sources"] = field_sources
    return intake


async def _get_submission(
    db: AsyncSession, tenant_id: int, submission_id: int
) -> DriverOnboardingSubmission:
    submission = await db.scalar(
        select(DriverOnboardingSubmission).where(
            DriverOnboardingSubmission.id == submission_id,
            DriverOnboardingSubmission.tenant_id == tenant_id,
        )
    )
    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")
    return submission


async def _get_person_application_admin_or_404(
    db: AsyncSession, tenant_id: int, application_id: int
) -> PersonApplication:
    application = await db.scalar(
        select(PersonApplication).where(
            PersonApplication.id == application_id,
            PersonApplication.tenant_id == tenant_id,
        )
    )
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")
    return application


async def _get_person_application_admin_for_update_or_404(
    db: AsyncSession, tenant_id: int, application_id: int
) -> PersonApplication:
    application = await db.scalar(
        select(PersonApplication)
        .where(
            PersonApplication.id == application_id,
            PersonApplication.tenant_id == tenant_id,
        )
        .with_for_update()
    )
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")
    return application


def _payload_to_people_fields(data: dict) -> dict:
    """Map submission payload to people/driver_profiles fields. tenant_id set by caller; status lives on submission."""
    return {
        "first_name": data["first_name"],
        "last_name": data["last_name"],
        "phone": data.get("phone"),
        "email": data.get("email"),
        "street_address": data.get("address_street"),
        "city": data.get("address_city"),
        "region": data.get("address_region"),
        "postal_code": data.get("address_postal"),
        "country": data.get("address_country"),
        "notes": data.get("notes"),
    }


def _clean_text(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _coerce_optional_date(value) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, date):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return date.fromisoformat(text[:10])
        except ValueError:
            return None
    return None


def _person_application_canonical_data(app: PersonApplication) -> dict:
    """Extract canonical data for Person/DriverProfile promotion. Shared fields + driver-only when DRIVER."""
    intake = app.intake_payload or {}
    data = {
        "first_name": _clean_text(app.first_name) or _clean_text(intake.get("first_name")),
        "last_name": _clean_text(app.last_name) or _clean_text(intake.get("last_name")),
        "phone": _clean_text(app.phone) or _clean_text(intake.get("phone")),
        "email": _clean_text(app.email) or _clean_text(intake.get("email")),
        "address_street": _clean_text(app.street_address) or _clean_text(intake.get("address_street")) or _clean_text(intake.get("address_line")),
        "address_city": _clean_text(app.city) or _clean_text(intake.get("address_city")),
        "address_region": _clean_text(app.region) or _clean_text(intake.get("address_region")) or _clean_text(intake.get("license_region")) or _clean_text(intake.get("license_state")),
        "address_postal": _clean_text(app.postal_code) or _clean_text(intake.get("address_postal")),
        "address_country": _clean_text(app.country) or _clean_text(intake.get("address_country")),
        "notes": _clean_text(app.notes) or _clean_text(intake.get("notes")),
        "driver_license_number": _clean_text(intake.get("driver_license_number")) or _clean_text(intake.get("license_number")),
        "license_region": _clean_text(intake.get("license_region")) or _clean_text(intake.get("license_state")),
        "license_expiry": _coerce_optional_date(intake.get("license_expiry")),
    }
    missing = [field for field in ("first_name", "last_name") if not data.get(field)]
    if missing:
        raise HTTPException(
            status_code=409,
            detail=f"Application is missing required applicant fields for approval: {', '.join(missing)}",
        )
    return data


async def _ensure_person_entities_for_application(
    db: AsyncSession,
    app: PersonApplication,
) -> Person:
    """Create/update Person, PersonRole(requested_role_code), DriverProfile only when requested_role_code==DRIVER."""
    data = _person_application_canonical_data(app)
    people_fields = _payload_to_people_fields(data)
    role_code = (app.requested_role_code or "DRIVER").strip().upper()
    if role_code not in APPLICATION_TYPES:
        role_code = "OTHER"

    person: Person | None = None
    if app.person_id is not None:
        person = await db.scalar(
            select(Person).where(
                Person.id == app.person_id,
                Person.tenant_id == app.tenant_id,
            )
        )
        if person is None:
            raise HTTPException(status_code=409, detail="Application is linked to a missing tenant person record")
    else:
        person = Person(
            tenant_id=app.tenant_id,
            **people_fields,
        )
        db.add(person)
        await db.flush()
        app.person_id = person.id

    person.is_active = True
    for field_name, value in people_fields.items():
        if value is not None:
            setattr(person, field_name, value)

    # PersonRole: use requested_role_code (role assigned on approval)
    active_role = await db.scalar(
        select(PersonRole).where(
            PersonRole.tenant_id == app.tenant_id,
            PersonRole.person_id == person.id,
            PersonRole.role_code == role_code,
            PersonRole.is_active.is_(True),
        )
    )
    if active_role is None:
        any_role = await db.scalar(
            select(PersonRole).where(
                PersonRole.tenant_id == app.tenant_id,
                PersonRole.person_id == person.id,
                PersonRole.role_code == role_code,
            )
        )
        if any_role is not None:
            any_role.is_active = True
        else:
            db.add(
                PersonRole(
                    tenant_id=app.tenant_id,
                    person_id=person.id,
                    role_code=role_code,
                    is_active=True,
                )
            )

    # DriverProfile: only when requested_role_code == DRIVER
    if role_code == "DRIVER":
        driver_profile_fields = {
            "license_number": data.get("driver_license_number"),
            "license_region": data.get("license_region"),
            "license_expiry": data.get("license_expiry"),
        }
        driver_profile = await db.scalar(
            select(DriverProfile).where(
                DriverProfile.tenant_id == app.tenant_id,
                DriverProfile.person_id == person.id,
            )
        )
        if driver_profile is None:
            driver_profile = DriverProfile(
                tenant_id=app.tenant_id,
                person_id=person.id,
                **driver_profile_fields,
            )
            db.add(driver_profile)
        else:
            driver_profile.is_active = True
            for field_name, value in driver_profile_fields.items():
                if value is not None:
                    setattr(driver_profile, field_name, value)

    await db.flush()
    return person


async def _get_my_latest_submission(
    db: AsyncSession, tenant_id: int, member_id: int
) -> DriverOnboardingSubmission | None:
    return await db.scalar(
        select(DriverOnboardingSubmission)
        .where(
            DriverOnboardingSubmission.tenant_id == tenant_id,
            DriverOnboardingSubmission.created_by_user_id == member_id,
        )
        .order_by(DriverOnboardingSubmission.created_at.desc())
        .limit(1)
    )


async def _get_application_by_token(
    db: AsyncSession, tenant_id: int, token: str
) -> PersonApplication:
    """Resolve invite token to PersonApplication. Raises 404 if invalid/expired/revoked."""
    now = _utcnow()
    access = await db.scalar(
        select(ApplicationAccessToken).where(
            ApplicationAccessToken.tenant_id == tenant_id,
            ApplicationAccessToken.token == token,
            ApplicationAccessToken.expires_at > now,
            ApplicationAccessToken.revoked_at.is_(None),
        )
    )
    if not access:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invalid or expired invite link")
    app = await db.get(PersonApplication, access.application_id)
    if not app or app.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found")
    return app


def _person_application_to_out(app: PersonApplication) -> ApplicantApplicationOut:
    intake = app.intake_payload or {}
    first_name = app.first_name or intake.get("first_name")
    last_name = app.last_name or intake.get("last_name")
    phone = app.phone or intake.get("phone")
    email = app.email or intake.get("email")
    address_street = app.street_address or intake.get("address_street") or intake.get("address_line")
    address_city = app.city or intake.get("address_city")
    address_region = app.region or intake.get("address_region")
    address_postal = app.postal_code or intake.get("address_postal")
    address_country = app.country or intake.get("address_country")
    notes = app.notes or intake.get("notes")
    # Avoid passing empty string to date field (Pydantic validation error)
    raw_expiry = intake.get("license_expiry")
    license_expiry = raw_expiry if (raw_expiry and str(raw_expiry).strip()) else None
    return ApplicantApplicationOut(
        id=app.id,
        tenant_id=app.tenant_id,
        person_id=app.person_id,
        status=app.status,
        source=app.source,
        application_type=app.application_type or "DRIVER",
        requested_role_code=app.requested_role_code or "DRIVER",
        reviewed_at=app.reviewed_at,
        reviewed_by_user_id=app.reviewed_by_user_id,
        approved_at=app.approved_at,
        approved_by_user_id=app.approved_by_user_id,
        rejection_reason=app.rejection_reason,
        first_name=first_name,
        last_name=last_name,
        phone=phone,
        email=email,
        address_street=address_street,
        address_city=address_city,
        address_region=address_region,
        address_postal=address_postal,
        address_country=address_country,
        driver_license_number=intake.get("driver_license_number"),
        license_region=intake.get("license_region"),
        license_expiry=license_expiry,
        notes=notes,
        submitted_at=app.submitted_at,
        created_at=app.created_at,
        updated_at=app.updated_at,
        intake_payload=app.intake_payload,
    )


@router.get("/applicant/application", response_model=ApplicantApplicationOut, dependencies=_APPLICANT_SUBSCRIPTION)
async def get_applicant_application(
    token: str = Query(..., description="Invite link token"),
    tenant_id: int = Depends(require_tenant),
    db: AsyncSession = Depends(get_tenant_db),
):
    """Get person application by invite token (no session required)."""
    app = await _get_application_by_token(db, tenant_id, token)
    return _person_application_to_out(app)


@router.put("/applicant/application", response_model=ApplicantApplicationOut, dependencies=_APPLICANT_SUBSCRIPTION)
async def update_applicant_application(
    payload: ApplicantApplicationUpdate,
    token: str = Query(..., description="Invite link token"),
    tenant_id: int = Depends(require_tenant),
    db: AsyncSession = Depends(get_tenant_db),
):
    """Update and optionally submit person application by invite token (no session required)."""
    app = await _get_application_by_token(db, tenant_id, token)
    if app.status != DriverOnboardingStatus.DRAFT.value:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Application already submitted",
        )
    data = payload.model_dump(exclude={"submit"})
    submit = payload.submit
    app.first_name = data.get("first_name") or app.first_name
    app.last_name = data.get("last_name") or app.last_name
    app.phone = data.get("phone")
    app.email = data.get("email")
    app.street_address = data.get("address_street")
    app.city = data.get("address_city")
    app.region = data.get("address_region")
    app.postal_code = data.get("address_postal")
    app.country = data.get("address_country")
    app.notes = data.get("notes")
    intake = dict(app.intake_payload or {})
    if data.get("driver_license_number") is not None:
        intake["driver_license_number"] = data["driver_license_number"]
    if data.get("license_region") is not None:
        intake["license_region"] = data["license_region"]
    if data.get("license_expiry") is not None:
        intake["license_expiry"] = data["license_expiry"]
    app.intake_payload = intake or None
    if submit:
        app.status = DriverOnboardingStatus.SUBMITTED.value
        app.submitted_at = _utcnow()
    await db.commit()
    await db.refresh(app)
    return _person_application_to_out(app)


@router.post("/applicant/application/intake", response_model=ApplicantApplicationOut, dependencies=_APPLICANT_SUBSCRIPTION)
async def save_applicant_intake(
    payload: ApplicantIntakeRequest,
    token: str = Query(..., description="Invite link token"),
    tenant_id: int = Depends(require_tenant),
    db: AsyncSession = Depends(get_tenant_db),
):
    """Save or submit applicant intake payload by invite token (no session required)."""
    app = await _get_application_by_token(db, tenant_id, token)
    if app.status != DriverOnboardingStatus.DRAFT.value:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Application already submitted",
        )
    app.intake_payload = {**(app.intake_payload or {}), **payload.intake_payload}
    if payload.submit:
        app.status = DriverOnboardingStatus.SUBMITTED.value
        app.submitted_at = _utcnow()
    await db.commit()
    await db.refresh(app)
    return _person_application_to_out(app)


@router.post("/applicant/application/reset", response_model=ApplicantApplicationOut, dependencies=_APPLICANT_SUBSCRIPTION)
async def reset_applicant_application(
    token: str = Query(..., description="Invite link token"),
    tenant_id: int = Depends(require_tenant),
    db: AsyncSession = Depends(get_tenant_db),
):
    """Clear saved draft onboarding data for the current invite token."""
    app = await _get_application_by_token(db, tenant_id, token)
    if app.status != DriverOnboardingStatus.DRAFT.value:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Application already submitted",
        )

    preserved_intake = {}
    for key in ("step", "form_country_default", "form_region_default"):
        value = (app.intake_payload or {}).get(key)
        if value not in (None, ""):
            preserved_intake[key] = value
    if "step" not in preserved_intake:
        preserved_intake["step"] = "dl_upload"

    app.first_name = None
    app.last_name = None
    app.phone = None
    app.email = None
    app.street_address = None
    app.city = None
    app.region = None
    app.postal_code = None
    app.country = None
    app.notes = None
    app.intake_payload = preserved_intake

    await db.commit()
    await db.refresh(app)
    return _person_application_to_out(app)


@router.post("/applicant/application/dl-upload", response_model=ApplicantApplicationOut, dependencies=_APPLICANT_SUBSCRIPTION)
async def upload_applicant_dl(
    token: str = Query(..., description="Invite link token"),
    doc_type: str = Form(..., description="CDL_FRONT or CDL_BACK"),
    file: UploadFile = File(...),
    tenant_id: int = Depends(require_tenant),
    tenant_slug: str = Depends(require_tenant_slug),
    db: AsyncSession = Depends(get_tenant_db),
):
    """Upload driver license front or back for applicant (token auth). Stores file and updates intake_payload.files."""
    if doc_type not in ("CDL_FRONT", "CDL_BACK"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="doc_type must be CDL_FRONT or CDL_BACK")
    app = await _get_application_by_token(db, tenant_id, token)
    if app.status != DriverOnboardingStatus.DRAFT.value:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Application already submitted",
        )
    stored = await save_applicant_dl_upload(tenant_slug, app.id, file)
    intake = dict(app.intake_payload or {})
    files = dict(intake.get("files") or {})
    files[doc_type] = {
        "storage_key": stored.storage_key,
        "file_id": stored.storage_key,
        "enh_file_id": stored.storage_key,
        "original_filename": stored.original_filename,
        "upload_status": "READY",
    }
    intake["files"] = files
    if doc_type == "CDL_BACK":
        intake = await _best_effort_pdf417_extract(intake, stored.storage_key, tenant_slug)
    intake["license_extract_status"] = "SUCCESS"
    intake.pop("license_extract_error", None)
    app.intake_payload = intake
    await db.commit()
    await db.refresh(app)
    return _person_application_to_out(app)


@router.get("/applicant/application/file", dependencies=_APPLICANT_SUBSCRIPTION)
async def get_applicant_application_file(
    token: str = Query(..., description="Invite link token"),
    file_id: str = Query(..., description="Storage key / file id"),
    tenant_id: int = Depends(require_tenant),
    tenant_slug: str = Depends(require_tenant_slug),
    db: AsyncSession = Depends(get_tenant_db),
):
    """Serve an uploaded applicant file (DL image or step-4 document) by token and file_id."""
    app = await _get_application_by_token(db, tenant_id, token)
    intake = app.intake_payload or {}
    # DL files (front/back)
    files = intake.get("files") or {}
    for _side, meta in files.items():
        if _file_meta_matches(meta, file_id):
            storage_key = meta.get("enh_file_id") if meta.get("enh_file_id") == file_id else meta.get("storage_key")
            return serve_file(storage_key or file_id, "applicant_dl", tenant_slug, meta.get("original_filename"))
    # Step-4 documents
    documents = intake.get("documents") or {}
    for _doc_type, meta in documents.items():
        if _file_meta_matches(meta, file_id):
            storage_key = meta.get("storage_key") or file_id
            return serve_file(storage_key, "applicant_docs", tenant_slug, meta.get("original_filename"))
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found for this application")


_ALLOWED_DOC_TYPES = frozenset({
    "dot_medical", "mvr", "drug_test", "psp_report",
    "ss_card", "employment_verification", "certificates", "void_cheque",
})


@router.post("/applicant/application/document-upload", response_model=ApplicantApplicationOut, dependencies=_APPLICANT_SUBSCRIPTION)
async def upload_applicant_document(
    token: str = Query(..., description="Invite link token"),
    doc_type: str = Form(..., description="Document type key (e.g. dot_medical, mvr)"),
    file: UploadFile = File(...),
    tenant_id: int = Depends(require_tenant),
    tenant_slug: str = Depends(require_tenant_slug),
    db: AsyncSession = Depends(get_tenant_db),
):
    """Upload a step-4 document (DOT medical, MVR, etc.) for applicant. Persists to storage and intake_payload.documents."""
    if doc_type not in _ALLOWED_DOC_TYPES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"doc_type must be one of {sorted(_ALLOWED_DOC_TYPES)}")
    app = await _get_application_by_token(db, tenant_id, token)
    if app.status != DriverOnboardingStatus.DRAFT.value:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Application already submitted",
        )
    stored = await save_applicant_doc_upload(tenant_slug, app.id, file)
    intake = dict(app.intake_payload or {})
    documents = dict(intake.get("documents") or {})
    documents[doc_type] = {
        "storage_key": stored.storage_key,
        "file_id": stored.storage_key,
        "original_filename": stored.original_filename,
        "uploaded_at": _utcnow().isoformat(),
    }
    intake["documents"] = documents
    app.intake_payload = intake
    await db.commit()
    await db.refresh(app)
    return _person_application_to_out(app)


def _file_meta_matches(meta: dict, file_id: str) -> bool:
    if not isinstance(meta, dict):
        return False
    return file_id in {
        meta.get("storage_key"),
        meta.get("file_id"),
        meta.get("enh_file_id"),
    }


@router.post("/submissions", response_model=DriverOnboardingCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_submission(
    payload: DriverOnboardingSubmissionCreate,
    tenant_id: int = Depends(require_tenant),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    # LEGACY QUARANTINE: No new entity creation or submissions. Use PersonApplication invite-link flow.
    raise HTTPException(
        status_code=410,
        detail="Legacy driver onboarding submission flow is deprecated. Use the invite-link application flow provided by your admin.",
    )


@router.get("/submissions/me", response_model=DriverOnboardingSubmissionOut | None)
async def get_my_latest_submission(
    tenant_id: int = Depends(require_tenant),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    if current_user.member_id is None:
        return None
    return await _get_my_latest_submission(db, tenant_id, current_user.member_id)


@router.get("/applications", response_model=list[PersonApplicationListItem])
async def list_person_applications(
    tenant_id: int = Depends(require_tenant),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
):
    """List person applications (invite-link submissions) for admin review."""
    if not is_tenant_admin(current_user.role):
        raise HTTPException(status_code=403, detail="Admin role required")
    stmt = select(PersonApplication).where(PersonApplication.tenant_id == tenant_id)
    if status:
        stmt = stmt.where(PersonApplication.status == status)
    stmt = stmt.order_by(PersonApplication.created_at.desc()).offset(offset).limit(limit)
    result = await db.execute(stmt)
    apps = result.scalars().all()
    return [
        PersonApplicationListItem(
            id=app.id,
            tenant_id=app.tenant_id,
            status=app.status,
            application_type=app.application_type or "DRIVER",
            requested_role_code=app.requested_role_code or "DRIVER",
            first_name=app.first_name or (app.intake_payload or {}).get("first_name"),
            last_name=app.last_name or (app.intake_payload or {}).get("last_name"),
            email=app.email or (app.intake_payload or {}).get("email"),
            phone=app.phone or (app.intake_payload or {}).get("phone"),
            submitted_at=app.submitted_at,
            source=app.source,
            created_at=app.created_at,
        )
        for app in apps
    ]


@router.get("/applications/{application_id}", response_model=ApplicantApplicationOut)
async def get_person_application_admin(
    application_id: int,
    tenant_id: int = Depends(require_tenant),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    """Get one canonical person application (invite-link) for admin review."""
    if not is_tenant_admin(current_user.role):
        raise HTTPException(status_code=403, detail="Admin role required")
    app = await _get_person_application_admin_or_404(db, tenant_id, application_id)
    return _person_application_to_out(app)


@router.get("/applications/{application_id}/file")
async def get_admin_application_file(
    application_id: int,
    file_id: str = Query(..., description="Storage key / file id"),
    tenant_id: int = Depends(require_tenant),
    tenant_slug: str = Depends(require_tenant_slug),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    """Serve an uploaded file (DL image or step-4 document) for admin review. Requires tenant admin."""
    if not is_tenant_admin(current_user.role):
        raise HTTPException(status_code=403, detail="Admin role required")
    app = await _get_person_application_admin_or_404(db, tenant_id, application_id)
    intake = app.intake_payload or {}
    # DL files (front/back)
    files = intake.get("files") or {}
    for _side, meta in files.items():
        if _file_meta_matches(meta, file_id):
            storage_key = meta.get("enh_file_id") if meta.get("enh_file_id") == file_id else meta.get("storage_key")
            return serve_file(storage_key or file_id, "applicant_dl", tenant_slug, meta.get("original_filename"))
    # Step-4 documents
    documents = intake.get("documents") or {}
    for _doc_type, meta in documents.items():
        if _file_meta_matches(meta, file_id):
            storage_key = meta.get("storage_key") or file_id
            return serve_file(storage_key, "applicant_docs", tenant_slug, meta.get("original_filename"))
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found for this application")


@router.post("/applications/{application_id}/approve", response_model=ApplicantApplicationOut)
async def approve_person_application(
    application_id: int,
    tenant_id: int = Depends(require_tenant),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    """Canonical admin approval path for PersonApplication invite-link onboarding."""
    if not is_tenant_admin(current_user.role):
        raise HTTPException(status_code=403, detail="Admin role required")
    app = await _get_person_application_admin_for_update_or_404(db, tenant_id, application_id)
    if app.status not in {
        DriverOnboardingStatus.SUBMITTED.value,
        DriverOnboardingStatus.APPROVED.value,
    }:
        raise HTTPException(status_code=409, detail="Application must be SUBMITTED or already APPROVED")

    person = await _ensure_person_entities_for_application(db, app)

    if app.status == DriverOnboardingStatus.SUBMITTED.value:
        now = _utcnow()
        app.reviewed_at = now
        app.reviewed_by_user_id = current_user.member_id
        app.approved_at = now
        app.approved_by_user_id = current_user.member_id

    app.status = DriverOnboardingStatus.APPROVED.value
    app.person_id = person.id
    app.rejection_reason = None

    await db.commit()
    await db.refresh(app)
    return _person_application_to_out(app)


@router.post("/applications/{application_id}/reject", response_model=ApplicantApplicationOut)
async def reject_person_application(
    application_id: int,
    payload: PersonApplicationRejectRequest,
    tenant_id: int = Depends(require_tenant),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    """Canonical admin rejection path for PersonApplication invite-link onboarding."""
    if not is_tenant_admin(current_user.role):
        raise HTTPException(status_code=403, detail="Admin role required")
    app = await _get_person_application_admin_or_404(db, tenant_id, application_id)
    if app.status != DriverOnboardingStatus.SUBMITTED.value:
        raise HTTPException(status_code=409, detail="Application is not in SUBMITTED status")

    app.status = DriverOnboardingStatus.REJECTED.value
    app.reviewed_at = _utcnow()
    app.reviewed_by_user_id = current_user.member_id
    app.approved_at = None
    app.approved_by_user_id = None
    app.rejection_reason = payload.rejection_reason

    await db.commit()
    await db.refresh(app)
    return _person_application_to_out(app)


# Legacy admin review/approval routes below are retained temporarily for compatibility only.
@router.get("/submissions", response_model=list[DriverOnboardingSubmissionOut])
async def list_submissions(
    tenant_id: int = Depends(require_tenant),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
):
    if not is_tenant_admin(current_user.role):
        raise HTTPException(status_code=403, detail="Admin role required")
    stmt = select(DriverOnboardingSubmission).where(DriverOnboardingSubmission.tenant_id == tenant_id)
    if status:
        stmt = stmt.where(DriverOnboardingSubmission.status == status)
    stmt = stmt.order_by(DriverOnboardingSubmission.created_at.desc()).offset(offset).limit(limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.get("/submissions/{submission_id}", response_model=DriverOnboardingSubmissionOut)
async def get_submission(
    submission_id: int,
    tenant_id: int = Depends(require_tenant),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    if not is_tenant_admin(current_user.role):
        raise HTTPException(status_code=403, detail="Admin role required")
    return await _get_submission(db, tenant_id, submission_id)


@router.post("/submissions/{submission_id}/submit", response_model=DriverOnboardingSubmissionOut)
async def submit_submission(
    submission_id: int,
    tenant_id: int = Depends(require_tenant),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    submission = await _get_submission(db, tenant_id, submission_id)
    if not _is_admin(current_user) and submission.created_by_user_id != current_user.member_id:
        raise HTTPException(status_code=403, detail="Not allowed to submit this draft")
    if submission.status != DriverOnboardingStatus.DRAFT.value:
        raise HTTPException(status_code=409, detail="Submission is not in DRAFT status")
    submission.status = DriverOnboardingStatus.SUBMITTED.value
    submission.submitted_at = _utcnow()
    # Person_roles.is_active stays False until approve; status lives on submission
    await db.commit()
    await db.refresh(submission)
    return submission


@router.post("/submissions/{submission_id}/approve", response_model=DriverOnboardingApproveResponse)
async def approve_submission(
    submission_id: int,
    tenant_id: int = Depends(require_tenant),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    # LEGACY QUARANTINE: Approval source of truth is PersonApplication. Use POST /applications/{id}/approve.
    raise HTTPException(
        status_code=410,
        detail="Legacy approval path is deprecated. Use POST /api/v1/driver-onboarding/applications/{id}/approve.",
    )


@router.post("/submissions/{submission_id}/reject", response_model=DriverOnboardingSubmissionOut)
async def reject_submission(
    submission_id: int,
    payload: DriverOnboardingRejectRequest,
    tenant_id: int = Depends(require_tenant),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    # LEGACY QUARANTINE: Reject source of truth is PersonApplication. Use POST /applications/{id}/reject.
    raise HTTPException(
        status_code=410,
        detail="Legacy reject path is deprecated. Use POST /api/v1/driver-onboarding/applications/{id}/reject.",
    )
