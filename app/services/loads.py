"""Load service. V1: stop-based, draft/ready, full replace stops on update."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Iterable, Sequence

from fastapi import HTTPException, status
from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.trip_dispatch import (
    DISPATCH_RESOURCES_REQUIRED,
    PRE_DISPATCH_TRIP_CANCEL_STATUSES,
    TRIP_ALLOCATED_AT_LOAD_STATUS,
)
from app.models.broker import Broker, BrokerContact
from app.models.customs_broker import CustomsBroker, LoadCustomsSnapshot
from app.models.driver import Driver
from app.models.load import Load, LoadNote, LoadStop
from app.models.truck import Truck
from app.models.trailer import Trailer
from app.core.concurrency.conflicts import load_version_conflict_exception
from app.schemas.load import LoadCreate, LoadResponse, LoadUpdate, LoadStopCreate, ALLOWED_STATUSES
from app.services import dispatch_trips as dispatch_trips_service
from app.utils.pagination import paginate


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
) -> None:
    """Best-effort audit_events writer for Loads (Slice 5).

    Never raises (load mutations must not fail due to audit).
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
            best_effort=True,
        )
    except Exception:
        # Avoid failing core load mutations; audit is additive during rollout.
        pass


async def _get_driver(db: AsyncSession, tenant_id: int, driver_id: int) -> Driver | None:
    result = await db.execute(select(Driver).where(Driver.id == driver_id, Driver.tenant_id == tenant_id))
    return result.scalar_one_or_none()


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


async def _get_truck(db: AsyncSession, tenant_id: int, truck_id: int) -> Truck | None:
    result = await db.execute(select(Truck).where(Truck.id == truck_id, Truck.tenant_id == tenant_id))
    return result.scalar_one_or_none()


async def _get_trailer(db: AsyncSession, tenant_id: int, trailer_id: int) -> Trailer | None:
    result = await db.execute(select(Trailer).where(Trailer.id == trailer_id, Trailer.tenant_id == tenant_id))
    return result.scalar_one_or_none()


def _merged_scalar(load: Load, data: dict, key: str):
    if key in data:
        return data[key]
    return getattr(load, key)



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
    """Exclude stops from data passed to Load model."""
    if isinstance(payload, LoadCreate):
        data = payload.model_dump(exclude={"stops"})
    else:
        data = payload.model_dump(exclude_unset=True, exclude={"stops", "expected_concurrency_version"})
    return data


