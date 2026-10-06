"""Toll PDF review persist + list/detail. No TollTransaction writes."""

from __future__ import annotations

import logging
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.storage import StoredFile, delete_toll_pdf_file, save_toll_pdf_file_bytes
from app.models.toll import (
    BATCH_STATUS_PARSED,
    FILE_FORMAT_PDF,
    PDF_PROFILE_EZPASS_WVPA_MONTHLY,
    PDF_PROFILES,
    REVIEW_STATUS_NEEDS_REVIEW,
    REVIEW_STATUS_RECONCILIATION_FAILED,
    SOURCE_TYPE_FILE,
    TollPdfReviewRow,
    TollPdfStatementReview,
    TollSourceBatch,
)
from app.services.toll_csv_intake import list_duplicate_batch_ids, sha256_hex
from app.services.toll_wvpa_pdf import (
    TollPdfIntakeError,
    TollPdfParseResult,
    parse_wvpa_monthly_statement_pdf,
    validate_toll_pdf_file,
)

logger = logging.getLogger(__name__)

PDF_REVIEW_LIST_LIMIT = 100
PDF_REVIEW_DETAIL_DEFAULT_LIMIT = 100
PDF_REVIEW_DETAIL_MAX_LIMIT = 500

TollPdfStoreBytes = Callable[..., Awaitable[StoredFile]]
TollPdfDeleteStored = Callable[..., None]


class TollPdfReviewError(Exception):
    def __init__(self, code: str, message: str, http_status: int = 404) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status


@dataclass(frozen=True)
class TollPdfPersistResult:
    batch_id: int
    source_type: str
    file_format: str
    profile_code: str
    filename: str
    source_hash: str
    status: str
    review_status: str
    duplicate_match_count: int
    duplicate_batch_ids: tuple[int, ...]
    statement_date: date | None
    account_number: str | None
    period_start: date | None
    period_end: date | None
    start_balance: Decimal | None
    end_balance: Decimal | None
    total_payment_amount: Decimal | None
    total_payment_count: int | None
    source_page_count: int | None
    source_total_trip_count: int | None
    source_total_trip_charge: Decimal | None
    parsed_trip_count: int
    parsed_total_trip_charge: Decimal
    trip_count_matches: bool
    trip_total_matches: bool
    reconciliation_ok: bool

    def as_api_dict(self) -> dict[str, Any]:
        return {
            "batch_id": self.batch_id,
            "source_type": self.source_type,
            "file_format": self.file_format,
            "profile_code": self.profile_code,
            "filename": self.filename,
            "source_hash": self.source_hash,
            "status": self.status,
            "review_status": self.review_status,
            "duplicate_match_count": self.duplicate_match_count,
            "duplicate_batch_ids": list(self.duplicate_batch_ids),
            "statement_date": self.statement_date.isoformat() if self.statement_date else None,
            "account_number": self.account_number,
            "period_start": self.period_start.isoformat() if self.period_start else None,
            "period_end": self.period_end.isoformat() if self.period_end else None,
            "start_balance": _dec(self.start_balance),
            "end_balance": _dec(self.end_balance),
            "total_payment_amount": _dec(self.total_payment_amount),
            "total_payment_count": self.total_payment_count,
            "source_page_count": self.source_page_count,
            "source_total_trip_count": self.source_total_trip_count,
            "source_total_trip_charge": _dec(self.source_total_trip_charge),
            "parsed_trip_count": self.parsed_trip_count,
            "parsed_total_trip_charge": _dec(self.parsed_total_trip_charge),
            "trip_count_matches": self.trip_count_matches,
            "trip_total_matches": self.trip_total_matches,
            "reconciliation_ok": self.reconciliation_ok,
        }


