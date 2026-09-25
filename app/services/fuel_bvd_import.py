"""BVD Implementation 1 — persist and read fuel_bvd imports (no canonical fuel pipeline)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.storage import save_fuel_bvd_import_bytes
from app.models.fuel import FuelBvd
from app.services.fuel_bvd_extraction import (
    FuelBvdExtractionError,
    FuelBvdExtractedRow,
    extract_bvd_rows_from_digital_pdf,
)

FUEL_BVD_STORAGE_MODULE = "fuel_bvd"

BVD_SOURCE_FIELD_NAMES: tuple[str, ...] = (
    "invoice_number",
    "invoice_date",
    "start_date",
    "end_date",
    "due_date",
    "client_name",
    "client_address",
    "client_phone",
    "client_email",
    "card_number",
    "hst_number",
    "qst_number",
    "auth_code",
    "driver_name",
    "unit_number",
    "transaction_date",
    "site_number",
    "site_name",
    "site_city",
    "prov_st",
    "prod",
    "qty",
    "retail",
    "billed",
    "pre_tax_amt",
    "hst",
    "gst",
    "pst",
    "qst",
    "disc_rate",
    "disc_amt",
    "final_amt",
    "cur",
    "row_label",
    "product",
    "final_amount",
    "legend_code",
    "legend_product_name",
)


class FuelBvdImportError(Exception):
    def __init__(self, code: str, message: str, http_status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status


def fuel_bvd_row_to_dict(row: FuelBvd) -> dict[str, Any]:
    """Serialize a persisted row for API (DB values only)."""
    data: dict[str, Any] = {
        "id": row.id,
        "import_id": str(row.import_id),
        "row_type": row.row_type,
        "source_file_name": row.source_file_name,
        "source_file_sha256": row.source_file_sha256,
        "source_storage_ref": row.source_storage_ref,
        "source_page": row.source_page,
        "source_row_number": row.source_row_number,
        "parse_status": row.parse_status,
        "parser_version": row.parser_version,
        "extraction_warnings": row.extraction_warnings,
    }
    for name in BVD_SOURCE_FIELD_NAMES:
        data[name] = getattr(row, name)
    return data


def _apply_extracted_fields(target: FuelBvd, fields: dict[str, str | None]) -> None:
    for name in BVD_SOURCE_FIELD_NAMES:
        if name in fields:
            setattr(target, name, fields[name])


async def save_bvd_pdf_to_storage(
    *,
    tenant_slug: str,
    import_id: uuid.UUID,
    pdf_bytes: bytes,
    filename: str,
) -> tuple[str, str]:
    stored = await save_fuel_bvd_import_bytes(
        tenant_slug,
        str(import_id),
        pdf_bytes,
        filename_hint=filename,
    )
    return stored.storage_key, stored.sha256


async def import_bvd_digital_pdf(
    db: AsyncSession,
    *,
    tenant_id: int,
    tenant_slug: str,
    pdf_bytes: bytes,
    filename: str,
    uploaded_by: str | None,
) -> tuple[uuid.UUID, int, str]:
    """Store PDF, extract, insert fuel_bvd rows, commit. Does not touch fuel_transactions."""
    if not pdf_bytes.startswith(b"%PDF"):
        raise FuelBvdImportError("NOT_PDF", "Upload must be a PDF file", http_status=400)

    import_id = uuid.uuid4()
    started = datetime.now(timezone.utc)

    try:
        extracted, extract_warnings, parser_version = extract_bvd_rows_from_digital_pdf(pdf_bytes)
    except FuelBvdExtractionError as exc:
        raise FuelBvdImportError(exc.code, exc.message, http_status=422) from exc

    storage_key, sha256 = await save_bvd_pdf_to_storage(
        tenant_slug=tenant_slug,
        import_id=import_id,
        pdf_bytes=pdf_bytes,
        filename=filename,
    )

    completed = datetime.now(timezone.utc)
    duration_ms = int((completed - started).total_seconds() * 1000)
    parse_status = "SUCCESS"
    warnings_payload = {"messages": extract_warnings} if extract_warnings else None

    orm_rows: list[FuelBvd] = []
    for order, item in enumerate(extracted, start=1):
        row = FuelBvd(
            tenant_id=tenant_id,
            import_id=import_id,
            row_type=item.row_type,
            source_file_name=filename,
            source_file_sha256=sha256,
            source_storage_ref=storage_key,
            source_page=item.source_page,
            source_row_number=order,
            uploaded_at=started,
            uploaded_by=uploaded_by,
            processing_started_at=started,
            processing_completed_at=completed,
            processing_duration_ms=duration_ms,
            processed_by=uploaded_by,
            parser_version=parser_version,
            parse_status=parse_status,
            review_status="PENDING",
            extraction_warnings=warnings_payload,
        )
        _apply_extracted_fields(row, item.fields)
        orm_rows.append(row)
        db.add(row)

    await db.commit()
    return import_id, len(orm_rows), parse_status


async def list_bvd_import_rows(
    db: AsyncSession,
    *,
    tenant_id: int,
    import_id: uuid.UUID,
) -> list[FuelBvd]:
    result = await db.execute(
        select(FuelBvd)
        .where(
            FuelBvd.tenant_id == tenant_id,
            FuelBvd.import_id == import_id,
        )
        .order_by(FuelBvd.source_row_number.asc(), FuelBvd.id.asc())
    )
    return list(result.scalars().all())


async def get_bvd_import_storage_ref(
    db: AsyncSession,
    *,
    tenant_id: int,
    import_id: uuid.UUID,
) -> tuple[str, str | None] | None:
    result = await db.execute(
        select(FuelBvd.source_storage_ref, FuelBvd.source_file_name)
        .where(FuelBvd.tenant_id == tenant_id, FuelBvd.import_id == import_id)
        .limit(1)
    )
    row = result.first()
    if row is None:
        return None
    return row[0], row[1]


async def count_bvd_rows_for_tenant(db: AsyncSession, tenant_id: int) -> int:
    result = await db.execute(
        select(func.count()).select_from(FuelBvd).where(FuelBvd.tenant_id == tenant_id)
    )
    return int(result.scalar_one())
