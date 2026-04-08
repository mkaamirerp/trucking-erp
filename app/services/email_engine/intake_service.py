"""
Shared intake policies after ingestion: TQL PDF auto-path (Gmail only today), review-only mailboxes.

No provider adapters call this directly — use `message_router.route_after_ingestion`.
"""

from __future__ import annotations

import hashlib
import logging
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.models.broker import Broker
from app.models.email_attachment import EmailMessageAttachment
from app.models.email_ingestion import EmailMessage, EmailThread
from app.models.load import Load
from app.constants.email_intake_routing import (
    append_qr_extractions_tag,
    AUTO_NON_INTAKE_MAIL_BACKGROUND,
    AUTO_TQL_DIGITAL_PDF_RATE_CONFIRMATION,
    BROKER_INTAKE_BLOCKED,
    DUPLICATE_PDF_SHA256,
    BROKER_RESOLVE_AMBIGUOUS,
    format_duplicate_pdf_sha256,
    format_tql_pdf_not_high_confidence,
    GLOBAL_BROKER_HEADER_VS_MC_DOT_DISAGREEMENT,
    GLOBAL_BROKER_MATCH_REQUIRES_WORKSPACE,
    GLOBAL_BROKER_RESOLVE_AMBIGUOUS,
    GLOBAL_BROKER_TIER_D_REQUIRES_REVIEW,
    GMAIL_MISSING_TOKEN_FOR_INTAKE_GATE,
    format_intake_broker_conflicting_signals_routing,
    MAILBOX_INTAKE_REVIEW_ONLY,
    TQL_AFFILIATED_NO_PDF_ATTACHMENT,
    TQL_PDF_NOT_HIGH_CONFIDENCE_PREFIX,
)
from app.services.email_engine.attachment_extractor import download_gmail_attachment_bytes
from app.services.broker_intake_resolve import (
    confidence_tier_for_match_method,
    explanation_for_match_method,
    fetch_latest_inbound_from_header,
)
from app.services.broker_intake_unified import resolve_booking_broker_for_email_intake
from app.services.email_engine.message_classifier import PostIngestIntakePath, thread_indicates_tql_affinity
from app.services.email_intake_review_service import (
    auto_resolve_email_intake_review_on_thread_linked_load,
    sync_email_intake_review_for_thread,
    upsert_intake_review_from_intake_source,
)
from app.services.email_intake_pdf import (
    extract_broker_mc_dot_hints,
    extract_pdf_text_bytes,
    extract_tql_rate_con_hints,
    guess_broker_load_reference,
    tql_digital_pdf_high_confidence,
)
from app.services.email_intake_qr_decode import extract_qr_strings_from_pdf_bytes
from app.services.email_intake_qr_extractions import (
    count_intake_qr_extractions_for_thread,
    link_thread_qr_extractions_to_load,
    record_intake_qr_extraction,
)

logger = logging.getLogger(__name__)