def _dec(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return format(value, "f")


def _iso(value: date | datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def _review_status(parsed: TollPdfParseResult) -> str:
    if parsed.reconciliation_ok:
        return REVIEW_STATUS_NEEDS_REVIEW
    return REVIEW_STATUS_RECONCILIATION_FAILED


async def persist_toll_pdf_file(
    db: AsyncSession,
    *,
    tenant_id: int,
    tenant_slug: str,
    filename: str,
    body: bytes,
    content_type: str | None = None,
    created_by: str | None = None,
    profile_code: str,
    store_bytes: TollPdfStoreBytes | None = None,
    delete_stored: TollPdfDeleteStored | None = None,
) -> TollPdfPersistResult:
    """Store original PDF and persist review-stage rows. No TollTransaction."""
    selected = (profile_code or "").strip()
    if not selected:
        raise TollPdfIntakeError(
            "TOLL_PDF_PROFILE_REQUIRED",
            "profile_code is required for Toll PDF intake",
        )
    if selected not in PDF_PROFILES:
        raise TollPdfIntakeError(
            "TOLL_PDF_PROFILE_NOT_IMPLEMENTED",
            f"Toll PDF profile {selected} is not implemented",
        )
    if selected != PDF_PROFILE_EZPASS_WVPA_MONTHLY:
        raise TollPdfIntakeError(
            "TOLL_PDF_PROFILE_NOT_IMPLEMENTED",
            f"Toll PDF profile {selected} is not implemented",
        )
    validate_toll_pdf_file(filename=filename, body=body, content_type=content_type)
    parsed = parse_wvpa_monthly_statement_pdf(body)
    source_hash = sha256_hex(body)
    duplicate_batch_ids = tuple(
        await list_duplicate_batch_ids(db, tenant_id=tenant_id, source_hash=source_hash)
    )
    intake_token = uuid.uuid4().hex
    save_original = store_bytes or save_toll_pdf_file_bytes
    remove_original = delete_stored or delete_toll_pdf_file
    stored: StoredFile | None = None
    captured: dict[str, Any] | None = None
    review_status = _review_status(parsed)
    try:
        stored = await save_original(
            tenant_slug,
            intake_token,
            body,
            filename_hint=filename,
        )
        batch = TollSourceBatch(
            tenant_id=tenant_id,
            source_type=SOURCE_TYPE_FILE,
            file_format=FILE_FORMAT_PDF,
            source_storage_ref=stored.storage_key,
            source_hash=source_hash,
            source_filename=filename,
            statement_start=parsed.period_start,
            statement_end=parsed.period_end,
            invoice_date=parsed.statement_date,
            account_reference=parsed.account_number,
            status=BATCH_STATUS_PARSED,
            created_by=created_by,
            updated_by=created_by,
        )
        db.add(batch)
        await db.flush()
        if batch.id is None:
            raise TollPdfIntakeError(
                "TOLL_PDF_PERSIST",
                "FILE batch was not assigned an id",
                http_status=500,
            )
        batch_id = int(batch.id)
        review = TollPdfStatementReview(
            tenant_id=tenant_id,
            batch_id=batch_id,
            profile_code=parsed.profile_code,
            parser_name=parsed.parser_name,
            parser_version=parsed.parser_version,
            statement_date=parsed.statement_date,
            account_number=parsed.account_number,
            period_start=parsed.period_start,
            period_end=parsed.period_end,
            start_balance=parsed.start_balance,
            end_balance=parsed.end_balance,
            total_payment_amount=parsed.total_payment_amount,
            total_payment_count=parsed.total_payment_count,
            source_total_trip_count=parsed.source_total_trip_count,
            source_total_trip_charge=parsed.source_total_trip_charge,
            parsed_trip_count=parsed.parsed_trip_count,
            parsed_total_trip_charge=parsed.parsed_total_trip_charge,
            trip_count_matches=parsed.trip_count_matches,
            trip_total_matches=parsed.trip_total_matches,
            reconciliation_ok=parsed.reconciliation_ok,
            review_status=review_status,
            source_page_count=parsed.source_page_count,
            source_metadata=dict(parsed.source_metadata),
        )
        db.add(review)
        for row in parsed.rows:
            db.add(
                TollPdfReviewRow(
                    tenant_id=tenant_id,
                    batch_id=batch_id,
                    source_row_order=row.source_row_order,
                    source_page_number=row.source_page_number,
                    post_date=row.post_date,
                    entry_date=row.entry_date,
                    entry_time=row.entry_time,
                    exit_date=row.exit_date,
                    exit_time=row.exit_time,
                    agency_raw=row.agency_raw,
                    entry_location=row.entry_location,
                    entry_lane=row.entry_lane,
                    exit_location=row.exit_location,
                    exit_lane=row.exit_lane,
                    transponder_number=row.transponder_number,
                    plate_number=row.plate_number,
                    trip_charge=row.trip_charge,
                    trip_charge_raw=row.trip_charge_raw,
                    source_group_transponder=row.source_group_transponder,
                    source_group_plate=row.source_group_plate,
                    provider_raw=dict(row.provider_raw),
                )
            )
        await db.flush()
        captured = {
            "batch_id": batch_id,
            "source_type": SOURCE_TYPE_FILE,
            "file_format": FILE_FORMAT_PDF,
            "profile_code": parsed.profile_code,
            "filename": filename,
            "source_hash": source_hash,
            "status": BATCH_STATUS_PARSED,
            "review_status": review_status,
            "duplicate_match_count": len(duplicate_batch_ids),
            "duplicate_batch_ids": duplicate_batch_ids,
            "statement_date": parsed.statement_date,
            "account_number": parsed.account_number,
            "period_start": parsed.period_start,
            "period_end": parsed.period_end,
            "start_balance": parsed.start_balance,
            "end_balance": parsed.end_balance,
            "total_payment_amount": parsed.total_payment_amount,
            "total_payment_count": parsed.total_payment_count,
            "source_page_count": parsed.source_page_count,
            "source_total_trip_count": parsed.source_total_trip_count,
            "source_total_trip_charge": parsed.source_total_trip_charge,
            "parsed_trip_count": parsed.parsed_trip_count,
            "parsed_total_trip_charge": parsed.parsed_total_trip_charge,
            "trip_count_matches": parsed.trip_count_matches,
            "trip_total_matches": parsed.trip_total_matches,
            "reconciliation_ok": parsed.reconciliation_ok,
        }
    except Exception:
        await db.rollback()
        if stored is not None:
            try:
                remove_original(stored.storage_key, tenant_slug=tenant_slug)
            except Exception:
                logger.exception(
                    "Toll PDF intake storage cleanup failed after DB rollback tenant_slug=%s",
                    tenant_slug,
                )
        raise
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        if stored is not None:
            try:
                remove_original(stored.storage_key, tenant_slug=tenant_slug)
            except Exception:
                logger.exception(
                    "Toll PDF intake storage cleanup failed after DB rollback tenant_slug=%s",
                    tenant_slug,
                )
        raise
    assert captured is not None
    return TollPdfPersistResult(**captured)


def _ilike_contains(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _clamp_detail_page(row_offset: int, row_limit: int) -> tuple[int, int]:
    offset = max(0, row_offset)
    if row_limit <= 0:
        limit = PDF_REVIEW_DETAIL_DEFAULT_LIMIT
    else:
        limit = min(row_limit, PDF_REVIEW_DETAIL_MAX_LIMIT)
    return offset, limit


def review_row_to_dict(row: TollPdfReviewRow) -> dict[str, Any]:
    return {
        "source_row_order": row.source_row_order,
        "source_page_number": row.source_page_number,
        "post_date": _iso(row.post_date),
        "entry_date": _iso(row.entry_date),
        "entry_time": row.entry_time,
        "exit_date": _iso(row.exit_date),
        "exit_time": row.exit_time,
        "agency_raw": row.agency_raw,
        "entry_location": row.entry_location,
        "entry_lane": row.entry_lane,
        "exit_location": row.exit_location,
        "exit_lane": row.exit_lane,
        "transponder_number": row.transponder_number,
        "plate_number": row.plate_number,
        "trip_charge": _dec(row.trip_charge),
        "trip_charge_raw": row.trip_charge_raw,
        "source_group_transponder": row.source_group_transponder,
        "source_group_plate": row.source_group_plate,
        "provider_raw": dict(row.provider_raw or {}),
    }


def statement_to_list_item(
    batch: TollSourceBatch,
    review: TollPdfStatementReview,
) -> dict[str, Any]:
    imported = getattr(batch, "imported_at", None)
    return {
        "batch_id": int(batch.id) if batch.id is not None else 0,
        "source_type": batch.source_type,
        "file_format": batch.file_format,
        "profile_code": review.profile_code,
        "filename": batch.source_filename,
        "source_hash": batch.source_hash,
        "status": batch.status,
        "review_status": review.review_status,
        "imported_at": imported.isoformat() if imported is not None else None,
        "statement_date": _iso(review.statement_date),
        "account_number": review.account_number,
        "period_start": _iso(review.period_start),
        "period_end": _iso(review.period_end),
        "source_total_trip_count": review.source_total_trip_count,
        "source_total_trip_charge": _dec(review.source_total_trip_charge),
        "parsed_trip_count": review.parsed_trip_count,
        "parsed_total_trip_charge": _dec(review.parsed_total_trip_charge),
        "trip_count_matches": review.trip_count_matches,
        "trip_total_matches": review.trip_total_matches,
        "reconciliation_ok": review.reconciliation_ok,
    }


async def list_toll_pdf_reviews(
    db: AsyncSession,
    *,
    tenant_id: int,
    q: str | None = None,
    limit: int = PDF_REVIEW_LIST_LIMIT,
) -> list[dict[str, Any]]:
    capped = max(0, min(limit, PDF_REVIEW_LIST_LIMIT))
    stmt = (
        select(TollSourceBatch, TollPdfStatementReview)
        .join(
            TollPdfStatementReview,
            (TollPdfStatementReview.tenant_id == TollSourceBatch.tenant_id)
            & (TollPdfStatementReview.batch_id == TollSourceBatch.id),
        )
        .where(
            TollSourceBatch.tenant_id == tenant_id,
            TollSourceBatch.source_type == SOURCE_TYPE_FILE,
            TollSourceBatch.file_format == FILE_FORMAT_PDF,
        )
        .order_by(TollSourceBatch.id.desc())
        .limit(capped)
    )
    needle = (q or "").strip()
    if needle:
        pattern = _ilike_contains(needle)
        stmt = stmt.where(
            or_(
                TollSourceBatch.source_filename.ilike(pattern, escape="\\"),
                TollSourceBatch.source_hash.ilike(pattern, escape="\\"),
                TollPdfStatementReview.account_number.ilike(pattern, escape="\\"),
            )
        )
    result = await db.execute(stmt)
    return [statement_to_list_item(batch, review) for batch, review in result.all()]


async def get_toll_pdf_review(
    db: AsyncSession,
    *,
    tenant_id: int,
    batch_id: int,
    row_offset: int = 0,
    row_limit: int = PDF_REVIEW_DETAIL_DEFAULT_LIMIT,
) -> dict[str, Any]:
    pair = (
        await db.execute(
            select(TollSourceBatch, TollPdfStatementReview)
            .join(
                TollPdfStatementReview,
                (TollPdfStatementReview.tenant_id == TollSourceBatch.tenant_id)
                & (TollPdfStatementReview.batch_id == TollSourceBatch.id),
            )
            .where(
                TollSourceBatch.tenant_id == tenant_id,
                TollSourceBatch.id == batch_id,
                TollSourceBatch.source_type == SOURCE_TYPE_FILE,
                TollSourceBatch.file_format == FILE_FORMAT_PDF,
            )
        )
    ).first()
    if pair is None:
        raise TollPdfReviewError("TOLL_PDF_NOT_FOUND", "Toll PDF review not found", http_status=404)
    batch, review = pair
    offset, limit = _clamp_detail_page(row_offset, row_limit)
    row_result = await db.execute(
        select(TollPdfReviewRow)
        .where(
            TollPdfReviewRow.tenant_id == tenant_id,
            TollPdfReviewRow.batch_id == batch_id,
        )
        .order_by(TollPdfReviewRow.source_row_order)
        .offset(offset)
        .limit(limit)
    )
    item = statement_to_list_item(batch, review)
    item["start_balance"] = _dec(review.start_balance)
    item["end_balance"] = _dec(review.end_balance)
    item["total_payment_amount"] = _dec(review.total_payment_amount)
    item["total_payment_count"] = review.total_payment_count
    item["source_page_count"] = review.source_page_count
    item["source_metadata"] = dict(review.source_metadata or {})
    item["total_row_count"] = review.parsed_trip_count
    item["row_offset"] = offset
    item["row_limit"] = limit
    item["rows"] = [review_row_to_dict(row) for row in row_result.scalars().all()]
    return item
