"""Manual Fuel Entry staging — draft, receipt hydrate, Process → canonical."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.storage import save_fuel_manual_entry_stage_bytes
from app.models.fuel import FuelManualEntryStage, FuelSourceBatch, FuelTransaction
from app.services.fuel_manual_canonical_projection import (
    FuelManualCanonicalProjectionError,
    build_manual_source_batch,
    finalize_batch,
    project_manual_draft_to_transaction,
)
from app.services.fuel_manual_entry_constants import (
    ENTRY_METHOD_DIRECT,
    ENTRY_METHOD_RECEIPT,
    MANUAL_ENTRY_PROVIDER_CODE,
    STAGE_STATUS_ACTIVE,
    STAGE_STATUS_DISCARDED,
    STAGE_STATUS_PROCESSED,
)
from app.services.fuel_manual_entry_validation import (
    FuelManualEntryValidationError,
    validate_and_prepare_draft,
)
from app.services.fuel_manual_receipt_extract import (
    PARSER_VERSION,
    extract_manual_fuel_receipt_from_upload_async,
    hydrate_draft_from_receipt_extraction,
)
from app.services.fuel_source_duplicate_gate import sha256_hex

STAGE_TTL_HOURS = 72


class FuelManualEntryStageError(Exception):
    def __init__(self, code: str, message: str, http_status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _empty_draft(entry_method: str) -> dict[str, Any]:
    return {
        "entry_method": entry_method,
        "field_provenance": {},
        "derived_fields": {},
        "provider_raw": {"entry_method": entry_method},
        "requires_review": False,
        "review_reasons": [],
    }


def stage_to_dict(stage: FuelManualEntryStage) -> dict[str, Any]:
    return {
        "stage_id": str(stage.stage_id),
        "provider_code": stage.provider_code,
        "status": stage.status,
        "entry_method": stage.entry_method,
        "draft": dict(stage.draft_json or {}),
        "extraction_raw": dict(stage.extraction_raw or {}) if stage.extraction_raw else None,
        "validation_snapshot": dict(stage.validation_snapshot or {}) if stage.validation_snapshot else None,
        "requires_review": stage.requires_review,
        "source_file_name": stage.source_file_name,
        "has_receipt_attachment": bool(stage.source_storage_ref),
        "processed_batch_id": stage.processed_batch_id,
        "expires_at": stage.expires_at.isoformat() if stage.expires_at else None,
    }


async def get_active_stage(
    db: AsyncSession,
    *,
    tenant_id: int,
    stage_id: uuid.UUID,
) -> FuelManualEntryStage | None:
    result = await db.execute(
        select(FuelManualEntryStage).where(
            FuelManualEntryStage.tenant_id == tenant_id,
            FuelManualEntryStage.stage_id == stage_id,
            FuelManualEntryStage.status == STAGE_STATUS_ACTIVE,
            FuelManualEntryStage.expires_at > _utcnow(),
        )
    )
    return result.scalar_one_or_none()


async def create_direct_stage(
    db: AsyncSession,
    *,
    tenant_id: int,
    created_by: str,
) -> FuelManualEntryStage:
    stage_id = uuid.uuid4()
    stage = FuelManualEntryStage(
        stage_id=stage_id,
        tenant_id=tenant_id,
        provider_code=MANUAL_ENTRY_PROVIDER_CODE,
        status=STAGE_STATUS_ACTIVE,
        entry_method=ENTRY_METHOD_DIRECT,
        draft_json=_empty_draft(ENTRY_METHOD_DIRECT),
        expires_at=_utcnow() + timedelta(hours=STAGE_TTL_HOURS),
        uploaded_by=created_by,
        uploaded_at=_utcnow(),
    )
    db.add(stage)
    await db.flush()
    return stage


async def create_receipt_stage_from_upload(
    db: AsyncSession,
    *,
    tenant_id: int,
    tenant_slug: str,
    created_by: str,
    file_bytes: bytes,
    filename: str,
    extraction: dict[str, Any] | None,
) -> FuelManualEntryStage:
    stage_id = uuid.uuid4()
    stored = await save_fuel_manual_entry_stage_bytes(
        tenant_slug,
        str(stage_id),
        file_bytes,
        filename_hint=filename or "receipt.pdf",
    )
    if extraction is not None:
        extraction_raw = dict(extraction)
    else:
        extraction_raw = await extract_manual_fuel_receipt_from_upload_async(file_bytes, filename)
    draft = _empty_draft(ENTRY_METHOD_RECEIPT)
    if extraction_raw:
        draft = hydrate_draft_from_receipt_extraction(extraction_raw, entry_method=ENTRY_METHOD_RECEIPT)
        try:
            draft = validate_and_prepare_draft(draft, strict=False)
        except FuelManualEntryValidationError:
            pass

    stage = FuelManualEntryStage(
        stage_id=stage_id,
        tenant_id=tenant_id,
        provider_code=MANUAL_ENTRY_PROVIDER_CODE,
        status=STAGE_STATUS_ACTIVE,
        entry_method=ENTRY_METHOD_RECEIPT,
        draft_json=draft,
        extraction_raw=extraction_raw or None,
        validation_snapshot=draft.get("validation_snapshot"),
        requires_review=bool(draft.get("requires_review")),
        source_file_name=filename,
        source_file_sha256=sha256_hex(file_bytes),
        source_storage_ref=stored.storage_key,
        expires_at=_utcnow() + timedelta(hours=STAGE_TTL_HOURS),
        uploaded_by=created_by,
        uploaded_at=_utcnow(),
    )
    db.add(stage)
    await db.flush()
    return stage


async def update_stage_draft(
    db: AsyncSession,
    *,
    tenant_id: int,
    stage_id: uuid.UUID,
    patch: dict[str, Any],
    updated_by: str,
) -> FuelManualEntryStage:
    stage = await get_active_stage(db, tenant_id=tenant_id, stage_id=stage_id)
    if stage is None:
        raise FuelManualEntryStageError("STAGE_NOT_FOUND", "Manual entry draft not found", http_status=404)

    draft = dict(stage.draft_json or {})
    provenance = dict(draft.get("field_provenance") or {})
    for key, value in patch.items():
        if key in {"field_provenance", "derived_fields", "provider_raw", "validation_snapshot"}:
            continue
        if value is None:
            draft.pop(key, None)
        else:
            draft[key] = value
            provenance[key] = "MANUAL" if stage.entry_method == ENTRY_METHOD_DIRECT else provenance.get(key, "MANUAL")
    draft["field_provenance"] = provenance
    draft["entry_method"] = stage.entry_method
    try:
        draft = validate_and_prepare_draft(draft, strict=False)
    except FuelManualEntryValidationError as exc:
        raise FuelManualEntryStageError(exc.code, exc.message) from exc

    stage.draft_json = draft
    stage.validation_snapshot = draft.get("validation_snapshot")
    stage.requires_review = bool(draft.get("requires_review"))
    stage.uploaded_by = updated_by
    await db.flush()
    return stage


async def validate_stage_draft(
    db: AsyncSession,
    *,
    tenant_id: int,
    stage_id: uuid.UUID,
) -> dict[str, Any]:
    stage = await get_active_stage(db, tenant_id=tenant_id, stage_id=stage_id)
    if stage is None:
        raise FuelManualEntryStageError("STAGE_NOT_FOUND", "Manual entry draft not found", http_status=404)
    draft = validate_and_prepare_draft(dict(stage.draft_json or {}), strict=True)
    stage.draft_json = draft
    stage.validation_snapshot = draft.get("validation_snapshot")
    stage.requires_review = bool(draft.get("requires_review"))
    await db.flush()
    return dict(draft.get("validation_snapshot") or {})


async def process_manual_entry_stage(
    db: AsyncSession,
    *,
    tenant_id: int,
    tenant_slug: str,
    stage_id: uuid.UUID,
    reviewed_by: str,
) -> dict[str, Any]:
    stage = await get_active_stage(db, tenant_id=tenant_id, stage_id=stage_id)
    if stage is None:
        raise FuelManualEntryStageError("STAGE_NOT_FOUND", "Manual entry draft not found", http_status=404)

    draft = validate_and_prepare_draft(dict(stage.draft_json or {}), strict=True)
    if draft.get("requires_review"):
        raise FuelManualEntryStageError(
            "REQUIRES_ADMIN_REVIEW",
            "Draft is flagged for admin review before Process",
            http_status=409,
        )

    batch = build_manual_source_batch(
        tenant_id=tenant_id,
        stage_id=stage_id,
        draft=draft,
        source_storage_ref=stage.source_storage_ref,
        source_hash=stage.source_file_sha256,
        reviewed_by=reviewed_by,
    )
    db.add(batch)
    await db.flush()

    txn = project_manual_draft_to_transaction(
        tenant_id=tenant_id,
        batch_id=batch.id,
        stage_id=stage_id,
        draft=draft,
        extraction_raw=stage.extraction_raw,
    )
    db.add(txn)
    await db.flush()

    finalize_batch(batch, reviewed_by=reviewed_by)
    stage.status = STAGE_STATUS_PROCESSED
    stage.processed_batch_id = batch.id
    stage.draft_json = draft
    await db.flush()

    return {
        "batch_id": batch.id,
        "transaction_id": txn.id,
        "provider_code": MANUAL_ENTRY_PROVIDER_CODE,
        "status": batch.status,
        "parser_version": PARSER_VERSION,
    }


async def discard_stage(
    db: AsyncSession,
    *,
    tenant_id: int,
    stage_id: uuid.UUID,
) -> None:
    stage = await get_active_stage(db, tenant_id=tenant_id, stage_id=stage_id)
    if stage is None:
        return
    stage.status = STAGE_STATUS_DISCARDED


def raise_http(exc: Exception) -> None:
    if isinstance(exc, FuelManualEntryStageError):
        raise HTTPException(status_code=exc.http_status, detail={"code": exc.code, "message": exc.message})
    if isinstance(exc, FuelManualEntryValidationError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": exc.code, "message": exc.message, "details": exc.details},
        )
    if isinstance(exc, FuelManualCanonicalProjectionError):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=exc.message)
    raise exc
