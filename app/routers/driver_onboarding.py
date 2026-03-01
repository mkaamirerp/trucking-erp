from __future__ import annotations

import logging
import secrets
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import cast, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import Integer as SAInteger

from app.deps.auth import CurrentUser, get_current_user
from app.deps.tenant import require_tenant
from app.deps.tenant_db import get_tenant_db
from app.models.application_access_token import ApplicationAccessToken
from app.models.person_application import PersonApplication
from app.models.person_application_file import PersonApplicationFile
from app.models.person_application_request import PersonApplicationRequest
from app.models.person import Person, PersonRole, DriverProfile
from app.schemas.driver_onboarding import (
    DriverOnboardingApproveResponse,
    DriverOnboardingCreateResponse,
    DriverOnboardingRejectRequest,
    DriverOnboardingSubmissionCreate,
    DriverOnboardingSubmissionOut,
    DriverOnboardingStatus,
    LicenseUploadResponse,
    PersonOut,
)
from app.services.dl_extract_stub import run_extraction_stub
from app.utils.email import send_onboarding_invite_email

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/driver-onboarding", tags=["driver-onboarding"])


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _is_admin(user: CurrentUser) -> bool:
    role = (user.role or "").upper()
    return role in {"OWNER", "ADMIN", "TENANT_ADMIN"}


def _get_created_by_expr():
    return cast(
        PersonApplication.intake_payload["created_by_user_id"].astext,
        SAInteger,
    )


def _get_review_payload(p: dict) -> dict:
    return p.get("review") or {}


def _get_license_payload(p: dict) -> dict:
    return p.get("license") or {}


def _get_extraction_payload(p: dict) -> dict:
    return p.get("extraction") or {}


def _set_payload(app: PersonApplication, payload: dict) -> None:
    app.intake_payload = payload


def _serialize_application(app: PersonApplication) -> dict:
    p = app.intake_payload or {}
    review = _get_review_payload(p)
    lic = _get_license_payload(p)
    extraction = _get_extraction_payload(p)

    return {
        "id": app.id,
        "tenant_id": app.tenant_id,
        "created_by_user_id": int(p.get("created_by_user_id") or 0),
        "status": app.status,
        "source": app.source or "driver_portal",
        "submitted_at": app.submitted_at,
        "reviewed_at": review.get("reviewed_at"),
        "reviewed_by_user_id": review.get("reviewed_by_user_id"),
        "rejection_reason": review.get("rejection_reason"),
        "extraction_status": extraction.get("overall_status"),
        "extraction_result_json": None,
        "license_uploads_json": None,
        "first_name": app.first_name,
        "last_name": app.last_name,
        "middle_name": p.get("middle_name"),
        "phone": app.phone,
        "email": app.email,
        "address_street": app.street_address,
        "address_city": app.city,
        "address_region": app.region,
        "address_postal": app.postal_code,
        "address_country": app.country,
        "driver_license_number": lic.get("number"),
        "license_region": lic.get("region"),
        "license_expiry": lic.get("expiry"),
        "notes": app.notes,
        "created_at": app.created_at,
        "updated_at": app.updated_at,
    }


async def _get_submission(
    db: AsyncSession, tenant_id: int, submission_id: int
) -> PersonApplication:
    app = await db.scalar(
        select(PersonApplication).where(
            PersonApplication.id == submission_id,
            PersonApplication.tenant_id == tenant_id,
        )
    )
    if not app:
        raise HTTPException(status_code=404, detail="Submission not found")
    return app


def _payload_to_people_fields(data: dict) -> dict:
    return {
        "first_name": data.get("first_name") or "",
        "last_name": data.get("last_name") or "",
        "phone": data.get("phone"),
        "email": data.get("email"),
        "street_address": data.get("address_street"),
        "city": data.get("address_city"),
        "region": data.get("address_region"),
        "postal_code": data.get("address_postal"),
        "country": data.get("address_country"),
        "notes": data.get("notes"),
    }


async def _get_my_latest_submission(
    db: AsyncSession, tenant_id: int, member_id: int
) -> PersonApplication | None:
    return await db.scalar(
        select(PersonApplication)
        .where(
            PersonApplication.tenant_id == tenant_id,
            _get_created_by_expr() == member_id,
        )
        .order_by(PersonApplication.created_at.desc())
        .limit(1)
    )


