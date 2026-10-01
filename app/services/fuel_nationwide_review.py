"""Nationwide import review + Process entry (staging-first)."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.fuel import FuelNationwide, FuelSourceBatch
from app.services.fuel_canonical import BATCH_STATUS_FINALIZED
from app.services.fuel_nationwide_canonical_projection import NATIONWIDE_VENDOR
from app.services.fuel_nationwide_completed_basic import build_nationwide_completed_basic_projection
from app.services.fuel_nationwide_card_total import apply_card_total_review_fields
from app.services.fuel_nationwide_effective import build_effective_nationwide_rows
from app.services.fuel_nationwide_import import (
    NATIONWIDE_SOURCE_FIELD_NAMES,
    NW_REVIEW_IN_PROGRESS,
    NW_REVIEW_SOURCE_COMPLETE,
    FuelNationwideImportError,
)
from app.services.fuel_nationwide_source_reconciliation import reconcile_nationwide_source_rows
from app.services.fuel_nationwide_stage import (
    get_active_stage,
    get_stage_storage_ref,
    list_stage_rows_for_review,
    process_nationwide_stage_to_permanent,
    save_nationwide_stage_import_review,
)

FUEL_NATIONWIDE_STORAGE_MODULE = "fuel_nationwide"


def fuel_nationwide_row_to_dict(row: FuelNationwide) -> dict[str, Any]:
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
        "review_status": row.review_status,
        "reviewed_at": row.reviewed_at.isoformat() if row.reviewed_at else None,
        "reviewed_by": row.reviewed_by,
    }
    for name in NATIONWIDE_SOURCE_FIELD_NAMES:
        data[name] = getattr(row, name)
    if data.get("row_type") == "CONTROL":
        apply_card_total_review_fields(data)
    return data


async def list_nationwide_import_rows_for_review(
    db: AsyncSession,
    *,
    tenant_id: int,
    import_id: uuid.UUID,
) -> list[dict[str, Any]] | None:
    staged = await list_stage_rows_for_review(db, tenant_id=tenant_id, stage_id=import_id)
    if staged:
        return staged
    result = await db.execute(
        select(FuelNationwide)
        .where(FuelNationwide.tenant_id == tenant_id, FuelNationwide.import_id == import_id)
        .order_by(FuelNationwide.source_row_number.asc(), FuelNationwide.id.asc())
    )
    orm_rows = list(result.scalars().all())
    if not orm_rows:
        return None
    return [{**fuel_nationwide_row_to_dict(r), "field_corrections": {}} for r in orm_rows]


def reconcile_nationwide_import_review_rows(rows: list[dict[str, Any]]):
    return reconcile_nationwide_source_rows(build_effective_nationwide_rows(rows))


async def get_nationwide_source_reconciliation_report(
    db: AsyncSession,
    *,
    tenant_id: int,
    import_id: uuid.UUID,
) -> dict[str, Any]:
    rows = await list_nationwide_import_rows_for_review(db, tenant_id=tenant_id, import_id=import_id)
    if not rows:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Nationwide import not found")
    return reconcile_nationwide_import_review_rows(rows).to_dict()


async def get_nationwide_import_review_summary(
    db: AsyncSession,
    *,
    tenant_id: int,
    import_id: uuid.UUID,
) -> dict[str, Any]:
    stage = await get_active_stage(db, tenant_id=tenant_id, stage_id=import_id)
    if stage is not None:
        rows = await list_stage_rows_for_review(db, tenant_id=tenant_id, stage_id=import_id)
        header = next((r for r in rows if r.get("row_type") == "HEADER"), None)
        transactions = [r for r in rows if r.get("row_type") == "TRANSACTION"]
        correction_count = sum(len(r.get("field_corrections") or {}) for r in rows)
        return {
            "import_id": str(import_id),
            "invoice_number": (header or {}).get("invoice_number"),
            "row_count": len(rows),
            "transaction_count": len(transactions),
            "correction_count": correction_count,
            "review_status": NW_REVIEW_IN_PROGRESS if correction_count else "PENDING",
            "account_code": (header or {}).get("account_code"),
        }

    rows = await list_nationwide_import_rows_for_review(db, tenant_id=tenant_id, import_id=import_id)
    if not rows:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Nationwide import not found")
    header = next((r for r in rows if r.get("row_type") == "HEADER"), rows[0])
    return {
        "import_id": str(import_id),
        "invoice_number": header.get("invoice_number"),
        "row_count": len(rows),
        "transaction_count": sum(1 for r in rows if r.get("row_type") == "TRANSACTION"),
        "correction_count": sum(len(r.get("field_corrections") or {}) for r in rows),
        "review_status": header.get("review_status") or NW_REVIEW_SOURCE_COMPLETE,
        "account_code": header.get("account_code"),
    }


async def save_nationwide_import_review(
    db: AsyncSession,
    *,
    tenant_id: int,
    import_id: uuid.UUID,
    reviewed_by: str,
    corrections: list[dict[str, Any]],
) -> int:
    if await get_active_stage(db, tenant_id=tenant_id, stage_id=import_id) is not None:
        return await save_nationwide_stage_import_review(
            db,
            tenant_id=tenant_id,
            stage_id=import_id,
            reviewed_by=reviewed_by,
            corrections=corrections,
        )
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Nationwide import not in active stage")


async def process_nationwide_import_review(
    db: AsyncSession,
    *,
    tenant_id: int,
    import_id: uuid.UUID,
    reviewed_by: str,
    review_reason: str | None = None,
    tenant_slug: str | None = None,
) -> dict[str, Any]:
    if await get_active_stage(db, tenant_id=tenant_id, stage_id=import_id) is not None:
        if not tenant_slug:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="tenant_slug required for Nationwide stage process",
            )
        return await process_nationwide_stage_to_permanent(
            db,
            tenant_id=tenant_id,
            tenant_slug=tenant_slug,
            stage_id=import_id,
            reviewed_by=reviewed_by,
            review_reason=review_reason,
        )
    summary = await get_nationwide_import_review_summary(db, tenant_id=tenant_id, import_id=import_id)
    if summary["review_status"] == NW_REVIEW_SOURCE_COMPLETE:
        return summary
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Nationwide import not in active stage")


async def get_nationwide_completed_basic_projection(
    db: AsyncSession,
    *,
    tenant_id: int,
    import_id: uuid.UUID,
) -> dict[str, Any]:
    rows = await list_nationwide_import_rows_for_review(db, tenant_id=tenant_id, import_id=import_id)
    if not rows:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Nationwide import not found")
    batch = await db.scalar(
        select(FuelSourceBatch).where(
            FuelSourceBatch.tenant_id == tenant_id,
            FuelSourceBatch.source_import_ref == str(import_id),
            FuelSourceBatch.provider_code == NATIONWIDE_VENDOR,
            FuelSourceBatch.status == BATCH_STATUS_FINALIZED,
        )
    )
    if batch is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Nationwide processed import not found")
    processed_at = batch.finalized_at.isoformat() if batch.finalized_at else None
    header = next((r for r in rows if r.get("row_type") == "HEADER"), None)
    return build_nationwide_completed_basic_projection(
        rows,
        import_id=str(import_id),
        review_status=(header or {}).get("review_status"),
        processed_at=processed_at,
    )


async def list_nationwide_completed_history(
    db: AsyncSession,
    *,
    tenant_id: int,
    limit: int = 40,
) -> list[dict[str, Any]]:
    result = await db.execute(
        select(FuelSourceBatch)
        .where(
            FuelSourceBatch.tenant_id == tenant_id,
            FuelSourceBatch.provider_code == NATIONWIDE_VENDOR,
            FuelSourceBatch.status == BATCH_STATUS_FINALIZED,
            FuelSourceBatch.source_import_ref.isnot(None),
        )
        .order_by(FuelSourceBatch.finalized_at.desc().nullslast(), FuelSourceBatch.id.desc())
        .limit(limit)
    )
    out: list[dict[str, Any]] = []
    for batch in result.scalars().all():
        import_id = uuid.UUID(str(batch.source_import_ref))
        out.append(
            await get_nationwide_completed_basic_projection(
                db, tenant_id=tenant_id, import_id=import_id
            )
        )
    return out


async def get_nationwide_import_storage_ref(
    db: AsyncSession,
    *,
    tenant_id: int,
    import_id: uuid.UUID,
) -> tuple[str, str | None, str] | None:
    staged = await get_stage_storage_ref(db, tenant_id=tenant_id, stage_id=import_id)
    if staged:
        return staged[0], staged[1], "fuel_nationwide_stage"
    result = await db.execute(
        select(FuelNationwide)
        .where(FuelNationwide.tenant_id == tenant_id, FuelNationwide.import_id == import_id)
        .limit(1)
    )
    row = result.scalar_one_or_none()
    if row is None or not row.source_storage_ref:
        return None
    return row.source_storage_ref, row.source_file_name, FUEL_NATIONWIDE_STORAGE_MODULE
