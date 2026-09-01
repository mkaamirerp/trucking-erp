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
import copy
import hashlib
import logging
import secrets
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
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
from app.models.driver import Driver
from app.models.platform import PlatformTenant
from app.models.driver_onboarding_submission import DriverOnboardingSubmission
from app.models.person import Person, PersonRole, DriverProfile
from app.models.person_application import APPLICATION_TYPES, PersonApplication
from app.schemas.driver_onboarding import (
    ApplicantApplicationOut,
    ApplicantIntakeRequest,
    ApplicantApplicationUpdate,
    DlCaptureLinkResponse,
    DlCaptureSessionOut,
    PersonApplicationDocumentAcceptBody,
    PersonApplicationDocumentRequest,
    PersonApplicationDocumentRequestResponse,
    PersonApplicationReviewPatch,
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
from app.services.applicant_dl_pdf417 import apply_stored_cdl_back_pdf417, pdf417_enabled_for_doc_type
from app.constants.person_application_workflow import WORKFLOW_LANE_COMPLETE, normalize_workflow_lane
from app.constants.person_onboarding import PERSON_SETUP_UI_COMBINED, normalize_person_setup_ui_mode
from app.schemas.driver_compensation_setup import DriverCompensationSetupOut, DriverCompensationSetupWrite
from app.services.driver_compensation_setup import (
    assert_combined_driver_onboarding_ready,
    get_driver_compensation_setup,
    upsert_driver_compensation_setup,
)
from app.services.person_application_onboarding import (
    apply_rejection_setup_state,
    ensure_processing_lane_if_submitted_admin_engaged,
    finalize_person_application_onboarding,
    get_person_setup_ui_mode,
    is_driver_driver_person_application,
    reconcile_person_application_lanes_for_tenant_ui_mode,
    set_lane_after_manager_approve,
    set_rejected_lane,
    set_submitted_lane_on_applicant_submit,
    setup_status_after_approval,
)
from app.utils.email import send_onboarding_document_request_email

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/driver-onboarding", tags=["driver-onboarding"])


class CombinedDriverApproveReadinessOut(BaseModel):
    """Admin-only: whether combined-mode DRIVER+DRIVER approve is blocked by missing in-page setup."""

    applies: bool = Field(description="True when tenant is combined and this is a driver/driver application in SUBMITTED status.")
    ready: bool
    blocking_code: str | None = None
    detail: str | None = None


def _combined_approve_guard_http_detail(code: str) -> str:
    return {
        "onboarding_person_missing": "Person record is not linked yet. Save review corrections once (or use Prepare person) so Driver setup can be saved, then finish Driver and Compensation setup before approving.",
        "onboarding_driver_configuration_incomplete": "Driver configuration is incomplete. Save the Driver setup card before approving.",
        "onboarding_operational_driver_missing": "Operational driver record is missing. Reload the page or contact support.",
        "onboarding_compensation_incomplete": "Compensation setup is incomplete. Save the Compensation card before approving.",
    }.get(code, code)


async def _maybe_ensure_person_for_combined_admin_setup(
    db: AsyncSession,
    platform_db: AsyncSession,
    tenant_id: int,
    app: PersonApplication,
) -> None:
    """Create tenant Person (+ driver entities) early so combined-mode admin can save setup before approve."""
    ui_mode = normalize_person_setup_ui_mode(await get_person_setup_ui_mode(platform_db, tenant_id))
    if ui_mode != PERSON_SETUP_UI_COMBINED:
        return
    if not is_driver_driver_person_application(app):
        return
    if app.status != DriverOnboardingStatus.SUBMITTED.value:
        return
    if app.person_id is not None:
        return
    await _ensure_person_entities_for_application(db, app)
    await db.flush()

TOKEN_PURPOSE_INVITE = "invite"
TOKEN_PURPOSE_DOCUMENT_RESUME = "document_resume"
TOKEN_PURPOSE_DL_CAPTURE = "dl_capture"

# Capture-link lifetime for purpose=dl_capture (not schema-bound).
DL_CAPTURE_TOKEN_TTL = timedelta(hours=24)

_DL_CAPTURE_INVALID = "Invalid or expired capture link"

# Applicant may upload / resubmit documents after initial submit or after approval (admin document request).
_POST_SUBMIT_DOC_RESUME_STATUSES = frozenset(
    {
        DriverOnboardingStatus.SUBMITTED.value,
        DriverOnboardingStatus.APPROVED.value,
    }
)

# Token-based applicant flows: subscription gate matches admin invite (no JWT on these routes).
_APPLICANT_SUBSCRIPTION = [Depends(require_tenant_subscription_active)]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _public_request_base_url(request: Request) -> str:
    """Public HTTPS base for applicant-facing links (respects reverse-proxy forwarded headers)."""
    forwarded_proto = request.headers.get("x-forwarded-proto")
    scheme = forwarded_proto.split(",")[0].strip() if forwarded_proto else request.url.scheme
    host_header = request.headers.get("x-forwarded-host") or request.headers.get("host")
    host = host_header.split(",")[0].strip() if host_header else request.url.netloc
    return f"{scheme}://{host}".rstrip("/")




def _merge_applicant_intake_payload(existing: dict | None, incoming: dict) -> dict:
    """Merge saved intake with incoming keys; skip blank strings so empty form fields do not erase PDF417 data."""
    base = dict(existing or {})
    for key, value in (incoming or {}).items():
        if isinstance(value, str) and value.strip() == "":
            continue
        base[key] = value
    return base


# Intake keys allowed for non-DRIVER workflows (shared foundation only; Phase 1).
_NON_DRIVER_INTAKE_ALLOWED_KEYS: frozenset[str] = frozenset(
    {
        "step",
        "form_country_default",
        "form_region_default",
        "first_name",
        "last_name",
        "phone",
        "email",
        "address_street",
        "address_line",
        "address_city",
        "address_region",
        "address_postal",
        "zip_code",
        "address_country",
        "notes",
    }
)


def _application_workflow_type(app: PersonApplication) -> str:
    return (app.application_type or "DRIVER").strip().upper()


def _is_driver_workflow_application(app: PersonApplication) -> bool:
    return _application_workflow_type(app) == "DRIVER"


def _require_driver_workflow(app: PersonApplication) -> None:
    if not _is_driver_workflow_application(app):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This action is only available for driver onboarding applications.",
        )


def _sanitize_intake_for_workflow(app: PersonApplication, intake: dict | None) -> dict | None:
    """Drop driver-only intake keys for non-DRIVER workflows; ensure a sensible default step."""
    if intake is None:
        return None
    base = dict(intake)
    if _is_driver_workflow_application(app):
        return base
    out = {k: v for k, v in base.items() if k in _NON_DRIVER_INTAKE_ALLOWED_KEYS}
    if "step" not in out:
        out["step"] = "common"
    return out


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
        "zip_code": data.get("zip_code"),
        "country": data.get("address_country"),
        "notes": data.get("notes"),
    }


def _clean_text(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalize_postal_zip_for_country(
    country: str | None, address_postal: str | None, zip_code: str | None
) -> tuple[str | None, str | None]:
    """Fill the sibling field for display/promotion when only one is stored (US ↔ ZIP, CA ↔ postal)."""
    c = (country or "").strip().upper()
    p = address_postal
    z = zip_code
    if c == "US" and z is None and p is not None:
        z = p
    if c == "CA" and p is None and z is not None:
        p = z
    return p, z


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
        "zip_code": _clean_text(app.zip_code) or _clean_text(intake.get("zip_code")),
        "address_country": _clean_text(app.country) or _clean_text(intake.get("address_country")),
        "notes": _clean_text(app.notes) or _clean_text(intake.get("notes")),
        "driver_license_number": _clean_text(intake.get("driver_license_number")) or _clean_text(intake.get("license_number")),
        "license_region": _clean_text(intake.get("license_region")) or _clean_text(intake.get("license_state")),
        "license_expiry": _coerce_optional_date(intake.get("license_expiry")),
    }
    p, z = _normalize_postal_zip_for_country(
        data.get("address_country"), data.get("address_postal"), data.get("zip_code")
    )
    data["address_postal"] = p
    data["zip_code"] = z
    missing = [field for field in ("first_name", "last_name") if not data.get(field)]
    if missing:
        raise HTTPException(
            status_code=409,
            detail=f"Application is missing required applicant fields for approval: {', '.join(missing)}",
        )
    return data


