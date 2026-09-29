"""BVD import staging — temporary upload/review before Process commits fuel_bvd."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.storage import (
    get_storage,
    purge_fuel_bvd_import_files,
    purge_fuel_bvd_stage_files,
    save_fuel_bvd_import_bytes,
    save_fuel_bvd_stage_bytes,
)
from app.models.fuel import (
    FuelBvd,
    FuelBvdImportStage,
    FuelBvdStageFieldCorrection,
    FuelBvdStageRow,
    FuelSourceBatch,
    FuelTransaction,
)
from app.services.fuel_bvd_canonical_projection import (
    BVD_VENDOR,
    FuelBvdCanonicalProjectionError,
    MONEY_ROW_TYPES,
    assert_canonical_money_gate,
    build_fuel_source_batch,
    finalize_batch,
    project_bvd_rows_to_canonical,
)
from app.services.fuel_bvd_extraction import ROW_HEADER
from app.services.fuel_bvd_source_reconciliation import parse_bvd_decimal
from app.services.fuel_bvd_correction_validate import (
    BvdCorrectionValidationError,
    validate_reviewed_bvd_field,
)
from app.services.fuel_bvd_extraction import (
    FuelBvdExtractionError,
    FuelBvdExtractedRow,
    extract_bvd_rows_from_digital_pdf,
)
from app.services.fuel_bvd_import import BVD_SOURCE_FIELD_NAMES, FuelBvdImportError
from app.services.fuel_bvd_effective import build_effective_bvd_rows
from app.services.fuel_bvd_review import (
    BVD_REVIEW_IN_PROGRESS,
    BVD_REVIEW_SOURCE_COMPLETE,
    EDITABLE_BVD_FIELDS,
    get_bvd_import_review_summary,
    reconcile_bvd_import_review_rows,
)
from app.services.fuel_bvd_source_reconciliation import reconcile_bvd_source_rows
from app.services.fuel_source_duplicate_gate import (
    ExistingBvdImportMatch,
    FuelDuplicateIngestionConflict,
    acquire_bvd_import_advisory_lock,
    check_bvd_pdf_duplicate_before_import,
    document_identity_from_extracted_rows,
    evaluate_bvd_pdf_duplicate,
    sha256_hex,
    _header_identity_matches,
    BvdDocumentIdentity,
    _norm_text,
)

logger = logging.getLogger(__name__)

STAGE_STATUS_ACTIVE = "ACTIVE"
STAGE_TTL_HOURS = 24


class FuelBvdStageNotFoundError(Exception):
    pass


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _apply_fields_to_stage_row(target: FuelBvdStageRow, fields: dict[str, str | None]) -> None:
    for name in BVD_SOURCE_FIELD_NAMES:
        if name in fields:
            setattr(target, name, fields[name])


def stage_row_to_dict(row: FuelBvdStageRow, stage: FuelBvdImportStage) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": row.id,
        "import_id": str(stage.stage_id),
        "row_type": row.row_type,
        "source_file_name": stage.source_file_name,
        "source_file_sha256": stage.source_file_sha256,
        "source_storage_ref": stage.source_storage_ref,
        "source_page": row.source_page,
        "source_row_number": row.source_row_number,
        "parse_status": stage.parse_status,
        "parser_version": stage.parser_version,
        "extraction_warnings": stage.extraction_warnings,
        "review_status": BVD_REVIEW_IN_PROGRESS,
    }
    for name in BVD_SOURCE_FIELD_NAMES:
        data[name] = getattr(row, name)
    return data


async def _latest_stage_corrections(
    db: AsyncSession,
    *,
    tenant_id: int,
    stage_id: uuid.UUID,
) -> dict[int, dict[str, dict[str, Any]]]:
    result = await db.execute(
        select(FuelBvdStageFieldCorrection)
        .where(
            FuelBvdStageFieldCorrection.tenant_id == tenant_id,
            FuelBvdStageFieldCorrection.stage_id == stage_id,
        )
        .order_by(FuelBvdStageFieldCorrection.id.desc())
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


async def get_active_stage(
    db: AsyncSession,
    *,
    tenant_id: int,
    stage_id: uuid.UUID,
) -> FuelBvdImportStage | None:
    result = await db.execute(
        select(FuelBvdImportStage).where(
            FuelBvdImportStage.tenant_id == tenant_id,
            FuelBvdImportStage.stage_id == stage_id,
            FuelBvdImportStage.status == STAGE_STATUS_ACTIVE,
            FuelBvdImportStage.expires_at > _utcnow(),
        )
    )
    return result.scalar_one_or_none()


async def is_staged_import_id(
    db: AsyncSession,
    *,
    tenant_id: int,
    import_id: uuid.UUID,
) -> bool:
    return await get_active_stage(db, tenant_id=tenant_id, stage_id=import_id) is not None


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
        select(FuelBvdStageRow)
        .where(FuelBvdStageRow.tenant_id == tenant_id, FuelBvdStageRow.stage_id == stage_id)
        .order_by(FuelBvdStageRow.source_row_number.asc(), FuelBvdStageRow.id.asc())
    )
    rows = list(result.scalars().all())
    corr_map = await _latest_stage_corrections(db, tenant_id=tenant_id, stage_id=stage_id)
    has_corr = any(corr_map.values())
    out: list[dict[str, Any]] = []
    for row in rows:
        data = stage_row_to_dict(row, stage)
        if not has_corr:
            data["review_status"] = "PENDING"
        data["field_corrections"] = corr_map.get(row.id) or {}
        out.append(data)
    return out


async def _load_permanent_reviewed_matches(
    db: AsyncSession,
    *,
    tenant_id: int,
    file_sha256: str,
    invoice_number: str | None,
) -> tuple[list[ExistingBvdImportMatch], list[ExistingBvdImportMatch]]:
    """Committed BVD imports only (SOURCE_REVIEWED)."""
    sha_result = await db.execute(
        select(FuelBvd).where(
            FuelBvd.tenant_id == tenant_id,
            FuelBvd.source_file_sha256 == file_sha256,
            FuelBvd.review_status == BVD_REVIEW_SOURCE_COMPLETE,
        )
    )
    sha_by_import: dict[uuid.UUID, ExistingBvdImportMatch] = {}
    for row in sha_result.scalars().all():
        if row.import_id not in sha_by_import or row.row_type == "HEADER":
            sha_by_import[row.import_id] = ExistingBvdImportMatch(
                import_id=row.import_id,
                review_status=row.review_status,
                uploaded_at=row.uploaded_at,
                source_file_sha256=row.source_file_sha256,
                source_file_name=row.source_file_name,
                invoice_number=row.invoice_number,
                invoice_date=row.invoice_date,
                start_date=row.start_date,
                end_date=row.end_date,
            )
    invoice_matches: list[ExistingBvdImportMatch] = []
    if invoice_number:
        hdr_result = await db.execute(
            select(FuelBvd).where(
                FuelBvd.tenant_id == tenant_id,
                FuelBvd.row_type == "HEADER",
                FuelBvd.invoice_number == invoice_number,
                FuelBvd.review_status == BVD_REVIEW_SOURCE_COMPLETE,
            )
        )
        for row in hdr_result.scalars().all():
            invoice_matches.append(
                ExistingBvdImportMatch(
                    import_id=row.import_id,
                    review_status=row.review_status,
                    uploaded_at=row.uploaded_at,
                    source_file_sha256=row.source_file_sha256,
                    source_file_name=row.source_file_name,
                    invoice_number=row.invoice_number,
                    invoice_date=row.invoice_date,
                    start_date=row.start_date,
                    end_date=row.end_date,
                )
            )
    return list(sha_by_import.values()), invoice_matches


def _stage_to_match(stage: FuelBvdImportStage) -> ExistingBvdImportMatch:
    return ExistingBvdImportMatch(
        import_id=stage.stage_id,
        review_status="PENDING",
        uploaded_at=stage.uploaded_at,
        source_file_sha256=stage.source_file_sha256,
        source_file_name=stage.source_file_name,
        invoice_number=stage.invoice_number,
        invoice_date=stage.invoice_date,
        start_date=stage.start_date,
        end_date=stage.end_date,
    )


async def _load_active_stage_matches(
    db: AsyncSession,
    *,
    tenant_id: int,
    file_sha256: str,
    identity: BvdDocumentIdentity,
) -> list[FuelBvdImportStage]:
    now = _utcnow()
    result = await db.execute(
        select(FuelBvdImportStage).where(
            FuelBvdImportStage.tenant_id == tenant_id,
            FuelBvdImportStage.status == STAGE_STATUS_ACTIVE,
            FuelBvdImportStage.expires_at > now,
        )
    )
    stages = list(result.scalars().all())
    out: list[FuelBvdImportStage] = []
    for s in stages:
        if s.source_file_sha256 == file_sha256:
            out.append(s)
            continue
        match = _stage_to_match(s)
        if identity.is_complete() and _header_identity_matches(match, identity):
            out.append(s)
    return out


async def purge_expired_stages(db: AsyncSession, *, tenant_id: int, tenant_slug: str) -> int:
    now = _utcnow()
    result = await db.execute(
        select(FuelBvdImportStage).where(
            FuelBvdImportStage.tenant_id == tenant_id,
            FuelBvdImportStage.status == STAGE_STATUS_ACTIVE,
            FuelBvdImportStage.expires_at <= now,
        )
    )
    stages = list(result.scalars().all())
    count = 0
    for stage in stages:
        await _delete_stage_records(db, tenant_id=tenant_id, stage_id=stage.stage_id, tenant_slug=tenant_slug)
        count += 1
    return count


async def _delete_stage_records(
    db: AsyncSession,
    *,
    tenant_id: int,
    stage_id: uuid.UUID,
    tenant_slug: str,
) -> None:
    await db.execute(
        delete(FuelBvdStageFieldCorrection).where(
            FuelBvdStageFieldCorrection.tenant_id == tenant_id,
            FuelBvdStageFieldCorrection.stage_id == stage_id,
        )
    )
    await db.execute(
        delete(FuelBvdStageRow).where(
            FuelBvdStageRow.tenant_id == tenant_id,
            FuelBvdStageRow.stage_id == stage_id,
        )
    )
    await db.execute(
        delete(FuelBvdImportStage).where(
            FuelBvdImportStage.tenant_id == tenant_id,
            FuelBvdImportStage.stage_id == stage_id,
        )
    )
    await db.commit()
    try:
        purge_fuel_bvd_stage_files(tenant_slug, str(stage_id))
    except Exception:
        logger.exception("fuel_bvd_stage purge files failed stage_id=%s", stage_id)


async def _import_already_source_reviewed(
    db: AsyncSession,
    *,
    tenant_id: int,
    import_id: uuid.UUID,
) -> bool:
    result = await db.execute(
        select(FuelBvd.id)
        .where(
            FuelBvd.tenant_id == tenant_id,
            FuelBvd.import_id == import_id,
            FuelBvd.review_status == BVD_REVIEW_SOURCE_COMPLETE,
        )
        .limit(1)
    )
    return result.scalar_one_or_none() is not None


async def _canonical_batch_for_bvd_import(
    db: AsyncSession,
    *,
    tenant_id: int,
    import_id: uuid.UUID,
) -> FuelSourceBatch | None:
    result = await db.execute(
        select(FuelSourceBatch).where(
            FuelSourceBatch.tenant_id == tenant_id,
            FuelSourceBatch.provider_code == BVD_VENDOR,
            FuelSourceBatch.source_import_ref == str(import_id),
        )
    )
    return result.scalar_one_or_none()


async def _verify_bvd_canonical_batch_complete(
    db: AsyncSession,
    *,
    tenant_id: int,
    import_id: uuid.UUID,
) -> FuelSourceBatch:
    batch = await _canonical_batch_for_bvd_import(db, tenant_id=tenant_id, import_id=import_id)
    if batch is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "code": "BVD_CANONICAL_PARTIAL",
                "message": "BVD import is SOURCE_REVIEWED but canonical FuelSourceBatch is missing",
            },
        )
    money_row_count = await db.scalar(
        select(func.count())
        .select_from(FuelBvd)
        .where(
            FuelBvd.tenant_id == tenant_id,
            FuelBvd.import_id == import_id,
            FuelBvd.row_type.in_(tuple(MONEY_ROW_TYPES)),
        )
    )
    txn_count = await db.scalar(
        select(func.count())
        .select_from(FuelTransaction)
        .where(FuelTransaction.tenant_id == tenant_id, FuelTransaction.batch_id == batch.id)
    )
    if money_row_count != txn_count:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "code": "BVD_CANONICAL_INCOMPLETE",
                "message": f"canonical transaction count {txn_count} != source money rows {money_row_count}",
            },
        )
    txn_sum = await db.scalar(
        select(func.coalesce(func.sum(FuelTransaction.total_amount), 0)).where(
            FuelTransaction.tenant_id == tenant_id,
            FuelTransaction.batch_id == batch.id,
        )
    )
    grand_row = await db.execute(
        select(FuelBvd.final_amount, FuelBvd.final_amt)
        .where(
            FuelBvd.tenant_id == tenant_id,
            FuelBvd.import_id == import_id,
            FuelBvd.row_type == "GRAND_TOTAL",
            FuelBvd.row_label == "Grand Total",
        )
        .limit(1)
    )
    grand_vals = grand_row.first()
    expected_total, _ = parse_bvd_decimal(
        (grand_vals[0] if grand_vals else None) or (grand_vals[1] if grand_vals else None)
    )
    if expected_total is not None and txn_sum is not None:
        if Decimal(str(txn_sum)) != expected_total:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={
                    "code": "BVD_CANONICAL_SUM_MISMATCH",
                    "message": f"canonical sum {txn_sum} != invoice grand {expected_total}",
                },
            )
    return batch


async def _finish_idempotent_process_cleanup(
    db: AsyncSession,
    *,
    tenant_id: int,
    tenant_slug: str,
    stage_id: uuid.UUID,
) -> dict[str, Any]:
    """Permanent commit already exists for stage_id — best-effort stage purge, return summary."""
    await _verify_bvd_canonical_batch_complete(db, tenant_id=tenant_id, import_id=stage_id)
    try:
        await _delete_stage_records(db, tenant_id=tenant_id, stage_id=stage_id, tenant_slug=tenant_slug)
    except Exception:
        logger.exception("idempotent process: stage cleanup failed stage_id=%s", stage_id)
    return await get_bvd_import_review_summary(db, tenant_id=tenant_id, import_id=stage_id)


async def discard_bvd_import_stage(
    db: AsyncSession,
    *,
    tenant_id: int,
    tenant_slug: str,
    stage_id: uuid.UUID,
) -> bool:
    stage = await get_active_stage(db, tenant_id=tenant_id, stage_id=stage_id)
    if stage is None:
        return False
    await _delete_stage_records(db, tenant_id=tenant_id, stage_id=stage_id, tenant_slug=tenant_slug)
    return True


async def create_bvd_import_stage_from_pdf(
    db: AsyncSession,
    *,
    tenant_id: int,
    tenant_slug: str,
    pdf_bytes: bytes,
    filename: str,
    uploaded_by: str | None,
) -> tuple[uuid.UUID, int, str, bool]:
    """Returns (stage_id, row_count, parse_status, reused_existing_stage)."""
    if not pdf_bytes.startswith(b"%PDF"):
        if pdf_bytes[:2] == b"\x1f\x8b":
            hint = "This file is gzip-compressed, not a PDF. Re-download the invoice from BVD (do not rename backups)."
        elif len(pdf_bytes) >= 2 and pdf_bytes[:2] == b"./":
            hint = "This file looks like a tar/archive, not a PDF. Use the original BVD invoice download."
        else:
            head = pdf_bytes[:8].hex() if len(pdf_bytes) >= 8 else (pdf_bytes.hex() if pdf_bytes else "empty")
            hint = f"File header is {head!r}; a real PDF starts with %PDF."
        raise FuelBvdImportError(
            "NOT_PDF",
            f"Upload must be a PDF file. {hint}",
            http_status=400,
        )

    await purge_expired_stages(db, tenant_id=tenant_id, tenant_slug=tenant_slug)

    started = _utcnow()
    try:
        extracted, extract_warnings, parser_version = extract_bvd_rows_from_digital_pdf(pdf_bytes)
    except FuelBvdExtractionError as exc:
        raise FuelBvdImportError(exc.code, exc.message, http_status=422) from exc

    file_sha256 = sha256_hex(pdf_bytes)
    identity = document_identity_from_extracted_rows(extracted)

    sha_perm, inv_perm = await _load_permanent_reviewed_matches(
        db,
        tenant_id=tenant_id,
        file_sha256=file_sha256,
        invoice_number=identity.invoice_number or None,
    )
    permanent_conflict = evaluate_bvd_pdf_duplicate(
        file_sha256=file_sha256,
        filename=filename,
        identity=identity,
        sha_matches=sha_perm,
        invoice_number_matches=inv_perm,
    )
    if permanent_conflict is not None:
        raise FuelBvdImportError(
            permanent_conflict.code,
            permanent_conflict.message,
            http_status=permanent_conflict.http_status,
            detail=permanent_conflict.to_detail(),
        )

    active_stages = await _load_active_stage_matches(
        db, tenant_id=tenant_id, file_sha256=file_sha256, identity=identity
    )
    if active_stages:
        reuse = active_stages[0]
        cnt_result = await db.execute(
            select(FuelBvdStageRow).where(
                FuelBvdStageRow.tenant_id == tenant_id,
                FuelBvdStageRow.stage_id == reuse.stage_id,
            )
        )
        return reuse.stage_id, len(list(cnt_result.scalars().all())), reuse.parse_status or "SUCCESS", True

    await acquire_bvd_import_advisory_lock(db, tenant_id=tenant_id, identity=identity)

    active_stages = await _load_active_stage_matches(
        db, tenant_id=tenant_id, file_sha256=file_sha256, identity=identity
    )
    if active_stages:
        reuse = active_stages[0]
        cnt_result = await db.execute(
            select(FuelBvdStageRow).where(
                FuelBvdStageRow.tenant_id == tenant_id,
                FuelBvdStageRow.stage_id == reuse.stage_id,
            )
        )
        return reuse.stage_id, len(list(cnt_result.scalars().all())), reuse.parse_status or "SUCCESS", True

    stage_id = uuid.uuid4()
    stored = await save_fuel_bvd_stage_bytes(
        tenant_slug=tenant_slug,
        stage_id=str(stage_id),
        body=pdf_bytes,
        filename_hint=filename,
    )
    storage_key = stored.storage_key

    completed = _utcnow()
    duration_ms = int((completed - started).total_seconds() * 1000)
    parse_status = "SUCCESS"
    warnings_payload = {"messages": extract_warnings} if extract_warnings else None
    header_fields = next((item.fields for item in extracted if item.row_type == "HEADER"), {})

    stage = FuelBvdImportStage(
        stage_id=stage_id,
        tenant_id=tenant_id,
        provider_code="BVD",
        status=STAGE_STATUS_ACTIVE,
        source_file_name=filename,
        source_file_sha256=file_sha256,
        source_storage_ref=storage_key,
        parser_version=parser_version,
        parse_status=parse_status,
        extraction_warnings=warnings_payload,
        uploaded_at=started,
        uploaded_by=uploaded_by,
        processing_started_at=started,
        processing_completed_at=completed,
        processing_duration_ms=duration_ms,
        invoice_number=header_fields.get("invoice_number"),
        invoice_date=header_fields.get("invoice_date"),
        start_date=header_fields.get("start_date"),
        end_date=header_fields.get("end_date"),
        expires_at=started + timedelta(hours=STAGE_TTL_HOURS),
    )
    db.add(stage)

    row_count = 0
    for order, item in enumerate(extracted, start=1):
        row = FuelBvdStageRow(
            tenant_id=tenant_id,
            stage_id=stage_id,
            row_type=item.row_type,
            source_page=item.source_page,
            source_row_number=order,
        )
        _apply_fields_to_stage_row(row, item.fields)
        db.add(row)
        row_count += 1

    await db.commit()
    return stage_id, row_count, parse_status, False


async def save_stage_import_review(
    db: AsyncSession,
    *,
    tenant_id: int,
    stage_id: uuid.UUID,
    reviewed_by: str,
    corrections: list[dict[str, Any]],
) -> int:
    stage = await get_active_stage(db, tenant_id=tenant_id, stage_id=stage_id)
    if stage is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="BVD stage not found")

    if not corrections:
        return 0

    row_ids = {int(c["fuel_bvd_id"]) for c in corrections if "fuel_bvd_id" in c}
    result = await db.execute(
        select(FuelBvdStageRow).where(
            FuelBvdStageRow.tenant_id == tenant_id,
            FuelBvdStageRow.stage_id == stage_id,
            FuelBvdStageRow.id.in_(row_ids),
        )
    )
    by_id = {r.id: r for r in result.scalars().all()}
    if len(by_id) != len(row_ids):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid stage row id")

    now = _utcnow()
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
        try:
            validate_reviewed_bvd_field(field_name, reviewed_value, row_type=row.row_type)
        except BvdCorrectionValidationError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "BVD_CORRECTION_INVALID", "field": exc.field_name, "message": str(exc)},
            ) from exc
        db.add(
            FuelBvdStageFieldCorrection(
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


async def process_stage_to_permanent(
    db: AsyncSession,
    *,
    tenant_id: int,
    tenant_slug: str,
    stage_id: uuid.UUID,
    reviewed_by: str,
    review_reason: str | None = None,
) -> dict[str, Any]:
    if await _import_already_source_reviewed(db, tenant_id=tenant_id, import_id=stage_id):
        return await _finish_idempotent_process_cleanup(
            db, tenant_id=tenant_id, tenant_slug=tenant_slug, stage_id=stage_id
        )

    stage = await get_active_stage(db, tenant_id=tenant_id, stage_id=stage_id)
    if stage is None:
        if await _import_already_source_reviewed(db, tenant_id=tenant_id, import_id=stage_id):
            return await _finish_idempotent_process_cleanup(
                db, tenant_id=tenant_id, tenant_slug=tenant_slug, stage_id=stage_id
            )
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="BVD stage not found")

    rows = await list_stage_rows_for_review(db, tenant_id=tenant_id, stage_id=stage_id)
    accepted_rows = build_effective_bvd_rows(rows)
    reconciliation = reconcile_bvd_source_rows(accepted_rows)
    if not reconciliation.passed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "BVD_SOURCE_RECONCILIATION_FAILED",
                "message": "Required BVD source validations did not pass",
                "reconciliation": reconciliation.to_dict(),
            },
        )

    if not stage.source_storage_ref:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Stage PDF missing")

    storage = get_storage()
    pdf_bytes = storage.read_bytes(stage.source_storage_ref, module="fuel_bvd_stage", tenant_slug=tenant_slug)

    identity = document_identity_from_extracted_rows(
        [
            FuelBvdExtractedRow(
                row_type=r["row_type"],
                fields={k: r.get(k) for k in BVD_SOURCE_FIELD_NAMES},
            )
            for r in accepted_rows
        ]
    )
    await acquire_bvd_import_advisory_lock(db, tenant_id=tenant_id, identity=identity)

    extracted_for_dup = [
        FuelBvdExtractedRow(
            row_type=r["row_type"],
            fields={k: (r.get(k) if r.get(k) is not None else None) for k in BVD_SOURCE_FIELD_NAMES},
        )
        for r in accepted_rows
    ]
    duplicate = await check_bvd_pdf_duplicate_before_import(
        db,
        tenant_id=tenant_id,
        pdf_bytes=pdf_bytes,
        filename=stage.source_file_name or "bvd.pdf",
        extracted_rows=extracted_for_dup,
        permanent_only=True,
        exclude_import_id=stage_id,
    )
    if duplicate is not None:
        raise FuelBvdImportError(
            duplicate.code,
            duplicate.message,
            http_status=duplicate.http_status,
            detail=duplicate.to_detail(),
        )

    import_id = stage_id
    permanent_key: str | None = None
    try:
        stored = await save_fuel_bvd_import_bytes(
            tenant_slug=tenant_slug,
            import_id=str(import_id),
            body=pdf_bytes,
            filename_hint=stage.source_file_name or "bvd.pdf",
        )
        permanent_key = stored.storage_key
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to store permanent BVD PDF: {exc}",
        ) from exc

    now = _utcnow()
    try:
        orm_rows: list[FuelBvd] = []
        stage_row_ids: list[int] = []
        for r in accepted_rows:
            fuel_row = FuelBvd(
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
                processing_started_at=stage.processing_started_at,
                processing_completed_at=stage.processing_completed_at,
                processing_duration_ms=stage.processing_duration_ms,
                processed_by=reviewed_by,
                parser_version=stage.parser_version,
                parse_status=stage.parse_status,
                review_status=BVD_REVIEW_SOURCE_COMPLETE,
                reviewed_by=reviewed_by,
                reviewed_at=now,
                review_reason=review_reason or "BVD source review confirmed",
                extraction_warnings=stage.extraction_warnings,
            )
            for name in BVD_SOURCE_FIELD_NAMES:
                if name in r:
                    setattr(fuel_row, name, r[name])
            db.add(fuel_row)
            orm_rows.append(fuel_row)
            stage_row_ids.append(int(r["id"]))

        await db.flush()

        id_map = {sid: orm.id for sid, orm in zip(stage_row_ids, orm_rows, strict=True)}

        header = next((r for r in accepted_rows if r.get("row_type") == ROW_HEADER), {})
        expected_money_count = sum(1 for r in accepted_rows if r.get("row_type") in MONEY_ROW_TYPES)
        expected_total, total_err = parse_bvd_decimal(reconciliation.provider_grand_total)
        if total_err or expected_total is None:
            raise FuelBvdCanonicalProjectionError(
                "GRAND_TOTAL_MISSING",
                "Cannot project canonical rows without provider grand total",
            )

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

        canonical_txns, canonical_controls = project_bvd_rows_to_canonical(
            tenant_id=tenant_id,
            batch=batch,
            import_id=import_id,
            raw_rows=accepted_rows,
            effective_rows=accepted_rows,
            fuel_bvd_id_by_stage_row_id=id_map,
        )
        for txn in canonical_txns:
            db.add(txn)
        for ctrl in canonical_controls:
            db.add(ctrl)
        await db.flush()

        assert_canonical_money_gate(
            canonical_txns,
            canonical_controls,
            expected_transaction_count=expected_money_count,
            expected_total=expected_total,
        )
        finalize_batch(batch, reviewed_by=reviewed_by)

        await db.commit()
    except FuelBvdCanonicalProjectionError as exc:
        await db.rollback()
        if permanent_key:
            try:
                purge_fuel_bvd_import_files(tenant_slug, str(import_id))
            except Exception:
                logger.exception("orphan permanent fuel_bvd file cleanup failed import_id=%s", import_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": exc.code, "message": exc.message},
        ) from exc
    except Exception:
        await db.rollback()
        if permanent_key:
            try:
                purge_fuel_bvd_import_files(tenant_slug, str(import_id))
            except Exception:
                logger.exception("orphan permanent fuel_bvd file cleanup failed import_id=%s", import_id)
        raise

    try:
        await _delete_stage_records(db, tenant_id=tenant_id, stage_id=stage_id, tenant_slug=tenant_slug)
    except Exception:
        logger.exception("stage cleanup after successful process failed stage_id=%s", stage_id)

    from app.services.fuel_classification_persistence import (
        best_effort_backfill_classifications_for_import,
    )

    await best_effort_backfill_classifications_for_import(
        db, tenant_id=tenant_id, import_id=str(import_id)
    )

    return await get_bvd_import_review_summary(db, tenant_id=tenant_id, import_id=import_id)
