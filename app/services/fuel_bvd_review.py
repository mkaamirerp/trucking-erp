"""BVD Implementation 1 — human review workflow (no financial posting)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.fuel import FuelBvd, FuelBvdFieldCorrection
from app.services.fuel_bvd_import import BVD_SOURCE_FIELD_NAMES, fuel_bvd_row_to_dict

BVD_REVIEW_PENDING = "PENDING"
BVD_REVIEW_IN_PROGRESS = "IN_REVIEW"
BVD_REVIEW_SOURCE_COMPLETE = "SOURCE_REVIEWED"

EDITABLE_BVD_FIELDS: frozenset[str] = frozenset(BVD_SOURCE_FIELD_NAMES)


def _serialize_correction(c: FuelBvdFieldCorrection) -> dict[str, Any]:
    return {
        "field_name": c.field_name,
        "extracted_value": c.extracted_value,
        "reviewed_value": c.reviewed_value,
        "reviewed_by": c.reviewed_by,
        "reviewed_at": c.reviewed_at.isoformat() if c.reviewed_at else None,
        "correction_reason": c.correction_reason,
    }


async def _latest_corrections_by_row(
    db: AsyncSession,
    *,
    tenant_id: int,
    import_id: uuid.UUID,
) -> dict[int, dict[str, dict[str, Any]]]:
    """Latest correction per (fuel_bvd_id, field_name)."""
    result = await db.execute(
        select(FuelBvdFieldCorrection)
        .where(
            FuelBvdFieldCorrection.tenant_id == tenant_id,
            FuelBvdFieldCorrection.import_id == import_id,
        )
        .order_by(FuelBvdFieldCorrection.id.desc())
    )
    out: dict[int, dict[str, dict[str, Any]]] = {}
    for row in result.scalars().all():
        per_row = out.setdefault(row.fuel_bvd_id, {})
        if row.field_name not in per_row:
            per_row[row.field_name] = _serialize_correction(row)
    return out


def fuel_bvd_row_to_review_dict(
    row: FuelBvd,
    corrections: dict[str, dict[str, Any]] | None,
) -> dict[str, Any]:
    data = fuel_bvd_row_to_dict(row)
    data["review_status"] = row.review_status
    data["reviewed_at"] = row.reviewed_at.isoformat() if row.reviewed_at else None
    data["reviewed_by"] = row.reviewed_by
    data["field_corrections"] = corrections or {}
    return data


async def list_bvd_import_rows_for_review(
    db: AsyncSession,
    *,
    tenant_id: int,
    import_id: uuid.UUID,
) -> list[dict[str, Any]]:
    from app.services.fuel_bvd_import import list_bvd_import_rows

    rows = await list_bvd_import_rows(db, tenant_id=tenant_id, import_id=import_id)
    if not rows:
        return []
    try:
        corr_map = await _latest_corrections_by_row(db, tenant_id=tenant_id, import_id=import_id)
    except Exception as exc:
        if "fuel_bvd_field_correction" in str(exc) or "does not exist" in str(exc):
            corr_map = {}
        else:
            raise
    return [fuel_bvd_row_to_review_dict(r, corr_map.get(r.id)) for r in rows]


async def get_bvd_import_review_summary(
    db: AsyncSession,
    *,
    tenant_id: int,
    import_id: uuid.UUID,
) -> dict[str, Any]:
    rows = await list_bvd_import_rows_for_review(db, tenant_id=tenant_id, import_id=import_id)
    if not rows:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="BVD import not found")

    header = next((r for r in rows if r["row_type"] == "HEADER"), rows[0])
    invoice_number = header.get("invoice_number") or "—"
    txn_count = sum(1 for r in rows if r["row_type"] == "TRANSACTION")
    correction_count = sum(len(r.get("field_corrections") or {}) for r in rows)
    review_status = header.get("review_status") or BVD_REVIEW_PENDING

    final_amt = None
    cur = None
    for r in rows:
        if r["row_type"] == "GRAND_TOTAL" and r.get("final_amt"):
            final_amt = r["final_amt"]
            cur = r.get("cur")
            break

    return {
        "import_id": str(import_id),
        "invoice_number": invoice_number,
        "row_count": len(rows),
        "transaction_count": txn_count,
        "correction_count": correction_count,
        "review_status": review_status,
        "final_amount": final_amt,
        "currency": cur,
    }


async def save_bvd_import_review(
    db: AsyncSession,
    *,
    tenant_id: int,
    import_id: uuid.UUID,
    reviewed_by: str,
    corrections: list[dict[str, Any]],
) -> int:
    """Append correction rows; does not mutate fuel_bvd source columns."""
    if not corrections:
        await db.execute(
            update(FuelBvd)
            .where(FuelBvd.tenant_id == tenant_id, FuelBvd.import_id == import_id)
            .values(review_status=BVD_REVIEW_IN_PROGRESS)
        )
        await db.commit()
        return 0

    row_ids = {int(c["fuel_bvd_id"]) for c in corrections if "fuel_bvd_id" in c}
    result = await db.execute(
        select(FuelBvd).where(
            FuelBvd.tenant_id == tenant_id,
            FuelBvd.import_id == import_id,
            FuelBvd.id.in_(row_ids),
        )
    )
    by_id = {r.id: r for r in result.scalars().all()}
    if len(by_id) != len(row_ids):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid fuel_bvd row id")

    now = datetime.now(timezone.utc)
    written = 0
    for item in corrections:
        row_id = int(item["fuel_bvd_id"])
        field_name = str(item["field_name"])
        if field_name not in EDITABLE_BVD_FIELDS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Field not editable: {field_name}",
            )
        row = by_id[row_id]
        extracted = getattr(row, field_name)
        extracted_str = "" if extracted is None else str(extracted)
        reviewed_value = str(item.get("reviewed_value", ""))
        if reviewed_value == extracted_str:
            continue
        db.add(
            FuelBvdFieldCorrection(
                tenant_id=tenant_id,
                import_id=import_id,
                fuel_bvd_id=row_id,
                field_name=field_name,
                extracted_value=extracted_str,
                reviewed_value=reviewed_value,
                reviewed_by=reviewed_by,
                reviewed_at=now,
                correction_reason=item.get("correction_reason"),
            )
        )
        written += 1

    await db.execute(
        update(FuelBvd)
        .where(FuelBvd.tenant_id == tenant_id, FuelBvd.import_id == import_id)
        .values(review_status=BVD_REVIEW_IN_PROGRESS)
    )
    await db.commit()
    return written


async def process_bvd_import_review(
    db: AsyncSession,
    *,
    tenant_id: int,
    import_id: uuid.UUID,
    reviewed_by: str,
    review_reason: str | None = None,
) -> dict[str, Any]:
    """Mark import source review complete — not settlement/posting."""
    summary = await get_bvd_import_review_summary(db, tenant_id=tenant_id, import_id=import_id)
    if summary["review_status"] == BVD_REVIEW_SOURCE_COMPLETE:
        return summary

    now = datetime.now(timezone.utc)
    await db.execute(
        update(FuelBvd)
        .where(FuelBvd.tenant_id == tenant_id, FuelBvd.import_id == import_id)
        .values(
            review_status=BVD_REVIEW_SOURCE_COMPLETE,
            reviewed_by=reviewed_by,
            reviewed_at=now,
            review_reason=review_reason or "BVD source review confirmed",
        )
    )
    await db.commit()
    summary["review_status"] = BVD_REVIEW_SOURCE_COMPLETE
    return summary