async def create_load(db: AsyncSession, tenant_id: int, payload: LoadCreate) -> Load:
    if payload.driver_id is not None and not await _get_driver(db, tenant_id, payload.driver_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Driver not found")
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
    if payload.truck_id is not None and not await _get_truck(db, tenant_id, payload.truck_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Truck not found")
    if payload.trailer_id is not None and not await _get_trailer(db, tenant_id, payload.trailer_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Trailer not found")
    if payload.customs_broker_id is not None and not await _get_customs_broker(db, tenant_id, payload.customs_broker_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Customs broker not found")

    load_number = payload.load_number or f"DRAFT-{uuid.uuid4().hex[:8].upper()}"
    await _ensure_unique_load_number(db, tenant_id, load_number)

    data = _load_data_from_payload(payload)
    data["load_number"] = load_number
    if "status" not in data:
        data["status"] = "draft"

    load = Load(**data, tenant_id=tenant_id)
    db.add(load)
    await db.flush()

    if payload.stops:
        for i, s in enumerate(payload.stops):
            stop_data = s.model_dump()
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
            selectinload(Load.stops),
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

    expected = payload.expected_concurrency_version
    old_status = (load.status or "").strip().lower()
    old_driver_id = load.driver_id
    old_customs_broker_id = load.customs_broker_id
    data = _load_data_from_payload(payload)
    before_snapshot: dict[str, object] = {str(k): getattr(load, k, None) for k in data.keys()}

    if "driver_id" in data:
        driver_id = data["driver_id"]
        if driver_id is not None and not await _get_driver(db, tenant_id, driver_id):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Driver not found")
    if "truck_id" in data:
        truck_id = data["truck_id"]
        if truck_id is not None and not await _get_truck(db, tenant_id, truck_id):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Truck not found")
    if "trailer_id" in data:
        trailer_id = data["trailer_id"]
        if trailer_id is not None and not await _get_trailer(db, tenant_id, trailer_id):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Trailer not found")

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

    new_status = (_merged_scalar(load, data, "status") or load.status or "").strip().lower()
    merged_driver_id = _merged_scalar(load, data, "driver_id")
    merged_truck_id = _merged_scalar(load, data, "truck_id")

    next_aid, next_tnum, next_atid = load.active_dispatch_trip_id, load.trip_number, load.active_trip_id
    if (
        new_status == TRIP_ALLOCATED_AT_LOAD_STATUS
        and old_status != TRIP_ALLOCATED_AT_LOAD_STATUS
    ):
        if not merged_driver_id or not merged_truck_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "detail": "Driver and truck are required before dispatching",
                    "code": DISPATCH_RESOURCES_REQUIRED,
                },
            )
        dres = await dispatch_trips_service.ensure_active_trip_for_freight_load(db, tenant_id, load.id)
        next_aid, next_tnum = dres.dispatch_trip.id, dres.dispatch_trip.trip_number
        next_atid = dres.container_trip_id
    elif (
        old_status == TRIP_ALLOCATED_AT_LOAD_STATUS
        and new_status != TRIP_ALLOCATED_AT_LOAD_STATUS
        and new_status in PRE_DISPATCH_TRIP_CANCEL_STATUSES
    ):
        await dispatch_trips_service.cancel_active_trip_for_load(db, tenant_id, load.id, load=None)
        next_aid, next_tnum, next_atid = None, None, None

    values = {**data}
    values["active_dispatch_trip_id"] = next_aid
    values["trip_number"] = next_tnum
    values["active_trip_id"] = next_atid
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

    if "stops" in payload.model_dump(exclude_unset=True):
        await db.execute(
            delete(LoadStop).where(LoadStop.load_id == load_id, LoadStop.tenant_id == tenant_id)
        )
        await db.flush()
        stops_payload: Sequence[LoadStopCreate] = payload.stops or []
        for i, s in enumerate(stops_payload):
            stop_data = s.model_dump()
            stop_data["sequence"] = s.sequence if s.sequence is not None else i
            stop = LoadStop(tenant_id=tenant_id, load_id=load_id, **stop_data)
            db.add(stop)

    await db.commit()
    db.expire_all()
    out = await get_load(db, tenant_id, load_id)
    if out is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Load not found")

    # Slice 5 audit writes (best-effort). Correlation defaults to request_id.
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
        await _write_load_audit(
            db,
            tenant_id=tenant_id,
            load=out,
            action="load_updated",
            actor_user_id=actor_user_id,
            request_id=request_id,
            correlation_id=corr,
            source=source,
            changed_fields=residual_changed,
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

    # Persist audit rows (best-effort writes are additive).
    await db.commit()
    return out


async def delete_load(
    db: AsyncSession, tenant_id: int, load_id: int, *, expected_concurrency_version: int
) -> None:
    stmt = delete(Load).where(
        Load.id == load_id,
        Load.tenant_id == tenant_id,
        Load.concurrency_version == expected_concurrency_version,
    )
    result = await db.execute(stmt)
    if result.rowcount == 1:
        await db.commit()
        return
    await db.rollback()
    current_load = await get_load(db, tenant_id, load_id)
    if current_load is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Load not found")
    server_snapshot = LoadResponse.model_validate(current_load).model_dump(mode="json")
    raise load_version_conflict_exception(
        load_id=load_id,
        client_version=expected_concurrency_version,
        server_version=current_load.concurrency_version,
        server_snapshot=server_snapshot,
    )


async def list_loads_for_board(
    db: AsyncSession,
    tenant_id: int,
    search: str | None = None,
) -> dict[str, list]:
    """Return loads grouped by status for dispatch board. Excludes draft. No pagination."""
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
    grouped: dict[str, list] = {s: [] for s in board_statuses}
    for load in loads:
        s = (load.status or "ready").strip().lower()
        if s in grouped:
            grouped[s].append(load)
        else:
            grouped.setdefault("ready", []).append(load)
    return grouped


async def mark_load_ready(
    db: AsyncSession, tenant_id: int, load_id: int, *, expected_concurrency_version: int
) -> Load:
    """Mark draft as ready. Validates minimum: broker, broker_load_reference, at least one pickup and one drop."""
    load = await get_load(db, tenant_id, load_id)
    if not load:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Load not found")

    if load.status != "draft":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Only draft loads can be marked ready; current status is {load.status}",
        )

    if not (load.broker_id or load.broker_name_snapshot):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Broker or broker name must be set before marking ready",
        )
    if not load.broker_load_reference:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Broker load reference must be set before marking ready",
        )

    pickups = [s for s in load.stops if s.stop_type.upper() == "PICKUP"]
    drops = [s for s in load.stops if s.stop_type.upper() == "DROP"]
    if not pickups:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one pickup stop is required before marking ready",
        )
    if not drops:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one drop stop is required before marking ready",
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
