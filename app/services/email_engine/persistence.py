"""Single persistence path: normalized messages → tenant DB rows (idempotent upsert)."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.email_attachment import EmailMessageAttachment
from app.models.email_ingestion import EmailMessage, EmailThread
from app.services.email_engine.normalized import NormalizedEmailMessage, NormalizedThreadRollup


async def upsert_thread_bundle(
    tenant_db: AsyncSession,
    tenant_id: int,
    provider: str,
    rollup: NormalizedThreadRollup,
    messages: list[NormalizedEmailMessage],
) -> tuple[EmailThread, int, int]:
    """
    Upsert one thread and its messages + attachments.
    Returns (thread, messages_touched, attachments_touched) — counts mirror per-row processing (insert or update = 1).
    """
    ext_tid = rollup.external_thread_id
    thread_row = await tenant_db.scalar(
        select(EmailThread).where(
            EmailThread.tenant_id == tenant_id,
            EmailThread.provider == provider,
            EmailThread.external_thread_id == ext_tid,
        )
    )
    if not thread_row:
        thread_row = EmailThread(
            tenant_id=tenant_id,
            provider=provider,
            external_thread_id=ext_tid,
            status="active",
        )
        tenant_db.add(thread_row)
        await tenant_db.flush()

    messages_touched = 0
    attachments_touched = 0

    for nm in messages:
        existing_msg = await tenant_db.scalar(
            select(EmailMessage).where(
                EmailMessage.tenant_id == tenant_id,
                EmailMessage.provider == provider,
                EmailMessage.external_message_id == nm.external_message_id,
            )
        )
        has_atts = bool(nm.attachments)
        if existing_msg:
            existing_msg.thread_id = thread_row.id
            existing_msg.external_thread_id = nm.external_thread_id
            existing_msg.direction = existing_msg.direction or nm.direction or "inbound"
            existing_msg.from_email = nm.from_email
            existing_msg.to_json = nm.to_json
            existing_msg.cc_json = nm.cc_json
            existing_msg.bcc_json = nm.bcc_json
            existing_msg.subject = nm.subject
            existing_msg.sent_at = nm.sent_at
            existing_msg.received_at = nm.received_at
            existing_msg.snippet = nm.snippet
            existing_msg.body_text = nm.body_text
            if nm.body_html is not None:
                existing_msg.body_html = nm.body_html
            existing_msg.has_attachments = has_atts
            existing_msg.updated_at = datetime.now(timezone.utc)
            em = existing_msg
        else:
            em = EmailMessage(
                tenant_id=tenant_id,
                thread_id=thread_row.id,
                provider=provider,
                external_message_id=nm.external_message_id,
                external_thread_id=nm.external_thread_id,
                direction=nm.direction or "inbound",
                from_email=nm.from_email,
                to_json=nm.to_json,
                cc_json=nm.cc_json,
                bcc_json=nm.bcc_json,
                subject=nm.subject,
                sent_at=nm.sent_at,
                received_at=nm.received_at,
                snippet=nm.snippet,
                body_text=nm.body_text,
                body_html=nm.body_html,
                has_attachments=has_atts,
            )
            tenant_db.add(em)
            await tenant_db.flush()
        messages_touched += 1

        for ap in nm.attachments:
            ext_aid = ap.external_attachment_id
            existing_att = await tenant_db.scalar(
                select(EmailMessageAttachment).where(
                    EmailMessageAttachment.tenant_id == tenant_id,
                    EmailMessageAttachment.provider == provider,
                    EmailMessageAttachment.message_id == em.id,
                    EmailMessageAttachment.external_attachment_id == ext_aid,
                )
            )
            if existing_att:
                existing_att.filename = ap.filename
                existing_att.mime_type = ap.mime_type
                existing_att.size_bytes = ap.size_bytes
                existing_att.is_inline = ap.is_inline
                existing_att.updated_at = datetime.now(timezone.utc)
            else:
                tenant_db.add(
                    EmailMessageAttachment(
                        tenant_id=tenant_id,
                        message_id=em.id,
                        provider=provider,
                        external_attachment_id=ext_aid,
                        filename=ap.filename,
                        mime_type=ap.mime_type,
                        size_bytes=ap.size_bytes,
                        is_inline=ap.is_inline,
                        download_status="metadata_only",
                    )
                )
            attachments_touched += 1

    if rollup.subject is not None:
        thread_row.subject = rollup.subject or thread_row.subject
    if rollup.snippet is not None:
        thread_row.snippet = rollup.snippet or thread_row.snippet
    if rollup.participants_json is not None:
        thread_row.participants_json = rollup.participants_json or thread_row.participants_json
    if rollup.last_message_at is not None:
        if thread_row.last_message_at is None or rollup.last_message_at > thread_row.last_message_at:
            thread_row.last_message_at = rollup.last_message_at
    if rollup.message_count is not None:
        thread_row.message_count = rollup.message_count
    else:
        cnt = await tenant_db.scalar(
            select(func.count()).select_from(EmailMessage).where(EmailMessage.thread_id == thread_row.id)
        )
        thread_row.message_count = int(cnt or 0)
    if rollup.unread_count is not None:
        thread_row.unread_count = rollup.unread_count
    thread_row.updated_at = datetime.now(timezone.utc)

    return thread_row, messages_touched, attachments_touched
