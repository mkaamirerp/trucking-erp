from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps.auth import CurrentUser, get_current_user
from app.deps.entitlements import require_entitlement
from app.deps.tenant import require_tenant, require_tenant_slug
from app.deps.tenant_db import get_tenant_db
from app.constants.email_intake_review_reason_codes import (
    IntakeReviewDismissReasonWrite,
    IntakeReviewDuplicateDismissBody,
    IntakeReviewReopenReasonWrite,
    IntakeReviewResolveReasonWrite,
)
from app.models.tenant_email_account import TenantEmailAccount
from app.schemas.email_intake_review import (
    DuplicateConfirmBody,
    DuplicateLinkPriorBody,
    EmailIntakeReviewBundleOut,
    EmailIntakeReviewEventOut,
    EmailIntakeReviewOut,
)
from app.schemas.email_threads import (
    EmailAttachmentOut,
    EmailIntakeQrExtractionOut,
    EmailMessageOut,
    EmailThreadActionLoadOut,
    EmailThreadDraftOrLinkResponse,
    EmailThreadLinkLoadBody,
    EmailThreadListResponse,
    EmailThreadOut,
)
from app.services.email_intake_qr_extractions import list_intake_qr_by_thread
from app.services import email_threads as email_threads_service
from app.services import email_intake_review_service as intake_review_svc
from app.services.email_ingestion_gmail import sync_gmail_inbox_for_tenant

logger = logging.getLogger(__name__)


def _review_workflow_error(exc: ValueError) -> HTTPException:
    code = str(exc)
    if code == "no_review":
        return HTTPException(status.HTTP_404_NOT_FOUND, detail="No intake review exists for this thread")
    if code == "not_duplicate_review":
        return HTTPException(status.HTTP_400_BAD_REQUEST, detail=code)
    if code in (
        "already_resolved",
        "already_dismissed",
        "claimed_by_other",
        "not_closed",
        "resolved_use_reopen_first",
        "invalid_state_for_dismiss",
        "invalid_state_for_duplicate_action",
        "thread_not_linked_to_load",
        "linked_load_neq_suggested_prior",
        "prior_load_id_mismatch",
    ):
        return HTTPException(status.HTTP_409_CONFLICT, detail=code)
    if code == "prior_load_id_required":
        return HTTPException(status.HTTP_400_BAD_REQUEST, detail=code)
    if code == "no_thread":
        return HTTPException(status.HTTP_404_NOT_FOUND, detail=code)
    return HTTPException(status.HTTP_400_BAD_REQUEST, detail=code)


router = APIRouter(
    prefix="/email-threads",
    tags=["email_threads"],
    dependencies=[Depends(require_entitlement("email_inbox"))],
)


@router.post("/gmail/pull-delta")
async def gmail_pull_delta_from_inbox(
    tenant_id: int = Depends(require_tenant),
    _user=Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
    max_threads: int = 30,
):
    """
    Operator fallback: run the same Gmail History (delta) sync as Pub/Sub push.
    Production ingestion must not depend on this endpoint; use when push is delayed or debugging.
    """
    if max_threads < 1 or max_threads > 200:
        raise HTTPException(status_code=400, detail="max_threads must be between 1 and 200")
    try:
        result = await sync_gmail_inbox_for_tenant(db, tenant_id=tenant_id, max_threads=max_threads)
        acc_row = await db.scalar(
            select(TenantEmailAccount)
            .where(TenantEmailAccount.tenant_id == tenant_id, TenantEmailAccount.provider == "gmail")
            .limit(1)
        )
        last_sync = acc_row.last_sync_at.isoformat() if acc_row and acc_row.last_sync_at else None
        return {
            "ok": True,
            "tenant_id": result.tenant_id,
            "provider": result.provider,
            "threads_scanned": result.threads_scanned,
            "threads_upserted": result.threads_upserted,
            "messages_upserted": result.messages_upserted,
            "attachments_upserted": result.attachments_upserted,
            "history_pages": result.history_pages,
            "last_sync_at": last_sync,
        }
    except Exception as e:
        try:
            acc = await db.scalar(
                select(TenantEmailAccount)
                .where(TenantEmailAccount.tenant_id == tenant_id, TenantEmailAccount.provider == "gmail")
                .limit(1)
            )
            if acc:
                acc.last_error = f"sync_failed: {(str(e) or 'unknown error')[:240]}"
                await db.commit()
        except Exception:
            logger.warning(
                "gmail_pull_delta: could not persist TenantEmailAccount.last_error after sync failure "
                "(tenant_id=%s, sync_error=%r)",
                tenant_id,
                e,
                exc_info=True,
            )
        raise HTTPException(status_code=502, detail="Gmail sync failed") from e


