"""Append-only PDF review field corrections. Never mutates parser row evidence."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.toll import (
    REVIEW_STATUS_NEEDS_REVIEW,
    REVIEW_STATUS_PROCESSED,
    REVIEW_STATUS_RECONCILIATION_FAILED,
    TOLL_PDF_EDITABLE_FIELDS,
    TollPdfReviewFieldCorrection,
    TollPdfReviewRow,
    TollPdfStatementReview,
    TollSourceBatch,
)
from app.services.toll_pdf_effective import (
    build_effective_toll_pdf_rows,
    reconcile_effective_pdf_rows,
    stringify_raw,
)
from app.services.toll_pdf_review import TollPdfReviewError


class TollPdfCorrectionError(TollPdfReviewError):
    pass


def _normalize_corrected(field_name: str, value: Any) -> str | None:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if isinstance(value, float):
        raise TollPdfCorrectionError("TOLL_PDF_INVALID_CORRECTION", "corrected values must not be float")
    if field_name == "trip_charge":
        if isinstance(value, Decimal):
            return format(value, "f")
        try:
            return format(Decimal(str(value).strip().replace("$", "").replace(",", "")), "f")
        except InvalidOperation as exc:
            raise TollPdfCorrectionError("TOLL_PDF_INVALID_CORRECTION", "trip_charge must be a decimal") from exc
    if field_name in {"post_date", "entry_date", "exit_date"}:
        text = str(value).strip()
        if len(text) != 10 or text[4] != "-" or text[7] != "-":
            raise TollPdfCorrectionError("TOLL_PDF_INVALID_CORRECTION", f"{field_name} must be YYYY-MM-DD")
        return text
    return str(value).strip()


async def load_latest_corrections(
    db: AsyncSession,
    *,
    tenant_id: int,
    review_row_ids: list[int],
) -> dict[int, dict[str, dict[str, Any]]]:
    if not review_row_ids:
        return {}
    result = await db.execute(
        select(TollPdfReviewFieldCorrection)
        .where(
            TollPdfReviewFieldCorrection.tenant_id == tenant_id,
            TollPdfReviewFieldCorrection.review_row_id.in_(review_row_ids),
        )
        .order_by(TollPdfReviewFieldCorrection.id.asc())
    )
    latest: dict[int, dict[str, dict[str, Any]]] = {}
    for item in result.scalars().all():
        latest.setdefault(int(item.review_row_id), {})[item.field_name] = {
            "original_value": item.original_value,
            "corrected_value": item.corrected_value,
            "reason": item.reason,
            "changed_by": item.changed_by,
        }
    return latest


async def apply_pdf_review_corrections(
    db: AsyncSession,
    *,
    tenant_id: int,
    batch_id: int,
    row_id: int,
    fields: dict[str, Any],
    reason: str | None = None,
    changed_by: str | None = None,
) -> tuple[TollPdfReviewRow, dict[str, Any]]:
    pair = (
        await db.execute(
            select(TollSourceBatch, TollPdfStatementReview, TollPdfReviewRow)
            .join(
                TollPdfStatementReview,
                (TollPdfStatementReview.tenant_id == TollSourceBatch.tenant_id)
                & (TollPdfStatementReview.batch_id == TollSourceBatch.id),
            )
            .join(
                TollPdfReviewRow,
                (TollPdfReviewRow.tenant_id == TollSourceBatch.tenant_id)
                & (TollPdfReviewRow.batch_id == TollSourceBatch.id),
            )
            .where(
                TollSourceBatch.tenant_id == tenant_id,
                TollSourceBatch.id == batch_id,
                TollPdfReviewRow.id == row_id,
            )
        )
    ).first()
    if pair is None:
        raise TollPdfCorrectionError("TOLL_PDF_NOT_FOUND", "Toll PDF review row not found", http_status=404)
    _batch, review, row = pair
    if review.review_status == REVIEW_STATUS_PROCESSED:
        raise TollPdfCorrectionError("TOLL_PDF_PROCESSED_READONLY", "Processed PDF review is read-only")
    unknown = sorted(name for name in fields if name not in TOLL_PDF_EDITABLE_FIELDS)
    if unknown:
        raise TollPdfCorrectionError(
            "TOLL_PDF_FIELD_NOT_EDITABLE",
            f"Field {unknown[0]} cannot be corrected",
        )
    for field_name, raw_value in fields.items():
        original = stringify_raw(getattr(row, field_name))
        corrected = _normalize_corrected(field_name, raw_value)
        db.add(
            TollPdfReviewFieldCorrection(
                tenant_id=tenant_id,
                review_row_id=int(row.id),
                field_name=field_name,
                original_value=original,
                corrected_value=corrected,
                reason=reason,
                changed_by=changed_by,
            )
        )
    await db.flush()
    all_rows = list(
        (
            await db.execute(
                select(TollPdfReviewRow)
                .where(TollPdfReviewRow.tenant_id == tenant_id, TollPdfReviewRow.batch_id == batch_id)
                .order_by(TollPdfReviewRow.source_row_order)
            )
        ).scalars().all()
    )
    overlays = await load_latest_corrections(db, tenant_id=tenant_id, review_row_ids=[int(r.id) for r in all_rows])
    effective_rows = build_effective_toll_pdf_rows(all_rows, overlays)
    recon = reconcile_effective_pdf_rows(
        effective_rows,
        source_total_trip_count=review.source_total_trip_count,
        source_total_trip_charge=review.source_total_trip_charge,
    )
    review.trip_count_matches = recon["trip_count_matches"]
    review.trip_total_matches = recon["trip_total_matches"]
    review.reconciliation_ok = recon["reconciliation_ok"]
    review.review_status = (
        REVIEW_STATUS_NEEDS_REVIEW if recon["reconciliation_ok"] else REVIEW_STATUS_RECONCILIATION_FAILED
    )
    await db.commit()
    return row, recon
