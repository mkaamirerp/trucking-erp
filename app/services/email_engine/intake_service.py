"""
Shared intake policies after ingestion: TQL PDF auto-path (Gmail only today), review-only mailboxes.

No provider adapters call this directly — use `message_router.route_after_ingestion`.
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.broker import Broker
from app.models.email_attachment import EmailMessageAttachment
from app.models.email_ingestion import EmailMessage, EmailThread
from app.models.load import Load
from app.services.email_engine.attachment_extractor import download_gmail_attachment_bytes
from app.services.email_engine.message_classifier import PostIngestIntakePath, thread_indicates_tql_affinity
from app.services.email_intake_pdf import (
    extract_pdf_text_bytes,
    guess_broker_load_reference,
    tql_digital_pdf_high_confidence,
)

logger = logging.getLogger(__name__)


async def resolve_tql_broker_for_intake(db: AsyncSession, tenant_id: int) -> tuple[int | None, str]:
    b = await db.scalar(
        select(Broker)
        .where(Broker.tenant_id == tenant_id)
        .where(Broker.name.ilike("%tql%"))
        .limit(1)
    )
    if b:
        return b.id, b.name
    return None, "Total Quality Logistics"


async def _latest_pdf_attachment_rows(
    db: AsyncSession, tenant_id: int, thread_id: int
) -> list[tuple[EmailMessage, EmailMessageAttachment]]:
    result = await db.execute(
        select(EmailMessage, EmailMessageAttachment)
        .join(
            EmailMessageAttachment,
            (EmailMessageAttachment.message_id == EmailMessage.id)
            & (EmailMessageAttachment.tenant_id == tenant_id),
        )
        .where(EmailMessage.tenant_id == tenant_id, EmailMessage.thread_id == thread_id)
        .where(EmailMessageAttachment.is_inline.is_(False))
        .where(
            (EmailMessageAttachment.mime_type == "application/pdf")
            | (EmailMessageAttachment.filename.ilike("%.pdf"))
        )
        .order_by(
            EmailMessage.received_at.desc().nulls_last(),
            EmailMessage.sent_at.desc().nulls_last(),
            EmailMessage.id.desc(),
        )
    )
    return list(result.all())


async def apply_review_only_mailbox_intake(
    db: AsyncSession,
    tenant_id: int,
    thread_id: int,
) -> None:
    thread = await db.scalar(
        select(EmailThread).where(EmailThread.id == thread_id, EmailThread.tenant_id == tenant_id)
    )
    if not thread or thread.status != "active":
        return
    if (thread.provider or "").strip().lower() == "gmail":
        return
    if thread.linked_load_id:
        return
    thread.intake_bucket = "needs_review"
    thread.confidence_level = thread.confidence_level or "low"
    thread.confidence_score = thread.confidence_score if thread.confidence_score is not None else 0.2
    thread.routing_reason = thread.routing_reason or "mailbox_intake_review_only"


async def apply_gmail_tql_intake_gate(
    db: AsyncSession,
    tenant_id: int,
    thread_id: int,
    access_token: str,
) -> None:
    """
    Narrow TQL digital-PDF auto path OR background for non-intake Gmail (shared engine policy for Gmail).
    """
    thread = await db.scalar(
        select(EmailThread).where(EmailThread.id == thread_id, EmailThread.tenant_id == tenant_id)
    )
    if not thread or thread.status != "active":
        return
    if thread.linked_load_id:
        return
    if thread.intake_bucket == "new_load":
        return

    tql_affinity = thread_indicates_tql_affinity(thread)
    rows = await _latest_pdf_attachment_rows(db, tenant_id, thread_id)

    if tql_affinity and not rows:
        thread.intake_bucket = "needs_review"
        thread.confidence_level = "low"
        thread.confidence_score = 0.25
        thread.routing_reason = "tql_affiliated_no_pdf_attachment"
        return

    if tql_affinity and rows:
        broker_id, broker_snapshot = await resolve_tql_broker_for_intake(db, tenant_id)
        high_ok = False
        gate_reason = "no_pdf_bytes"
        pdf_text = ""

        for msg, att in rows:
            try:
                raw = await download_gmail_attachment_bytes(
                    access_token, msg.external_message_id, att.external_attachment_id
                )
            except Exception as exc:
                logger.warning("intake gmail attachment download failed: %s", exc)
                gate_reason = "gmail_attachment_download_failed"
                continue
            if not raw:
                gate_reason = "empty_attachment"
                continue
            try:
                pdf_text = extract_pdf_text_bytes(raw)
            except Exception as exc:
                logger.warning("intake pdf text extract failed: %s", exc)
                gate_reason = "pdf_text_extract_failed"
                continue

            ok, reason = tql_digital_pdf_high_confidence(pdf_text)
            if ok:
                high_ok = True
                gate_reason = reason
                break
            gate_reason = reason

        if high_ok:
            ref = guess_broker_load_reference(pdf_text)
            excerpt = (pdf_text or "")[:4000]
            load_number = f"INT-{uuid.uuid4().hex[:12].upper()}"
            load = Load(
                tenant_id=tenant_id,
                load_number=load_number,
                broker_id=broker_id,
                broker_name_snapshot=broker_snapshot,
                broker_load_reference=ref,
                status="draft",
                internal_notes=excerpt or None,
            )
            db.add(load)
            await db.flush()
            thread.linked_load_id = load.id
            thread.intake_bucket = "new_load"
            thread.confidence_level = "high"
            thread.confidence_score = 0.95
            thread.routing_reason = "auto_tql_digital_pdf_rate_confirmation"
            return

        thread.intake_bucket = "needs_review"
        thread.confidence_level = "low"
        thread.confidence_score = 0.35
        thread.routing_reason = f"tql_pdf_not_high_confidence:{gate_reason}"
        return

    if thread.intake_bucket == "needs_review" and not thread.linked_load_id and thread.status == "active":
        thread.intake_bucket = "background"
        thread.routing_reason = thread.routing_reason or "auto_non_intake_mail_background"
    return


async def run_post_ingest_intake(
    db: AsyncSession,
    tenant_id: int,
    thread_id: int,
    path: PostIngestIntakePath,
    *,
    gmail_access_token: str | None = None,
) -> None:
    if path == "gmail_tql_gate":
        if not gmail_access_token:
            thread = await db.scalar(
                select(EmailThread).where(EmailThread.id == thread_id, EmailThread.tenant_id == tenant_id)
            )
            if (
                thread
                and (thread.provider or "").strip().lower() == "gmail"
                and thread.status == "active"
                and not thread.linked_load_id
            ):
                thread.intake_bucket = "needs_review"
                thread.routing_reason = thread.routing_reason or "gmail_missing_token_for_intake_gate"
            return
        await apply_gmail_tql_intake_gate(db, tenant_id, thread_id, gmail_access_token)
    else:
        await apply_review_only_mailbox_intake(db, tenant_id, thread_id)
