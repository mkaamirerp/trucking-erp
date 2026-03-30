"""Tenant-safe read queries for email threads and messages."""

from __future__ import annotations

import uuid

from fastapi import HTTPException, status
from sqlalchemy import case, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.email_attachment import EmailMessageAttachment
from app.models.email_ingestion import EmailMessage, EmailThread
from app.models.tenant_email_account import TenantEmailAccount
from app.models.load import Load
from app.schemas.email_threads import EmailThreadOut, email_thread_to_out
from app.services.email_intake_pdf import guess_broker_load_reference
from app.services.email_intake_routing import (
    _resolve_tql_broker,
    apply_intake_routing_for_gmail_thread,
    thread_indicates_tql_affinity,
)
from app.services.gmail_oauth import refresh_access_token
from app.utils.encryption import decrypt_secret
from app.utils.pagination import paginate


def _require_thread_eligible_for_manual_intake(thread: EmailThread) -> None:
    if thread.status != "active":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Thread is not active")
    if thread.intake_bucket not in ("needs_review", "background"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Thread must be in needs_review or background intake bucket for this action",
        )
    if thread.linked_load_id is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Thread already has a linked load",
        )


async def _allocate_intake_style_load_number(db: AsyncSession, tenant_id: int) -> str:
    for _ in range(16):
        candidate = f"INT-{uuid.uuid4().hex[:12].upper()}"
        taken = await db.scalar(
            select(Load.id).where(Load.tenant_id == tenant_id, Load.load_number == candidate).limit(1)
        )
        if taken is None:
            return candidate
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Could not allocate a unique intake load number",
    )


async def _latest_inbound_message_body_excerpt(
    db: AsyncSession, tenant_id: int, thread_id: int, max_chars: int = 2000
) -> str:
    row = (
        await db.execute(
            select(EmailMessage.body_text)
            .where(EmailMessage.tenant_id == tenant_id, EmailMessage.thread_id == thread_id)
            .order_by(
                case((EmailMessage.received_at.is_(None), 1), else_=0).asc(),
                EmailMessage.received_at.desc(),
                case((EmailMessage.sent_at.is_(None), 1), else_=0).asc(),
                EmailMessage.sent_at.desc(),
                EmailMessage.id.desc(),
            )
            .limit(1)
        )
    ).first()
    if not row or not row[0]:
        return ""
    text = str(row[0]).strip()
    return text[:max_chars] if len(text) > max_chars else text


def _compose_internal_notes_from_thread(thread: EmailThread, body_excerpt: str) -> str | None:
    parts: list[str] = []
    if thread.subject:
        parts.append(f"Subject: {thread.subject}")
    if thread.snippet:
        parts.append(f"Snippet: {thread.snippet}")
    if body_excerpt:
        parts.append(f"Latest message excerpt:\n{body_excerpt}")
    if not parts:
        return None
    joined = "\n\n".join(parts)
    return joined[:4000] if len(joined) > 4000 else joined


async def _loads_by_ids(db: AsyncSession, tenant_id: int, ids: list[int]) -> dict[int, Load]:
    if not ids:
        return {}
    result = await db.execute(
        select(Load)
        .options(selectinload(Load.stops))
        .where(Load.tenant_id == tenant_id, Load.id.in_(ids))
    )
    return {row.id: row for row in result.scalars().all()}


async def get_email_thread(db: AsyncSession, tenant_id: int, thread_id: int) -> EmailThread:
    thread = await db.scalar(
        select(EmailThread).where(
            EmailThread.id == thread_id,
            EmailThread.tenant_id == tenant_id,
        )
    )
    if not thread:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Email thread not found")
    return thread


async def create_draft_load_from_review_thread(
    db: AsyncSession, tenant_id: int, thread_id: int
) -> tuple[EmailThreadOut, Load]:
    thread = await get_email_thread(db, tenant_id, thread_id)
    _require_thread_eligible_for_manual_intake(thread)

    broker_id: int | None = None
    broker_name_snapshot: str | None = None
    if thread_indicates_tql_affinity(thread):
        bid, snap = await _resolve_tql_broker(db, tenant_id)
        broker_id = bid
        broker_name_snapshot = snap

    ref = guess_broker_load_reference(f"{thread.subject or ''}\n{thread.snippet or ''}")
    body_excerpt = await _latest_inbound_message_body_excerpt(db, tenant_id, thread.id)
    notes = _compose_internal_notes_from_thread(thread, body_excerpt)

    load_number = await _allocate_intake_style_load_number(db, tenant_id)
    load = Load(
        tenant_id=tenant_id,
        load_number=load_number,
        broker_id=broker_id,
        broker_name_snapshot=broker_name_snapshot,
        broker_load_reference=ref,
        status="draft",
        internal_notes=notes,
    )
    db.add(load)
    await db.flush()

    thread.linked_load_id = load.id
    thread.intake_bucket = "linked"
    thread.routing_reason = "manual_create_draft_from_review"

    await db.commit()
    await db.refresh(thread)
    await db.refresh(load)

    loads_map = await _loads_by_ids(db, tenant_id, [load.id])
    linked = loads_map.get(load.id) or load
    return email_thread_to_out(thread, linked_load=linked), linked


