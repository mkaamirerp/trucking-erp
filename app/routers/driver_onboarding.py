from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps.auth import CurrentUser, get_current_user
from app.deps.tenant import require_tenant
from app.deps.tenant_db import get_tenant_db
from app.models.driver_onboarding_submission import DriverOnboardingSubmission
from app.models.person import Person, PersonRole, DriverProfile
from app.schemas.driver_onboarding import (
    DriverOnboardingApproveResponse,
    DriverOnboardingCreateResponse,
    DriverOnboardingRejectRequest,
    DriverOnboardingSubmissionCreate,
    DriverOnboardingSubmissionOut,
    DriverOnboardingStatus,
    PersonOut,
)

router = APIRouter(prefix="/api/v1/driver-onboarding", tags=["driver-onboarding"])


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _is_admin(user: CurrentUser) -> bool:
    role = (user.role or "").upper()
    return role in {"OWNER", "ADMIN", "TENANT_ADMIN"}


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


@router.post("/submissions", response_model=DriverOnboardingCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_submission(
    payload: DriverOnboardingSubmissionCreate,
    tenant_id: int = Depends(require_tenant),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    if current_user.member_id is None:
        raise HTTPException(status_code=403, detail="User membership not found")

    data = payload.model_dump(exclude={"submit"})
    submitted = bool(payload.submit)
    onboarding_status = DriverOnboardingStatus.SUBMITTED.value if submitted else DriverOnboardingStatus.DRAFT.value

    # Draft/Submit: create or update Person + DriverProfile + PersonRole(role_code=DRIVER, is_active=False)
    existing = await _get_my_latest_submission(db, tenant_id, current_user.member_id)
    if (
        existing
        and existing.status == DriverOnboardingStatus.DRAFT.value
        and existing.person_id is not None
    ):
        # Update existing person, driver_profile, person_role, submission
        person = await db.get(Person, existing.person_id)
        if person and person.tenant_id == tenant_id:
            for k, v in _payload_to_people_fields(data).items():
                setattr(person, k, v)
            # Status lives on submission; people table has no onboarding_status in foundation schema
            # Update driver_profile
            dp_stmt = select(DriverProfile).where(
                DriverProfile.person_id == person.id,
                DriverProfile.tenant_id == tenant_id,
            )
            dp = await db.scalar(dp_stmt)
            if dp:
                dp.license_number = data.get("driver_license_number")
                dp.license_region = data.get("license_region")
                dp.license_expiry = data.get("license_expiry")
            # PersonRole stays role_code=DRIVER, is_active=False until approve
            existing.status = onboarding_status
            existing.submitted_at = _utcnow() if submitted else None
            for k, v in data.items():
                if hasattr(existing, k):
                    setattr(existing, k, v)
            await db.commit()
            await db.refresh(existing)
            return {"submission": existing, "missing_required_documents": []}

    # Create new Person + PersonRole(role_code=DRIVER, is_active=False) + DriverProfile + Submission
    person = Person(
        tenant_id=tenant_id,
        **_payload_to_people_fields(data),
    )
    db.add(person)
    await db.flush()

    person_role = PersonRole(
        tenant_id=tenant_id,
        person_id=person.id,
        role_code="DRIVER",
        is_active=False,
    )
    db.add(person_role)

    driver_profile = DriverProfile(
        tenant_id=tenant_id,
        person_id=person.id,
        license_number=data.get("driver_license_number"),
        license_region=data.get("license_region"),
        license_expiry=data.get("license_expiry"),
    )
    db.add(driver_profile)
    await db.flush()

    submission = DriverOnboardingSubmission(
        tenant_id=tenant_id,
        created_by_user_id=current_user.member_id,
        person_id=person.id,
        status=onboarding_status,
        submitted_at=_utcnow() if submitted else None,
        **data,
    )
    db.add(submission)
    await db.commit()
    await db.refresh(submission)
    return {"submission": submission, "missing_required_documents": []}


@router.get("/submissions/me", response_model=DriverOnboardingSubmissionOut | None)
async def get_my_latest_submission(
    tenant_id: int = Depends(require_tenant),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    if current_user.member_id is None:
        return None
    return await _get_my_latest_submission(db, tenant_id, current_user.member_id)


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
    if not _is_admin(current_user):
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
    if not _is_admin(current_user):
        raise HTTPException(status_code=403, detail="Admin role required")
    submission = await _get_submission(db, tenant_id, submission_id)
    if submission.status != DriverOnboardingStatus.SUBMITTED.value:
        raise HTTPException(status_code=409, detail="Submission is not in SUBMITTED status")

    # People-first: approve = set person_roles.is_active=True for DRIVER (no write to drivers)
    person = None
    if submission.person_id is not None:
        person = await db.get(Person, submission.person_id)
        if person and person.tenant_id == tenant_id:
            role_stmt = select(PersonRole).where(
                PersonRole.person_id == person.id,
                PersonRole.tenant_id == tenant_id,
                PersonRole.role_code == "DRIVER",
            )
            role_result = await db.execute(role_stmt)
            for pr in role_result.scalars().all():
                pr.is_active = True
    if person is None:
        raise HTTPException(status_code=409, detail="Submission has no linked person; cannot approve")

    submission.status = DriverOnboardingStatus.APPROVED.value
    submission.reviewed_at = _utcnow()
    submission.reviewed_by_user_id = current_user.member_id
    await db.commit()
    await db.refresh(submission)
    await db.refresh(person)
    return {"submission": submission, "person": PersonOut.model_validate(person)}


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
    submission = await _get_submission(db, tenant_id, submission_id)
    if submission.status != DriverOnboardingStatus.SUBMITTED.value:
        raise HTTPException(status_code=409, detail="Submission is not in SUBMITTED status")

    submission.status = DriverOnboardingStatus.REJECTED.value
    submission.rejection_reason = payload.rejection_reason
    submission.reviewed_at = _utcnow()
    submission.reviewed_by_user_id = current_user.member_id
    await db.commit()
    await db.refresh(submission)
    return submission