async def _upsert_operational_driver_for_person(
    db: AsyncSession,
    tenant_id: int,
    person: Person,
    driver_profile: DriverProfile,
) -> Driver:
    """Create or refresh the tenant `drivers` row for dispatch (approved operational roster).

    PersonApplication and intake payloads are not the operational roster; this row is the
    dispatch-facing roster entry materialized when a DRIVER application is approved (idempotent).
    Match key: (tenant_id, person_id). If multiple rows exist (legacy duplicates), the lowest ``id``
    is the canonical survivor and is updated in place; all other matching rows are soft-retired
    (``is_active=False``) so only one active operational driver remains per person per tenant.
    """
    result = await db.scalars(
        select(Driver)
        .where(
            Driver.tenant_id == tenant_id,
            Driver.person_id == person.id,
        )
        .order_by(Driver.id.asc())
    )
    rows = list(result.all())
    op_driver = rows[0] if rows else None

    if op_driver is None:
        op_driver = Driver(
            tenant_id=tenant_id,
            person_id=person.id,
            first_name=person.first_name,
            last_name=person.last_name,
            email=person.email,
            phone=person.phone,
            is_active=True,
            license_number=driver_profile.license_number,
            issuing_region=driver_profile.license_region,
            license_expiry_date=driver_profile.license_expiry,
        )
        db.add(op_driver)
    else:
        # Legacy duplicate `drivers` rows: keep lowest-id survivor active; soft-retire the rest (no hard delete).
        for dup in rows[1:]:
            dup.is_active = False

        op_driver.tenant_id = tenant_id
        op_driver.person_id = person.id
        op_driver.first_name = person.first_name
        op_driver.last_name = person.last_name
        op_driver.email = person.email
        op_driver.phone = person.phone
        op_driver.is_active = True
        if driver_profile.license_number is not None:
            op_driver.license_number = driver_profile.license_number
        if driver_profile.license_region is not None:
            op_driver.issuing_region = driver_profile.license_region
        if driver_profile.license_expiry is not None:
            op_driver.license_expiry_date = driver_profile.license_expiry

    await db.flush()
    return op_driver


async def _ensure_person_entities_for_application(
    db: AsyncSession,
    app: PersonApplication,
) -> Person:
    """Create/update Person, PersonRole(requested_role_code).

    DriverProfile and operational ``drivers`` rows are created only when both the **workflow**
    (``application_type``) and the **approval role** (``requested_role_code``) are DRIVER—so
    non-driver invite workflows never materialize driver entities even if columns were inconsistent.
    """
    data = _person_application_canonical_data(app)
    people_fields = _payload_to_people_fields(data)
    role_code = (app.requested_role_code or "DRIVER").strip().upper()
    if role_code not in APPLICATION_TYPES:
        role_code = "OTHER"
    workflow_type = _application_workflow_type(app)
    materialize_driver_extension = role_code == "DRIVER" and workflow_type == "DRIVER"

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

    # DriverProfile + operational Driver row: DRIVER workflow + DRIVER approval role only
    if materialize_driver_extension:
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
        # PersonApplication is intake/review state only; `drivers` is the dispatch roster.
        await _upsert_operational_driver_for_person(db, app.tenant_id, person, driver_profile)

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


def _token_sha256_hex(raw: str) -> str:
    return hashlib.sha256(raw.strip().encode("utf-8")).hexdigest()


async def _get_application_and_access_by_token(
    db: AsyncSession,
    tenant_id: int,
    token: str,
    *,
    purpose: str | None = None,
    detail: str = "Invalid or expired invite link",
) -> tuple[PersonApplication, ApplicationAccessToken]:
    """Resolve token by SHA-256 hash (preferred) or legacy plaintext `token` column.

    When ``purpose`` is set, only tokens with that purpose authenticate (e.g. dl_capture).
    """
    if not token or not str(token).strip():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)
    raw = str(token).strip()
    now = _utcnow()
    th = _token_sha256_hex(raw)
    clauses = [
        ApplicationAccessToken.tenant_id == tenant_id,
        ApplicationAccessToken.expires_at > now,
        ApplicationAccessToken.revoked_at.is_(None),
        or_(ApplicationAccessToken.token_hash == th, ApplicationAccessToken.token == raw),
    ]
    if purpose is not None:
        clauses.append(ApplicationAccessToken.purpose == purpose)
    access = await db.scalar(select(ApplicationAccessToken).where(*clauses))
    if not access:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)
    app = await db.get(PersonApplication, access.application_id)
    if not app or app.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)
    return app, access


async def _get_application_by_token(db: AsyncSession, tenant_id: int, token: str) -> PersonApplication:
    app, _access = await _get_application_and_access_by_token(db, tenant_id, token)
    return app


def _dl_side_status(intake: dict, side: str) -> str:
    meta = (intake.get("files") or {}).get(side)
    if not isinstance(meta, dict):
        return "MISSING"
    status_val = meta.get("dl_preprocess_status")
    if status_val == "PROCESSED":
        return "PROCESSED"
    if status_val == "FAILED":
        return "FAILED"
    return "MISSING"


def _dl_side_preview_file_id(intake: dict, side: str) -> str | None:
    meta = (intake.get("files") or {}).get(side)
    if not isinstance(meta, dict):
        return None
    return (
        meta.get("enh_file_id")
        or meta.get("file_id")
        or meta.get("storage_key")
    )


def _dl_capture_step(front_status: str, back_status: str) -> str:
    if front_status != "PROCESSED":
        return "FRONT"
    if back_status != "PROCESSED":
        return "BACK"
    return "COMPLETE"


async def _maybe_complete_dl_capture_token(
    db: AsyncSession,
    access: ApplicationAccessToken,
    intake: dict,
) -> None:
    """Set completed_at when both licence sides are PROCESSED."""
    if access.completed_at is not None:
        return
    if (
        _dl_side_status(intake, "CDL_FRONT") == "PROCESSED"
        and _dl_side_status(intake, "CDL_BACK") == "PROCESSED"
    ):
        access.completed_at = _utcnow()


def _dl_capture_session_out(
    access: ApplicationAccessToken,
    intake: dict,
    *,
    message: str | None = None,
) -> DlCaptureSessionOut:
    front_status = _dl_side_status(intake, "CDL_FRONT")
    back_status = _dl_side_status(intake, "CDL_BACK")
    step = _dl_capture_step(front_status, back_status)
    if access.completed_at is not None:
        step = "COMPLETE"
    return DlCaptureSessionOut(
        step=step,
        front_status=front_status,
        back_status=back_status,
        front_preview_file_id=_dl_side_preview_file_id(intake, "CDL_FRONT"),
        back_preview_file_id=_dl_side_preview_file_id(intake, "CDL_BACK"),
        message=message,
    )


