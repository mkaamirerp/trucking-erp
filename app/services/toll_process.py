"""Toll Process: effective review rows → canonical TollTransaction. No unit mapping."""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.toll import (
    BATCH_STATUS_PROCESSED,
    MANUAL_STAGE_DISCARDED,
    MANUAL_STAGE_DRAFT,
    MANUAL_STAGE_NEEDS_REVIEW,
    MANUAL_STAGE_PROCESSED,
    READ_TYPE_DEVICE,
    READ_TYPE_PLATE,
    REVIEW_STATUS_PROCESSED,
    SOURCE_TYPE_FILE,
    SOURCE_TYPE_MANUAL,
    TRANSACTION_TYPE_NORMAL,
    TollManualEntryStage,
    TollPdfReviewRow,
    TollPdfStatementReview,
    TollSourceBatch,
    TollTransaction,
)
from app.services.toll_manual_entry import TollManualEntryError
from app.services.toll_pdf_corrections import load_latest_corrections
from app.services.toll_pdf_effective import build_effective_toll_pdf_rows, reconcile_effective_pdf_rows
from app.services.toll_pdf_review import TollPdfReviewError


class TollProcessError(Exception):
    def __init__(self, code: str, message: str, http_status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status


def _read_type(transponder: str | None, plate: str | None) -> str | None:
    if transponder:
        return READ_TYPE_DEVICE
    if plate:
        return READ_TYPE_PLATE
    return None


def _datetime_source(entry_date: str | None, entry_time: str | None, post_date: str | None) -> str:
    if entry_date and entry_time:
        return f"{entry_date} {entry_time}"
    if entry_date:
        return entry_date
    if post_date:
        return post_date
    return "unspecified"


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    return date.fromisoformat(value)


def _accepted_snapshot(effective: dict[str, Any], extra: dict[str, Any]) -> dict[str, Any]:
    snapshot = {
        "row_id": effective.get("row_id"),
        "source_row_order": effective.get("source_row_order"),
        "post_date": effective.get("post_date"),
        "entry_date": effective.get("entry_date"),
        "entry_time": effective.get("entry_time"),
        "exit_date": effective.get("exit_date"),
        "exit_time": effective.get("exit_time"),
        "agency_raw": effective.get("agency_raw"),
        "entry_location": effective.get("entry_location"),
        "entry_lane": effective.get("entry_lane"),
        "exit_location": effective.get("exit_location"),
        "exit_lane": effective.get("exit_lane"),
        "transponder_number": effective.get("transponder_number"),
        "plate_number": effective.get("plate_number"),
        "trip_charge": effective.get("trip_charge"),
        "changed_fields": list(effective.get("changed_fields") or []),
        "corrections": dict(effective.get("corrections") or {}),
    }
    snapshot.update(extra)
    return snapshot


async def _existing_process_result(
    db: AsyncSession,
    *,
    tenant_id: int,
    batch_id: int,
    source_id: str,
    recon: dict[str, Any],
) -> dict[str, Any]:
    count = await db.scalar(
        select(func.count()).select_from(TollTransaction).where(
            TollTransaction.tenant_id == tenant_id,
            TollTransaction.batch_id == batch_id,
        )
    )
    total = await db.scalar(
        select(func.coalesce(func.sum(TollTransaction.amount), 0)).where(
            TollTransaction.tenant_id == tenant_id,
            TollTransaction.batch_id == batch_id,
        )
    )
    return {
        "source_id": source_id,
        "processed_transaction_count": int(count or 0),
        "processed_total": format(Decimal(str(total or 0)), "f"),
        "reconciliation": recon,
        "process_status": BATCH_STATUS_PROCESSED,
        "idempotent_replay": True,
    }


async def process_toll_pdf_review(
    db: AsyncSession,
    *,
    tenant_id: int,
    batch_id: int,
    processed_by: str | None = None,
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
            )
        )
    ).first()
    if pair is None:
        raise TollPdfReviewError("TOLL_PDF_NOT_FOUND", "Toll PDF review not found", http_status=404)
    batch, review = pair
    rows = list(
        (
            await db.execute(
                select(TollPdfReviewRow)
                .where(TollPdfReviewRow.tenant_id == tenant_id, TollPdfReviewRow.batch_id == batch_id)
                .order_by(TollPdfReviewRow.source_row_order)
            )
        ).scalars().all()
    )
    overlays = await load_latest_corrections(db, tenant_id=tenant_id, review_row_ids=[int(r.id) for r in rows])
    effective_rows = build_effective_toll_pdf_rows(rows, overlays)
    recon = reconcile_effective_pdf_rows(
        effective_rows,
        source_total_trip_count=review.source_total_trip_count,
        source_total_trip_charge=review.source_total_trip_charge,
    )
    if review.review_status == REVIEW_STATUS_PROCESSED or batch.status == BATCH_STATUS_PROCESSED:
        return await _existing_process_result(
            db, tenant_id=tenant_id, batch_id=batch_id, source_id=str(batch_id), recon=recon
        )
    if not recon["reconciliation_ok"]:
        review.reconciliation_ok = False
        review.trip_count_matches = recon["trip_count_matches"]
        review.trip_total_matches = recon["trip_total_matches"]
        review.review_status = "RECONCILIATION_FAILED"
        await db.commit()
        raise TollProcessError(
            "TOLL_RECONCILIATION_FAILED",
            "Effective PDF rows do not match source statement controls",
        )
    try:
        for row, effective in zip(rows, effective_rows, strict=True):
            transponder = effective.get("transponder_number")
            plate = effective.get("plate_number")
            snapshot = _accepted_snapshot(
                effective,
                {
                    "source_type": SOURCE_TYPE_FILE,
                    "file_format": batch.file_format,
                    "batch_id": int(batch.id),
                    "pdf_review_row_id": int(row.id),
                    "profile_code": review.profile_code,
                    "processed_by": processed_by,
                },
            )
            db.add(
                TollTransaction(
                    tenant_id=tenant_id,
                    batch_id=int(batch.id),
                    pdf_review_row_id=int(row.id),
                    source_row_order=int(row.source_row_order),
                    source_row_id=str(row.id),
                    transaction_datetime_source=_datetime_source(
                        effective.get("entry_date"),
                        effective.get("entry_time"),
                        effective.get("post_date"),
                    ),
                    transaction_date=_parse_date(effective.get("entry_date") or effective.get("post_date")),
                    post_date=_parse_date(effective.get("post_date")),
                    truck_id=None,
                    unit_number_snapshot=None,
                    toll_agency_code=effective.get("agency_raw"),
                    amount=effective["trip_charge_decimal"],
                    transaction_type=TRANSACTION_TYPE_NORMAL,
                    read_type=_read_type(transponder, plate),
                    device_number=transponder,
                    plate_number=plate,
                    accepted_effective_json=snapshot,
                    provider_raw={
                        "source_type": SOURCE_TYPE_FILE,
                        "file_format": batch.file_format,
                        "pdf_review_row_id": int(row.id),
                        "source_row_order": int(row.source_row_order),
                        "entry_location": effective.get("entry_location"),
                        "entry_lane": effective.get("entry_lane"),
                        "exit_location": effective.get("exit_location"),
                        "exit_lane": effective.get("exit_lane"),
                    },
                )
            )
        await db.flush()
        batch.status = BATCH_STATUS_PROCESSED
        batch.updated_by = processed_by
        review.review_status = REVIEW_STATUS_PROCESSED
        review.reconciliation_ok = True
        review.trip_count_matches = True
        review.trip_total_matches = True
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    return {
        "source_id": str(batch_id),
        "processed_transaction_count": len(effective_rows),
        "processed_total": recon["effective_total_trip_charge"],
        "reconciliation": recon,
        "process_status": BATCH_STATUS_PROCESSED,
        "idempotent_replay": False,
    }


