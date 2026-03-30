from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps.auth import get_current_user
from app.deps.entitlements import require_entitlement
from app.deps.tenant import require_tenant
from app.deps.tenant_db import get_tenant_db
from app.models.tenant_email_account import TenantEmailAccount
from app.schemas.email_threads import (
    EmailAttachmentOut,
    EmailMessageOut,
    EmailThreadActionLoadOut,
    EmailThreadDraftOrLinkResponse,
    EmailThreadLinkLoadBody,
    EmailThreadListResponse,
    EmailThreadOut,
)
from app.services import email_threads as email_threads_service
from app.services.email_ingestion_gmail import sync_gmail_inbox_for_tenant

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
            pass
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


@router.post("/{thread_id}/disregard", response_model=EmailThreadOut)
async def disregard_email_thread(
    thread_id: int,
    tenant_id: int = Depends(require_tenant),
    _user=Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    return await email_threads_service.disregard_thread(db, tenant_id=tenant_id, thread_id=thread_id)