async def _apply_applicant_dl_upload(
    *,
    db: AsyncSession,
    app: PersonApplication,
    tenant_slug: str,
    doc_type: str,
    file: UploadFile,
) -> PersonApplication:
    """Shared DL storage + OpenCV path used by invite upload and dl-capture upload."""
    intake_before = dict(app.intake_payload or {})
    old_front = _dl_side_status(intake_before, "CDL_FRONT")
    old_back = _dl_side_status(intake_before, "CDL_BACK")

    stored = await save_applicant_dl_upload(tenant_slug, app.id, file)
    intake = dict(app.intake_payload or {})
    files = dict(intake.get("files") or {})

    from app.core.storage import save_applicant_dl_processed_bytes
    from app.services.applicant_dl_preprocess import run_applicant_dl_opencv

    import asyncio

    with readable_path(stored.storage_key, "applicant_dl", tenant_slug) as image_path:
        processed = await asyncio.to_thread(run_applicant_dl_opencv, str(image_path), doc_type)

    preprocess_debug = processed.debug
    preprocess_status = "FAILED"
    ocr_storage_key: str | None = None

    if processed.success and processed.jpeg_bytes:
        stored_processed = await save_applicant_dl_processed_bytes(
            tenant_slug,
            app.id,
            processed.jpeg_bytes,
            original_storage_key=stored.storage_key,
        )
        ocr_storage_key = stored_processed.storage_key
        preprocess_status = "PROCESSED"
        files[f"{doc_type}_PROCESSED"] = {
            "storage_key": stored_processed.storage_key,
            "file_id": stored_processed.storage_key,
            "enh_file_id": stored_processed.storage_key,
            "original_filename": stored_processed.original_filename,
            "upload_status": "READY",
            "dl_preprocess_status": preprocess_status,
        }

    files[doc_type] = {
        "storage_key": stored.storage_key,
        "file_id": stored.storage_key,
        "original_filename": stored.original_filename,
        "upload_status": "READY" if preprocess_status == "PROCESSED" else "FAILED",
        "dl_preprocess_status": preprocess_status,
        "dl_preprocess_debug": preprocess_debug,
    }
    if ocr_storage_key:
        files[doc_type]["enh_file_id"] = ocr_storage_key

    intake["files"] = files
    if pdf417_enabled_for_doc_type(doc_type):
        intake = await apply_stored_cdl_back_pdf417(
            intake,
            stored.storage_key,
            tenant_slug,
            processed_storage_key=ocr_storage_key,
        )
    app.intake_payload = intake

    new_front = _dl_side_status(intake, "CDL_FRONT")
    new_back = _dl_side_status(intake, "CDL_BACK")
    from app.services.domain_event_outbox import (
        AGGREGATE_TYPE_PERSON_APPLICATION,
        build_dl_licence_domain_events,
        enqueue_domain_event,
    )

    for event_type, payload in build_dl_licence_domain_events(
        old_front=old_front,
        old_back=old_back,
        new_front=new_front,
        new_back=new_back,
        doc_type=doc_type,
        upload_failed=preprocess_status == "FAILED",
    ):
        await enqueue_domain_event(
            db,
            tenant_id=app.tenant_id,
            aggregate_type=AGGREGATE_TYPE_PERSON_APPLICATION,
            aggregate_id=str(app.id),
            event_type=event_type,
            payload=payload,
        )

    await db.commit()
    await db.refresh(app)

    from app.services.domain_event_delivery import get_domain_event_dispatcher

    get_domain_event_dispatcher().wake(app.tenant_id)
    return app


def _person_application_to_out(
    app: PersonApplication,
    *,
    include_review_meta: bool = False,
    document_resume_active: bool = False,
) -> ApplicantApplicationOut:
    intake = _sanitize_intake_for_workflow(app, dict(app.intake_payload or {})) or {}
    first_name = app.first_name or intake.get("first_name")
    last_name = app.last_name or intake.get("last_name")
    phone = app.phone or intake.get("phone")
    email = app.email or intake.get("email")
    address_street = app.street_address or intake.get("address_street") or intake.get("address_line")
    address_city = app.city or intake.get("address_city")
    address_region = app.region or intake.get("address_region")
    address_postal = app.postal_code or intake.get("address_postal")
    zip_code = app.zip_code or intake.get("zip_code")
    address_country = app.country or intake.get("address_country")
    notes = app.notes or intake.get("notes")
    ap_norm, z_norm = _normalize_postal_zip_for_country(address_country, address_postal, zip_code)
    address_postal, zip_code = ap_norm, z_norm
    if (_clean_text(address_country) or "").upper() == "CA":
        zip_code = None
    # Avoid passing empty string to date field (Pydantic validation error)
    raw_expiry = intake.get("license_expiry")
    license_expiry = raw_expiry if (raw_expiry and str(raw_expiry).strip()) else None
    out = ApplicantApplicationOut(
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
        onboarded_at=app.onboarded_at,
        onboarded_by_user_id=app.onboarded_by_user_id,
        setup_status=getattr(app, "setup_status", None) or "pending",
        current_workflow_lane=normalize_workflow_lane(getattr(app, "current_workflow_lane", None)),
        rejection_reason=app.rejection_reason,
        first_name=first_name,
        last_name=last_name,
        phone=phone,
        email=email,
        address_street=address_street,
        address_city=address_city,
        address_region=address_region,
        address_postal=address_postal,
        zip_code=zip_code,
        address_country=address_country,
        driver_license_number=intake.get("driver_license_number") or intake.get("license_number"),
        license_region=intake.get("license_region") or intake.get("license_state"),
        license_expiry=license_expiry,
        notes=notes,
        submitted_at=app.submitted_at,
        created_at=app.created_at,
        updated_at=app.updated_at,
        intake_payload=intake,
        document_resume_active=document_resume_active,
    )
    if include_review_meta:
        snap = getattr(app, "intake_submitted_snapshot", None)
        aud = getattr(app, "intake_review_audit", None)
        return out.model_copy(
            update={
                "intake_submitted_snapshot": dict(snap) if isinstance(snap, dict) else None,
                "intake_review_audit": list(aud) if isinstance(aud, list) else [],
            }
        )
    return out


@router.get("/applicant/application", response_model=ApplicantApplicationOut, dependencies=_APPLICANT_SUBSCRIPTION)
async def get_applicant_application(
    token: str = Query(..., description="Invite link token"),
    tenant_id: int = Depends(require_tenant),
    db: AsyncSession = Depends(get_tenant_db),
):
    """Get person application by invite token (no session required)."""
    app, access = await _get_application_and_access_by_token(db, tenant_id, token)
    purpose = getattr(access, "purpose", None) or TOKEN_PURPOSE_INVITE
    intake = dict(app.intake_payload or {})
    followup_done = bool(intake.get("document_followup_completed_at"))
    resume_active = (
        purpose == TOKEN_PURPOSE_DOCUMENT_RESUME
        and not followup_done
        and app.status in _POST_SUBMIT_DOC_RESUME_STATUSES
    )
    return _person_application_to_out(app, document_resume_active=resume_active)


@router.get("/applicant/application/events", dependencies=_APPLICANT_SUBSCRIPTION)
async def stream_applicant_application_events(
    token: str = Query(..., description="Invite link token"),
    tenant_id: int = Depends(require_tenant),
    db: AsyncSession = Depends(get_tenant_db),
):
    """SSE: signal-only stream for invite-token application changes (DB remains authoritative)."""
    app, access = await _get_application_and_access_by_token(db, tenant_id, token)
    purpose = getattr(access, "purpose", None) or TOKEN_PURPOSE_INVITE
    if purpose != TOKEN_PURPOSE_INVITE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the main application invite link can subscribe to application events",
        )

    from app.services.domain_event_delivery import format_sse_application_changed, get_domain_event_dispatcher

    dispatcher = get_domain_event_dispatcher()
    queue: asyncio.Queue[dict[str, str]] = asyncio.Queue(maxsize=32)
    await dispatcher.registry.subscribe(tenant_id, app.id, queue)

    async def event_generator():
        try:
            yield ": connected\n\n"
            while True:
                try:
                    message = await asyncio.wait_for(queue.get(), timeout=25.0)
                    yield format_sse_application_changed(message["event_id"], message["event_type"])
                except asyncio.TimeoutError:
                    yield ": heartbeat\n\n"
        finally:
            await dispatcher.registry.unsubscribe(tenant_id, app.id, queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


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
    app.zip_code = data.get("zip_code")
    app.country = data.get("address_country")
    app.notes = data.get("notes")
    intake = dict(app.intake_payload or {})
    if _is_driver_workflow_application(app):
        if data.get("driver_license_number") is not None:
            intake["driver_license_number"] = data["driver_license_number"]
        if data.get("license_region") is not None:
            intake["license_region"] = data["license_region"]
        if data.get("license_expiry") is not None:
            intake["license_expiry"] = data["license_expiry"]
    if data.get("zip_code") is not None:
        intake["zip_code"] = data["zip_code"]
    app.intake_payload = _sanitize_intake_for_workflow(app, intake)
    if submit:
        app.status = DriverOnboardingStatus.SUBMITTED.value
        app.submitted_at = _utcnow()
        set_submitted_lane_on_applicant_submit(app)
        if getattr(app, "intake_submitted_snapshot", None) is None:
            app.intake_submitted_snapshot = copy.deepcopy(app.intake_payload or {})
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
    app, access = await _get_application_and_access_by_token(db, tenant_id, token)
    purpose = getattr(access, "purpose", None) or TOKEN_PURPOSE_INVITE
    incoming = dict(payload.intake_payload or {})

    if app.status == DriverOnboardingStatus.DRAFT.value:
        merged = _merge_applicant_intake_payload(app.intake_payload, incoming)
        app.intake_payload = _sanitize_intake_for_workflow(app, merged)
        if payload.submit:
            app.status = DriverOnboardingStatus.SUBMITTED.value
            app.submitted_at = _utcnow()
            set_submitted_lane_on_applicant_submit(app)
            if getattr(app, "intake_submitted_snapshot", None) is None:
                app.intake_submitted_snapshot = copy.deepcopy(app.intake_payload or {})
    elif (
        app.status in _POST_SUBMIT_DOC_RESUME_STATUSES
        and purpose == TOKEN_PURPOSE_DOCUMENT_RESUME
        and _is_driver_workflow_application(app)
    ):
        merged = dict(app.intake_payload or {})
        for k in ("agree_info_accurate", "agree_background_check", "agree_dot_compliance", "onboarding_step"):
            if k in incoming:
                merged[k] = incoming[k]
        if payload.submit:
            if not (
                bool(merged.get("agree_info_accurate"))
                and bool(merged.get("agree_background_check"))
                and bool(merged.get("agree_dot_compliance"))
            ):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="All agreements must be confirmed before resubmitting.",
                )
            merged["document_followup_completed_at"] = _utcnow().isoformat()
            app.submitted_at = _utcnow()
        app.intake_payload = _sanitize_intake_for_workflow(app, merged)
    else:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This application cannot be edited with this link. If you were asked to upload documents, use the latest link from that email.",
        )

    await db.commit()
    await db.refresh(app)
    intake_after = dict(app.intake_payload or {})
    followup_done = bool(intake_after.get("document_followup_completed_at"))
    resume_active = (
        purpose == TOKEN_PURPOSE_DOCUMENT_RESUME
        and not followup_done
        and app.status in _POST_SUBMIT_DOC_RESUME_STATUSES
    )
    return _person_application_to_out(app, document_resume_active=resume_active)


