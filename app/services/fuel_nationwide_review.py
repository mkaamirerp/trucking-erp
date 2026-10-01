"""Nationwide import review + Process entry (staging-first)."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.fuel import FuelNationwide
from app.services.fuel_nationwide_effective import build_effective_nationwide_rows
from app.services.fuel_nationwide_import import (
    NATIONWIDE_SOURCE_FIELD_NAMES,
    NW_REVIEW_IN_PROGRESS,
    NW_REVIEW_SOURCE_COMPLETE,
)
from app.services.fuel_nationwide_source_reconciliation import reconcile_nationwide_source_rows
from app.services.fuel_nationwide_stage import (
    get_active_stage,
    list_stage_rows_for_review,
    process_nationwide_stage_to_permanent,
)

async def get_nationwide_import_review_summary(
    db: AsyncSession,
    *,
    tenant_id: int,
    import_id: uuid.UUID,
) -> dict[str, Any]:
    result = await db.execute(
        select(FuelNationwide)
        .where(FuelNationwide.tenant_id == tenant_id, FuelNationwide.import_id == import_id)
        .order_by(FuelNationwide.id.asc())
    )
    rows = list(result.scalars().all())
    if not rows:
        if await get_active_stage(db, tenant_id=tenant_id, stage_id=import_id) is not None:
            return {
                "import_id": str(import_id),
                "review_status": NW_REVIEW_IN_PROGRESS,
                "row_count": 0,
            }
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Nationwide import not found")
    header = next((r for r in rows if r.row_type == "HEADER"), None)
    return {
        "import_id": str(import_id),
        "review_status": rows[0].review_status or "PENDING",
        "row_count": len(rows),
        "invoice_number": header.invoice_number if header else None,
    }


def reconcile_nationwide_import_review_rows(rows: list[dict[str, Any]]):
    return reconcile_nationwide_source_rows(build_effective_nationwide_rows(rows))


async def list_nationwide_import_rows_for_review(
    db: AsyncSession,
    *,
    tenant_id: int,
    import_id: uuid.UUID,
) -> list[dict[str, Any]] | None:
    if await get_active_stage(db, tenant_id=tenant_id, stage_id=import_id) is not None:
        return await list_stage_rows_for_review(db, tenant_id=tenant_id, stage_id=import_id)
    result = await db.execute(
        select(FuelNationwide)
        .where(FuelNationwide.tenant_id == tenant_id, FuelNationwide.import_id == import_id)
        .order_by(FuelNationwide.source_row_number.asc(), FuelNationwide.id.asc())
    )
    orm_rows = list(result.scalars().all())
    if not orm_rows:
        return None
    out: list[dict[str, Any]] = []
    for row in orm_rows:
        data: dict[str, Any] = {
            "id": row.id,
            "import_id": str(import_id),
            "row_type": row.row_type,
            "source_page": row.source_page,
            "source_row_number": row.source_row_number,
            "field_corrections": {},
        }
        for name in NATIONWIDE_SOURCE_FIELD_NAMES:
            data[name] = getattr(row, name)
        out.append(data)
    return out


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
