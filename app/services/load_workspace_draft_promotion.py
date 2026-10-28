"""Promote a load workspace draft into one commercial Load (atomic, idempotent)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.concurrency.draft_conflicts import workspace_draft_version_conflict_exception
from app.models.load_commercial_evidence import LoadCommercialEvidence
from app.models.load_workspace_draft import LoadWorkspaceDraft
from app.schemas.load import LoadCreate
from app.schemas.load_workspace_draft import LoadWorkspaceDraftPromote
from app.services.load_workspace_draft_lifecycle import apply_expiry_if_overdue, raise_not_editable
from app.services.load_workspace_draft_mapper import DraftJsonMappingError, draft_json_to_load_create
from app.services.load_rate_confirmation_duplicate import assert_promote_rate_confirmation_not_duplicate
from app.services.load_workspace_draft_document import (
    extracted_fields_in_draft,
    reconcile_accepted_parse_json,
)
from app.schemas.trip_read import TripAssignmentBody
from app.services.loads import (
    _insert_commercial_load_uncommitted,
    _write_load_audit,
    get_load,
)
from app.models.trip import Trip, TripLoad
from app.services.trips import _validate_assignment_targets, create_planned_trip, update_trip_assignment


class PromotionResult:
    def __init__(
        self,
        *,
        draft: LoadWorkspaceDraft,
        load_id: int,
        idempotent_replay: bool,
        trip_id: int | None = None,
    ) -> None:
        self.draft = draft
        self.load_id = load_id
        self.idempotent_replay = idempotent_replay
        self.trip_id = trip_id


def _positive_int_from_draft(value: object) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def proposed_assignment_from_draft_json(draft_json: dict) -> tuple[int | None, int | None, int | None]:
    """Pre-promote movement assignment stored in draft_json (not on Load)."""
    driver_id = _positive_int_from_draft(draft_json.get("driverId") or draft_json.get("driver_id"))
    truck_id = _positive_int_from_draft(draft_json.get("truckId") or draft_json.get("truck_id"))
    trailer_id = _positive_int_from_draft(
        draft_json.get("trailerAssetId")
        or draft_json.get("trailer_asset_id")
        or draft_json.get("trailerId")
        or draft_json.get("trailer_id")
    )
    return driver_id, truck_id, trailer_id


def draft_json_has_non_empty_driver_reference(draft_json: dict) -> bool:
    """True when the operator set a driver on the draft (including invalid non-numeric values)."""
    raw = draft_json.get("driverId")
    if raw is None:
        raw = draft_json.get("driver_id")
    if raw is None:
        return False
    if isinstance(raw, bool):
        return False
    if isinstance(raw, str):
        return bool(raw.strip())
    if isinstance(raw, (int, float)):
        try:
            return int(raw) > 0
        except (TypeError, ValueError):
            return True
    return True


async def assert_draft_movement_assignment_promotable(
    db: AsyncSession,
    tenant_id: int,
    draft_json: dict,
) -> tuple[int | None, int | None, int | None]:
    """Reject promotion when draft shows driver intent but assignment cannot be honored."""
    driver_id, truck_id, trailer_id = proposed_assignment_from_draft_json(draft_json)
    if draft_json_has_non_empty_driver_reference(draft_json) and driver_id is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "LOAD_WORKSPACE_DRAFT_INVALID_DRIVER",
                "detail": "Driver assignment on the draft is invalid. Clear or fix the driver before creating the load.",
            },
        )
    if driver_id is not None:
        await _validate_assignment_targets(
            db,
            tenant_id,
            driver_id=driver_id,
            truck_id=truck_id,
            trailer_id=trailer_id,
        )
    return driver_id, truck_id, trailer_id


async def _trip_id_for_promoted_load(db: AsyncSession, tenant_id: int, load_id: int) -> int | None:
    """First non-cancelled trip membership for the load (any status), for idempotent promote replay."""
    trip_id = await db.scalar(
        select(TripLoad.trip_id)
        .join(Trip, and_(Trip.tenant_id == TripLoad.tenant_id, Trip.id == TripLoad.trip_id))
        .where(
            TripLoad.tenant_id == tenant_id,
            TripLoad.load_id == int(load_id),
            Trip.cancelled_at.is_(None),
        )
        .order_by(TripLoad.id.asc())
        .limit(1)
    )
    return int(trip_id) if trip_id is not None else None


async def _create_planned_trip_for_promoted_load(
    db: AsyncSession,
    tenant_id: int,
    load_id: int,
    *,
    driver_id: int,
    truck_id: int | None,
    trailer_id: int | None,
    promoted_by_platform_user_id: str | None,
) -> int:
    trip_detail = await create_planned_trip(
        db,
        tenant_id,
        driver_id=driver_id,
        truck_id=truck_id,
        trailer_id=trailer_id,
        load_ids=[int(load_id)],
    )
    trip_id = int(trip_detail.id)
    await update_trip_assignment(
        db,
        tenant_id,
        trip_id,
        TripAssignmentBody(driver_id=driver_id, truck_id=truck_id, trailer_id=trailer_id),
        actor_user_id=None,
        actor_label=promoted_by_platform_user_id,
    )
    return trip_id


def merge_broker_load_reference_from_accepted_parse(
    load_create: LoadCreate,
    draft: LoadWorkspaceDraft,
) -> LoadCreate:
    """Fill broker_load_reference from accepted_parse_json when draft_json left it blank."""
    if (load_create.broker_load_reference or "").strip():
        return load_create
    accepted = draft.accepted_parse_json
    if not isinstance(accepted, dict):
        return load_create
    extracted = accepted.get("extracted")
    if not isinstance(extracted, dict):
        return load_create
    ref = (extracted.get("broker_load_reference") or "").strip()
    if not ref:
        return load_create
    return load_create.model_copy(update={"broker_load_reference": ref})


async def _idempotent_replay(
    db: AsyncSession, tenant_id: int, draft: LoadWorkspaceDraft, key: str
) -> PromotionResult | None:
    if draft.status == "promoted" and draft.promoted_load_id is not None:
        if draft.promotion_idempotency_key == key:
            load_id = int(draft.promoted_load_id)
            trip_id = await _trip_id_for_promoted_load(db, tenant_id, load_id)
            return PromotionResult(
                draft=draft,
                load_id=load_id,
                idempotent_replay=True,
                trip_id=trip_id,
            )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "LOAD_WORKSPACE_DRAFT_ALREADY_PROMOTED",
                "promoted_load_id": draft.promoted_load_id,
            },
        )
    key_owner = await db.scalar(
        select(LoadWorkspaceDraft).where(
            LoadWorkspaceDraft.tenant_id == tenant_id,
            LoadWorkspaceDraft.promotion_idempotency_key == key,
        )
    )
    if key_owner is not None and key_owner.id != draft.id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "LOAD_WORKSPACE_DRAFT_PROMOTION_IDEMPOTENCY_KEY_CONFLICT",
                "owner_draft_id": str(key_owner.id),
            },
        )
    return None


def _maybe_commercial_evidence_row(
    draft: LoadWorkspaceDraft,
    *,
    tenant_id: int,
    load_id: int,
    promoted_by_platform_user_id: str | None,
    promoted_at: datetime,
    accepted_parse_json: dict | None = None,
) -> LoadCommercialEvidence | None:
    if draft.pdf_upload_state != "ready":
        return None
    if not draft.pdf_storage_key or not draft.pdf_sha256:
        return None
    return LoadCommercialEvidence(
        tenant_id=tenant_id,
        load_id=load_id,
        workspace_draft_id=draft.id,
        file_sha256=draft.pdf_sha256,
        storage_key=draft.pdf_storage_key,
        filename=draft.pdf_filename,
        accepted_parse_json=(
            draft.accepted_parse_json or {}
            if accepted_parse_json is None
            else accepted_parse_json
        ),
        parse_schema_version=draft.accepted_parse_schema_version,
        promoted_by_platform_user_id=promoted_by_platform_user_id,
        promoted_at=promoted_at,
    )


async def promote_workspace_draft(
    db: AsyncSession,
    tenant_id: int,
    draft_id: uuid.UUID,
    payload: LoadWorkspaceDraftPromote,
    *,
    promoted_by_platform_user_id: str | None,
) -> PromotionResult:
    draft = await db.scalar(
        select(LoadWorkspaceDraft)
        .where(LoadWorkspaceDraft.tenant_id == tenant_id, LoadWorkspaceDraft.id == draft_id)
        .with_for_update()
    )
    if draft is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace draft not found")

    replay = await _idempotent_replay(db, tenant_id, draft, payload.promotion_idempotency_key)
    if replay is not None:
        return replay

    await apply_expiry_if_overdue(db, draft)
    if draft.status != "draft":
        if draft.status in {"discarded", "expired"}:
            raise_not_editable(draft)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "LOAD_WORKSPACE_DRAFT_NOT_PROMOTABLE", "status": draft.status},
        )
    if int(draft.concurrency_version) != payload.expected_concurrency_version:
        raise workspace_draft_version_conflict_exception(
            draft_id=draft_id,
            client_version=payload.expected_concurrency_version,
            server_version=int(draft.concurrency_version),
        )

    try:
        load_create = draft_json_to_load_create(draft.draft_json or {})
        load_create = merge_broker_load_reference_from_accepted_parse(load_create, draft)
    except DraftJsonMappingError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "LOAD_WORKSPACE_DRAFT_MAPPING_INVALID", "field": exc.field, "message": str(exc)},
        ) from exc
    await assert_promote_rate_confirmation_not_duplicate(
        db,
        tenant_id=tenant_id,
        broker_load_reference=load_create.broker_load_reference,
        broker_id=load_create.broker_id,
        acknowledge_soft=payload.acknowledge_soft_rate_confirmation_duplicate,
    )
    movement_assignment = await assert_draft_movement_assignment_promotable(
        db, tenant_id, draft.draft_json or {}
    )
    now = datetime.now(timezone.utc)

    load, _stop_create_diff = await _insert_commercial_load_uncommitted(
        db,
        tenant_id,
        load_create,
        promotion_origin_workspace_draft_id=draft.id,
        insert_as_ready=True,
    )

    verified_parse = reconcile_accepted_parse_json(
        draft.accepted_parse_json or {},
        load_create,
        only_fields=extracted_fields_in_draft(draft.draft_json or {}),
    )
    evidence = _maybe_commercial_evidence_row(
        draft,
        tenant_id=tenant_id,
        load_id=int(load.id),
        promoted_by_platform_user_id=promoted_by_platform_user_id,
        promoted_at=now,
        accepted_parse_json=verified_parse,
    )
    if evidence is not None:
        db.add(evidence)

    draft.status = "promoted"
    draft.promoted_load_id = int(load.id)
    draft.promoted_at = now
    draft.promotion_idempotency_key = payload.promotion_idempotency_key
    draft.concurrency_version = int(draft.concurrency_version) + 1
    draft.updated_by_platform_user_id = promoted_by_platform_user_id

    await db.flush()

    hydrated = await get_load(db, tenant_id, int(load.id))
    if hydrated is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Load missing after promotion")
    await _write_load_audit(
        db,
        tenant_id=tenant_id,
        load=hydrated,
        action="load_created",
        actor_user_id=None,
        request_id=None,
        correlation_id=None,
        source="ui",
        changed_fields={"status": {"before": None, "after": "ready"}},
        context_json={
            "origin": "workspace_draft_promotion",
            "workspace_draft_id": str(draft.id),
            "promotion_idempotency_key": payload.promotion_idempotency_key,
        },
        best_effort=False,
    )

    trip_id: int | None = None
    driver_id, truck_id, trailer_id = movement_assignment
    if driver_id is not None:
        trip_id = await _create_planned_trip_for_promoted_load(
            db,
            tenant_id,
            int(load.id),
            driver_id=driver_id,
            truck_id=truck_id,
            trailer_id=trailer_id,
            promoted_by_platform_user_id=promoted_by_platform_user_id,
        )

    await db.commit()
    await db.refresh(draft)
    return PromotionResult(
        draft=draft,
        load_id=int(load.id),
        idempotent_replay=False,
        trip_id=trip_id,
    )