async def process_toll_manual_stage(
    db: AsyncSession,
    *,
    tenant_id: int,
    stage_id: int,
    processed_by: str | None = None,
) -> dict[str, Any]:
    stage = await db.scalar(
        select(TollManualEntryStage).where(
            TollManualEntryStage.tenant_id == tenant_id,
            TollManualEntryStage.id == stage_id,
        )
    )
    if stage is None:
        raise TollManualEntryError("TOLL_MANUAL_NOT_FOUND", "Manual Toll stage not found", http_status=404)
    if stage.status == MANUAL_STAGE_DISCARDED:
        raise TollProcessError(
            "TOLL_MANUAL_DISCARDED",
            "Discarded manual stages cannot Process",
        )
    if stage.status == MANUAL_STAGE_DRAFT:
        raise TollProcessError("TOLL_MANUAL_NOT_READY", "DRAFT manual stages cannot Process")
    if stage.status == MANUAL_STAGE_PROCESSED:
        existing = await db.scalar(
            select(TollTransaction).where(
                TollTransaction.tenant_id == tenant_id,
                TollTransaction.manual_stage_id == stage_id,
            )
        )
        amount = existing.amount if existing is not None else Decimal("0")
        return {
            "source_id": str(stage_id),
            "processed_transaction_count": 1 if existing is not None else 0,
            "processed_total": format(amount, "f"),
            "reconciliation": {"reconciliation_ok": True},
            "process_status": MANUAL_STAGE_PROCESSED,
            "idempotent_replay": True,
        }
    if stage.status != MANUAL_STAGE_NEEDS_REVIEW:
        raise TollProcessError("TOLL_MANUAL_NOT_READY", "Manual stage is not ready to Process")
    if stage.trip_charge is None:
        raise TollProcessError("TOLL_MANUAL_NOT_READY", "Manual stage has no trip charge")
    source_import_ref = f"manual-stage-{int(stage.id)}"
    try:
        batch = await db.scalar(
            select(TollSourceBatch).where(
                TollSourceBatch.tenant_id == tenant_id,
                TollSourceBatch.source_type == SOURCE_TYPE_MANUAL,
                TollSourceBatch.source_import_ref == source_import_ref,
            )
        )
        if batch is None:
            batch = TollSourceBatch(
                tenant_id=tenant_id,
                source_type=SOURCE_TYPE_MANUAL,
                file_format=None,
                provider_code=None,
                provider_connection_id=None,
                account_reference=None,
                source_storage_ref=None,
                source_hash=None,
                source_filename=None,
                source_import_ref=source_import_ref,
                statement_start=None,
                statement_end=None,
                invoice_number=None,
                invoice_date=None,
                csv_raw_header_names=None,
                csv_column_keys=None,
                csv_parsed_row_count=None,
                csv_skipped_blank_row_count=None,
                csv_parser_name=None,
                csv_parser_version=None,
                csv_encoding=None,
                csv_delimiter=None,
                status=BATCH_STATUS_PROCESSED,
                created_by=processed_by,
                updated_by=processed_by,
            )
            db.add(batch)
            await db.flush()
        event_date = stage.event_date.isoformat() if stage.event_date else None
        post_date = stage.post_date.isoformat() if stage.post_date else None
        snapshot = {
            "source_type": SOURCE_TYPE_MANUAL,
            "file_format": None,
            "manual_stage_id": int(stage.id),
            "event_date": event_date,
            "event_time": stage.event_time,
            "post_date": post_date,
            "agency_raw": stage.agency_raw,
            "entry_location": stage.entry_location,
            "entry_lane": stage.entry_lane,
            "exit_location": stage.exit_location,
            "exit_lane": stage.exit_lane,
            "transponder_number": stage.transponder_number,
            "plate_number": stage.plate_number,
            "plate_state": stage.plate_state,
            "trip_charge": format(stage.trip_charge, "f"),
            "currency": stage.currency,
            "notes": stage.notes,
            "vehicle_identity_status": stage.vehicle_identity_status,
        }
        db.add(
            TollTransaction(
                tenant_id=tenant_id,
                batch_id=int(batch.id),
                manual_stage_id=int(stage.id),
                source_row_order=1,
                source_row_id=f"manual-{stage.id}",
                transaction_datetime_source=_datetime_source(event_date, stage.event_time, post_date),
                transaction_date=stage.event_date or stage.post_date,
                post_date=stage.post_date,
                truck_id=None,
                unit_number_snapshot=None,
                toll_agency_code=stage.agency_raw,
                amount=stage.trip_charge,
                transaction_type=TRANSACTION_TYPE_NORMAL,
                read_type=_read_type(stage.transponder_number, stage.plate_number),
                device_number=stage.transponder_number,
                plate_number=stage.plate_number,
                accepted_effective_json=snapshot,
                provider_raw={
                    "source_type": SOURCE_TYPE_MANUAL,
                    "file_format": None,
                    "manual_stage_id": int(stage.id),
                    "entry_location": stage.entry_location,
                    "entry_lane": stage.entry_lane,
                    "exit_location": stage.exit_location,
                    "exit_lane": stage.exit_lane,
                },
            )
        )
        await db.flush()
        stage.status = MANUAL_STAGE_PROCESSED
        stage.updated_by = processed_by
        evidence = dict(stage.source_evidence_json or {})
        evidence["processed_at"] = datetime.now(timezone.utc).isoformat()
        stage.source_evidence_json = evidence
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    return {
        "source_id": str(stage_id),
        "processed_transaction_count": 1,
        "processed_total": format(stage.trip_charge, "f"),
        "reconciliation": {"reconciliation_ok": True},
        "process_status": MANUAL_STAGE_PROCESSED,
        "idempotent_replay": False,
    }
