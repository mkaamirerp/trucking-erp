"""Toll MANUAL review-stage foundation. No TollTransaction writes."""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.toll import (
    MANUAL_STAGE_DISCARDED,
    MANUAL_STAGE_DRAFT,
    MANUAL_STAGE_NEEDS_REVIEW,
    SOURCE_TYPE_MANUAL,
    VEHICLE_IDENTITY_PRESENT,
    VEHICLE_IDENTITY_UNRESOLVED,
    TollManualEntryStage,
)

_DATE_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
_TIME_RE = re.compile(r"^(\d{1,2}):(\d{2})$")
_PATCH_FIELDS = (
    "post_date",
    "event_date",
    "event_time",
    "agency_raw",
    "entry_location",
    "entry_lane",
    "exit_location",
    "exit_lane",
    "transponder_number",
    "plate_number",
    "plate_state",
    "trip_charge",
    "currency",
    "notes",
    "unresolved_vehicle_identity",
)


class TollManualEntryError(Exception):
    def __init__(self, code: str, message: str, http_status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status


def _blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def parse_optional_date(value: Any, *, field: str) -> date | None:
    if _blank(value):
        return None
    if isinstance(value, date):
        return value
    text = str(value).strip()
    match = _DATE_RE.match(text)
    if match is None:
        raise TollManualEntryError("TOLL_MANUAL_INVALID_DATE", f"{field} must be YYYY-MM-DD")
    try:
        return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
    except ValueError as exc:
        raise TollManualEntryError("TOLL_MANUAL_INVALID_DATE", f"{field} is not a valid date") from exc


def parse_optional_time(value: Any, *, field: str) -> str | None:
    if _blank(value):
        return None
    text = str(value).strip()
    match = _TIME_RE.match(text)
    if match is None:
        raise TollManualEntryError("TOLL_MANUAL_INVALID_TIME", f"{field} must be HH:MM")
    hour, minute = int(match.group(1)), int(match.group(2))
    if hour > 23 or minute > 59:
        raise TollManualEntryError("TOLL_MANUAL_INVALID_TIME", f"{field} is not a valid time")
    return f"{hour:02d}:{minute:02d}"


def parse_optional_charge(value: Any) -> Decimal | None:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if isinstance(value, float):
        raise TollManualEntryError("TOLL_MANUAL_INVALID_CHARGE", "trip_charge must not be a float")
    if isinstance(value, Decimal):
        amount = value
    else:
        text = str(value).strip().replace("$", "").replace(",", "")
        try:
            amount = Decimal(text)
        except InvalidOperation as exc:
            raise TollManualEntryError("TOLL_MANUAL_INVALID_CHARGE", "trip_charge is not a valid decimal") from exc
    if amount < 0:
        raise TollManualEntryError("TOLL_MANUAL_INVALID_CHARGE", "trip_charge must be >= 0")
    return amount


def _vehicle_status(stage: TollManualEntryStage) -> str:
    if (stage.transponder_number or "").strip() or (stage.plate_number or "").strip():
        return VEHICLE_IDENTITY_PRESENT
    return VEHICLE_IDENTITY_UNRESOLVED


def stage_to_dict(stage: TollManualEntryStage) -> dict[str, Any]:
    charge = stage.trip_charge
    return {
        "stage_id": int(stage.id) if stage.id is not None else 0,
        "source_type": stage.source_type,
        "file_format": stage.file_format,
        "status": stage.status,
        "post_date": stage.post_date.isoformat() if stage.post_date else None,
        "event_date": stage.event_date.isoformat() if stage.event_date else None,
        "event_time": stage.event_time,
        "agency_raw": stage.agency_raw,
        "entry_location": stage.entry_location,
        "entry_lane": stage.entry_lane,
        "exit_location": stage.exit_location,
        "exit_lane": stage.exit_lane,
        "transponder_number": stage.transponder_number,
        "plate_number": stage.plate_number,
        "plate_state": stage.plate_state,
        "trip_charge": format(charge, "f") if charge is not None else None,
        "currency": stage.currency,
        "notes": stage.notes,
        "unresolved_vehicle_identity": bool(stage.unresolved_vehicle_identity),
        "vehicle_identity_status": stage.vehicle_identity_status,
        "source_evidence_json": dict(stage.source_evidence_json or {}),
    }


async def _get_open_stage(
    db: AsyncSession,
    *,
    tenant_id: int,
    stage_id: int,
) -> TollManualEntryStage:
    stage = await db.scalar(
        select(TollManualEntryStage).where(
            TollManualEntryStage.tenant_id == tenant_id,
            TollManualEntryStage.id == stage_id,
        )
    )
    if stage is None or stage.status == MANUAL_STAGE_DISCARDED:
        raise TollManualEntryError("TOLL_MANUAL_NOT_FOUND", "Manual Toll stage not found", http_status=404)
    return stage


def _apply_patch(stage: TollManualEntryStage, patch: dict[str, Any]) -> None:
    if "post_date" in patch:
        stage.post_date = parse_optional_date(patch.get("post_date"), field="post_date")
    if "event_date" in patch:
        stage.event_date = parse_optional_date(patch.get("event_date"), field="event_date")
    if "event_time" in patch:
        stage.event_time = parse_optional_time(patch.get("event_time"), field="event_time")
    for name in (
        "agency_raw",
        "entry_location",
        "entry_lane",
        "exit_location",
        "exit_lane",
        "transponder_number",
        "plate_number",
        "plate_state",
        "currency",
        "notes",
    ):
        if name in patch:
            raw = patch.get(name)
            setattr(stage, name, None if _blank(raw) else str(raw).strip())
    if "trip_charge" in patch:
        stage.trip_charge = parse_optional_charge(patch.get("trip_charge"))
    if "unresolved_vehicle_identity" in patch:
        stage.unresolved_vehicle_identity = bool(patch.get("unresolved_vehicle_identity"))
    stage.vehicle_identity_status = _vehicle_status(stage)
    evidence = dict(stage.source_evidence_json or {})
    evidence["source_type"] = SOURCE_TYPE_MANUAL
    evidence["file_format"] = None
    evidence["last_patch_fields"] = sorted(key for key in patch if key in _PATCH_FIELDS)
    stage.source_evidence_json = evidence


def validate_stage_fields(stage: TollManualEntryStage) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    if stage.event_date is None:
        errors.append({"code": "TOLL_MANUAL_EVENT_DATE_REQUIRED", "message": "event_date is required"})
    if stage.trip_charge is None:
        errors.append({"code": "TOLL_MANUAL_CHARGE_REQUIRED", "message": "trip_charge is required"})
    elif stage.trip_charge < 0:
        errors.append({"code": "TOLL_MANUAL_INVALID_CHARGE", "message": "trip_charge must be >= 0"})
    has_vehicle = bool((stage.transponder_number or "").strip() or (stage.plate_number or "").strip())
    if not has_vehicle and not stage.unresolved_vehicle_identity:
        errors.append(
            {
                "code": "TOLL_MANUAL_VEHICLE_REQUIRED",
                "message": "Provide transponder, plate, or mark vehicle identity unresolved",
            }
        )
    return errors


async def create_manual_stage(
    db: AsyncSession,
    *,
    tenant_id: int,
    created_by: str | None = None,
    payload: dict[str, Any] | None = None,
) -> TollManualEntryStage:
    stage = TollManualEntryStage(
        tenant_id=tenant_id,
        source_type=SOURCE_TYPE_MANUAL,
        file_format=None,
        status=MANUAL_STAGE_DRAFT,
        unresolved_vehicle_identity=False,
        source_evidence_json={"source_type": SOURCE_TYPE_MANUAL, "file_format": None},
        created_by=created_by,
        updated_by=created_by,
    )
    db.add(stage)
    await db.flush()
    if payload:
        _apply_patch(stage, payload)
        stage.updated_by = created_by
        await db.flush()
    if stage.id is None:
        raise TollManualEntryError("TOLL_MANUAL_PERSIST", "Manual stage was not assigned an id", http_status=500)
    stage_id = int(stage.id)
    await db.commit()
    return await _get_open_stage(db, tenant_id=tenant_id, stage_id=stage_id)


async def get_manual_stage(
    db: AsyncSession,
    *,
    tenant_id: int,
    stage_id: int,
) -> TollManualEntryStage:
    return await _get_open_stage(db, tenant_id=tenant_id, stage_id=stage_id)


async def list_manual_stages(
    db: AsyncSession,
    *,
    tenant_id: int,
    limit: int = 50,
) -> list[TollManualEntryStage]:
    capped = max(0, min(limit, 100))
    result = await db.execute(
        select(TollManualEntryStage)
        .where(
            TollManualEntryStage.tenant_id == tenant_id,
            TollManualEntryStage.status != MANUAL_STAGE_DISCARDED,
        )
        .order_by(TollManualEntryStage.id.desc())
        .limit(capped)
    )
    return list(result.scalars().all())


async def patch_manual_stage(
    db: AsyncSession,
    *,
    tenant_id: int,
    stage_id: int,
    patch: dict[str, Any],
    updated_by: str | None = None,
) -> TollManualEntryStage:
    stage = await _get_open_stage(db, tenant_id=tenant_id, stage_id=stage_id)
    _apply_patch(stage, patch)
    stage.status = MANUAL_STAGE_DRAFT
    stage.updated_by = updated_by
    stage_id = int(stage.id)
    await db.commit()
    return await _get_open_stage(db, tenant_id=tenant_id, stage_id=stage_id)


async def validate_manual_stage(
    db: AsyncSession,
    *,
    tenant_id: int,
    stage_id: int,
    updated_by: str | None = None,
) -> tuple[TollManualEntryStage, list[dict[str, str]]]:
    stage = await _get_open_stage(db, tenant_id=tenant_id, stage_id=stage_id)
    errors = validate_stage_fields(stage)
    if errors:
        stage.status = MANUAL_STAGE_DRAFT
        stage_id = int(stage.id)
        await db.commit()
        return await _get_open_stage(db, tenant_id=tenant_id, stage_id=stage_id), errors
    stage.vehicle_identity_status = _vehicle_status(stage)
    # Structural validation only. This is not human approval and not Process.
    stage.status = MANUAL_STAGE_NEEDS_REVIEW
    stage.updated_by = updated_by
    evidence = dict(stage.source_evidence_json or {})
    evidence["structurally_valid"] = True
    evidence["vehicle_identity_status"] = stage.vehicle_identity_status
    stage.source_evidence_json = evidence
    stage_id = int(stage.id)
    await db.commit()
    return await _get_open_stage(db, tenant_id=tenant_id, stage_id=stage_id), []


async def discard_manual_stage(
    db: AsyncSession,
    *,
    tenant_id: int,
    stage_id: int,
) -> None:
    stage = await _get_open_stage(db, tenant_id=tenant_id, stage_id=stage_id)
    stage.status = MANUAL_STAGE_DISCARDED
    await db.commit()