@router.get("", response_model=EmailThreadListResponse)
async def list_email_threads(
    tenant_id: int = Depends(require_tenant),
    _user=Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
    status: str | None = Query(None),
    provider: str | None = Query(None),
    intake_bucket: str | None = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(25, ge=1, le=200),
):
    paged = await email_threads_service.list_email_threads(
        db,
        tenant_id=tenant_id,
        status_filter=status,
        provider=provider,
        intake_bucket=intake_bucket,
        page=page,
        size=size,
    )
    return paged


@router.post("/{thread_id}/create-draft-load", response_model=EmailThreadDraftOrLinkResponse)
async def create_draft_load_from_email_thread(
    thread_id: int,
    tenant_id: int = Depends(require_tenant),
    _user=Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    thread_out, load = await email_threads_service.create_draft_load_from_review_thread(
        db, tenant_id=tenant_id, thread_id=thread_id
    )
    return EmailThreadDraftOrLinkResponse(
        thread=thread_out,
        load=EmailThreadActionLoadOut(id=load.id, load_number=load.load_number, status=load.status),
    )


@router.post("/{thread_id}/link-load", response_model=EmailThreadDraftOrLinkResponse)
async def link_load_to_email_thread(
    thread_id: int,
    body: EmailThreadLinkLoadBody,
    tenant_id: int = Depends(require_tenant),
    _user=Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    thread_out, load = await email_threads_service.link_existing_load_from_review_thread(
        db, tenant_id=tenant_id, thread_id=thread_id, load_id=body.load_id
    )
    return EmailThreadDraftOrLinkResponse(
        thread=thread_out,
        load=EmailThreadActionLoadOut(id=load.id, load_number=load.load_number, status=load.status),
    )


@router.get("/{thread_id}", response_model=EmailThreadOut)
async def get_email_thread_detail(
    thread_id: int,
    tenant_id: int = Depends(require_tenant),
    _user=Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    return await email_threads_service.get_email_thread_out(db, tenant_id=tenant_id, thread_id=thread_id)


@router.get("/{thread_id}/intake-qr-extractions", response_model=list[EmailIntakeQrExtractionOut])
async def list_email_thread_intake_qr_extractions(
    thread_id: int,
    tenant_id: int = Depends(require_tenant),
    _user=Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    """Supplemental read: structured QR payloads persisted for this thread (intake audit / matching)."""
    await email_threads_service.get_email_thread(db, tenant_id=tenant_id, thread_id=thread_id)
    rows = await list_intake_qr_by_thread(db, tenant_id=tenant_id, thread_id=thread_id)
    return [EmailIntakeQrExtractionOut.model_validate(r) for r in rows]


@router.get("/{thread_id}/messages", response_model=list[EmailMessageOut])
async def list_email_thread_messages(
    thread_id: int,
    tenant_id: int = Depends(require_tenant),
    _user=Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    messages = await email_threads_service.list_thread_messages(db, tenant_id=tenant_id, thread_id=thread_id)
    mids = [m.id for m in messages]
    att_map = await email_threads_service.map_message_attachments(db, tenant_id=tenant_id, message_ids=mids)
    out: list[EmailMessageOut] = []
    for m in messages:
        atts = [EmailAttachmentOut.model_validate(a) for a in att_map.get(m.id, [])]
        d = EmailMessageOut.model_validate(m)
        out.append(d.model_copy(update={"attachments": atts}))
    return out


@router.post("/{thread_id}/recompute-intake", response_model=EmailThreadOut)
async def recompute_email_thread_intake(
    thread_id: int,
    tenant_id: int = Depends(require_tenant),
    _user=Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    """Re-apply Gmail intake routing (e.g. TQL heuristics) without waiting for a new sync event."""
    return await email_threads_service.recompute_gmail_intake_for_thread(db, tenant_id=tenant_id, thread_id=thread_id)


@router.post("/{thread_id}/upload-pdf", response_model=EmailThreadOut)
async def upload_pdf_to_email_thread(
    thread_id: int,
    file: UploadFile = File(...),
    tenant_id: int = Depends(require_tenant),
    tenant_slug: str = Depends(require_tenant_slug),
    _user=Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    """Attach a PDF from the intake UI; stored in tenant object storage and included in TQL PDF intake."""
    return await email_threads_service.upload_pdf_to_intake_thread(
        db,
        tenant_id=tenant_id,
        tenant_slug=tenant_slug,
        thread_id=thread_id,
        file=file,
    )


@router.post("/{thread_id}/disregard", response_model=EmailThreadOut)
async def disregard_email_thread(
    thread_id: int,
    tenant_id: int = Depends(require_tenant),
    _user=Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    return await email_threads_service.disregard_thread(db, tenant_id=tenant_id, thread_id=thread_id)


@router.get("/{thread_id}/intake-review", response_model=EmailIntakeReviewBundleOut)
async def get_email_thread_intake_review(
    thread_id: int,
    tenant_id: int = Depends(require_tenant),
    _user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    await email_threads_service.get_email_thread(db, tenant_id=tenant_id, thread_id=thread_id)
    rev, evs = await intake_review_svc.get_review_with_events(db, tenant_id, thread_id)
    if not rev:
        return EmailIntakeReviewBundleOut(review=None, events=[])
    return EmailIntakeReviewBundleOut(
        review=EmailIntakeReviewOut.model_validate(rev),
        events=[EmailIntakeReviewEventOut.model_validate(e) for e in evs],
    )


@router.post("/{thread_id}/intake-review/claim", response_model=EmailIntakeReviewOut)
async def claim_email_thread_intake_review(
    thread_id: int,
    tenant_id: int = Depends(require_tenant),
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    if not user.tenant_user:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="Claim requires tenant-user (workspace credentials) session",
        )
    await email_threads_service.get_email_thread(db, tenant_id=tenant_id, thread_id=thread_id)
    try:
        rev = await intake_review_svc.claim_email_intake_review(
            db,
            tenant_id,
            thread_id,
            user,
            tenant_user_id=int(user.tenant_user.id),
        )
        await db.commit()
        await db.refresh(rev)
        return EmailIntakeReviewOut.model_validate(rev)
    except ValueError as e:
        raise _review_workflow_error(e) from e


@router.post("/{thread_id}/intake-review/resolve", response_model=EmailIntakeReviewOut)
async def resolve_email_thread_intake_review(
    thread_id: int,
    body: IntakeReviewResolveReasonWrite,
    tenant_id: int = Depends(require_tenant),
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    await email_threads_service.get_email_thread(db, tenant_id=tenant_id, thread_id=thread_id)
    try:
        rev = await intake_review_svc.resolve_email_intake_review(
            db,
            tenant_id,
            thread_id,
            user,
            reason_code=body.reason_code,
            note=body.note,
        )
        await db.commit()
        await db.refresh(rev)
        return EmailIntakeReviewOut.model_validate(rev)
    except ValueError as e:
        raise _review_workflow_error(e) from e


@router.post("/{thread_id}/intake-review/dismiss", response_model=EmailIntakeReviewOut)
async def dismiss_email_thread_intake_review(
    thread_id: int,
    body: IntakeReviewDismissReasonWrite,
    tenant_id: int = Depends(require_tenant),
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    await email_threads_service.get_email_thread(db, tenant_id=tenant_id, thread_id=thread_id)
    try:
        rev = await intake_review_svc.dismiss_email_intake_review(
            db,
            tenant_id,
            thread_id,
            user,
            reason_code=body.reason_code,
            note=body.note,
        )
        await db.commit()
        await db.refresh(rev)
        return EmailIntakeReviewOut.model_validate(rev)
    except ValueError as e:
        raise _review_workflow_error(e) from e


@router.post("/{thread_id}/intake-review/duplicate/link-prior", response_model=EmailThreadDraftOrLinkResponse)
async def duplicate_intake_review_link_prior(
    thread_id: int,
    body: DuplicateLinkPriorBody,
    tenant_id: int = Depends(require_tenant),
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    await email_threads_service.get_email_thread(db, tenant_id=tenant_id, thread_id=thread_id)
    try:
        _rev, load_id = await intake_review_svc.duplicate_review_prepare_link_prior(
            db,
            tenant_id,
            thread_id,
            user,
            prior_load_id=body.prior_load_id,
        )
        thread_out, load = await email_threads_service.link_existing_load_from_review_thread(
            db, tenant_id=tenant_id, thread_id=thread_id, load_id=load_id
        )
        await db.commit()
        await db.refresh(load)
        return EmailThreadDraftOrLinkResponse(
            thread=thread_out,
            load=EmailThreadActionLoadOut(id=load.id, load_number=load.load_number, status=load.status),
        )
    except ValueError as e:
        raise _review_workflow_error(e) from e


@router.post("/{thread_id}/intake-review/duplicate/confirm", response_model=EmailIntakeReviewOut)
async def duplicate_intake_review_confirm(
    thread_id: int,
    body: DuplicateConfirmBody,
    tenant_id: int = Depends(require_tenant),
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    await email_threads_service.get_email_thread(db, tenant_id=tenant_id, thread_id=thread_id)
    try:
        rev = await intake_review_svc.duplicate_review_confirm(
            db,
            tenant_id,
            thread_id,
            user,
            note=body.note,
        )
        await db.commit()
        await db.refresh(rev)
        return EmailIntakeReviewOut.model_validate(rev)
    except ValueError as e:
        raise _review_workflow_error(e) from e


@router.post("/{thread_id}/intake-review/duplicate/dismiss-false-positive", response_model=EmailIntakeReviewOut)
async def duplicate_intake_review_dismiss_false_positive(
    thread_id: int,
    body: IntakeReviewDuplicateDismissBody,
    tenant_id: int = Depends(require_tenant),
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    await email_threads_service.get_email_thread(db, tenant_id=tenant_id, thread_id=thread_id)
    try:
        rev = await intake_review_svc.duplicate_review_dismiss_false_positive(
            db,
            tenant_id,
            thread_id,
            user,
            note=body.note,
        )
        await db.commit()
        await db.refresh(rev)
        return EmailIntakeReviewOut.model_validate(rev)
    except ValueError as e:
        raise _review_workflow_error(e) from e


@router.post("/{thread_id}/intake-review/reopen", response_model=EmailIntakeReviewOut)
async def reopen_email_thread_intake_review(
    thread_id: int,
    body: IntakeReviewReopenReasonWrite,
    tenant_id: int = Depends(require_tenant),
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    await email_threads_service.get_email_thread(db, tenant_id=tenant_id, thread_id=thread_id)
    try:
        rev = await intake_review_svc.reopen_email_intake_review(
            db,
            tenant_id,
            thread_id,
            user,
            reason_code=body.reason_code,
            note=body.note,
        )
        await db.commit()
        await db.refresh(rev)
        return EmailIntakeReviewOut.model_validate(rev)
    except ValueError as e:
        raise _review_workflow_error(e) from e
