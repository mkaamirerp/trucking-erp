"""Post-sync email → load intake routing (narrow TQL digital-PDF auto path)."""

from __future__ import annotations

import logging
import uuid
from urllib.parse import quote

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.broker import Broker
from app.models.email_attachment import EmailMessageAttachment
from app.models.email_ingestion import EmailMessage, EmailThread
from app.models.load import Load
from app.services.email_intake_pdf import (
    extract_pdf_text_bytes,
    guess_broker_load_reference,
    tql_digital_pdf_high_confidence,
)

logger = logging.getLogger(__name__)

GMAIL_API_BASE = "https://gmail.googleapis.com/gmail/v1/users/me"

_TQL_EMAIL_MARKERS = ("@tql.com", "@tqltrucks.com", "@tql.net")


def participants_indicate_tql(participants_json: dict | list | None) -> bool:
    if not participants_json or not isinstance(participants_json, list):
        return False
    for p in participants_json:
        if not isinstance(p, dict):
            continue
        email = str(p.get("email") or "").strip().lower()
        if any(m in email for m in _TQL_EMAIL_MARKERS):
            return True
    return False


async def _gmail_download_attachment(access_token: str, gmail_message_id: str, attachment_id: str) -> bytes:
    mid = quote(gmail_message_id, safe="")
    aid = quote(attachment_id, safe="")
    url = f"{GMAIL_API_BASE}/messages/{mid}/attachments/{aid}"
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.get(url, headers={"Authorization": f"Bearer {access_token}"})
        resp.raise_for_status()
        data = resp.json().get("data")
        if not data:
            return b""
        import base64

        padded = data + "=" * (-len(data) % 4)
        return base64.urlsafe_b64decode(padded.encode("utf-8"))


async def _resolve_tql_broker(db: AsyncSession, tenant_id: int) -> tuple[int | None, str]:
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


async def apply_intake_routing_for_gmail_thread(
    db: AsyncSession,
    tenant_id: int,
    thread_id: int,
    access_token: str,
) -> None:
    """
    If thread qualifies for the locked TQL digital-PDF rule, create a load, assign INT-* trip/load number,
    link the thread, and set intake_bucket=new_load. Otherwise, TQL-affine threads with PDFs may be
    downgraded to needs_review with routing_reason (no load created).
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

    tql_parties = participants_indicate_tql(thread.participants_json)
    rows = await _latest_pdf_attachment_rows(db, tenant_id, thread_id)

    if tql_parties and not rows:
        thread.intake_bucket = "needs_review"
        thread.confidence_level = "low"
        thread.confidence_score = 0.25
        thread.routing_reason = "tql_affiliated_no_pdf_attachment"
        return

    if tql_parties and rows:
        broker_id, broker_snapshot = await _resolve_tql_broker(db, tenant_id)
        high_ok = False
        gate_reason = "no_pdf_bytes"
        pdf_text = ""

        for msg, att in rows:
            try:
                raw = await _gmail_download_attachment(access_token, msg.external_message_id, att.external_attachment_id)
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

    # Non–TQL threads: no automatic routing in this slice (remain default needs_review).
    return