async def _get_my_submission(
    db: AsyncSession, tenant_id: int, submission_id: int, member_id: int
) -> PersonApplication:
    app = await db.scalar(
        select(PersonApplication).where(
            PersonApplication.id == submission_id,
            PersonApplication.tenant_id == tenant_id,
            _get_created_by_expr() == member_id,
        )
    )
    if not app:
        raise HTTPException(status_code=404, detail="Submission not found")
    return app


@router.post("/submissions", response_model=DriverOnboardingCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_submission(
    payload: DriverOnboardingSubmissionCreate,
    tenant_id: int = Depends(require_tenant),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    if current_user.member_id is None:
        raise HTTPException(status_code=403, detail="User membership not found")

    submitted = bool(payload.submit)
    status_val = DriverOnboardingStatus.SUBMITTED.value if submitted else DriverOnboardingStatus.DRAFT.value

    expiry_val = None
    if payload.license_expiry:
        expiry_val = payload.license_expiry.isoformat() if hasattr(payload.license_expiry, "isoformat") else str(payload.license_expiry)
    intake = {
        "created_by_user_id": current_user.member_id,
        "middle_name": getattr(payload, "middle_name", None) or (payload.model_dump().get("middle_name")),
        "license": {
            "number": payload.driver_license_number,
            "region": payload.license_region,
            "expiry": expiry_val,
        },
        "extraction": {"overall_status": None},
    }

    existing = await _get_my_latest_submission(db, tenant_id, current_user.member_id)
    if existing and existing.status == DriverOnboardingStatus.DRAFT.value:
        existing.status = status_val
        existing.submitted_at = _utcnow() if submitted else None
        existing.first_name = payload.first_name
        existing.last_name = payload.last_name
        existing.phone = payload.phone
        existing.email = payload.email
        existing.street_address = payload.address_street
        existing.city = payload.address_city
        existing.region = payload.address_region
        existing.postal_code = payload.address_postal
        existing.country = payload.address_country
        existing.notes = payload.notes
        p = existing.intake_payload or {}
        p["middle_name"] = intake["middle_name"]
        p["license"] = intake["license"]
        existing.intake_payload = p
        await db.commit()
        await db.refresh(existing)
        return {"submission": _serialize_application(existing), "missing_required_documents": []}

    app = PersonApplication(
        tenant_id=tenant_id,
        status=status_val,
        source="driver_portal",
        submitted_at=_utcnow() if submitted else None,
        first_name=payload.first_name,
        last_name=payload.last_name,
        phone=payload.phone,
        email=payload.email,
        street_address=payload.address_street,
        city=payload.address_city,
        region=payload.address_region,
        postal_code=payload.address_postal,
        country=payload.address_country,
        notes=payload.notes,
        intake_payload=intake,
    )
    db.add(app)
    await db.commit()
    await db.refresh(app)
    return {"submission": _serialize_application(app), "missing_required_documents": []}


@router.post(
    "/submissions/{submission_id}/license-upload",
    status_code=status.HTTP_410_GONE,
)
async def upload_license_deprecated():
    """Deprecated. Use POST /api/v1/person-applications/{id}/dl-files instead."""
    raise HTTPException(
        status_code=410,
        detail="Deprecated. Use POST /api/v1/person-applications/{id}/dl-files",
    )


@router.post("/submissions/{submission_id}/license-upload/swap", response_model=DriverOnboardingSubmissionOut)
async def swap_license_front_back(
    submission_id: int,
    tenant_id: int = Depends(require_tenant),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    if current_user.member_id is None:
        raise HTTPException(status_code=403, detail="User membership not found")
    app = await _get_my_submission(db, tenant_id, submission_id, current_user.member_id)
    if app.status != DriverOnboardingStatus.DRAFT.value:
        raise HTTPException(status_code=409, detail="Only draft submissions can swap front/back")

    result = await db.execute(
        select(PersonApplicationFile).where(
            PersonApplicationFile.application_id == submission_id,
            PersonApplicationFile.tenant_id == tenant_id,
            PersonApplicationFile.is_active.is_(True),
            PersonApplicationFile.doc_type.in_(["CDL_FRONT", "CDL_BACK"]),
        )
    )
    files = list(result.scalars().all())
    if len(files) != 2:
        raise HTTPException(status_code=400, detail="Need exactly two active CDL files to swap")

    for f in files:
        f.doc_type = "CDL_BACK" if f.doc_type == "CDL_FRONT" else "CDL_FRONT"

    front_file = next((x for x in files if x.doc_type == "CDL_FRONT"), None)
    back_file = next((x for x in files if x.doc_type == "CDL_BACK"), None)
    if not front_file or not back_file:
        raise HTTPException(status_code=400, detail="Could not resolve front/back after swap")
    inputs = {
        "front": {
            "original_file_id": front_file.storage_key,
            "mime_type": front_file.content_type or "",
            "normalized_image_ids": [front_file.storage_key],
            "page_indices": [1],
            "assigned_side": "FRONT",
        },
        "back": {
            "original_file_id": back_file.storage_key,
            "mime_type": back_file.content_type or "",
            "normalized_image_ids": [back_file.storage_key],
            "page_indices": [2],
            "assigned_side": "BACK",
        },
    }

    result_obj = run_extraction_stub(submission_id, inputs)
    for f in files:
        f.extract_payload = result_obj

    await db.commit()
    await db.refresh(app)
    return _serialize_application(app)


@router.get("/submissions/me", response_model=DriverOnboardingSubmissionOut | None)
async def get_my_latest_submission(
    tenant_id: int = Depends(require_tenant),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    if current_user.member_id is None:
        return None
    app = await _get_my_latest_submission(db, tenant_id, current_user.member_id)
    return _serialize_application(app) if app else None


@router.get("/submissions", response_model=list[DriverOnboardingSubmissionOut])
async def list_submissions(
    tenant_id: int = Depends(require_tenant),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
):
    if not _is_admin(current_user):
        raise HTTPException(status_code=403, detail="Admin role required")
    stmt = select(PersonApplication).where(PersonApplication.tenant_id == tenant_id)
    if status:
        stmt = stmt.where(PersonApplication.status == status)
    stmt = stmt.order_by(PersonApplication.created_at.desc()).offset(offset).limit(limit)
    result = await db.execute(stmt)
    return [_serialize_application(row) for row in result.scalars().all()]


@router.get("/submissions/{submission_id}", response_model=DriverOnboardingSubmissionOut)
async def get_submission(
    submission_id: int,
    tenant_id: int = Depends(require_tenant),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    if not _is_admin(current_user):
        raise HTTPException(status_code=403, detail="Admin role required")
    app = await _get_submission(db, tenant_id, submission_id)
    return _serialize_application(app)


@router.post("/submissions/{submission_id}/submit", response_model=DriverOnboardingSubmissionOut)
async def submit_submission(
    submission_id: int,
    tenant_id: int = Depends(require_tenant),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    app = await _get_submission(db, tenant_id, submission_id)
    p = app.intake_payload or {}
    created_by = int(p.get("created_by_user_id") or 0)
    if not _is_admin(current_user) and created_by != (current_user.member_id or 0):
        raise HTTPException(status_code=403, detail="Not allowed to submit this draft")
    if app.status != DriverOnboardingStatus.DRAFT.value:
        raise HTTPException(status_code=409, detail="Submission is not in DRAFT status")

    app.status = DriverOnboardingStatus.SUBMITTED.value
    app.submitted_at = _utcnow()
    await db.commit()
    await db.refresh(app)
    return _serialize_application(app)


@router.post("/submissions/{submission_id}/approve", response_model=DriverOnboardingApproveResponse)
async def approve_submission(
    submission_id: int,
    tenant_id: int = Depends(require_tenant),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    if not _is_admin(current_user):
        raise HTTPException(status_code=403, detail="Admin role required")

    # Lock + fetch (tenant equation)
    app = await db.scalar(
        select(PersonApplication)
        .where(
            PersonApplication.tenant_id == tenant_id,
            PersonApplication.id == submission_id,
        )
        .with_for_update()
    )
    if not app:
        raise HTTPException(status_code=404, detail="Application not found.")

    # Idempotent: if already approved, return existing result (no duplicates)
    if app.status == DriverOnboardingStatus.APPROVED.value:
        person_id = app.person_id
        if person_id is None:
            review = (app.intake_payload or {}).get("review") or {}
            person_id = review.get("person_id")
        person = None
        if person_id is not None:
            person = await db.scalar(
                select(Person).where(Person.tenant_id == tenant_id, Person.id == int(person_id))
            )
        return {
            "submission": _serialize_application(app),
            "person": PersonOut.model_validate(person) if person else None,
        }

    # Status gate: only SUBMITTED or IN_REVIEW can be approved
    if app.status not in (
        DriverOnboardingStatus.SUBMITTED.value,
        DriverOnboardingStatus.IN_REVIEW.value,
    ):
        raise HTTPException(
            status_code=409,
            detail="Only submitted or in-review applications can be approved.",
        )

    # Block approve if any required document request is not ACCEPTED (no request rows => allow)
    open_required = (
        await db.execute(
            select(func.count())
            .select_from(PersonApplicationRequest)
            .where(
                PersonApplicationRequest.tenant_id == tenant_id,
                PersonApplicationRequest.application_id == app.id,
                PersonApplicationRequest.required.is_(True),
                PersonApplicationRequest.status != "ACCEPTED",
            )
        )
    ).scalar() or 0
    if open_required > 0:
        raise HTTPException(
            status_code=409,
            detail="Required documents not completed. Accept or resolve all required document requests before approving.",
        )

    # Required name fields
    first = (app.first_name or "").strip()
    last = (app.last_name or "").strip()
    if not first or not last:
        raise HTTPException(status_code=422, detail="First and last name are required to approve.")

    # Required files: both CDL_FRONT and CDL_BACK must exist and be active
    rows = await db.execute(
        select(PersonApplicationFile.doc_type)
        .where(
            PersonApplicationFile.tenant_id == tenant_id,
            PersonApplicationFile.application_id == app.id,
            PersonApplicationFile.is_active.is_(True),
            PersonApplicationFile.doc_type.in_(["CDL_FRONT", "CDL_BACK"]),
        )
    )
    uploaded = {r[0] for r in rows.all()}
    if "CDL_FRONT" not in uploaded or "CDL_BACK" not in uploaded:
        raise HTTPException(
            status_code=400,
            detail="Both front and back license images are required.",
        )

    # Existing logic preserved
    lic = _get_license_payload(app.intake_payload or {})
    data = _payload_to_people_fields(
        {
            "first_name": first,
            "last_name": last,
            "phone": app.phone,
            "email": app.email,
            "address_street": app.street_address,
            "address_city": app.city,
            "address_region": app.region,
            "address_postal": app.postal_code,
            "address_country": app.country,
            "notes": app.notes,
        }
    )

    person = Person(tenant_id=tenant_id, onboarding_status="APPROVED", **data)
    db.add(person)
    await db.flush()

    app.person_id = person.id

    person_role = PersonRole(
        tenant_id=tenant_id,
        person_id=person.id,
        role_code="DRIVER",
        is_active=True,
    )
    db.add(person_role)

    expiry_raw = lic.get("expiry")
    license_expiry_date = None
    if expiry_raw:
        if isinstance(expiry_raw, date):
            license_expiry_date = expiry_raw
        elif isinstance(expiry_raw, str):
            try:
                license_expiry_date = date.fromisoformat(expiry_raw)
            except ValueError:
                pass

    driver_profile = DriverProfile(
        tenant_id=tenant_id,
        person_id=person.id,
        license_number=lic.get("number"),
        license_region=lic.get("region"),
        license_expiry=license_expiry_date,
    )
    db.add(driver_profile)

    # Mark approved + review payload with person_id (source of truth)
    app.status = DriverOnboardingStatus.APPROVED.value
    p = app.intake_payload or {}
    p["review"] = {
        "reviewed_at": _utcnow().isoformat(),
        "reviewed_by_user_id": current_user.member_id,
        "person_id": person.id,
    }
    app.intake_payload = p

    # Invalidate invite-link tokens immediately (no reuse after approval)
    await db.execute(
        delete(ApplicationAccessToken).where(
            ApplicationAccessToken.tenant_id == tenant_id,
            ApplicationAccessToken.application_id == app.id,
        )
    )

    await db.commit()
    await db.refresh(app)
    await db.refresh(person)

    return {
        "submission": _serialize_application(app),
        "person": PersonOut.model_validate(person),
    }


@router.post("/submissions/{submission_id}/reject", response_model=DriverOnboardingSubmissionOut)
async def reject_submission(
    submission_id: int,
    payload: DriverOnboardingRejectRequest,
    tenant_id: int = Depends(require_tenant),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    if not _is_admin(current_user):
        raise HTTPException(status_code=403, detail="Admin role required")
    app = await _get_submission(db, tenant_id, submission_id)
    if app.status != DriverOnboardingStatus.SUBMITTED.value:
        raise HTTPException(status_code=409, detail="Submission is not in SUBMITTED status")

    app.status = DriverOnboardingStatus.REJECTED.value
    p = app.intake_payload or {}
    p["review"] = {
        "reviewed_at": _utcnow().isoformat(),
        "reviewed_by_user_id": current_user.member_id,
        "rejection_reason": payload.rejection_reason,
    }
    app.intake_payload = p

    # Invalidate invite-link tokens immediately (no reuse after rejection)
    await db.execute(
        delete(ApplicationAccessToken).where(
            ApplicationAccessToken.tenant_id == tenant_id,
            ApplicationAccessToken.application_id == app.id,
        )
    )

    await db.commit()
    await db.refresh(app)
    return _serialize_application(app)


class ResendInviteResponse(BaseModel):
    email_sent: bool
    email_error: str | None = None


@router.post("/submissions/{submission_id}/resend-invite", response_model=ResendInviteResponse)
async def resend_invite(
    submission_id: int,
    request: Request,
    tenant_id: int = Depends(require_tenant),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    """Resend the onboarding invite link email to the applicant. Admin only."""
    if not _is_admin(current_user):
        raise HTTPException(status_code=403, detail="Admin role required")
    app = await _get_submission(db, tenant_id, submission_id)
    email = (app.email or "").strip()
    if not email:
        raise HTTPException(status_code=400, detail="Application has no email to send to.")

    # Get existing valid token or create one
    token_row = await db.scalar(
        select(ApplicationAccessToken).where(
            ApplicationAccessToken.tenant_id == tenant_id,
            ApplicationAccessToken.application_id == app.id,
            ApplicationAccessToken.expires_at > _utcnow(),
        ).order_by(ApplicationAccessToken.expires_at.desc()).limit(1)
    )
    if not token_row:
        token = secrets.token_urlsafe(32)
        expires_at = datetime.now(timezone.utc) + timedelta(days=60)
        token_row = ApplicationAccessToken(
            tenant_id=tenant_id,
            application_id=app.id,
            token=token,
            expires_at=expires_at,
        )
        db.add(token_row)
        await db.commit()
    else:
        token = token_row.token

    base = str(request.base_url).rstrip("/")
    link = f"{base}/onboarding?token={token}"
    email_sent = False
    email_error: str | None = None
    try:
        await send_onboarding_invite_email(to=email, invite_link=link)
        email_sent = True
    except Exception as exc:
        logger.exception("Resend invite email failed to %s: %s", email, exc)
        email_error = "Could not send email. Check SMTP configuration. See server logs for details."
    return ResendInviteResponse(email_sent=email_sent, email_error=email_error)


@router.delete("/submissions/{submission_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_submission(
    submission_id: int,
    tenant_id: int = Depends(require_tenant),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    """Delete one submission (any status). Admin only. Cascades to tokens, requests, files."""
    if not _is_admin(current_user):
        raise HTTPException(status_code=403, detail="Admin role required")
    app = await _get_submission(db, tenant_id, submission_id)
    await db.delete(app)
    await db.commit()


class DeleteDraftsResponse(BaseModel):
    deleted: int


@router.delete("/submissions/drafts", response_model=DeleteDraftsResponse)
async def delete_draft_and_in_progress_submissions(
    tenant_id: int = Depends(require_tenant),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    """Delete all DRAFT and IN_PROGRESS person_applications for this tenant. Cascades to tokens, requests, files."""
    if not _is_admin(current_user):
        raise HTTPException(status_code=403, detail="Admin role required")
    stmt = delete(PersonApplication).where(
        PersonApplication.tenant_id == tenant_id,
        PersonApplication.status.in_([DriverOnboardingStatus.DRAFT.value, DriverOnboardingStatus.IN_PROGRESS.value]),
    )
    result = await db.execute(stmt)
    await db.commit()
    return DeleteDraftsResponse(deleted=result.rowcount or 0)
