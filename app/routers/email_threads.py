from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps.auth import get_current_user
from app.deps.entitlements import require_entitlement
from app.deps.tenant import require_tenant
from app.deps.tenant_db import get_tenant_db
from app.schemas.email_threads import (
    EmailMessageOut,
    EmailThreadActionLoadOut,
    EmailThreadDraftOrLinkResponse,
    EmailThreadLinkLoadBody,
    EmailThreadListResponse,
    EmailThreadOut,
)
from app.services import email_threads as email_threads_service

router = APIRouter(
    prefix="/email-threads",
    tags=["email_threads"],
    dependencies=[Depends(require_entitlement("email_inbox"))],
)


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
    return [EmailMessageOut.model_validate(m) for m in messages]


@router.post("/{thread_id}/disregard", response_model=EmailThreadOut)
async def disregard_email_thread(
    thread_id: int,
    tenant_id: int = Depends(require_tenant),
    _user=Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    return await email_threads_service.disregard_thread(db, tenant_id=tenant_id, thread_id=thread_id)
