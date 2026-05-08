"""
Shared intake policies after ingestion: email PDF attachment intake + review-only mailboxes.

After a thread is stored, the email PDF path runs provider-neutral intake (PDF → product parser
→ needs_review / review detail). Attachment bytes may still be fetched via a Gmail connector
helper when not in tenant storage.

No provider adapters call this directly — use `message_router.route_after_ingestion`.
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.models.email_attachment import EmailMessageAttachment
from app.models.email_ingestion import EmailMessage, EmailThread
from app.models.load import Load
from app.constants.email_intake_routing import (
    append_qr_extractions_tag,
    AUTO_NON_INTAKE_MAIL_BACKGROUND,
    BROKER_INTAKE_BLOCKED,
    DUPLICATE_PDF_SHA256,
    BROKER_RESOLVE_AMBIGUOUS,
    EMAIL_INTAKE_PDF_LOW_CONFIDENCE_PRIMARY,
    EMAIL_INTAKE_PDF_PARSE_REVIEW_PRIMARY,
    EMAIL_INTAKE_TOUCHPOINTS_NO_PDF_ATTACHMENT,
    format_duplicate_pdf_sha256,
    format_email_intake_pdf_low_confidence,
    format_email_intake_pdf_parse_review,
    GLOBAL_BROKER_HEADER_VS_MC_DOT_DISAGREEMENT,
    GLOBAL_BROKER_MATCH_REQUIRES_WORKSPACE,
    GLOBAL_BROKER_RESOLVE_AMBIGUOUS,
    GLOBAL_BROKER_TIER_D_REQUIRES_REVIEW,
    GMAIL_MISSING_TOKEN_FOR_INTAKE_GATE,
    format_intake_broker_conflicting_signals_routing,
    MAILBOX_INTAKE_REVIEW_ONLY,
)
from app.services.email_engine.attachment_extractor import download_gmail_attachment_bytes
from app.services.broker_intake_resolve import (
    confidence_tier_for_match_method,
    explanation_for_match_method,
    fetch_latest_inbound_from_header,
)
from app.services.broker_intake_unified import resolve_booking_broker_for_email_intake
from app.services.email_engine.message_classifier import (
    PostIngestIntakePath,
    thread_indicates_booking_broker_touchpoints,
)
from app.services.email_intake_review_service import (
    sync_email_intake_review_for_thread,
    upsert_intake_review_from_intake_source,
)
from app.services.email_intake_pdf import extract_broker_mc_dot_hints, extract_pdf_text_bytes
from app.schemas.load_document_parse import LoadDocumentParseResponse
from app.services.load_document_product_parser import parse_pdf_bytes_to_load_document_response
from app.services.email_intake_qr_decode import extract_qr_strings_from_pdf_bytes
from app.services.email_intake_qr_extractions import (
    count_intake_qr_extractions_for_thread,
    record_intake_qr_extraction,
)

logger = logging.getLogger(__name__)


async def _fetch_gmail_pdf_attachment_bytes(
    gmail_access_token: str,
    external_message_id: str | None,
    external_attachment_id: str | None,
) -> bytes | None:
    """Gmail API fetch only; not used when attachment is already in tenant object storage."""
    if not external_message_id or not external_attachment_id:
        return None
    return await download_gmail_attachment_bytes(
        gmail_access_token, external_message_id, external_attachment_id
    )


async def _fetch_email_pdf_attachment_bytes(
    *,
    msg: EmailMessage,
    att: EmailMessageAttachment,
    gmail_access_token: str,
) -> bytes | None:
    """Resolve PDF bytes from storage (any provider) or Gmail connector when not stored."""
    if getattr(att, "storage_key", None):
        from app.core.storage import get_storage

        return get_storage().read_bytes(att.storage_key, "email_intake", None)
    return await _fetch_gmail_pdf_attachment_bytes(
        gmail_access_token, msg.external_message_id, att.external_attachment_id
    )


def _guarded_parse_detail_for_review(parse: LoadDocumentParseResponse) -> dict[str, Any]:
    d = parse.model_dump(mode="json")
    rt = d.get("raw_text")
    if isinstance(rt, str) and len(rt) > 12_000:
        d["raw_text"] = rt[:12_000] + "\n…[truncated for intake review storage]"
    return {"guarded_parse": d}


async def _supplemental_mc_dot_hints_from_pdf_attachments(
    db: AsyncSession,
    tenant_id: int,
    thread: EmailThread,
    rows: list,
    access_token: str,
) -> tuple[str | None, str | None]:
    """MC/USDOT from thread text; if missing, first successful PDF text extraction on attachments."""
    hint_mc, hint_dot = extract_broker_mc_dot_hints(f"{thread.subject or ''}\n{thread.snippet or ''}")
    if hint_mc or hint_dot:
        return hint_mc, hint_dot
    for msg, att in rows:
        try:
            raw = await _fetch_email_pdf_attachment_bytes(
                msg=msg, att=att, gmail_access_token=access_token
            )
        except Exception as exc:
            logger.warning("intake supplemental mc/dot pdf read failed: %s", exc)
            continue
        if not raw:
            continue
        try:
            pdf_text = extract_pdf_text_bytes(raw)
        except Exception as exc:
            logger.warning("intake supplemental mc/dot pdf text failed: %s", exc)
            continue
        hint_mc, hint_dot = extract_broker_mc_dot_hints(pdf_text)
        if hint_mc or hint_dot:
            return hint_mc, hint_dot
    return None, None


async def _routing_reason_with_qr_supplement(
    db: AsyncSession,
    tenant_id: int,
    thread_id: int,
    base_reason: str,
) -> str:
    n = await count_intake_qr_extractions_for_thread(db, tenant_id=tenant_id, thread_id=thread_id)
    return append_qr_extractions_tag(base_reason, n)


async def _first_linked_load_id_for_sha256_elsewhere(
    db: AsyncSession,
    tenant_id: int,
    content_sha256: str,
    exclude_thread_id: int,
) -> int | None:
    """If another thread already linked a load from this attachment hash, return that load id."""
    stmt = (
        select(Load.id)
        .join(EmailThread, EmailThread.linked_load_id == Load.id)
        .join(EmailMessage, EmailMessage.thread_id == EmailThread.id)
        .join(
            EmailMessageAttachment,
            (EmailMessageAttachment.message_id == EmailMessage.id)
            & (EmailMessageAttachment.tenant_id == tenant_id),
        )
        .where(
            Load.tenant_id == tenant_id,
            EmailThread.tenant_id == tenant_id,
            EmailMessage.tenant_id == tenant_id,
            EmailMessageAttachment.content_sha256 == content_sha256,
            EmailThread.id != exclude_thread_id,
            EmailThread.linked_load_id.isnot(None),
        )
        .order_by(Load.id.asc())
        .limit(1)
    )
    row = await db.scalar(stmt)
    return int(row) if row is not None else None


async def find_duplicate_linked_load_for_thread_pdf_content(
    db: AsyncSession, tenant_id: int, thread_id: int
) -> int | None:
    """Best-effort: first load id elsewhere that was linked from the same PDF bytes (sha256) as this thread."""
    stmt = (
        select(EmailMessageAttachment.content_sha256)
        .join(EmailMessage, EmailMessage.id == EmailMessageAttachment.message_id)
        .where(
            EmailMessage.tenant_id == tenant_id,
            EmailMessage.thread_id == thread_id,
            EmailMessageAttachment.tenant_id == tenant_id,
            EmailMessageAttachment.content_sha256.isnot(None),
        )
        .distinct()
    )
    hashes = [r[0] for r in (await db.execute(stmt)).all() if r[0]]
    for h in hashes:
        lid = await _first_linked_load_id_for_sha256_elsewhere(db, tenant_id, h, thread_id)
        if lid is not None:
            return lid
    return None


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
    thread.routing_reason = thread.routing_reason or MAILBOX_INTAKE_REVIEW_ONLY


async def apply_email_pdf_intake(
    db: AsyncSession,
    tenant_id: int,
    thread_id: int,
    access_token: str,
) -> None:
    """
    Email PDF intake (stage 2): when PDF rows exist, call product parser; snapshot → review — no auto Load.

    Stage 1 cues: generic load-language in subject/snippet but no PDF → needs_review (email_touchpoints_no_pdf_attachment).
    Broker resolution uses unified intake only (no default broker). Gmail OAuth fetch only when bytes not in storage.
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

    rows = await _latest_pdf_attachment_rows(db, tenant_id, thread_id)
    load_intake_text_cues = thread_indicates_booking_broker_touchpoints(thread)

    if load_intake_text_cues and not rows:
        thread.intake_bucket = "needs_review"
        thread.confidence_level = "low"
        thread.confidence_score = 0.25
        thread.routing_reason = await _routing_reason_with_qr_supplement(
            db, tenant_id, thread_id, EMAIL_INTAKE_TOUCHPOINTS_NO_PDF_ATTACHMENT
        )
        return

    if rows:
        from_hdr = await fetch_latest_inbound_from_header(db, tenant_id, thread_id)
        sup_mc, sup_dot = await _supplemental_mc_dot_hints_from_pdf_attachments(
            db, tenant_id, thread, rows, access_token
        )
        async with AsyncSessionLocal() as platform_db:
            resolve_res = await resolve_booking_broker_for_email_intake(
                db,
                tenant_id,
                from_hdr,
                platform_db=platform_db,
                supplemental_mc=sup_mc,
                supplemental_dot=sup_dot,
            )
        if resolve_res.ambiguous:
            thread.intake_bucket = "needs_review"
            thread.confidence_level = "low"
            thread.confidence_score = 0.3
            code = (
                GLOBAL_BROKER_RESOLVE_AMBIGUOUS
                if resolve_res.is_global_ambiguous
                else BROKER_RESOLVE_AMBIGUOUS
            )
            thread.routing_reason = await _routing_reason_with_qr_supplement(db, tenant_id, thread_id, code)
            await upsert_intake_review_from_intake_source(
                db,
                tenant_id,
                thread_id,
                primary_code=code,
                detail_extensions={},
                routing_reason_snapshot=thread.routing_reason,
            )
            return
        if resolve_res.blocked_match:
            thread.intake_bucket = "needs_review"
            thread.confidence_level = "low"
            thread.confidence_score = 0.3
            thread.routing_reason = await _routing_reason_with_qr_supplement(
                db, tenant_id, thread_id, BROKER_INTAKE_BLOCKED
            )
            await upsert_intake_review_from_intake_source(
                db,
                tenant_id,
                thread_id,
                primary_code=BROKER_INTAKE_BLOCKED,
                detail_extensions={},
                routing_reason_snapshot=thread.routing_reason,
            )
            return
        if resolve_res.global_identity_disagreement:
            thread.intake_bucket = "needs_review"
            thread.confidence_level = "low"
            thread.confidence_score = 0.31
            thread.routing_reason = await _routing_reason_with_qr_supplement(
                db, tenant_id, thread_id, GLOBAL_BROKER_HEADER_VS_MC_DOT_DISAGREEMENT
            )
            return
        if resolve_res.global_tier_d_requires_review:
            thread.intake_bucket = "needs_review"
            thread.confidence_level = "low"
            thread.confidence_score = 0.32
            thread.routing_reason = await _routing_reason_with_qr_supplement(
                db, tenant_id, thread_id, GLOBAL_BROKER_TIER_D_REQUIRES_REVIEW
            )
            return
        if resolve_res.intake_signal_conflict:
            thread.intake_bucket = "needs_review"
            thread.confidence_level = "low"
            thread.confidence_score = 0.33
            thread.routing_reason = await _routing_reason_with_qr_supplement(
                db, tenant_id, thread_id, format_intake_broker_conflicting_signals_routing()
            )
            return
        if resolve_res.global_match_no_workspace:
            thread.intake_bucket = "needs_review"
            thread.confidence_level = "low"
            thread.confidence_score = 0.32
            thread.routing_reason = await _routing_reason_with_qr_supplement(
                db, tenant_id, thread_id, GLOBAL_BROKER_MATCH_REQUIRES_WORKSPACE
            )
            return

        broker_id = resolve_res.broker_id
        broker_snapshot = resolve_res.broker_label
        match_method: str | None = resolve_res.match_method
        tier_note = confidence_tier_for_match_method(match_method) if match_method else None
        expl_note = explanation_for_match_method(match_method) if match_method else None

        gate_reason = "no_pdf_bytes"
        last_parse: LoadDocumentParseResponse | None = None
        thread_hashes: set[str] = set()

        for msg, att in rows:
            try:
                raw = await _fetch_email_pdf_attachment_bytes(
                    msg=msg, att=att, gmail_access_token=access_token
                )
            except Exception as exc:
                logger.warning("intake email PDF attachment fetch failed: %s", exc)
                gate_reason = "email_attachment_fetch_failed"
                continue
            if not raw:
                gate_reason = "empty_attachment"
                continue
            digest = hashlib.sha256(raw).hexdigest()
            if getattr(att, "content_sha256", None) != digest:
                att.content_sha256 = digest
                await db.flush()
            if digest in thread_hashes:
                gate_reason = "duplicate_attachment_bytes_skipped"
                continue
            for page_num, qr_text in extract_qr_strings_from_pdf_bytes(raw):
                try:
                    await record_intake_qr_extraction(
                        db,
                        tenant_id=tenant_id,
                        thread_id=msg.thread_id,
                        message_id=msg.id,
                        attachment_id=att.id,
                        raw_value=qr_text,
                        extracted_from_source_type="pdf",
                        page_number=page_num,
                        format_hint="qr",
                        decoder_backend="zxingcpp",
                    )
                except Exception as exc:
                    logger.warning("intake qr persist failed: %s", exc)
            dup_load = await _first_linked_load_id_for_sha256_elsewhere(db, tenant_id, digest, thread_id)
            if dup_load is not None:
                thread.intake_bucket = "needs_review"
                thread.confidence_level = "low"
                thread.confidence_score = 0.35
                dup_reason = format_duplicate_pdf_sha256(
                    prior_load_id=dup_load,
                    content_sha256=digest,
                    detection_source="pdf_sha256_match_same_tenant",
                )
                thread.routing_reason = await _routing_reason_with_qr_supplement(
                    db, tenant_id, thread_id, dup_reason
                )
                await upsert_intake_review_from_intake_source(
                    db,
                    tenant_id,
                    thread_id,
                    primary_code=DUPLICATE_PDF_SHA256,
                    detail_extensions={},
                    routing_reason_snapshot=thread.routing_reason,
                )
                return
            thread_hashes.add(digest)
            try:
                parse_res = await parse_pdf_bytes_to_load_document_response(
                    db,
                    tenant_id=tenant_id,
                    pdf_bytes=raw,
                    filename=(getattr(att, "filename", None) or "attachment.pdf")[:512],
                )
            except Exception as exc:
                logger.warning("intake guarded pdf parse failed: %s", exc)
                gate_reason = "guarded_pdf_parse_failed"
                continue

            last_parse = parse_res
            gate_reason = "guarded_parse_ok"
            break

        if last_parse is not None:
            thread.intake_bucket = "needs_review"
            thread.confidence_level = "medium"
            thread.confidence_score = 0.55
            parse_rr = format_email_intake_pdf_parse_review(gate_detail=gate_reason)
            thread.routing_reason = await _routing_reason_with_qr_supplement(
                db, tenant_id, thread_id, parse_rr
            )
            detail = {
                **_guarded_parse_detail_for_review(last_parse),
                "broker_resolution": {
                    "broker_id": broker_id,
                    "broker_label": broker_snapshot,
                    "match_method": match_method,
                    "confidence_tier": tier_note,
                    "match_explanation": expl_note,
                },
            }
            await upsert_intake_review_from_intake_source(
                db,
                tenant_id,
                thread_id,
                primary_code=EMAIL_INTAKE_PDF_PARSE_REVIEW_PRIMARY,
                detail_extensions=detail,
                routing_reason_snapshot=thread.routing_reason,
            )
            return

        thread.intake_bucket = "needs_review"
        thread.confidence_level = "low"
        thread.confidence_score = 0.35
        low_conf = format_email_intake_pdf_low_confidence(gate_reason)
        thread.routing_reason = await _routing_reason_with_qr_supplement(db, tenant_id, thread_id, low_conf)
        await upsert_intake_review_from_intake_source(
            db,
            tenant_id,
            thread_id,
            primary_code=EMAIL_INTAKE_PDF_LOW_CONFIDENCE_PRIMARY,
            detail_extensions={},
            routing_reason_snapshot=thread.routing_reason,
        )
        return

    if thread.intake_bucket == "needs_review" and not thread.linked_load_id and thread.status == "active":
        thread.intake_bucket = "background"
        thread.routing_reason = thread.routing_reason or AUTO_NON_INTAKE_MAIL_BACKGROUND
    return


async def run_post_ingest_intake(
    db: AsyncSession,
    tenant_id: int,
    thread_id: int,
    path: PostIngestIntakePath,
    *,
    gmail_access_token: str | None = None,
) -> None:
    if path == "email_pdf_intake":
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
                thread.routing_reason = thread.routing_reason or GMAIL_MISSING_TOKEN_FOR_INTAKE_GATE
            await sync_email_intake_review_for_thread(db, tenant_id, thread_id)
            return
        await apply_email_pdf_intake(db, tenant_id, thread_id, gmail_access_token)
    else:
        await apply_review_only_mailbox_intake(db, tenant_id, thread_id)
    await sync_email_intake_review_for_thread(db, tenant_id, thread_id)