@router.post("/applicant/application/reset", response_model=ApplicantApplicationOut, dependencies=_APPLICANT_SUBSCRIPTION)
async def reset_applicant_application(
    token: str = Query(..., description="Invite link token"),
    tenant_id: int = Depends(require_tenant),
    tenant_slug: str = Depends(require_tenant_slug),
    db: AsyncSession = Depends(get_tenant_db),
):
    """Clear saved draft onboarding data for the current invite token."""
    app = await _get_application_by_token(db, tenant_id, token)
    if app.status != DriverOnboardingStatus.DRAFT.value:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Application already submitted",
        )

    from app.core.storage import purge_applicant_dl_application

    purge_applicant_dl_application(tenant_slug, app.id)

    preserved_intake = {}
    for key in ("step", "form_country_default", "form_region_default"):
        value = (app.intake_payload or {}).get(key)
        if value not in (None, ""):
            preserved_intake[key] = value
    if "step" not in preserved_intake:
        preserved_intake["step"] = "dl_upload" if _is_driver_workflow_application(app) else "common"

    app.first_name = None
    app.last_name = None
    app.phone = None
    app.email = None
    app.street_address = None
    app.city = None
    app.region = None
    app.postal_code = None
    app.zip_code = None
    app.country = None
    app.notes = None
    app.intake_payload = _sanitize_intake_for_workflow(app, preserved_intake)

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
    _require_driver_workflow(app)
    if app.status != DriverOnboardingStatus.DRAFT.value:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Application already submitted",
        )
    app = await _apply_applicant_dl_upload(
        db=db,
        app=app,
        tenant_slug=tenant_slug,
        doc_type=doc_type,
        file=file,
    )
    return _person_application_to_out(app)


@router.get(
    "/applicant/dl-capture/{token}",
    response_model=DlCaptureSessionOut,
    dependencies=_APPLICANT_SUBSCRIPTION,
)
async def get_dl_capture_session(
    token: str,
    tenant_id: int = Depends(require_tenant),
    db: AsyncSession = Depends(get_tenant_db),
):
    """Resume DL capture: step derived from application file preprocess status."""
    app, access = await _get_application_and_access_by_token(
        db,
        tenant_id,
        token,
        purpose=TOKEN_PURPOSE_DL_CAPTURE,
        detail=_DL_CAPTURE_INVALID,
    )
    _require_driver_workflow(app)
    intake = dict(app.intake_payload or {})
    before_completed = access.completed_at
    await _maybe_complete_dl_capture_token(db, access, intake)
    if access.completed_at is not None and before_completed is None:
        await db.commit()
        await db.refresh(access)
    return _dl_capture_session_out(access, intake)


@router.post(
    "/applicant/dl-capture/{token}/upload",
    response_model=DlCaptureSessionOut,
    dependencies=_APPLICANT_SUBSCRIPTION,
)
async def upload_dl_capture_side(
    token: str,
    doc_type: str = Form(..., description="CDL_FRONT or CDL_BACK"),
    file: UploadFile = File(...),
    tenant_id: int = Depends(require_tenant),
    tenant_slug: str = Depends(require_tenant_slug),
    db: AsyncSession = Depends(get_tenant_db),
):
    """Upload one DL side via capture token; same OpenCV path as applicant dl-upload."""
    if doc_type not in ("CDL_FRONT", "CDL_BACK"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="doc_type must be CDL_FRONT or CDL_BACK")

    app, access = await _get_application_and_access_by_token(
        db,
        tenant_id,
        token,
        purpose=TOKEN_PURPOSE_DL_CAPTURE,
        detail=_DL_CAPTURE_INVALID,
    )
    _require_driver_workflow(app)

    if access.completed_at is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Driver licence capture is already complete",
        )
    if app.status != DriverOnboardingStatus.DRAFT.value:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Application already submitted",
        )

    intake_before = dict(app.intake_payload or {})
    step = _dl_capture_step(
        _dl_side_status(intake_before, "CDL_FRONT"),
        _dl_side_status(intake_before, "CDL_BACK"),
    )
    if step == "COMPLETE":
        await _maybe_complete_dl_capture_token(db, access, intake_before)
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Driver licence capture is already complete",
        )
    expected = "CDL_FRONT" if step == "FRONT" else "CDL_BACK"
    if doc_type != expected:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Expected {expected} for current capture step",
        )

    app = await _apply_applicant_dl_upload(
        db=db,
        app=app,
        tenant_slug=tenant_slug,
        doc_type=doc_type,
        file=file,
    )
    intake = dict(app.intake_payload or {})
    # Re-load access after commit (session may expire identity); refresh by id.
    access = await db.get(ApplicationAccessToken, access.id)
    assert access is not None
    await _maybe_complete_dl_capture_token(db, access, intake)
    await db.commit()
    await db.refresh(access)
    await db.refresh(app)

    side_status = _dl_side_status(intake, doc_type)
    message = None
    if side_status == "FAILED":
        message = "We couldn't clearly detect all four edges."
    return _dl_capture_session_out(access, intake, message=message)


@router.get("/applicant/dl-capture/{token}/file", dependencies=_APPLICANT_SUBSCRIPTION)
async def get_dl_capture_file(
    token: str,
    file_id: str = Query(..., description="Storage key / file id"),
    tenant_id: int = Depends(require_tenant),
    tenant_slug: str = Depends(require_tenant_slug),
    db: AsyncSession = Depends(get_tenant_db),
):
    """Serve a DL file for the capture session (original or processed)."""
    app, _access = await _get_application_and_access_by_token(
        db,
        tenant_id,
        token,
        purpose=TOKEN_PURPOSE_DL_CAPTURE,
        detail=_DL_CAPTURE_INVALID,
    )
    _require_driver_workflow(app)
    files = (app.intake_payload or {}).get("files") or {}
    for _side, meta in files.items():
        storage_key = _resolve_applicant_dl_serve_key(meta, file_id)
        if storage_key:
            return serve_file(storage_key, "applicant_dl", tenant_slug, meta.get("original_filename"))
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")


