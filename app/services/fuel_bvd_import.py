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
from app.services.fuel_bvd_completed_basic import (
    BVD_REVIEW_COMPLETE,
    build_bvd_completed_basic_projection,
)
from app.services.fuel_bvd_document_identity import (
    dedupe_bvd_headers_by_document_identity,
    header_row_to_list_item,
)
from app.services.fuel_source_duplicate_gate import (
    acquire_bvd_import_advisory_lock,
    check_bvd_pdf_duplicate_before_import,
    document_identity_from_extracted_rows,
    sha256_hex,
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
    "express_code",
    "express_tractor",
    "express_trailer",
    "express_cdl",
    "express_trip_number",
    "amount_cashed",
    "express_fee",
    "payee_raw",
    "notes_raw",
)


class FuelBvdImportNotFoundError(Exception):
    """Raised when a tenant-scoped BVD import_id does not exist."""


class FuelBvdImportError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        http_status: int = 400,
        *,
        detail: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status
        self.detail = detail or {}


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
    """Parse PDF into temporary staging only — fuel_bvd rows created on Process."""
    from app.services.fuel_bvd_stage import create_bvd_import_stage_from_pdf

    stage_id, row_count, parse_status, _reused = await create_bvd_import_stage_from_pdf(
        db,
        tenant_id=tenant_id,
        tenant_slug=tenant_slug,
        pdf_bytes=pdf_bytes,
        filename=filename,
        uploaded_by=uploaded_by,
    )
    return stage_id, row_count, parse_status


async def list_bvd_import_headers(
    db: AsyncSession,
    *,
    tenant_id: int,
    limit: int = 40,
    dedupe_by_document_identity: bool = True,
    review_status: str | None = None,
    exclude_review_status: str | None = None,
) -> list[dict[str, Any]]:
    """Recent BVD uploads (HEADER rows).

    When deduping, groups by full BVD document identity (tenant + provider + invoice # + dates),
    not invoice number alone. Legacy duplicates with the same identity collapse to one canonical row.
    """
    fetch_cap = limit * 24 if dedupe_by_document_identity else limit
    result = await db.execute(
        select(FuelBvd)
        .where(FuelBvd.tenant_id == tenant_id, FuelBvd.row_type == "HEADER")
        .order_by(FuelBvd.id.desc())
        .limit(fetch_cap)
    )
    filtered: list[FuelBvd] = []
    for row in result.scalars().all():
        status = row.review_status or "PENDING"
        if review_status is not None and status != review_status:
            continue
        # Do not apply exclude_review_status before identity dedupe — otherwise a
        # SOURCE_REVIEWED sibling is dropped and a stale IN_REVIEW duplicate surfaces.
        filtered.append(row)

    if dedupe_by_document_identity:
        chosen = dedupe_bvd_headers_by_document_identity(tenant_id, filtered, limit=limit)
    else:
        chosen = filtered[:limit]

    if exclude_review_status is not None:
        chosen = [
            row
            for row in chosen
            if (row.review_status or "PENDING") != exclude_review_status
        ]

    return [header_row_to_list_item(row) for row in chosen]


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
) -> tuple[str, str | None, str | None] | None:
    """Returns (storage_ref, filename, storage_module). module None means fuel_bvd."""
    from app.services.fuel_bvd_stage import get_stage_storage_ref

    staged = await get_stage_storage_ref(db, tenant_id=tenant_id, stage_id=import_id)
    if staged is not None:
        return staged[0], staged[1], "fuel_bvd_stage"

    result = await db.execute(
        select(FuelBvd.source_storage_ref, FuelBvd.source_file_name)
        .where(FuelBvd.tenant_id == tenant_id, FuelBvd.import_id == import_id)
        .limit(1)
    )
    row = result.first()
    if row is None:
        return None
    return row[0], row[1], None


async def count_bvd_rows_for_tenant(db: AsyncSession, tenant_id: int) -> int:
    result = await db.execute(
        select(func.count()).select_from(FuelBvd).where(FuelBvd.tenant_id == tenant_id)
    )
    return int(result.scalar_one())


async def get_bvd_completed_basic_projection(
    db: AsyncSession,
    *,
    tenant_id: int,
    import_id: uuid.UUID,
) -> dict[str, Any]:
    rows = await list_bvd_import_rows(db, tenant_id=tenant_id, import_id=import_id)
    if not rows:
        raise FuelBvdImportNotFoundError(str(import_id))
    dict_rows = [fuel_bvd_row_to_dict(r) for r in rows]
    header = next((r for r in rows if r.row_type == "HEADER"), None)
    review_status = header.review_status if header else None
    return build_bvd_completed_basic_projection(
        dict_rows,
        import_id=str(import_id),
        review_status=review_status,
    )


async def list_bvd_completed_history(
    db: AsyncSession,
    *,
    tenant_id: int,
    limit: int = 40,
) -> list[dict[str, Any]]:
    headers = await list_bvd_import_headers(
        db,
        tenant_id=tenant_id,
        limit=limit,
        dedupe_by_document_identity=True,
        review_status=BVD_REVIEW_COMPLETE,
    )
    out: list[dict[str, Any]] = []
    for item in headers:
        import_id = uuid.UUID(item["import_id"])
        out.append(
            await get_bvd_completed_basic_projection(
                db, tenant_id=tenant_id, import_id=import_id
            )
        )
    return out
