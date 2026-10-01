"""Nationwide import staging — temporary upload/review before Process commits fuel_nationwide."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.storage import (
    get_storage,
    purge_fuel_nationwide_import_files,
    purge_fuel_nationwide_stage_files,
    save_fuel_nationwide_import_bytes,
    save_fuel_nationwide_stage_bytes,
)
from app.models.fuel import (
    FuelNationwide,
    FuelNationwideImportStage,
    FuelNationwideStageFieldCorrection,
    FuelNationwideStageRow,
    FuelSourceBatch,
    FuelTransaction,
)
from app.services.fuel_nationwide_canonical_projection import (
    FuelNationwideCanonicalProjectionError,
    assert_nationwide_canonical_money_gate,
    build_fuel_source_batch,
    finalize_batch,
    project_nationwide_rows_to_canonical,
)
from app.services.fuel_nationwide_correction_validate import (
    EDITABLE_NATIONWIDE_FIELDS,
    NationwideCorrectionValidationError,
    validate_reviewed_nationwide_field,
)
from app.services.fuel_nationwide_effective import build_effective_nationwide_rows
from app.services.fuel_nationwide_extraction import (
    FuelNationwideExtractionError,
    extract_nationwide_rows_from_digital_pdf,
)
from app.services.fuel_nationwide_import import (
    NATIONWIDE_SOURCE_FIELD_NAMES,
    ROW_HEADER,
    ROW_TRANSACTION,
    FuelNationwideImportError,
)
from app.services.fuel_nationwide_import import NW_REVIEW_IN_PROGRESS, NW_REVIEW_SOURCE_COMPLETE
from app.services.fuel_nationwide_card_total import apply_card_total_review_fields
from app.services.fuel_nationwide_source_reconciliation import reconcile_nationwide_source_rows
from app.services.fuel_source_duplicate_gate import (
    acquire_nationwide_import_advisory_lock,
    check_nationwide_pdf_duplicate_before_import,
    document_identity_from_nationwide_rows,
    sha256_hex,
)

logger = logging.getLogger(__name__)

STAGE_STATUS_ACTIVE = "ACTIVE"
STAGE_TTL_HOURS = 24


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _apply_fields(target: Any, fields: dict[str, str | None]) -> None:
    for name in NATIONWIDE_SOURCE_FIELD_NAMES:
        if name in fields:
            setattr(target, name, fields[name])


async def get_active_stage(
    db: AsyncSession,
    *,
    tenant_id: int,
    stage_id: uuid.UUID,
) -> FuelNationwideImportStage | None:
    result = await db.execute(
        select(FuelNationwideImportStage).where(
            FuelNationwideImportStage.tenant_id == tenant_id,
            FuelNationwideImportStage.stage_id == stage_id,
            FuelNationwideImportStage.status == STAGE_STATUS_ACTIVE,
            FuelNationwideImportStage.expires_at > _utcnow(),
        )
    )
    return result.scalar_one_or_none()


async def _latest_stage_corrections(
    db: AsyncSession,
    *,
    tenant_id: int,
    stage_id: uuid.UUID,
) -> dict[int, dict[str, dict[str, Any]]]:
    result = await db.execute(
        select(FuelNationwideStageFieldCorrection)
        .where(
            FuelNationwideStageFieldCorrection.tenant_id == tenant_id,
            FuelNationwideStageFieldCorrection.stage_id == stage_id,
        )
        .order_by(FuelNationwideStageFieldCorrection.id.desc())
    )
    out: dict[int, dict[str, dict[str, Any]]] = {}
    for row in result.scalars().all():
        per_row = out.setdefault(row.stage_row_id, {})
        if row.field_name not in per_row:
            per_row[row.field_name] = {
                "field_name": row.field_name,
                "extracted_value": row.extracted_value,
                "reviewed_value": row.reviewed_value,
                "reviewed_by": row.reviewed_by,
                "reviewed_at": row.reviewed_at.isoformat() if row.reviewed_at else None,
                "correction_reason": row.correction_reason,
            }
    return out


def stage_row_to_dict(row: FuelNationwideStageRow, stage: FuelNationwideImportStage) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": row.id,
        "import_id": str(stage.stage_id),
        "row_type": row.row_type,
        "source_page": row.source_page,
        "source_row_number": row.source_row_number,
        "review_status": NW_REVIEW_IN_PROGRESS,
    }
    for name in NATIONWIDE_SOURCE_FIELD_NAMES:
        data[name] = getattr(row, name)
    apply_card_total_review_fields(data)
    return data


async def list_stage_rows_for_review(
    db: AsyncSession,
    *,
    tenant_id: int,
    stage_id: uuid.UUID,
) -> list[dict[str, Any]]:
    stage = await get_active_stage(db, tenant_id=tenant_id, stage_id=stage_id)
    if stage is None:
        return []
    result = await db.execute(
        select(FuelNationwideStageRow)
        .where(FuelNationwideStageRow.tenant_id == tenant_id, FuelNationwideStageRow.stage_id == stage_id)
        .order_by(FuelNationwideStageRow.source_row_number.asc(), FuelNationwideStageRow.id.asc())
    )
    rows = list(result.scalars().all())
    corr_map = await _latest_stage_corrections(db, tenant_id=tenant_id, stage_id=stage_id)
    out: list[dict[str, Any]] = []
    for row in rows:
        data = stage_row_to_dict(row, stage)
        data["field_corrections"] = corr_map.get(row.id) or {}
        out.append(data)
    return out


async def _delete_stage_records(
    db: AsyncSession,
    *,
    tenant_id: int,
    stage_id: uuid.UUID,
    tenant_slug: str,
) -> None:
    await db.execute(
        delete(FuelNationwideStageFieldCorrection).where(
            FuelNationwideStageFieldCorrection.tenant_id == tenant_id,
            FuelNationwideStageFieldCorrection.stage_id == stage_id,
        )
    )
    await db.execute(
        delete(FuelNationwideStageRow).where(
            FuelNationwideStageRow.tenant_id == tenant_id,
            FuelNationwideStageRow.stage_id == stage_id,
        )
    )
    await db.execute(
        delete(FuelNationwideImportStage).where(
            FuelNationwideImportStage.tenant_id == tenant_id,
            FuelNationwideImportStage.stage_id == stage_id,
        )
    )
    await db.commit()
    try:
        purge_fuel_nationwide_stage_files(tenant_slug, str(stage_id))
    except Exception:
        logger.exception("fuel_nationwide_stage purge failed stage_id=%s", stage_id)


async def save_nationwide_stage_import_review(
    db: AsyncSession,
    *,
    tenant_id: int,
    stage_id: uuid.UUID,
    reviewed_by: str,
    corrections: list[dict[str, Any]],
) -> int:
    stage = await get_active_stage(db, tenant_id=tenant_id, stage_id=stage_id)
    if stage is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Nationwide stage not found")
    if not corrections:
        return 0
    row_ids = {int(c["fuel_nationwide_id"]) for c in corrections if "fuel_nationwide_id" in c}
    result = await db.execute(
        select(FuelNationwideStageRow).where(
            FuelNationwideStageRow.tenant_id == tenant_id,
            FuelNationwideStageRow.stage_id == stage_id,
            FuelNationwideStageRow.id.in_(row_ids),
        )
    )
    by_id = {r.id: r for r in result.scalars().all()}
    if len(by_id) != len(row_ids):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid stage row id")
    now = _utcnow()
    written = 0
    for item in corrections:
        row_id = int(item["fuel_nationwide_id"])
        field_name = str(item["field_name"])
        if field_name not in EDITABLE_NATIONWIDE_FIELDS:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Field not editable: {field_name}")
        row = by_id[row_id]
        extracted = getattr(row, field_name)
        extracted_str = "" if extracted is None else str(extracted)
        reviewed_value = str(item.get("reviewed_value", ""))
        if reviewed_value == extracted_str:
            continue
        try:
            validate_reviewed_nationwide_field(field_name, reviewed_value, row_type=row.row_type)
        except NationwideCorrectionValidationError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "NATIONWIDE_CORRECTION_INVALID", "field": exc.field_name, "message": str(exc)},
            ) from exc
        db.add(
            FuelNationwideStageFieldCorrection(
                tenant_id=tenant_id,
                stage_id=stage_id,
                stage_row_id=row_id,
                field_name=field_name,
                extracted_value=extracted_str,
                reviewed_value=reviewed_value,
                reviewed_by=reviewed_by,
                reviewed_at=now,
                correction_reason=item.get("correction_reason"),
            )
        )
        written += 1
    await db.commit()
    return written


async def get_stage_storage_ref(
    db: AsyncSession,
    *,
    tenant_id: int,
    stage_id: uuid.UUID,
) -> tuple[str, str | None] | None:
    stage = await get_active_stage(db, tenant_id=tenant_id, stage_id=stage_id)
    if stage is None or not stage.source_storage_ref:
        return None
    return stage.source_storage_ref, stage.source_file_name


async def discard_nationwide_import_stage(
    db: AsyncSession,
    *,
    tenant_id: int,
    tenant_slug: str,
    stage_id: uuid.UUID,
) -> bool:
    if await get_active_stage(db, tenant_id=tenant_id, stage_id=stage_id) is None:
        return False
    await _delete_stage_records(db, tenant_id=tenant_id, stage_id=stage_id, tenant_slug=tenant_slug)
    return True


async def _import_already_source_reviewed(
    db: AsyncSession,
    *,
    tenant_id: int,
    import_id: uuid.UUID,
) -> bool:
    result = await db.execute(
        select(FuelNationwide.id)
        .where(
            FuelNationwide.tenant_id == tenant_id,
            FuelNationwide.import_id == import_id,
            FuelNationwide.review_status == NW_REVIEW_SOURCE_COMPLETE,
        )
        .limit(1)
    )
    return result.scalar_one_or_none() is not None


async def create_nationwide_import_stage_from_pdf(
    db: AsyncSession,
    *,
    tenant_id: int,
    tenant_slug: str,
    pdf_bytes: bytes,
    filename: str,
    uploaded_by: str | None,
) -> tuple[uuid.UUID, int, str, bool]:
    if not pdf_bytes.startswith(b"%PDF"):
        raise FuelNationwideImportError("NOT_PDF", "Upload must be a PDF file", http_status=400)

    started = _utcnow()
    try:
        extracted, extract_warnings, parser_version = extract_nationwide_rows_from_digital_pdf(pdf_bytes)
    except FuelNationwideExtractionError as exc:
        raise FuelNationwideImportError(exc.code, exc.message, http_status=422) from exc

    file_sha256 = sha256_hex(pdf_bytes)
    identity = document_identity_from_nationwide_rows(extracted)

    duplicate = await check_nationwide_pdf_duplicate_before_import(
        db,
        tenant_id=tenant_id,
        pdf_bytes=pdf_bytes,
        filename=filename,
        extracted_rows=extracted,
        permanent_only=True,
        exclude_import_id=None,
    )
    if duplicate is not None:
        raise FuelNationwideImportError(
            duplicate.code,
            duplicate.message,
            http_status=duplicate.http_status,
            detail=duplicate.to_detail(),
        )

    stage_id = uuid.uuid4()
    stored = await save_fuel_nationwide_stage_bytes(
        tenant_slug=tenant_slug,
        stage_id=str(stage_id),
        body=pdf_bytes,
        filename_hint=filename,
    )
    completed = _utcnow()
    header_fields = next((r.fields for r in extracted if r.row_type == ROW_HEADER), {})
    warnings_payload = {"messages": extract_warnings} if extract_warnings else None

    stage = FuelNationwideImportStage(
        stage_id=stage_id,
        tenant_id=tenant_id,
        provider_code="NATIONWIDE",
        status=STAGE_STATUS_ACTIVE,
        source_file_name=filename,
        source_file_sha256=file_sha256,
        source_storage_ref=stored.storage_key,
        parser_version=parser_version,
        parse_status="SUCCESS",
        extraction_warnings=warnings_payload,
        uploaded_at=started,
        uploaded_by=uploaded_by,
        processing_started_at=started,
        processing_completed_at=completed,
        processing_duration_ms=int((completed - started).total_seconds() * 1000),
        invoice_number=header_fields.get("invoice_number"),
        invoice_start_date=header_fields.get("invoice_start_date"),
        invoice_end_date=header_fields.get("invoice_end_date"),
        due_date=header_fields.get("due_date"),
        expires_at=completed + timedelta(hours=STAGE_TTL_HOURS),
    )
    db.add(stage)
    for item in extracted:
        row = FuelNationwideStageRow(
            tenant_id=tenant_id,
            stage_id=stage_id,
            row_type=item.row_type,
            source_page=item.source_page,
            source_row_number=item.source_row_number,
        )
        _apply_fields(row, item.fields)
        db.add(row)
    await db.commit()
    return stage_id, len(extracted), "SUCCESS", False


async def process_nationwide_stage_to_permanent(
    db: AsyncSession,
    *,
    tenant_id: int,
    tenant_slug: str,
    stage_id: uuid.UUID,
    reviewed_by: str,
    review_reason: str | None = None,
) -> dict[str, Any]:
    from app.services.fuel_nationwide_review import get_nationwide_import_review_summary

    if await _import_already_source_reviewed(db, tenant_id=tenant_id, import_id=stage_id):
        return await get_nationwide_import_review_summary(db, tenant_id=tenant_id, import_id=stage_id)

    stage = await get_active_stage(db, tenant_id=tenant_id, stage_id=stage_id)
    if stage is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Nationwide stage not found")

    rows = await list_stage_rows_for_review(db, tenant_id=tenant_id, stage_id=stage_id)
    accepted_rows = build_effective_nationwide_rows(rows)
    reconciliation = reconcile_nationwide_source_rows(accepted_rows)
    if not reconciliation.passed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "NATIONWIDE_SOURCE_RECONCILIATION_FAILED",
                "message": "Required Nationwide source validations did not pass",
                "reconciliation": reconciliation.to_dict(),
            },
        )

    storage = get_storage()
    pdf_bytes = storage.read_bytes(stage.source_storage_ref, module="fuel_nationwide_stage", tenant_slug=tenant_slug)
    from app.services.fuel_nationwide_extraction import FuelNationwideExtractedRow

    dup_rows = [
        FuelNationwideExtractedRow(
            row_type=str(r["row_type"]),
            fields={k: r.get(k) for k in NATIONWIDE_SOURCE_FIELD_NAMES if r.get(k) is not None},
        )
        for r in accepted_rows
    ]
    identity = document_identity_from_nationwide_rows(dup_rows)
    await acquire_nationwide_import_advisory_lock(db, tenant_id=tenant_id, identity=identity)

    duplicate = await check_nationwide_pdf_duplicate_before_import(
        db,
        tenant_id=tenant_id,
        pdf_bytes=pdf_bytes,
        filename=stage.source_file_name or "nationwide.pdf",
        extracted_rows=dup_rows,
        permanent_only=True,
        exclude_import_id=stage_id,
    )
    if duplicate is not None:
        raise FuelNationwideImportError(
            duplicate.code,
            duplicate.message,
            http_status=duplicate.http_status,
            detail=duplicate.to_detail(),
        )

    import_id = stage_id
    permanent_key: str | None = None
    try:
        stored = await save_fuel_nationwide_import_bytes(
            tenant_slug=tenant_slug,
            import_id=str(import_id),
            body=pdf_bytes,
            filename_hint=stage.source_file_name or "nationwide.pdf",
        )
        permanent_key = stored.storage_key
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to store permanent Nationwide PDF: {exc}") from exc

    now = _utcnow()
    try:
        orm_rows: list[FuelNationwide] = []
        stage_row_ids: list[int] = []
        for r in accepted_rows:
            fuel_row = FuelNationwide(
                tenant_id=tenant_id,
                import_id=import_id,
                row_type=r["row_type"],
                source_file_name=stage.source_file_name,
                source_file_sha256=stage.source_file_sha256,
                source_storage_ref=permanent_key,
                source_page=r.get("source_page"),
                source_row_number=r.get("source_row_number"),
                uploaded_at=stage.uploaded_at,
                uploaded_by=stage.uploaded_by,
                processed_by=reviewed_by,
                parser_version=stage.parser_version,
                parse_status=stage.parse_status,
                review_status=NW_REVIEW_SOURCE_COMPLETE,
                reviewed_by=reviewed_by,
                reviewed_at=now,
                review_reason=review_reason or "Nationwide source review confirmed",
                extraction_warnings=stage.extraction_warnings,
            )
            for name in NATIONWIDE_SOURCE_FIELD_NAMES:
                if name in r:
                    setattr(fuel_row, name, r[name])
            db.add(fuel_row)
            orm_rows.append(fuel_row)
            stage_row_ids.append(int(r["id"]))

        await db.flush()
        id_map = {sid: orm.id for sid, orm in zip(stage_row_ids, orm_rows, strict=True)}
        header = next((r for r in accepted_rows if r.get("row_type") == ROW_HEADER), {})
        expected_money_count = sum(1 for r in accepted_rows if r.get("row_type") == ROW_TRANSACTION)

        batch = build_fuel_source_batch(
            tenant_id=tenant_id,
            import_id=import_id,
            header=header,
            source_hash=stage.source_file_sha256,
            source_storage_ref=permanent_key,
            parser_version=stage.parser_version,
            reviewed_by=reviewed_by,
            imported_at=now,
        )
        db.add(batch)
        await db.flush()

        canonical_txns, canonical_controls = project_nationwide_rows_to_canonical(
            tenant_id=tenant_id,
            batch=batch,
            import_id=import_id,
            raw_rows=accepted_rows,
            effective_rows=accepted_rows,
            fuel_nationwide_id_by_stage_row_id=id_map,
        )
        for txn in canonical_txns:
            db.add(txn)
        for ctrl in canonical_controls:
            db.add(ctrl)
        await db.flush()

        assert_nationwide_canonical_money_gate(canonical_txns, expected_transaction_count=expected_money_count)
        finalize_batch(batch, reviewed_by=reviewed_by)
        await db.commit()
    except FuelNationwideCanonicalProjectionError as exc:
        await db.rollback()
        if permanent_key:
            try:
                purge_fuel_nationwide_import_files(tenant_slug, str(import_id))
            except Exception:
                logger.exception("orphan nationwide import cleanup failed")
        raise HTTPException(status_code=500, detail={"code": exc.code, "message": exc.message}) from exc
    except Exception:
        await db.rollback()
        if permanent_key:
            try:
                purge_fuel_nationwide_import_files(tenant_slug, str(import_id))
            except Exception:
                logger.exception("orphan nationwide import cleanup failed")
        raise

    try:
        await _delete_stage_records(db, tenant_id=tenant_id, stage_id=stage_id, tenant_slug=tenant_slug)
    except Exception:
        logger.exception("stage cleanup after process failed")

    from app.services.fuel_classification_persistence import best_effort_backfill_classifications_for_import

    await best_effort_backfill_classifications_for_import(db, tenant_id=tenant_id, import_id=str(import_id))
    return await get_nationwide_import_review_summary(db, tenant_id=tenant_id, import_id=import_id)