async def _issue_dl_capture_link_for_application(
    db: AsyncSession,
    tenant_id: int,
    application_id: int,
    request: Request,
) -> DlCaptureLinkResponse:
    """Issue hash-only dl_capture token; revokes prior active dl_capture tokens for this application only."""
    await _revoke_active_access_tokens_for_application(
        db,
        tenant_id,
        application_id,
        purpose=TOKEN_PURPOSE_DL_CAPTURE,
    )
    raw = secrets.token_urlsafe(32)
    th = _token_sha256_hex(raw)
    now = _utcnow()
    expires_at = now + DL_CAPTURE_TOKEN_TTL
    db.add(
        ApplicationAccessToken(
            tenant_id=tenant_id,
            application_id=application_id,
            token=None,
            token_hash=th,
            expires_at=expires_at,
            revoked_at=None,
            completed_at=None,
            purpose=TOKEN_PURPOSE_DL_CAPTURE,
        )
    )
    await db.commit()

    base = _public_request_base_url(request)
    link = f"{base}/dl-capture/{raw}"
    return DlCaptureLinkResponse(
        application_id=application_id,
        token=raw,
        link=link,
        expires_at=expires_at,
    )


@router.post(
    "/applications/{application_id}/dl-capture-link",
    response_model=DlCaptureLinkResponse,
)
async def issue_dl_capture_link(
    application_id: int,
    request: Request,
    tenant_id: int = Depends(require_tenant),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    """Admin: issue a resumable DL capture link (hash-only; revokes prior dl_capture tokens only)."""
    if not is_tenant_admin(current_user.role):
        raise HTTPException(status_code=403, detail="Admin role required")
    app = await _get_person_application_admin_or_404(db, tenant_id, application_id)
    _require_driver_workflow(app)
    return await _issue_dl_capture_link_for_application(db, tenant_id, application_id, request)


@router.post(
    "/applicant/application/dl-capture-link",
    response_model=DlCaptureLinkResponse,
    dependencies=_APPLICANT_SUBSCRIPTION,
)
async def issue_applicant_dl_capture_link(
    request: Request,
    token: str = Query(..., description="Invite link token"),
    tenant_id: int = Depends(require_tenant),
    db: AsyncSession = Depends(get_tenant_db),
):
    """Applicant: issue restricted phone DL capture link for the authenticated draft application."""
    app, access = await _get_application_and_access_by_token(db, tenant_id, token)
    purpose = getattr(access, "purpose", None) or TOKEN_PURPOSE_INVITE
    if purpose != TOKEN_PURPOSE_INVITE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the main application invite link can request a phone capture link",
        )
    if app.status != DriverOnboardingStatus.DRAFT.value:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Phone capture links are only available while the application is in draft",
        )
    _require_driver_workflow(app)
    return await _issue_dl_capture_link_for_application(db, tenant_id, app.id, request)


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
    _require_driver_workflow(app)
    intake = app.intake_payload or {}
    # DL files (front/back)
    files = intake.get("files") or {}
    for _side, meta in files.items():
        storage_key = _resolve_applicant_dl_serve_key(meta, file_id)
        if storage_key:
            return serve_file(storage_key, "applicant_dl", tenant_slug, meta.get("original_filename"))
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


def _merge_document_slot_after_upload(
    existing: dict | None,
    *,
    storage_key: str,
    original_filename: str,
    uploaded_by: str,
    uploaded_by_member_id: int | None = None,
) -> dict:
    base = dict(existing) if isinstance(existing, dict) else {}
    base.update(
        {
            "storage_key": storage_key,
            "file_id": storage_key,
            "original_filename": original_filename,
            "uploaded_at": _utcnow().isoformat(),
            "uploaded_by": uploaded_by,
            "workflow_status": "uploaded",
        }
    )
    if uploaded_by_member_id is not None:
        base["uploaded_by_member_id"] = uploaded_by_member_id
    else:
        base.pop("uploaded_by_member_id", None)
    base.pop("accepted_at", None)
    base.pop("accepted_by_member_id", None)
    return base


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
    app, access = await _get_application_and_access_by_token(db, tenant_id, token)
    _require_driver_workflow(app)
    purpose = getattr(access, "purpose", None) or TOKEN_PURPOSE_INVITE
    allowed = app.status == DriverOnboardingStatus.DRAFT.value or (
        app.status in _POST_SUBMIT_DOC_RESUME_STATUSES and purpose == TOKEN_PURPOSE_DOCUMENT_RESUME
    )
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Application already submitted",
        )
    stored = await save_applicant_doc_upload(tenant_slug, app.id, file)
    intake = dict(app.intake_payload or {})
    documents = dict(intake.get("documents") or {})
    documents[doc_type] = _merge_document_slot_after_upload(
        documents.get(doc_type),
        storage_key=stored.storage_key,
        original_filename=stored.original_filename,
        uploaded_by="applicant",
    )
    intake["documents"] = documents
    app.intake_payload = _sanitize_intake_for_workflow(app, intake)
    await db.commit()
    await db.refresh(app)
    intake_after = dict(app.intake_payload or {})
    followup_done = bool(intake_after.get("document_followup_completed_at"))
    resume_active = (
        purpose == TOKEN_PURPOSE_DOCUMENT_RESUME
        and not followup_done
        and app.status in _POST_SUBMIT_DOC_RESUME_STATUSES
    )
    return _person_application_to_out(app, document_resume_active=resume_active)


def _file_meta_matches(meta: dict, file_id: str) -> bool:
    if not isinstance(meta, dict):
        return False
    return file_id in {
        meta.get("storage_key"),
        meta.get("file_id"),
        meta.get("enh_file_id"),
    }


def _resolve_applicant_dl_serve_key(meta: dict, file_id: str) -> str | None:
    """Return storage key to serve. When preprocess succeeded, always serve processed JPEG."""
    if not _file_meta_matches(meta, file_id):
        return None
    if meta.get("dl_preprocess_status") == "PROCESSED" and meta.get("enh_file_id"):
        return str(meta["enh_file_id"])
    return str(meta.get("storage_key") or meta.get("file_id") or file_id)


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
    platform_db: AsyncSession = Depends(get_db),
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
):
    """List person applications (invite-link submissions) for admin review."""
    if not is_tenant_admin(current_user.role):
        raise HTTPException(status_code=403, detail="Admin role required")
    await reconcile_person_application_lanes_for_tenant_ui_mode(db, platform_db, tenant_id)
    await db.flush()
    stmt = select(PersonApplication).where(PersonApplication.tenant_id == tenant_id)
    # Post-submit queue only; unsubmitted invites stay in tenant DB but off this list.
    stmt = stmt.where(PersonApplication.status != DriverOnboardingStatus.DRAFT.value)
    stmt = stmt.where(PersonApplication.current_workflow_lane != WORKFLOW_LANE_COMPLETE)
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
            setup_status=getattr(app, "setup_status", None) or "pending",
            current_workflow_lane=normalize_workflow_lane(getattr(app, "current_workflow_lane", None)),
            application_type=app.application_type or "DRIVER",
            requested_role_code=app.requested_role_code or "DRIVER",
            first_name=app.first_name or (app.intake_payload or {}).get("first_name"),
            last_name=app.last_name or (app.intake_payload or {}).get("last_name"),
            email=app.email or (app.intake_payload or {}).get("email"),
            phone=app.phone or (app.intake_payload or {}).get("phone"),
            submitted_at=app.submitted_at,
            source=app.source,
            created_at=app.created_at,
            reviewed_at=getattr(app, "reviewed_at", None),
        )
        for app in apps
    ]