async def _supplemental_mc_dot_hints_for_tql_gate(
    db: AsyncSession,
    tenant_id: int,
    thread: EmailThread,
    rows: list,
    access_token: str,
) -> tuple[str | None, str | None]:
    """MC/USDOT from thread text; if missing, first successful PDF text extraction on TQL attachments.

    PDF text can be incomplete or noisy; Tier D matches are review-only by policy so weak extraction
    does not auto-attach or auto-create workspace brokers.
    """
    hint_mc, hint_dot = extract_broker_mc_dot_hints(f"{thread.subject or ''}\n{thread.snippet or ''}")
    if hint_mc or hint_dot:
        return hint_mc, hint_dot
    for msg, att in rows:
        try:
            if getattr(att, "storage_key", None):
                from app.core.storage import get_storage

                raw = get_storage().read_bytes(att.storage_key, "email_intake", None)
            else:
                raw = await download_gmail_attachment_bytes(
                    access_token, msg.external_message_id, att.external_attachment_id
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


async def resolve_tql_broker_for_intake(db: AsyncSession, tenant_id: int) -> tuple[int | None, str]:
    label = func.coalesce(Broker.display_name, Broker.legal_name, Broker.name)
    b = await db.scalar(
        select(Broker)
        .where(Broker.tenant_id == tenant_id)
        .where(Broker.is_active.is_(True))
        .where(label.ilike("%tql%"))
        .limit(1)
    )
    if b:
        disp = (b.display_name or b.legal_name or b.name or "").strip()
        return b.id, disp or b.name
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
    thread.routing_reason = thread.routing_reason or MAILBOX_INTAKE_REVIEW_ONLY


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
        thread.routing_reason = await _routing_reason_with_qr_supplement(
            db, tenant_id, thread_id, TQL_AFFILIATED_NO_PDF_ATTACHMENT
        )
        return

    if tql_affinity and rows:
        from_hdr = await fetch_latest_inbound_from_header(db, tenant_id, thread_id)
        sup_mc, sup_dot = await _supplemental_mc_dot_hints_for_tql_gate(
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
        if broker_id is None:
            broker_id, broker_snapshot = await resolve_tql_broker_for_intake(db, tenant_id)
            match_method = "fallback_tql"
        tier = confidence_tier_for_match_method(match_method)
        explanation = explanation_for_match_method(match_method)

        high_ok = False
        gate_reason = "no_pdf_bytes"
        pdf_text = ""
        thread_hashes: set[str] = set()

        for msg, att in rows:
            try:
                if getattr(att, "storage_key", None):
                    from app.core.storage import get_storage

                    raw = get_storage().read_bytes(att.storage_key, "email_intake", None)
                else:
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
            hints = extract_tql_rate_con_hints(pdf_text)
            rate = hints.get("rate")
            miles = hints.get("miles")
            commodity = hints.get("commodity")
            load_number = f"INT-{uuid.uuid4().hex[:12].upper()}"
            load = Load(
                tenant_id=tenant_id,
                load_number=load_number,
                broker_id=broker_id,
                broker_name_snapshot=broker_snapshot,
                broker_load_reference=ref,
                broker_match_method=match_method,
                broker_match_confidence_tier=tier,
                broker_match_explanation=explanation,
                review_required=False,
                status="draft",
                internal_notes=excerpt or None,
                rate=float(rate) if isinstance(rate, (int, float)) else None,
                miles=int(miles) if isinstance(miles, int) else None,
                commodity=str(commodity)[:255] if commodity else None,
            )
            db.add(load)
            await db.flush()
            try:
                await link_thread_qr_extractions_to_load(
                    db,
                    tenant_id=tenant_id,
                    thread_id=thread_id,
                    load_id=load.id,
                    linked_broker_id=broker_id,
                )
            except Exception as exc:
                logger.warning("link_thread_qr_extractions_to_load failed: %s", exc)
            thread.linked_load_id = load.id
            thread.intake_bucket = "new_load"
            thread.confidence_level = "high"
            thread.confidence_score = 0.95
            thread.routing_reason = await _routing_reason_with_qr_supplement(
                db, tenant_id, thread_id, AUTO_TQL_DIGITAL_PDF_RATE_CONFIRMATION
            )
            await auto_resolve_email_intake_review_on_thread_linked_load(
                db, tenant_id, thread_id, linked_load_id=load.id
            )
            return

        thread.intake_bucket = "needs_review"
        thread.confidence_level = "low"
        thread.confidence_score = 0.35
        low_conf = format_tql_pdf_not_high_confidence(gate_reason)
        thread.routing_reason = await _routing_reason_with_qr_supplement(db, tenant_id, thread_id, low_conf)
        await upsert_intake_review_from_intake_source(
            db,
            tenant_id,
            thread_id,
            primary_code=TQL_PDF_NOT_HIGH_CONFIDENCE_PREFIX,
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
                thread.routing_reason = thread.routing_reason or GMAIL_MISSING_TOKEN_FOR_INTAKE_GATE
            await sync_email_intake_review_for_thread(db, tenant_id, thread_id)
            return
        await apply_gmail_tql_intake_gate(db, tenant_id, thread_id, gmail_access_token)
    else:
        await apply_review_only_mailbox_intake(db, tenant_id, thread_id)
    await sync_email_intake_review_for_thread(db, tenant_id, thread_id)