async def link_existing_load_from_review_thread(
    db: AsyncSession, tenant_id: int, thread_id: int, load_id: int
) -> tuple[EmailThreadOut, Load]:
    thread = await get_email_thread(db, tenant_id, thread_id)
    _require_thread_eligible_for_manual_intake(thread)

    loads_map = await _loads_by_ids(db, tenant_id, [load_id])
    load = loads_map.get(load_id)
    if not load:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Load not found")

    thread.linked_load_id = load.id
    thread.intake_bucket = "linked"
    thread.routing_reason = "manual_link_existing_load"

    await db.commit()
    await db.refresh(thread)

    loads_map2 = await _loads_by_ids(db, tenant_id, [load.id])
    linked = loads_map2.get(load.id) or load
    return email_thread_to_out(thread, linked_load=linked), linked


async def list_email_threads(
    db: AsyncSession,
    tenant_id: int,
    *,
    status_filter: str | None = None,
    provider: str | None = None,
    intake_bucket: str | None = None,
    page: int = 1,
    size: int = 25,
) -> dict:
    stmt = select(EmailThread).where(EmailThread.tenant_id == tenant_id)

    if status_filter:
        stmt = stmt.where(EmailThread.status == status_filter)
    else:
        # Intake default: show active queue unless caller explicitly asks for other status.
        stmt = stmt.where(EmailThread.status == "active")
    if provider:
        stmt = stmt.where(EmailThread.provider == provider)
    if intake_bucket:
        stmt = stmt.where(EmailThread.intake_bucket == intake_bucket)
    stmt = stmt.order_by(
        case((EmailThread.last_message_at.is_(None), 1), else_=0).asc(),
        EmailThread.last_message_at.desc(),
        EmailThread.created_at.desc(),
    )
    paged = await paginate(db, stmt, page=page, size=size)
    threads: list[EmailThread] = paged["items"]
    load_ids = list({t.linked_load_id for t in threads if t.linked_load_id})
    loads_map = await _loads_by_ids(db, tenant_id, load_ids)
    paged["items"] = [
        email_thread_to_out(t, linked_load=loads_map.get(t.linked_load_id)) for t in threads
    ]
    return paged


async def get_email_thread_out(db: AsyncSession, tenant_id: int, thread_id: int) -> EmailThreadOut:
    thread = await get_email_thread(db, tenant_id, thread_id)
    load = None
    if thread.linked_load_id:
        loads = await _loads_by_ids(db, tenant_id, [thread.linked_load_id])
        load = loads.get(thread.linked_load_id)
    return email_thread_to_out(thread, linked_load=load)


async def list_thread_messages(db: AsyncSession, tenant_id: int, thread_id: int) -> list[EmailMessage]:
    # Ensure thread exists in current tenant; cross-tenant and missing both return 404.
    await get_email_thread(db, tenant_id, thread_id)
    result = await db.execute(
        select(EmailMessage)
        .where(
            EmailMessage.tenant_id == tenant_id,
            EmailMessage.thread_id == thread_id,
        )
        .order_by(
            case((EmailMessage.received_at.is_(None), 1), else_=0).asc(),
            EmailMessage.received_at.asc(),
            case((EmailMessage.sent_at.is_(None), 1), else_=0).asc(),
            EmailMessage.sent_at.asc(),
            EmailMessage.created_at.asc(),
        )
    )
    return list(result.scalars().all())


async def map_message_attachments(
    db: AsyncSession, tenant_id: int, message_ids: list[int]
) -> dict[int, list[EmailMessageAttachment]]:
    if not message_ids:
        return {}
    result = await db.execute(
        select(EmailMessageAttachment).where(
            EmailMessageAttachment.tenant_id == tenant_id,
            EmailMessageAttachment.message_id.in_(message_ids),
        )
    )
    rows = list(result.scalars().all())
    out: dict[int, list[EmailMessageAttachment]] = {}
    for r in rows:
        out.setdefault(r.message_id, []).append(r)
    return out


async def recompute_gmail_intake_for_thread(db: AsyncSession, tenant_id: int, thread_id: int) -> EmailThreadOut:
    """Re-run apply_intake_routing_for_gmail_thread (e.g. after tightening TQL heuristics). Gmail only."""
    thread = await get_email_thread(db, tenant_id, thread_id)
    if thread.provider != "gmail":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only Gmail threads support intake recompute")
    acc = await db.scalar(
        select(TenantEmailAccount)
        .where(TenantEmailAccount.tenant_id == tenant_id, TenantEmailAccount.provider == "gmail")
        .limit(1)
    )
    if not acc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No Gmail account connected for this tenant",
        )
    refresh_token = decrypt_secret(acc.refresh_token_encrypted).decode("utf-8")
    tok = await refresh_access_token(refresh_token)
    access_token = tok.get("access_token")
    if not access_token:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Could not refresh Gmail access token")
    await apply_intake_routing_for_gmail_thread(db, tenant_id, thread_id, access_token)
    await db.commit()
    await db.refresh(thread)
    return await get_email_thread_out(db, tenant_id, thread_id)


async def disregard_thread(db: AsyncSession, tenant_id: int, thread_id: int) -> EmailThreadOut:
    thread = await get_email_thread(db, tenant_id, thread_id)
    thread.status = "disregarded"
    thread.intake_bucket = "disregarded"
    await db.commit()
    await db.refresh(thread)
    return await get_email_thread_out(db, tenant_id, thread_id)