@router.post(
    "/applications/{application_id}/mark-admin-review-engaged",
    response_model=ApplicantApplicationOut,
)
async def mark_admin_review_engaged(
    application_id: int,
    tenant_id: int = Depends(require_tenant),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    """Record that an admin opened the review UI while SUBMITTED (idempotent).

    Primary trigger for moving ``current_workflow_lane`` from **submitted** → **processing**:
    sets ``reviewed_at`` / ``reviewed_by_user_id`` when still SUBMITTED and not yet set, then aligns lane.
    """
    if not is_tenant_admin(current_user.role):
        raise HTTPException(status_code=403, detail="Admin role required")
    app = await _get_person_application_admin_for_update_or_404(db, tenant_id, application_id)
    if app.status == DriverOnboardingStatus.SUBMITTED.value and app.reviewed_at is None:
        now = _utcnow()
        app.reviewed_at = now
        app.reviewed_by_user_id = current_user.member_id
    ensure_processing_lane_if_submitted_admin_engaged(app)
    await db.commit()
    await db.refresh(app)
    return _person_application_to_out(app, include_review_meta=True)


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
    return _person_application_to_out(app, include_review_meta=True)


def _date_to_intake(v: date | None) -> str | None:
    if v is None:
        return None
    return v.isoformat()


def _apply_person_application_review_patch(
    app: PersonApplication,
    payload: PersonApplicationReviewPatch,
    *,
    actor_member_id: int,
) -> list[str]:
    """Mutates app (columns + intake). Returns list of patch keys applied. Raises HTTPException if invalid."""
    patch = payload.model_dump(exclude_unset=True)
    if not patch:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No fields to update")
    if getattr(app, "intake_submitted_snapshot", None) is None:
        app.intake_submitted_snapshot = copy.deepcopy(app.intake_payload or {})

    intake = dict(app.intake_payload or {})
    changed: list[str] = []

    def mark(key: str) -> None:
        if key not in changed:
            changed.append(key)

    col_text = {
        "first_name": "first_name",
        "last_name": "last_name",
        "phone": "phone",
        "email": "email",
        "address_street": "street_address",
        "address_city": "city",
        "address_region": "region",
        "address_postal": "postal_code",
        "zip_code": "zip_code",
        "address_country": "country",
        "notes": "notes",
    }
    for pk, attr in col_text.items():
        if pk not in patch:
            continue
        raw = patch[pk]
        val = _clean_text(raw) if pk != "email" else (_clean_text(str(raw)) if raw is not None else None)
        setattr(app, attr, val)
        mark(pk)

    if _is_driver_workflow_application(app):
        if "driver_license_number" in patch:
            v = _clean_text(patch["driver_license_number"])
            if v:
                intake["driver_license_number"] = v
            else:
                intake.pop("driver_license_number", None)
            mark("driver_license_number")
        if "license_region" in patch:
            v = _clean_text(patch["license_region"])
            if v:
                intake["license_region"] = v
                intake["license_state"] = v
            else:
                intake.pop("license_region", None)
                intake.pop("license_state", None)
            mark("license_region")
        if "license_expiry" in patch:
            intake["license_expiry"] = _date_to_intake(patch["license_expiry"])
            mark("license_expiry")

        for ik in ("middle_name", "cdl_class", "endorsements", "restrictions", "conditions"):
            if ik not in patch:
                continue
            v = _clean_text(patch[ik])
            if v:
                intake[ik] = v
            else:
                intake.pop(ik, None)
            mark(ik)
        if "date_of_birth" in patch:
            intake["date_of_birth"] = _date_to_intake(patch["date_of_birth"])
            mark("date_of_birth")
        if "license_issue_date" in patch:
            intake["license_issue_date"] = _date_to_intake(patch["license_issue_date"])
            mark("license_issue_date")

    app.intake_payload = _sanitize_intake_for_workflow(app, intake)
    mi = app.intake_payload or {}
    ap = _clean_text(app.postal_code) or _clean_text(mi.get("address_postal"))
    zc = _clean_text(app.zip_code) or _clean_text(mi.get("zip_code"))
    co = _clean_text(app.country) or _clean_text(mi.get("address_country"))
    ap2, zc2 = _normalize_postal_zip_for_country(co, ap, zc)
    app.postal_code = ap2
    app.zip_code = zc2
    if (_clean_text(app.country) or "").upper() == "CA":
        app.zip_code = None
    intake2 = dict(mi)
    if (_clean_text(app.country) or "").upper() == "CA":
        intake2.pop("zip_code", None)
    elif app.zip_code:
        intake2["zip_code"] = app.zip_code
    app.intake_payload = _sanitize_intake_for_workflow(app, intake2)

    if not changed:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No applicable fields to update for this workflow")

    # Validate still promotable
    _person_application_canonical_data(app)

    audit = getattr(app, "intake_review_audit", None)
    if not isinstance(audit, list):
        audit = []
    audit = list(audit)
    audit.append(
        {
            "at": _utcnow().isoformat(),
            "by_user_id": actor_member_id,
            "changed_keys": changed,
        }
    )
    app.intake_review_audit = audit[-40:]
    return changed


@router.patch("/applications/{application_id}/review-fields", response_model=ApplicantApplicationOut)
async def patch_person_application_review_fields(
    application_id: int,
    payload: PersonApplicationReviewPatch,
    tenant_id: int = Depends(require_tenant),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
    platform_db: AsyncSession = Depends(get_db),
):
    """Admin: correct structured applicant fields during review. Preserves original submission snapshot + audit trail."""
    if not is_tenant_admin(current_user.role):
        raise HTTPException(status_code=403, detail="Admin role required")
    app = await _get_person_application_admin_for_update_or_404(db, tenant_id, application_id)
    if app.status not in {
        DriverOnboardingStatus.SUBMITTED.value,
        DriverOnboardingStatus.APPROVED.value,
    }:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Review edits are only allowed for SUBMITTED or APPROVED applications",
        )
    await _maybe_ensure_person_for_combined_admin_setup(db, platform_db, tenant_id, app)
    _apply_person_application_review_patch(app, payload, actor_member_id=current_user.member_id)
    ensure_processing_lane_if_submitted_admin_engaged(app)
    if app.status == DriverOnboardingStatus.APPROVED.value and app.person_id:
        await _ensure_person_entities_for_application(db, app)
    await db.commit()
    await db.refresh(app)
    return _person_application_to_out(app, include_review_meta=True)


async def _revoke_active_access_tokens_for_application(
    db: AsyncSession,
    tenant_id: int,
    application_id: int,
    *,
    purpose: str | None = None,
) -> None:
    """Revoke active tokens for an application. When purpose is set, only that purpose is revoked."""
    now = _utcnow()
    clauses = [
        ApplicationAccessToken.tenant_id == tenant_id,
        ApplicationAccessToken.application_id == application_id,
        ApplicationAccessToken.revoked_at.is_(None),
    ]
    if purpose is not None:
        clauses.append(ApplicationAccessToken.purpose == purpose)
    await db.execute(
        update(ApplicationAccessToken).where(*clauses).values(revoked_at=now)
    )


@router.post(
    "/applications/{application_id}/request-documents",
    response_model=PersonApplicationDocumentRequestResponse,
)
async def request_person_application_documents(
    application_id: int,
    payload: PersonApplicationDocumentRequest,
    request: Request,
    tenant_id: int = Depends(require_tenant),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
    platform_db: AsyncSession = Depends(get_db),
):
    """Admin: email applicant a combined document request; rotate resume token (hash-only)."""
    if not is_tenant_admin(current_user.role):
        raise HTTPException(status_code=403, detail="Admin role required")
    app = await _get_person_application_admin_for_update_or_404(db, tenant_id, application_id)
    _require_driver_workflow(app)
    if app.status not in (
        DriverOnboardingStatus.SUBMITTED.value,
        DriverOnboardingStatus.APPROVED.value,
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Documents can only be requested after the application is submitted",
        )

    for dt in payload.doc_types:
        if dt not in _ALLOWED_DOC_TYPES:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown document type: {dt}")

    intake_mi = app.intake_payload or {}
    to_email = (app.email or "").strip() or (_clean_text(intake_mi.get("email")) or "")
    if not to_email:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Applicant has no email address on file")

    now = _utcnow()
    intake = dict(intake_mi)
    docs = dict(intake.get("documents") or {})
    for dt in payload.doc_types:
        prev = dict(docs.get(dt) or {}) if isinstance(docs.get(dt), dict) else {}
        prev["requested_at"] = now.isoformat()
        prev["requested_by_member_id"] = current_user.member_id
        if not (prev.get("storage_key") or prev.get("file_id")):
            prev["workflow_status"] = "requested"
        docs[dt] = prev
    intake["documents"] = docs
    intake.pop("document_followup_completed_at", None)
    app.intake_payload = _sanitize_intake_for_workflow(app, intake)
    ensure_processing_lane_if_submitted_admin_engaged(app)

    tenant_cfg = await platform_db.get(PlatformTenant, int(tenant_id))
    expiry_days = int(getattr(tenant_cfg, "doc_request_link_expiry_days", None) or 21)

    await _revoke_active_access_tokens_for_application(db, tenant_id, application_id)
    raw = secrets.token_urlsafe(32)
    th = _token_sha256_hex(raw)
    db.add(
        ApplicationAccessToken(
            tenant_id=tenant_id,
            application_id=application_id,
            token=None,
            token_hash=th,
            expires_at=now + timedelta(days=expiry_days),
            revoked_at=None,
            purpose=TOKEN_PURPOSE_DOCUMENT_RESUME,
        )
    )

    base = str(request.base_url).rstrip("/")
    link = f"{base}/onboarding?token={raw}"

    await db.commit()

    email_sent = False
    email_error: str | None = None
    body = payload.body.strip()
    if link not in body:
        body = f"{body.rstrip()}\n\n---\nOpen your application to upload requested documents:\n{link}\n"
    try:
        await send_onboarding_document_request_email(to=to_email, subject=payload.subject, body=body)
        email_sent = True
    except Exception as exc:
        logger.exception("Document request email failed: %s", exc)
        email_error = "Could not send email. Verify SMTP is configured. See server logs for details."

    return PersonApplicationDocumentRequestResponse(email_sent=email_sent, email_error=email_error)


