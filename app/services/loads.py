"""Load service. V1: stop-based, draft/ready; PATCH stops sync in-place (Issue I2)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Iterable, Sequence

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.load_integrity import (
    LOAD_BOARD_UNKNOWN_STATUS_BUCKET,
    LOAD_STOP_DUPLICATE_ID,
    LOAD_STOP_HISTORY_PROTECTED,
    LOAD_STOP_INVALID_ID,
    LOAD_STOP_REMOVAL_FORBIDDEN,
    LOAD_STOP_TYPE_UNRESOLVED,
    WRITABLE_LOAD_STOP_TYPES,
)
from app.constants.custody import CUSTODY_OWNER_DELIVERED, CUSTODY_OWNER_UNKNOWN
from app.constants.trip_dispatch import (
    LEGACY_LOAD_ASSIGNMENT_DEPRECATED,
    LEGACY_LOAD_OPERATIONAL_STATUSES,
    LEGACY_LOAD_STATUS_DISPATCH_DEPRECATED,
    LEGACY_LOAD_STATUS_TRANSITION_BLOCKED,
    LOAD_ASSIGNMENT_FIELDS,
    LOAD_CREATE_STATUS_MUST_BE_DRAFT,
    LOAD_STATUS_NOT_WRITABLE,
    LOAD_STATUS_READY_USE_MARK_READY_ENDPOINT,
    LOAD_WRITABLE_STATUSES,
    TRIP_CONTAINER_STATUS_ASSIGNED,
    TRIP_CONTAINER_STATUS_IN_PROGRESS,
    TRIP_LOAD_STATUS_WITHIN_ACTIVE,
)
from app.models.broker import Broker, BrokerContact
from app.models.customs_broker import CustomsBroker, LoadCustomsSnapshot
from app.models.load import Load, LoadNote, LoadStop, LoadStopAction
from app.models.trip import Trip, TripLoad
from app.core.concurrency.conflicts import load_version_conflict_exception
from app.schemas.load import LoadCreate, LoadResponse, LoadUpdate, LoadStopCreate, ALLOWED_STATUSES
from app.services.load_operational_references import sanitize_load_operational_references
from app.services.trips import _lock_load_for_membership
from app.utils.pagination import paginate

# Commercial money fields audited on PATCH (Issue 26).
LOAD_MONEY_AUDIT_FIELDS = frozenset({"rate", "customer_rate"})


def _audit_encode_money_value(value: object) -> object:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, (int, float)):
        return format(Decimal(str(value)), "f")
    return value


def _encode_load_money_changed_fields(changed: dict) -> dict:
    encoded: dict = {}
    for field, diff in changed.items():
        if field in LOAD_MONEY_AUDIT_FIELDS and isinstance(diff, dict):
            encoded[field] = {
                "before": _audit_encode_money_value(diff.get("before")),
                "after": _audit_encode_money_value(diff.get("after")),
            }
        else:
            encoded[field] = diff
    return encoded


def _residual_includes_money_mutation(residual_changed: dict) -> bool:
    return bool(LOAD_MONEY_AUDIT_FIELDS & residual_changed.keys())


async def _write_load_audit(
    db: AsyncSession,
    *,
    tenant_id: int,
    load: Load,
    action: str,
    actor_user_id: int | None,
    request_id: str | None,
    correlation_id: str | None,
    source: str,
    changed_fields: dict | None = None,
    context_json: dict | None = None,
    best_effort: bool = True,
) -> None:
    """Write tenant audit_events for Loads.

    Default best-effort (never raises). Issue 26 money PATCH uses best_effort=False so
    a failed required audit rolls back with the Load mutation in the same transaction.
    """
    try:
        from app.services.audit_events import write_audit_event

        ctx = context_json
        if ctx is None and changed_fields is None:
            # Writer requires at least one payload surface; use minimal context for checkpoint events.
            ctx = {"checkpoint": True}

        await write_audit_event(
            db,
            tenant_id=int(tenant_id),
            module="loads",
            entity_type="load",
            entity_id=str(int(load.id)),
            entity_label=(str(load.load_number) if getattr(load, "load_number", None) else None),
            action=action,
            source=source,
            actor_user_id=actor_user_id,
            request_id=request_id,
            correlation_id=correlation_id,
            changed_fields=changed_fields,
            context_json=ctx,
            best_effort=best_effort,
        )
    except Exception:
        if best_effort:
            # Avoid failing core load mutations; audit is additive during rollout.
            pass
        else:
            raise


async def _get_broker(db: AsyncSession, tenant_id: int, broker_id: int) -> Broker | None:
    result = await db.execute(select(Broker).where(Broker.id == broker_id, Broker.tenant_id == tenant_id))
    return result.scalar_one_or_none()


async def _get_broker_contact(db: AsyncSession, tenant_id: int, contact_id: int) -> BrokerContact | None:
    result = await db.execute(
        select(BrokerContact).where(
            BrokerContact.id == contact_id,
            BrokerContact.tenant_id == tenant_id,
        )
    )
    return result.scalar_one_or_none()


async def _get_customs_broker(db: AsyncSession, tenant_id: int, customs_broker_id: int) -> CustomsBroker | None:
    result = await db.execute(
        select(CustomsBroker).where(
            CustomsBroker.id == customs_broker_id,
            CustomsBroker.tenant_id == tenant_id,
        )
    )
    return result.scalar_one_or_none()


def _legacy_write_conflict(code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"detail": message, "code": code})


def _reject_load_assignment_fields(payload: LoadCreate | LoadUpdate) -> None:
    """Driver/truck/trailer are Trip equipment; Load create/PATCH must not carry them (even as null)."""
    sent = [f for f in LOAD_ASSIGNMENT_FIELDS if f in payload.model_fields_set]
    if sent:
        raise _legacy_write_conflict(
            LEGACY_LOAD_ASSIGNMENT_DEPRECATED,
            f"Load {', '.join(sent)} is not writable. Assign driver/truck/trailer on the Trip.",
        )


def _reject_legacy_status_target(new_status: str) -> None:
    if new_status in LEGACY_LOAD_OPERATIONAL_STATUSES:
        raise _legacy_write_conflict(
            LEGACY_LOAD_STATUS_DISPATCH_DEPRECATED,
            f"Load.status = {new_status} is legacy operational vocabulary and cannot be written. "
            "Use Trip assignment and Trip lifecycle actions.",
        )


def _guard_create_payload(payload: LoadCreate) -> None:
    _reject_load_assignment_fields(payload)
    new_status = (payload.status or "draft").strip().lower()
    _reject_legacy_status_target(new_status)
    if new_status != "draft":
        raise _legacy_write_conflict(
            LOAD_CREATE_STATUS_MUST_BE_DRAFT,
            "New loads are created as draft. Use Mark ready after required fields are complete.",
        )


def _guard_update_payload(load: Load, payload: LoadUpdate) -> None:
    _reject_load_assignment_fields(payload)
    old_status = (load.status or "").strip().lower()
    if old_status == LOAD_COMMERCIAL_STATUS_CANCELLED:
        raise _legacy_write_conflict(
            LOAD_COMMERCIALLY_CANCELLED_MUTATION_BLOCKED,
            "Cancelled loads cannot be edited or reactivated via PATCH. Use append-only notes if needed.",
        )
    if "status" not in payload.model_fields_set:
        return
    new_status = (payload.status or "").strip().lower()
    _reject_legacy_status_target(new_status)
    if new_status not in LOAD_WRITABLE_STATUSES:
        raise _legacy_write_conflict(
            LOAD_STATUS_NOT_WRITABLE,
            "Load status must be draft or ready when provided. Omit status to keep the current value.",
        )
    if old_status in LEGACY_LOAD_OPERATIONAL_STATUSES:
        raise _legacy_write_conflict(
            LEGACY_LOAD_STATUS_TRANSITION_BLOCKED,
            f"This load holds legacy status {old_status}; its status cannot be changed from the Load page. "
            "Commercial fields remain editable when status is omitted.",
        )
    if new_status == "ready" and old_status != "ready":
        raise _legacy_write_conflict(
            LOAD_STATUS_READY_USE_MARK_READY_ENDPOINT,
            "Transitioning a load to ready is only allowed via POST /api/v1/loads/{load_id}/mark-ready.",
        )


_COMMERCIAL_STOP_ATTRS = (
    "stop_type",
    "sequence",
    "facility_name",
    "street",
    "city",
    "state_or_province",
    "postal_code",
    "country",
    "reference_number",
    "appointment_type",
    "appointment_date",
    "appointment_time_text",
    "notes",
    "commodity_notes",
)


async def _stop_has_operational_history(
    db: AsyncSession, tenant_id: int, stop: LoadStop
) -> bool:
    if stop.scheduled_at is not None or stop.arrived_at is not None or stop.departed_at is not None:
        return True
    cnt = await db.scalar(
        select(func.count())
        .select_from(LoadStopAction)
        .where(
            LoadStopAction.tenant_id == tenant_id,
            LoadStopAction.load_stop_id == stop.id,
        )
    )
    return int(cnt or 0) > 0


def _stop_commercial_snapshot(stop: LoadStop | LoadStopCreate) -> dict[str, object]:
    if isinstance(stop, LoadStop):
        return {k: getattr(stop, k, None) for k in _COMMERCIAL_STOP_ATTRS}
    data = stop.model_dump(exclude={"id"}, exclude_unset=False)
    return {k: data.get(k) for k in _COMMERCIAL_STOP_ATTRS}


def _validate_stops_write_payload(stops_payload: Sequence[LoadStopCreate]) -> None:
    seen_ids: set[int] = set()
    for s in stops_payload:
        st = (s.stop_type or "").strip().upper()
        if st not in WRITABLE_LOAD_STOP_TYPES:
            raise _legacy_write_conflict(
                LOAD_STOP_TYPE_UNRESOLVED,
                f"Stop type '{s.stop_type}' must be classified as PICKUP, DROP, or DELIVERY before save.",
            )
        if s.id is not None and int(s.id) > 0:
            sid = int(s.id)
            if sid in seen_ids:
                raise _legacy_write_conflict(
                    LOAD_STOP_DUPLICATE_ID,
                    f"Duplicate stop id {sid} in request.",
                )
            seen_ids.add(sid)


async def _sync_load_stops_on_update(
    db: AsyncSession,
    tenant_id: int,
    load_id: int,
    stops_payload: Sequence[LoadStopCreate],
) -> dict[str, object]:
    """Upsert commercial stop fields; never delete operational/history-bearing stops (Issue I2)."""
    _validate_stops_write_payload(stops_payload)

    result = await db.execute(
        select(LoadStop).where(LoadStop.tenant_id == tenant_id, LoadStop.load_id == load_id)
    )
    existing = list(result.scalars().all())
    by_id = {int(s.id): s for s in existing}
    before_by_id = {sid: _stop_commercial_snapshot(row) for sid, row in by_id.items()}

    keep_ids: set[int] = set()
    for s in stops_payload:
        if s.id is not None and int(s.id) > 0:
            keep_ids.add(int(s.id))

    removed: list[dict[str, object]] = []
    for sid, row in by_id.items():
        if sid in keep_ids:
            continue
        if await _stop_has_operational_history(db, tenant_id, row):
            raise _legacy_write_conflict(
                LOAD_STOP_HISTORY_PROTECTED,
                "Cannot remove a stop with operational history or dependencies.",
            )
        removed.append({"stop_id": sid, "before": before_by_id[sid]})
        await db.delete(row)

    added: list[dict[str, object]] = []
    updated: list[dict[str, object]] = []
    for i, s in enumerate(stops_payload):
        seq = s.sequence if s.sequence is not None else i
        data = s.model_dump(exclude={"id"}, exclude_unset=False)
        for k in list(data.keys()):
            if k not in _COMMERCIAL_STOP_ATTRS:
                data.pop(k, None)
        data["sequence"] = seq

        if s.id is not None and int(s.id) > 0:
            row = by_id.get(int(s.id))
            if row is None or row.tenant_id != tenant_id or row.load_id != load_id:
                raise _legacy_write_conflict(
                    LOAD_STOP_INVALID_ID,
                    f"Stop id {s.id} is not part of this load.",
                )
            before = before_by_id[int(row.id)]
            for k, v in data.items():
                setattr(row, k, v)
            after = _stop_commercial_snapshot(row)
            if before != after:
                updated.append({"stop_id": int(row.id), "before": before, "after": after})
        else:
            row = LoadStop(tenant_id=tenant_id, load_id=load_id, **data)
            db.add(row)
            await db.flush()
            added.append({"stop_id": int(row.id), "after": _stop_commercial_snapshot(row)})

    await db.flush()
    return {"removed": removed, "updated": updated, "added": added}


def _stop_is_delivery_or_drop(stop_type: str | None) -> bool:
    """True for DROP or DELIVERY (Load Page default second stop uses DELIVERY)."""
    if not stop_type:
        return False
    u = stop_type.strip().upper()
    return u in ("DROP", "DELIVERY")


async def _ready_requirements_violation(
    db: AsyncSession,
    tenant_id: int,
    load_id: int,
) -> str | None:
    row = (
        await db.execute(
            select(
                Load.broker_id,
                Load.broker_name_snapshot,
                Load.broker_load_reference,
            ).where(
                Load.id == load_id,
                Load.tenant_id == tenant_id,
            )
        )
    ).one_or_none()

    if row is None:
        return "Load not found"

    if not (
        row.broker_id
        or (row.broker_name_snapshot or "").strip()
    ):
        return "Broker or broker name is required"

    if not (row.broker_load_reference or "").strip():
        return "Broker load reference is required"

    stop_types = [
        (value or "").strip().upper()
        for value in (
            await db.scalars(
                select(LoadStop.stop_type).where(
                    LoadStop.tenant_id == tenant_id,
                    LoadStop.load_id == load_id,
                )
            )
        ).all()
    ]

    if "PICKUP" not in stop_types:
        return "At least one pickup is required"

    if not any(
        _stop_is_delivery_or_drop(value)
        for value in stop_types
    ):
        return "At least one delivery or drop is required"

    return None


async def _ensure_unique_load_number(db: AsyncSession, tenant_id: int, load_number: str, exclude_id: int | None = None):
    stmt = select(Load).where(Load.tenant_id == tenant_id, Load.load_number == load_number)
    if exclude_id:
        stmt = stmt.where(Load.id != exclude_id)
    exists = await db.scalar(stmt.limit(1))
    if exists:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="A load with this load_number already exists"
        )


def _load_data_from_payload(payload: LoadCreate | LoadUpdate) -> dict:
    """Exclude stops from data passed to Load model. Map API ``references`` → ORM ``operational_references``."""
    if isinstance(payload, LoadCreate):
        data = payload.model_dump(exclude={"stops", "references"})
        data["operational_references"] = sanitize_load_operational_references(payload.references)
        return data
    data = payload.model_dump(exclude_unset=True, exclude={"stops", "expected_concurrency_version", "references"})
    if "references" in payload.model_fields_set:
        data["operational_references"] = sanitize_load_operational_references(payload.references or [])
    return data


async def create_load(db: AsyncSession, tenant_id: int, payload: LoadCreate) -> Load:
    _guard_create_payload(payload)
    if payload.broker_id is not None and not await _get_broker(db, tenant_id, payload.broker_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Broker not found")
    if payload.broker_contact_id is not None:
        contact = await _get_broker_contact(db, tenant_id, payload.broker_contact_id)
        if not contact:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Broker contact not found")
        if payload.broker_id is not None and contact.broker_id != payload.broker_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Broker contact must belong to the selected broker",
            )
    if payload.customs_broker_id is not None and not await _get_customs_broker(db, tenant_id, payload.customs_broker_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Customs broker not found")

    load_number = payload.load_number or f"DRAFT-{uuid.uuid4().hex[:8].upper()}"
    await _ensure_unique_load_number(db, tenant_id, load_number)

    data = _load_data_from_payload(payload)
    data["load_number"] = load_number
    data["status"] = "draft"

    load = Load(**data, tenant_id=tenant_id)
    db.add(load)
    await db.flush()

    if payload.stops:
        _validate_stops_write_payload(payload.stops)
        for i, s in enumerate(payload.stops):
            stop_data = s.model_dump(exclude={"id"}, exclude_unset=False)
            for k in list(stop_data.keys()):
                if k not in _COMMERCIAL_STOP_ATTRS and k != "sequence":
                    stop_data.pop(k, None)
            stop_data["sequence"] = s.sequence if s.sequence is not None else i
            stop = LoadStop(tenant_id=tenant_id, load_id=load.id, **stop_data)
            db.add(stop)

    await db.commit()
    created_id = load.id
    # Session uses expire_on_commit=False; expire so get_load re-reads row (e.g. concurrency_version).
    db.expire_all()
    # Re-fetch with relationships for LoadResponse (avoids async lazy-load). Do not touch `load` after expire_all.
    out = await get_load(db, tenant_id, created_id)
    if out is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Load missing after create")

    await _write_load_audit(
        db,
        tenant_id=tenant_id,
        load=out,
        action="load_created",
        actor_user_id=None,
        request_id=None,
        correlation_id=None,
        source="ui",
        changed_fields=None,
    )
    # Persist audit row (load already committed above).
    await db.commit()
    return out


async def get_load(db: AsyncSession, tenant_id: int, load_id: int) -> Load | None:
    result = await db.execute(
        select(Load)
        .options(
            selectinload(Load.driver),
            selectinload(Load.broker),
            selectinload(Load.broker_contact),
            selectinload(Load.customs_broker),
            selectinload(Load.customs_snapshot),
            selectinload(Load.truck),
            selectinload(Load.trailer),
            selectinload(Load.stops).selectinload(LoadStop.actions),
        )
        .where(Load.id == load_id, Load.tenant_id == tenant_id)
    )
    row = result.scalar_one_or_none()
    # selectinload for this one-to-one with composite (tenant_id, load_id) -> loads does not populate in tests +
    # async batch loaders; explicit SELECT matches the row. Relationship primaryjoin remains correct for lazy access.
    if row is not None and row.customs_snapshot is None:
        snap = await db.scalar(
            select(LoadCustomsSnapshot).where(
                LoadCustomsSnapshot.load_id == row.id,
                LoadCustomsSnapshot.tenant_id == row.tenant_id,
            )
        )
        row.customs_snapshot = snap
    return row


async def list_loads(
    db: AsyncSession,
    tenant_id: int,
    statuses: Iterable[str] | None = None,
    driver_id: int | None = None,
    broker_id: int | None = None,
    truck_id: int | None = None,
    trailer_id: int | None = None,
    search: str | None = None,
    page: int = 1,
    size: int = 25,
):
    stmt = (
        select(Load)
        .options(
            selectinload(Load.driver),
            selectinload(Load.broker),
            selectinload(Load.broker_contact),
            selectinload(Load.customs_broker),
            selectinload(Load.customs_snapshot),
            selectinload(Load.truck),
            selectinload(Load.trailer),
            selectinload(Load.stops),
        )
        .where(Load.tenant_id == tenant_id)
        .order_by(Load.id.desc())
    )

    if statuses:
        normalized = [s.strip().lower() for s in statuses if s]
        stmt = stmt.where(Load.status.in_([s for s in normalized if s in ALLOWED_STATUSES]))
    q = (search or "").strip()
    if q:
        pat = f"%{q}%"
        stmt = stmt.where(
            or_(
                Load.load_number.ilike(pat),
                Load.broker_load_reference.ilike(pat),
                Load.broker_name_snapshot.ilike(pat),
                Load.trip_number.ilike(pat),
            )
        )
    if driver_id:
        stmt = stmt.where(Load.driver_id == driver_id)
    if broker_id:
        stmt = stmt.where(Load.broker_id == broker_id)
    if truck_id:
        stmt = stmt.where(Load.truck_id == truck_id)
    if trailer_id:
        stmt = stmt.where(Load.trailer_id == trailer_id)

    return await paginate(db, stmt, page=page, size=size)


async def update_load(
    db: AsyncSession,
    tenant_id: int,
    load_id: int,
    payload: LoadUpdate,
    *,
    actor_user_id: int | None = None,
    request_id: str | None = None,
    correlation_id: str | None = None,
    source: str = "ui",
) -> Load:
    load = await get_load(db, tenant_id, load_id)
    if not load:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Load not found")

    _reject_commercial_mutation_if_cancelled(load)
    _guard_update_payload(load, payload)

    expected = payload.expected_concurrency_version
    old_status = (load.status or "").strip().lower()
    old_driver_id = load.driver_id
    old_customs_broker_id = load.customs_broker_id
    data = _load_data_from_payload(payload)
    before_snapshot: dict[str, object] = {str(k): getattr(load, k, None) for k in data.keys()}

    if "broker_id" in data:
        broker_id = data["broker_id"]
        if broker_id is not None and not await _get_broker(db, tenant_id, broker_id):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Broker not found")
    if "broker_contact_id" in data:
        contact_id = data["broker_contact_id"]
        if contact_id is not None:
            contact = await _get_broker_contact(db, tenant_id, contact_id)
            if not contact:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Broker contact not found")
            broker_id = data.get("broker_id") if "broker_id" in data else load.broker_id
            if broker_id is not None and contact.broker_id != broker_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Broker contact must belong to the selected broker",
                )

    if "customs_broker_id" in data:
        if load.document_snapshot_confirmed_at is not None:
            new_cb = data["customs_broker_id"]
            if new_cb != load.customs_broker_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Cannot change customs broker after document snapshot is confirmed",
                )
        new_val = data["customs_broker_id"]
        if new_val is not None and not await _get_customs_broker(db, tenant_id, new_val):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Customs broker not found")

    if "load_number" in data and data["load_number"]:
        await _ensure_unique_load_number(db, tenant_id, data["load_number"], exclude_id=load.id)

    # Trip read-model pointers (trip_number, active_dispatch_trip_id, active_trip_id) are never written here.
    values = {**data}
    values["updated_at"] = func.now()
    values["concurrency_version"] = Load.concurrency_version + 1

    stmt = (
        update(Load)
        .where(
            Load.id == load_id,
            Load.tenant_id == tenant_id,
            Load.concurrency_version == expected,
        )
        .values(**values)
        .execution_options(synchronize_session=False)
    )
    result = await db.execute(stmt)
    if result.rowcount != 1:
        await db.rollback()
        current_load = await get_load(db, tenant_id, load_id)
        server_snapshot = LoadResponse.model_validate(current_load).model_dump(mode="json") if current_load else None
        raise load_version_conflict_exception(
            load_id=load_id,
            client_version=expected,
            server_version=current_load.concurrency_version if current_load else None,
            server_snapshot=server_snapshot,
        )

    stop_audit_diff: dict[str, object] | None = None
    if "stops" in payload.model_dump(exclude_unset=True):
        stops_payload: Sequence[LoadStopCreate] = payload.stops or []
        stop_audit_diff = await _sync_load_stops_on_update(
            db,
            tenant_id,
            load_id,
            stops_payload,
        )
        if not stops_payload and stop_audit_diff.get("removed"):
            stop_audit_diff = {**stop_audit_diff, "removed_all": True}

    # Issue 26: keep Load mutation and audit in one transaction (no commit before audit).
    await db.flush()

    ready_relevant_fields = {
        "broker_id",
        "broker_name_snapshot",
        "broker_load_reference",
    }
    if (
        old_status == "ready"
        and (
            bool(ready_relevant_fields.intersection(data))
            or "stops" in payload.model_fields_set
        )
    ):
        violation = await _ready_requirements_violation(
            db, tenant_id, load_id
        )
        if violation:
            await db.rollback()
            raise _legacy_write_conflict(
                "LOAD_READY_REQUIREMENTS_VIOLATED",
                f"Ready Load would become invalid: {violation}",
            )

    # CAS uses synchronize_session=False; refresh this row so audit before/after sees DB values.
    await db.refresh(load)
    out = load

    # Slice 5 audit writes. Correlation defaults to request_id.
    corr = correlation_id or request_id
    changed: dict = {}
    for k, v in data.items():
        # note: for stops we don't include full stop diff here; this is lightweight.
        before = before_snapshot.get(str(k))
        after = getattr(out, k, None)
        if before != after:
            changed[str(k)] = {"before": before, "after": after}

    # Duplicate-event policy:
    # - Emit semantic events for status/assignment/customs broker changes.
    # - Emit `load_updated` only for residual diffs not fully explained by semantic events.
    semantic_keys = {"status", "driver_id", "customs_broker_id"}
    residual_changed = {k: v for k, v in changed.items() if k not in semantic_keys}

    if residual_changed:
        money_audit_required = _residual_includes_money_mutation(residual_changed)
        audit_changed = (
            _encode_load_money_changed_fields(residual_changed) if money_audit_required else residual_changed
        )
        await _write_load_audit(
            db,
            tenant_id=tenant_id,
            load=out,
            action="load_updated",
            actor_user_id=actor_user_id,
            request_id=request_id,
            correlation_id=corr,
            source=source,
            changed_fields=audit_changed,
            best_effort=not money_audit_required,
        )

    if stop_audit_diff is not None:
        await _write_load_audit(
            db,
            tenant_id=tenant_id,
            load=out,
            action="load_stops_changed",
            actor_user_id=actor_user_id,
            request_id=request_id,
            correlation_id=corr,
            source=source,
            changed_fields={"stops": stop_audit_diff},
            context_json={
                "load_id": int(load_id),
                "tenant_id": int(tenant_id),
                "stop_change_summary": stop_audit_diff,
            },
            best_effort=False,
        )

    if old_status != (out.status or "").strip().lower():
        await _write_load_audit(
            db,
            tenant_id=tenant_id,
            load=out,
            action="load_status_changed",
            actor_user_id=actor_user_id,
            request_id=request_id,
            correlation_id=corr,
            source=source,
            changed_fields={"status": {"before": old_status or None, "after": (out.status or "").strip().lower() or None}},
        )
        if (out.status or "").strip().lower() == "dispatched":
            await _write_load_audit(
                db,
                tenant_id=tenant_id,
                load=out,
                action="load_dispatched",
                actor_user_id=actor_user_id,
                request_id=request_id,
                correlation_id=corr,
                source=source,
                changed_fields=None,
            )

    if old_driver_id != out.driver_id:
        await _write_load_audit(
            db,
            tenant_id=tenant_id,
            load=out,
            action="load_assigned",
            actor_user_id=actor_user_id,
            request_id=request_id,
            correlation_id=corr,
            source=source,
            changed_fields={"driver_id": {"before": old_driver_id, "after": out.driver_id}},
        )

    if old_customs_broker_id != out.customs_broker_id:
        await _write_load_audit(
            db,
            tenant_id=tenant_id,
            load=out,
            action="customs_broker_changed",
            actor_user_id=actor_user_id,
            request_id=request_id,
            correlation_id=corr,
            source=source,
            changed_fields={"customs_broker_id": {"before": old_customs_broker_id, "after": out.customs_broker_id}},
        )

    await db.commit()
    await db.refresh(load)
    return load


LOAD_PHYSICAL_DELETE_TEMPORARILY_DISABLED = "LOAD_PHYSICAL_DELETE_TEMPORARILY_DISABLED"

LOAD_COMMERCIAL_STATUS_CANCELLED = "cancelled"
LOAD_CANCELLABLE_COMMERCIAL_STATUSES = frozenset({"draft", "ready"})
LOAD_ALREADY_CANCELLED = "LOAD_ALREADY_CANCELLED"
LOAD_CANCEL_STATUS_NOT_ALLOWED = "LOAD_CANCEL_STATUS_NOT_ALLOWED"
LOAD_CANCEL_ACTIVE_TRIP_EXECUTION = "LOAD_CANCEL_ACTIVE_TRIP_EXECUTION"
LOAD_CANCEL_UNRESOLVED_CUSTODY = "LOAD_CANCEL_UNRESOLVED_CUSTODY"
LOAD_COMMERCIALLY_CANCELLED_MUTATION_BLOCKED = "LOAD_COMMERCIALLY_CANCELLED_MUTATION_BLOCKED"


def _reject_commercial_mutation_if_cancelled(load: Load) -> None:
    if (load.status or "").strip().lower() == LOAD_COMMERCIAL_STATUS_CANCELLED:
        raise _legacy_write_conflict(
            LOAD_COMMERCIALLY_CANCELLED_MUTATION_BLOCKED,
            "Cancelled loads cannot be commercially modified. Append-only notes are still allowed.",
        )


async def _load_has_open_active_on_executing_trip(
    db: AsyncSession, tenant_id: int, load_id: int
) -> bool:
    """OPEN ACTIVE membership on assigned or in_progress Trip blocks commercial cancel."""
    n = await db.scalar(
        select(func.count())
        .select_from(TripLoad)
        .join(
            Trip,
            (Trip.id == TripLoad.trip_id) & (Trip.tenant_id == TripLoad.tenant_id),
        )
        .where(
            TripLoad.tenant_id == tenant_id,
            TripLoad.load_id == load_id,
            TripLoad.status_within_trip == TRIP_LOAD_STATUS_WITHIN_ACTIVE,
            TripLoad.completed_at.is_(None),
            TripLoad.removed_at.is_(None),
            Trip.status.in_(
                (TRIP_CONTAINER_STATUS_ASSIGNED, TRIP_CONTAINER_STATUS_IN_PROGRESS)
            ),
        )
    )
    return int(n or 0) > 0


async def cancel_load(
    db: AsyncSession,
    tenant_id: int,
    load_id: int,
    *,
    expected_concurrency_version: int,
    reason: str,
    actor_user_id: int | None = None,
    request_id: str | None = None,
    source: str = "api",
) -> Load:
    """Commercial cancel — row and history preserved; does not remove TripLoad rows.

    Lock order: Load FOR UPDATE (same row trips use via _lock_load_for_membership) so cancel
    serializes with TripLoad insert/activate on this load_id.
    """
    load = await _lock_load_for_membership(db, tenant_id, load_id)

    status_now = (load.status or "").strip().lower()
    if status_now == LOAD_COMMERCIAL_STATUS_CANCELLED:
        existing = await get_load(db, tenant_id, load_id)
        return existing if existing is not None else load

    if status_now not in LOAD_CANCELLABLE_COMMERCIAL_STATUSES:
        if status_now in LEGACY_LOAD_OPERATIONAL_STATUSES:
            raise _legacy_write_conflict(
                LOAD_CANCEL_STATUS_NOT_ALLOWED,
                f"Load in legacy operational status '{load.status}' cannot be cancelled via this endpoint.",
            )
        raise _legacy_write_conflict(
            LOAD_CANCEL_STATUS_NOT_ALLOWED,
            f"Load status '{load.status}' cannot be cancelled.",
        )

    if await _load_has_open_active_on_executing_trip(db, tenant_id, load_id):
        raise _legacy_write_conflict(
            LOAD_CANCEL_ACTIVE_TRIP_EXECUTION,
            "Load has an active TripLoad on an assigned or in-progress Trip. "
            "Close operational custody/membership on the Trip before commercial cancel.",
        )

    custody_owner = (load.custody_owner or CUSTODY_OWNER_UNKNOWN).strip().lower()
    if custody_owner not in (CUSTODY_OWNER_UNKNOWN, CUSTODY_OWNER_DELIVERED):
        raise _legacy_write_conflict(
            LOAD_CANCEL_UNRESOLVED_CUSTODY,
            f"Load custody is held by '{custody_owner}'. Resolve custody before commercial cancel.",
        )

    rate_before = load.rate
    customer_rate_before = load.customer_rate

    stmt = (
        update(Load)
        .where(
            Load.id == load_id,
            Load.tenant_id == tenant_id,
            Load.concurrency_version == expected_concurrency_version,
            Load.status.in_(tuple(LOAD_CANCELLABLE_COMMERCIAL_STATUSES)),
        )
        .values(
            status=LOAD_COMMERCIAL_STATUS_CANCELLED,
            concurrency_version=Load.concurrency_version + 1,
            updated_at=func.now(),
        )
        .execution_options(synchronize_session=False)
    )
    result = await db.execute(stmt)
    if result.rowcount != 1:
        await db.rollback()
        current_load = await get_load(db, tenant_id, load_id)
        if current_load and (current_load.status or "").strip().lower() == LOAD_COMMERCIAL_STATUS_CANCELLED:
            replay = await get_load(db, tenant_id, load_id)
            return replay if replay is not None else current_load
        server_snapshot = (
            LoadResponse.model_validate(current_load).model_dump(mode="json")
            if current_load
            else None
        )
        raise load_version_conflict_exception(
            load_id=load_id,
            client_version=expected_concurrency_version,
            server_version=current_load.concurrency_version if current_load else None,
            server_snapshot=server_snapshot,
        )

    await db.flush()
    refreshed = await get_load(db, tenant_id, load_id)
    if refreshed is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Load not found")

    await _write_load_audit(
        db,
        tenant_id=tenant_id,
        load=refreshed,
        action="load_cancelled",
        actor_user_id=actor_user_id,
        request_id=request_id,
        correlation_id=request_id,
        source=source,
        changed_fields={
            "status": {"before": status_now, "after": LOAD_COMMERCIAL_STATUS_CANCELLED},
        },
        context_json={"cancel_reason": reason.strip()},
        best_effort=False,
    )
    await db.commit()
    db.expire_all()
    out = await get_load(db, tenant_id, load_id)
    if out is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Load not found")
    return out


async def delete_load(
    db: AsyncSession, tenant_id: int, load_id: int, *, expected_concurrency_version: int
) -> None:
    """Issue 5 Phase 2: block all physical deletes until guarded delete is implemented."""
    _ = expected_concurrency_version
    current_load = await get_load(db, tenant_id, load_id)
    if current_load is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Load not found")
    raise _legacy_write_conflict(
        LOAD_PHYSICAL_DELETE_TEMPORARILY_DISABLED,
        "Physical load deletion is temporarily disabled.",
    )


async def list_loads_for_board(
    db: AsyncSession,
    tenant_id: int,
    search: str | None = None,
) -> dict[str, list]:
    """Return loads grouped by status for dispatch board (legacy UI: DeprecatedDispatchPage). Excludes draft. No pagination."""
    stmt = (
        select(Load)
        .options(
            selectinload(Load.driver),
            selectinload(Load.broker),
            selectinload(Load.broker_contact),
            selectinload(Load.customs_broker),
            selectinload(Load.customs_snapshot),
            selectinload(Load.truck),
            selectinload(Load.trailer),
            selectinload(Load.stops),
        )
        .where(Load.tenant_id == tenant_id)
        .where(Load.status != "draft")
        .order_by(Load.id.desc())
    )
    if search and search.strip():
        q = f"%{search.strip()}%"
        stmt = stmt.where(
            or_(
                Load.load_number.ilike(q),
                Load.broker_load_reference.ilike(q),
                Load.broker_name_snapshot.ilike(q),
                Load.trip_number.ilike(q),
            )
        )
    result = await db.execute(stmt)
    loads = list(result.scalars().all())

    board_statuses = [s for s in ALLOWED_STATUSES if s != "draft"]
    board_set = set(board_statuses)
    grouped: dict[str, list] = {s: [] for s in board_statuses}
    grouped[LOAD_BOARD_UNKNOWN_STATUS_BUCKET] = []
    for load in loads:
        bucket = _legacy_board_bucket_for_status(load.status, board_set)
        grouped[bucket].append(load)
    return grouped


def _legacy_board_bucket_for_status(status: str | None, board_statuses: set[str]) -> str:
    """Issue I10: unknown/empty statuses never map to ready."""
    s = (status or "").strip().lower()
    if not s or s not in board_statuses:
        return LOAD_BOARD_UNKNOWN_STATUS_BUCKET
    return s


async def mark_load_ready(
    db: AsyncSession,
    tenant_id: int,
    load_id: int,
    *,
    expected_concurrency_version: int,
    actor_user_id: int | None = None,
    request_id: str | None = None,
    source: str = "api",
) -> Load:
    """Mark draft as ready. Validates minimum: broker, broker_load_reference, at least one pickup and one delivery/drop."""
    load = await get_load(db, tenant_id, load_id)
    if not load:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Load not found")

    _reject_commercial_mutation_if_cancelled(load)

    if load.status != "draft":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Only draft loads can be marked ready; current status is {load.status}",
        )

    violation = await _ready_requirements_violation(
        db, tenant_id, load_id
    )
    if violation:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=violation,
        )

    stmt = (
        update(Load)
        .where(
            Load.id == load_id,
            Load.tenant_id == tenant_id,
            Load.concurrency_version == expected_concurrency_version,
            Load.status == "draft",
        )
        .values(
            status="ready",
            concurrency_version=Load.concurrency_version + 1,
            updated_at=func.now(),
        )
        .execution_options(synchronize_session=False)
    )
    result = await db.execute(stmt)
    if result.rowcount != 1:
        await db.rollback()
        current_load = await get_load(db, tenant_id, load_id)
        server_snapshot = LoadResponse.model_validate(current_load).model_dump(mode="json") if current_load else None
        raise load_version_conflict_exception(
            load_id=load_id,
            client_version=expected_concurrency_version,
            server_version=current_load.concurrency_version if current_load else None,
            server_snapshot=server_snapshot,
        )
    await db.flush()
    refreshed = await get_load(db, tenant_id, load_id)
    if refreshed is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Load not found")
    await _write_load_audit(
        db,
        tenant_id=tenant_id,
        load=refreshed,
        action="load_marked_ready",
        actor_user_id=actor_user_id,
        request_id=request_id,
        correlation_id=request_id,
        source=source,
        changed_fields={"status": {"before": "draft", "after": "ready"}},
        best_effort=False,
    )
    await db.commit()
    db.expire_all()
    out = await get_load(db, tenant_id, load_id)
    if out is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Load not found")
    return out


async def add_load_note(
    db: AsyncSession,
    tenant_id: int,
    load_id: int,
    body: str,
    author_user_id: str | None = None,
    *,
    request_id: str | None = None,
    correlation_id: str | None = None,
    source: str = "ui",
) -> LoadNote:
    load = await get_load(db, tenant_id, load_id)
    if not load:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Load not found")
    note = LoadNote(tenant_id=tenant_id, load_id=load_id, body=body.strip(), author_user_id=author_user_id)
    db.add(note)
    await db.commit()
    await db.refresh(note)

    await _write_load_audit(
        db,
        tenant_id=tenant_id,
        load=load,
        action="note_added",
        actor_user_id=int(author_user_id) if author_user_id is not None and str(author_user_id).isdigit() else None,
        request_id=request_id,
        correlation_id=correlation_id or request_id,
        source=source,
        changed_fields={"note_id": {"before": None, "after": int(note.id)}},
        context_json={"note_preview": (note.body[:120] if note.body else "")},
    )
    await db.commit()
    return note


async def list_load_notes(db: AsyncSession, tenant_id: int, load_id: int) -> list[LoadNote]:
    load = await get_load(db, tenant_id, load_id)
    if not load:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Load not found")
    result = await db.execute(
        select(LoadNote).where(LoadNote.load_id == load_id, LoadNote.tenant_id == tenant_id).order_by(LoadNote.created_at.desc())
    )
    return list(result.scalars().all())


async def confirm_load_customs_document_snapshot(
    db: AsyncSession,
    tenant_id: int,
    load_id: int,
    *,
    confirming_user_id: str | None,
    expected_concurrency_version: int,
) -> Load:
    load = await get_load(db, tenant_id, load_id)
    if not load:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Load not found")
    _reject_commercial_mutation_if_cancelled(load)
    if load.document_snapshot_confirmed_at is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "detail": "Document snapshot already confirmed for this load",
                "code": "DOCUMENT_SNAPSHOT_ALREADY_CONFIRMED",
                "load_id": load_id,
            },
        )
    if load.customs_broker_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Link a customs broker on the load before confirming the document snapshot",
        )

    broker = await _get_customs_broker(db, tenant_id, load.customs_broker_id)
    if not broker:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Customs broker not found")

    now = datetime.now(timezone.utc)
    snap = LoadCustomsSnapshot(
        load_id=load.id,
        tenant_id=tenant_id,
        legal_name_snapshot=broker.legal_name,
        address_line1_snapshot=broker.address_line1,
        address_line2_snapshot=broker.address_line2,
        city_snapshot=broker.city,
        admin_area_snapshot=broker.admin_area,
        postal_code_snapshot=broker.postal_code,
        country_code_snapshot=broker.country_code,
        phone_primary_snapshot=broker.phone_primary,
        phone_secondary_snapshot=broker.phone_secondary,
        fax_snapshot=broker.fax,
        generic_email_snapshot=broker.generic_email,
        website_url_snapshot=broker.website_url,
        customs_broker_id_at_confirm=broker.id,
        confirmed_at=now,
    )
    db.add(snap)
    await db.flush()

    stmt = (
        update(Load)
        .where(
            Load.id == load_id,
            Load.tenant_id == tenant_id,
            Load.concurrency_version == expected_concurrency_version,
            Load.document_snapshot_confirmed_at.is_(None),
        )
        .values(
            document_snapshot_confirmed_at=now,
            document_snapshot_confirmed_by_user_id=confirming_user_id,
            document_snapshot_version=Load.document_snapshot_version + 1,
            concurrency_version=Load.concurrency_version + 1,
            updated_at=func.now(),
        )
        .execution_options(synchronize_session=False)
    )
    result = await db.execute(stmt)
    if result.rowcount != 1:
        await db.rollback()
        current_load = await get_load(db, tenant_id, load_id)
        server_snapshot = LoadResponse.model_validate(current_load).model_dump(mode="json") if current_load else None
        raise load_version_conflict_exception(
            load_id=load_id,
            client_version=expected_concurrency_version,
            server_version=current_load.concurrency_version if current_load else None,
            server_snapshot=server_snapshot,
        )

    # audit
    out = await get_load(db, tenant_id, load_id)
    if out is not None:
        await _write_load_audit(
            db,
            tenant_id=tenant_id,
            load=out,
            action="document_snapshot_confirmed",
            actor_user_id=int(confirming_user_id) if confirming_user_id and str(confirming_user_id).isdigit() else None,
            request_id=None,
            correlation_id=None,
            source="ui",
            changed_fields={"document_snapshot_confirmed_at": {"before": None, "after": now.isoformat()}},
        )
    await db.commit()
    db.expire_all()
    out = await get_load(db, tenant_id, load_id)
    if out is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Load not found")
    return out
