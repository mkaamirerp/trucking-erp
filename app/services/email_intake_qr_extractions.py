"""Email intake QR rows: deduped persistence and primary lookup helpers."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.email_intake_qr_extraction import EXTRACTED_FROM_SOURCE_TYPES, EmailIntakeQrExtraction


async def find_existing_intake_qr(
    db: AsyncSession,
    *,
    tenant_id: int,
    message_id: int,
    attachment_id: int | None,
    raw_value: str,
) -> EmailIntakeQrExtraction | None:
    """Mirror partial uniques: (tenant, attachment, raw) or (tenant, message, raw) when attachment is NULL."""
    if attachment_id is not None:
        return await db.scalar(
            select(EmailIntakeQrExtraction).where(
                EmailIntakeQrExtraction.tenant_id == tenant_id,
                EmailIntakeQrExtraction.attachment_id == attachment_id,
                EmailIntakeQrExtraction.raw_value == raw_value,
            )
        )
    return await db.scalar(
        select(EmailIntakeQrExtraction).where(
            EmailIntakeQrExtraction.tenant_id == tenant_id,
            EmailIntakeQrExtraction.message_id == message_id,
            EmailIntakeQrExtraction.attachment_id.is_(None),
            EmailIntakeQrExtraction.raw_value == raw_value,
        )
    )


async def record_intake_qr_extraction(
    db: AsyncSession,
    *,
    tenant_id: int,
    thread_id: int,
    message_id: int,
    attachment_id: int | None,
    raw_value: str,
    extracted_from_source_type: str = "other",
    normalized_value: str | None = None,
    page_number: int | None = None,
    format_hint: str | None = None,
    decoder_backend: str | None = None,
    parse_status: str = "ok",
    confidence: float | None = None,
    notes: str | None = None,
    linked_broker_id: int | None = None,
    linked_load_id: int | None = None,
) -> EmailIntakeQrExtraction:
    """
    Idempotent per duplicate rule: same tenant + lineage + raw_value returns the existing row.
    Does not overwrite raw_value; optional fields on re-call are ignored (caller can add updates later).
    """
    if extracted_from_source_type not in EXTRACTED_FROM_SOURCE_TYPES:
        raise ValueError(f"extracted_from_source_type must be one of {sorted(EXTRACTED_FROM_SOURCE_TYPES)}")

    existing = await find_existing_intake_qr(
        db,
        tenant_id=tenant_id,
        message_id=message_id,
        attachment_id=attachment_id,
        raw_value=raw_value,
    )
    if existing is not None:
        return existing

    row = EmailIntakeQrExtraction(
        tenant_id=tenant_id,
        thread_id=thread_id,
        message_id=message_id,
        attachment_id=attachment_id,
        raw_value=raw_value,
        normalized_value=normalized_value,
        extracted_from_source_type=extracted_from_source_type,
        page_number=page_number,
        format_hint=format_hint,
        decoder_backend=decoder_backend,
        parse_status=parse_status,
        confidence=confidence,
        notes=notes,
        linked_broker_id=linked_broker_id,
        linked_load_id=linked_load_id,
    )
    db.add(row)
    await db.flush()
    return row


async def list_intake_qr_by_tenant_raw(
    db: AsyncSession,
    *,
    tenant_id: int,
    raw_value: str,
) -> list[EmailIntakeQrExtraction]:
    result = await db.execute(
        select(EmailIntakeQrExtraction)
        .where(EmailIntakeQrExtraction.tenant_id == tenant_id, EmailIntakeQrExtraction.raw_value == raw_value)
        .order_by(EmailIntakeQrExtraction.id.asc())
    )
    return list(result.scalars().all())


async def list_intake_qr_by_attachment(
    db: AsyncSession,
    *,
    tenant_id: int,
    attachment_id: int,
) -> list[EmailIntakeQrExtraction]:
    result = await db.execute(
        select(EmailIntakeQrExtraction)
        .where(
            EmailIntakeQrExtraction.tenant_id == tenant_id,
            EmailIntakeQrExtraction.attachment_id == attachment_id,
        )
        .order_by(EmailIntakeQrExtraction.id.asc())
    )
    return list(result.scalars().all())


async def list_intake_qr_by_message(
    db: AsyncSession,
    *,
    tenant_id: int,
    message_id: int,
) -> list[EmailIntakeQrExtraction]:
    result = await db.execute(
        select(EmailIntakeQrExtraction)
        .where(
            EmailIntakeQrExtraction.tenant_id == tenant_id,
            EmailIntakeQrExtraction.message_id == message_id,
        )
        .order_by(EmailIntakeQrExtraction.id.asc())
    )
    return list(result.scalars().all())


async def count_intake_qr_extractions_for_thread(
    db: AsyncSession,
    *,
    tenant_id: int,
    thread_id: int,
) -> int:
    c = await db.scalar(
        select(func.count())
        .select_from(EmailIntakeQrExtraction)
        .where(
            EmailIntakeQrExtraction.tenant_id == tenant_id,
            EmailIntakeQrExtraction.thread_id == thread_id,
        )
    )
    return int(c or 0)


async def list_intake_qr_by_thread(
    db: AsyncSession,
    *,
    tenant_id: int,
    thread_id: int,
) -> list[EmailIntakeQrExtraction]:
    result = await db.execute(
        select(EmailIntakeQrExtraction)
        .where(
            EmailIntakeQrExtraction.tenant_id == tenant_id,
            EmailIntakeQrExtraction.thread_id == thread_id,
        )
        .order_by(EmailIntakeQrExtraction.id.asc())
    )
    return list(result.scalars().all())


async def link_thread_qr_extractions_to_load(
    db: AsyncSession,
    *,
    tenant_id: int,
    thread_id: int,
    load_id: int,
    linked_broker_id: int | None = None,
) -> int:
    """Set ``linked_load_id`` (and optionally ``linked_broker_id``) on thread rows still unlinked."""
    now = datetime.now(timezone.utc)
    values: dict = {"linked_load_id": load_id, "updated_at": now}
    if linked_broker_id is not None:
        values["linked_broker_id"] = linked_broker_id
    res = await db.execute(
        update(EmailIntakeQrExtraction)
        .where(
            EmailIntakeQrExtraction.tenant_id == tenant_id,
            EmailIntakeQrExtraction.thread_id == thread_id,
            EmailIntakeQrExtraction.linked_load_id.is_(None),
        )
        .values(**values)
    )
    return int(res.rowcount or 0)


async def list_intake_qr_by_linked_load(
    db: AsyncSession,
    *,
    tenant_id: int,
    load_id: int,
) -> list[EmailIntakeQrExtraction]:
    result = await db.execute(
        select(EmailIntakeQrExtraction)
        .where(
            EmailIntakeQrExtraction.tenant_id == tenant_id,
            EmailIntakeQrExtraction.linked_load_id == load_id,
        )
        .order_by(EmailIntakeQrExtraction.id.asc())
    )
    return list(result.scalars().all())