@router.post("/applications/{application_id}/documents/accept", response_model=ApplicantApplicationOut)
async def set_person_application_document_acceptance(
    application_id: int,
    body: PersonApplicationDocumentAcceptBody,
    tenant_id: int = Depends(require_tenant),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    if not is_tenant_admin(current_user.role):
        raise HTTPException(status_code=403, detail="Admin role required")
    app = await _get_person_application_admin_for_update_or_404(db, tenant_id, application_id)
    _require_driver_workflow(app)
    if app.status not in (
        DriverOnboardingStatus.SUBMITTED.value,
        DriverOnboardingStatus.APPROVED.value,
    ):
        raise HTTPException(status_code=409, detail="Document review is only allowed for submitted or approved applications")
    if body.doc_type not in _ALLOWED_DOC_TYPES:
        raise HTTPException(status_code=400, detail=f"doc_type must be one of {sorted(_ALLOWED_DOC_TYPES)}")

    intake = dict(app.intake_payload or {})
    docs = dict(intake.get("documents") or {})
    slot = dict(docs.get(body.doc_type) or {}) if isinstance(docs.get(body.doc_type), dict) else {}
    if body.accepted:
        if not (slot.get("storage_key") or slot.get("file_id")):
            raise HTTPException(status_code=400, detail="No file uploaded for this document type")
        slot["accepted_at"] = _utcnow().isoformat()
        slot["accepted_by_member_id"] = current_user.member_id
        slot["workflow_status"] = "accepted"
    else:
        slot.pop("accepted_at", None)
        slot.pop("accepted_by_member_id", None)
        if slot.get("storage_key") or slot.get("file_id"):
            slot["workflow_status"] = "uploaded"
        else:
            slot.pop("workflow_status", None)
    docs[body.doc_type] = slot
    intake["documents"] = docs
    app.intake_payload = _sanitize_intake_for_workflow(app, intake)
    ensure_processing_lane_if_submitted_admin_engaged(app)
    await db.commit()
    await db.refresh(app)
    return _person_application_to_out(app, include_review_meta=True)


@router.post("/applications/{application_id}/document-upload", response_model=ApplicantApplicationOut)
async def admin_upload_person_application_document(
    application_id: int,
    doc_type: str = Form(..., description="Document type key (e.g. dot_medical, mvr)"),
    file: UploadFile = File(...),
    tenant_id: int = Depends(require_tenant),
    tenant_slug: str = Depends(require_tenant_slug),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    if not is_tenant_admin(current_user.role):
        raise HTTPException(status_code=403, detail="Admin role required")
    app = await _get_person_application_admin_for_update_or_404(db, tenant_id, application_id)
    _require_driver_workflow(app)
    if app.status not in (
        DriverOnboardingStatus.SUBMITTED.value,
        DriverOnboardingStatus.APPROVED.value,
        DriverOnboardingStatus.DRAFT.value,
    ):
        raise HTTPException(status_code=409, detail="Cannot upload documents for this application status")
    if doc_type not in _ALLOWED_DOC_TYPES:
        raise HTTPException(status_code=400, detail=f"doc_type must be one of {sorted(_ALLOWED_DOC_TYPES)}")

    stored = await save_applicant_doc_upload(tenant_slug, app.id, file)
    intake = dict(app.intake_payload or {})
    documents = dict(intake.get("documents") or {})
    documents[doc_type] = _merge_document_slot_after_upload(
        documents.get(doc_type),
        storage_key=stored.storage_key,
        original_filename=stored.original_filename,
        uploaded_by="admin",
        uploaded_by_member_id=current_user.member_id,
    )
    intake["documents"] = documents
    app.intake_payload = _sanitize_intake_for_workflow(app, intake)
    ensure_processing_lane_if_submitted_admin_engaged(app)
    await db.commit()
    await db.refresh(app)
    return _person_application_to_out(app, include_review_meta=True)


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
    _require_driver_workflow(app)
    intake = app.intake_payload or {}
    # DL files (front/back)
    files = intake.get("files") or {}
    for _side, meta in files.items():
        storage_key = _resolve_applicant_dl_serve_key(meta, file_id)
        if storage_key:
            return serve_file(storage_key, "applicant_dl", tenant_slug, meta.get("original_filename"))
    # Step-4 documents
    documents = intake.get("documents") or {}
    for _doc_type, meta in documents.items():
        if _file_meta_matches(meta, file_id):
            storage_key = meta.get("storage_key") or file_id
            return serve_file(storage_key, "applicant_docs", tenant_slug, meta.get("original_filename"))
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found for this application")


@router.post(
    "/applications/{application_id}/materialize-person-for-combined-setup",
    response_model=ApplicantApplicationOut,
)
async def materialize_person_for_combined_setup(
    application_id: int,
    tenant_id: int = Depends(require_tenant),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
    platform_db: AsyncSession = Depends(get_db),
):
    """Create tenant Person (+ driver path entities) while SUBMITTED so combined-mode admin can use setup cards before approve."""
    if not is_tenant_admin(current_user.role):
        raise HTTPException(status_code=403, detail="Admin role required")
    ui_mode = normalize_person_setup_ui_mode(await get_person_setup_ui_mode(platform_db, tenant_id))
    if ui_mode != PERSON_SETUP_UI_COMBINED:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Person materialization for setup is only used when tenant person setup mode is combined.",
        )
    app = await _get_person_application_admin_for_update_or_404(db, tenant_id, application_id)
    _require_driver_workflow(app)
    if not is_driver_driver_person_application(app):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Person materialization for setup applies only to DRIVER workflow with DRIVER requested role.",
        )
    if app.status != DriverOnboardingStatus.SUBMITTED.value:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Person can only be materialized for setup while the application is SUBMITTED.",
        )
    if app.person_id is not None:
        ensure_processing_lane_if_submitted_admin_engaged(app)
        await db.commit()
        await db.refresh(app)
        return _person_application_to_out(app, include_review_meta=True)
    await _ensure_person_entities_for_application(db, app)
    ensure_processing_lane_if_submitted_admin_engaged(app)
    await db.commit()
    await db.refresh(app)
    return _person_application_to_out(app, include_review_meta=True)


