from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps.auth import CurrentUser, get_current_user
from app.deps.tenant import require_tenant
from app.deps.tenant_db import get_tenant_db
from app.models.driver import Driver
from app.models.driver_onboarding_submission import DriverOnboardingSubmission
from app.schemas.driver import DriverOut
from app.schemas.driver_onboarding import (
    DriverOnboardingApproveResponse,
    DriverOnboardingCreateResponse,
    DriverOnboardingRejectRequest,
    DriverOnboardingSubmissionCreate,
    DriverOnboardingSubmissionOut,
    DriverOnboardingStatus,
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
    submission = DriverOnboardingSubmission(
        tenant_id=tenant_id,
        created_by_user_id=current_user.member_id,
        status=DriverOnboardingStatus.SUBMITTED.value if submitted else DriverOnboardingStatus.DRAFT.value,
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
    submission = await db.scalar(
        select(DriverOnboardingSubmission)
        .where(
            DriverOnboardingSubmission.tenant_id == tenant_id,
            DriverOnboardingSubmission.created_by_user_id == current_user.member_id,
        )
        .order_by(DriverOnboardingSubmission.created_at.desc())
        .limit(1)
    )
    return submission


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

    driver = Driver(
        tenant_id=tenant_id,
        first_name=submission.first_name,
        last_name=submission.last_name,
        email=submission.email,
        phone=submission.phone,
        license_number=submission.driver_license_number,
        license_expiry_date=submission.license_expiry,
        issuing_region=submission.license_region,
        is_active=True,
    )
    db.add(driver)

    submission.status = DriverOnboardingStatus.APPROVED.value
    submission.reviewed_at = _utcnow()
    submission.reviewed_by_user_id = current_user.member_id
    await db.commit()
    await db.refresh(submission)
    await db.refresh(driver)
    return {"submission": submission, "driver": DriverOut.model_validate(driver)}


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