@router.get(
    "/applications/{application_id}/combined-driver-approve-readiness",
    response_model=CombinedDriverApproveReadinessOut,
)
async def get_combined_driver_approve_readiness(
    application_id: int,
    tenant_id: int = Depends(require_tenant),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
    platform_db: AsyncSession = Depends(get_db),
):
    """Admin: whether Approve is allowed for combined-mode DRIVER+DRIVER (in-page setup complete)."""
    if not is_tenant_admin(current_user.role):
        raise HTTPException(status_code=403, detail="Admin role required")
    app = await _get_person_application_admin_or_404(db, tenant_id, application_id)
    ui_mode = normalize_person_setup_ui_mode(await get_person_setup_ui_mode(platform_db, tenant_id))
    if ui_mode != PERSON_SETUP_UI_COMBINED or not is_driver_driver_person_application(app):
        return CombinedDriverApproveReadinessOut(applies=False, ready=True)
    _require_driver_workflow(app)
    if app.status != DriverOnboardingStatus.SUBMITTED.value:
        return CombinedDriverApproveReadinessOut(applies=False, ready=True)
    if not app.person_id:
        return CombinedDriverApproveReadinessOut(
            applies=True,
            ready=False,
            blocking_code="onboarding_person_missing",
            detail=_combined_approve_guard_http_detail("onboarding_person_missing"),
        )
    try:
        await assert_combined_driver_onboarding_ready(db, tenant_id=tenant_id, app=app)
    except ValueError as exc:
        code = str(exc)
        return CombinedDriverApproveReadinessOut(
            applies=True,
            ready=False,
            blocking_code=code,
            detail=_combined_approve_guard_http_detail(code),
        )
    return CombinedDriverApproveReadinessOut(applies=True, ready=True)


@router.post("/applications/{application_id}/approve", response_model=ApplicantApplicationOut)
async def approve_person_application(
    application_id: int,
    tenant_id: int = Depends(require_tenant),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
    platform_db: AsyncSession = Depends(get_db),
):
    """Canonical admin approval path for PersonApplication invite-link onboarding.

    Approving DRIVER materializes the operational `Driver` row used by dispatch (`GET /drivers`);
    PersonApplication itself is never the dispatch roster.
    """
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
        ui_mode = normalize_person_setup_ui_mode(await get_person_setup_ui_mode(platform_db, tenant_id))
        if ui_mode == PERSON_SETUP_UI_COMBINED and is_driver_driver_person_application(app):
            try:
                await assert_combined_driver_onboarding_ready(db, tenant_id=tenant_id, app=app)
            except ValueError as exc:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=_combined_approve_guard_http_detail(str(exc)),
                ) from exc
        app.reviewed_at = now
        app.reviewed_by_user_id = current_user.member_id
        app.approved_at = now
        app.approved_by_user_id = current_user.member_id
        app.setup_status = setup_status_after_approval(ui_mode)
        set_lane_after_manager_approve(app, person_setup_ui_mode=ui_mode)

    app.status = DriverOnboardingStatus.APPROVED.value
    app.person_id = person.id
    app.rejection_reason = None

    await db.commit()
    await db.refresh(app)
    return _person_application_to_out(app, include_review_meta=True)


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
    app = await _get_person_application_admin_for_update_or_404(db, tenant_id, application_id)
    if app.status != DriverOnboardingStatus.SUBMITTED.value:
        raise HTTPException(status_code=409, detail="Application is not in SUBMITTED status")

    app.status = DriverOnboardingStatus.REJECTED.value
    app.reviewed_at = _utcnow()
    app.reviewed_by_user_id = current_user.member_id
    app.approved_at = None
    app.approved_by_user_id = None
    app.rejection_reason = payload.rejection_reason
    apply_rejection_setup_state(app)
    set_rejected_lane(app)

    await db.commit()
    await db.refresh(app)
    return _person_application_to_out(app, include_review_meta=True)


@router.get(
    "/applications/{application_id}/driver-compensation-setup",
    response_model=DriverCompensationSetupOut,
)
async def get_application_driver_compensation_setup(
    application_id: int,
    tenant_id: int = Depends(require_tenant),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
    platform_db: AsyncSession = Depends(get_db),
):
    """Combined mode only: read payee + current compensation profile for the person's operational driver (SUBMITTED or APPROVED)."""
    if not is_tenant_admin(current_user.role):
        raise HTTPException(status_code=403, detail="Admin role required")
    ui_mode = normalize_person_setup_ui_mode(await get_person_setup_ui_mode(platform_db, tenant_id))
    if ui_mode != PERSON_SETUP_UI_COMBINED:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Driver compensation setup is only available when tenant person setup mode is combined.",
        )
    app = await _get_person_application_admin_or_404(db, tenant_id, application_id)
    _require_driver_workflow(app)
    if app.status not in (
        DriverOnboardingStatus.SUBMITTED.value,
        DriverOnboardingStatus.APPROVED.value,
    ):
        raise HTTPException(
            status_code=409,
            detail="Application must be submitted or approved to view compensation setup",
        )
    if not app.person_id:
        raise HTTPException(status_code=409, detail="Application has no linked person")
    return await get_driver_compensation_setup(db, tenant_id=tenant_id, person_id=int(app.person_id))


@router.put(
    "/applications/{application_id}/driver-compensation-setup",
    response_model=DriverCompensationSetupOut,
)
async def put_application_driver_compensation_setup(
    application_id: int,
    body: DriverCompensationSetupWrite,
    tenant_id: int = Depends(require_tenant),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
    platform_db: AsyncSession = Depends(get_db),
):
    """Combined mode only: upsert payee + open compensation profile (tenant truth; not driver_person_extensions)."""
    if not is_tenant_admin(current_user.role):
        raise HTTPException(status_code=403, detail="Admin role required")
    ui_mode = normalize_person_setup_ui_mode(await get_person_setup_ui_mode(platform_db, tenant_id))
    if ui_mode != PERSON_SETUP_UI_COMBINED:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Driver compensation setup is only available when tenant person setup mode is combined.",
        )
    app = await _get_person_application_admin_or_404(db, tenant_id, application_id)
    _require_driver_workflow(app)
    if app.status not in (
        DriverOnboardingStatus.SUBMITTED.value,
        DriverOnboardingStatus.APPROVED.value,
    ):
        raise HTTPException(
            status_code=409,
            detail="Application must be submitted or approved to edit compensation setup",
        )
    if not app.person_id:
        raise HTTPException(status_code=409, detail="Application has no linked person")
    try:
        return await upsert_driver_compensation_setup(
            db, tenant_id=tenant_id, person_id=int(app.person_id), payload=body
        )
    except ValueError as exc:
        code = str(exc)
        if code == "operational_driver_missing":
            raise HTTPException(
                status_code=409,
                detail="Operational driver row is missing; re-approve the application if needed.",
            ) from exc
        if code == "payee_not_found":
            raise HTTPException(status_code=404, detail="Payee not found") from exc
        if code == "driver_person_extension_required":
            raise HTTPException(
                status_code=400,
                detail="Save Driver Configuration before compensation setup.",
            ) from exc
        raise HTTPException(status_code=400, detail=code) from exc


@router.post("/applications/{application_id}/complete-onboarding", response_model=ApplicantApplicationOut)
async def complete_person_application_onboarding(
    application_id: int,
    tenant_id: int = Depends(require_tenant),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
    platform_db: AsyncSession = Depends(get_db),
):
    """Mark person application onboarding fully complete (onboarded_* + setup_status=complete). Admin only.

    People/onboarding completion (not driver-only); this path lives under ``driver-onboarding`` today because
    that router owns ``PersonApplication`` — acceptable for this slice; a future cleanup may relocate it.
    """
    if not is_tenant_admin(current_user.role):
        raise HTTPException(status_code=403, detail="Admin role required")
    ui_mode = await get_person_setup_ui_mode(platform_db, tenant_id)
    try:
        await finalize_person_application_onboarding(
            db,
            tenant_id=tenant_id,
            application_id=application_id,
            actor_member_id=current_user.member_id,
            person_setup_ui_mode=ui_mode,
        )
    except ValueError as exc:
        code = str(exc)
        if code == "application_not_found":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found") from exc
        if code == "application_not_approved":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Application must be APPROVED before onboarding can be completed",
            ) from exc
        if code in {
            "onboarding_compensation_incomplete",
            "onboarding_driver_configuration_incomplete",
            "onboarding_operational_driver_missing",
            "onboarding_person_missing",
        }:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=code,
            ) from exc
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=code) from exc

    await db.commit()
    app = await _get_person_application_admin_or_404(db, tenant_id, application_id)
    return _person_application_to_out(app, include_review_meta=True)


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
