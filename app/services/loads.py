"""Load service. V1: stop-based, draft/ready, full replace stops on update."""
from __future__ import annotations

import uuid
from datetime import date
from typing import Iterable, Sequence

from fastapi import HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.broker import Broker, BrokerContact
from app.models.driver import Driver
from app.models.load import Load, LoadNote, LoadStop
from app.models.truck import Truck
from app.models.trailer import Trailer
from app.schemas.load import LoadCreate, LoadUpdate, LoadStopCreate, ALLOWED_STATUSES
from app.utils.pagination import paginate


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


async def _get_truck(db: AsyncSession, tenant_id: int, truck_id: int) -> Truck | None:
    result = await db.execute(select(Truck).where(Truck.id == truck_id, Truck.tenant_id == tenant_id))
    return result.scalar_one_or_none()


async def _get_trailer(db: AsyncSession, tenant_id: int, trailer_id: int) -> Trailer | None:
    result = await db.execute(select(Trailer).where(Trailer.id == trailer_id, Trailer.tenant_id == tenant_id))
    return result.scalar_one_or_none()


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
        data = payload.model_dump(exclude_unset=True, exclude={"stops"})
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
    await db.refresh(load)
    # Re-fetch with relationships for LoadResponse (avoids async lazy-load)
    return await get_load(db, tenant_id, load.id) or load


async def get_load(db: AsyncSession, tenant_id: int, load_id: int) -> Load | None:
    result = await db.execute(
        select(Load)
        .options(
            selectinload(Load.driver),
            selectinload(Load.broker),
            selectinload(Load.broker_contact),
            selectinload(Load.truck),
            selectinload(Load.trailer),
            selectinload(Load.stops),
        )
        .where(Load.id == load_id, Load.tenant_id == tenant_id)
    )
    return result.scalar_one_or_none()


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


async def update_load(db: AsyncSession, tenant_id: int, load_id: int, payload: LoadUpdate) -> Load:
    load = await get_load(db, tenant_id, load_id)
    if not load:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Load not found")

    data = _load_data_from_payload(payload)

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

    if "load_number" in data and data["load_number"]:
        await _ensure_unique_load_number(db, tenant_id, data["load_number"], exclude_id=load.id)

    for key, value in data.items():
        setattr(load, key, value)

    # Full replace stops: submitted ordered list is authoritative
    if "stops" in payload.model_dump(exclude_unset=True):
        await db.execute(select(LoadStop).where(LoadStop.load_id == load.id).with_for_update())
        for s in load.stops:
            await db.delete(s)
        await db.flush()
        stops_payload: Sequence[LoadStopCreate] = payload.stops or []
        for i, s in enumerate(stops_payload):
            stop_data = s.model_dump()
            stop_data["sequence"] = s.sequence if s.sequence is not None else i
            stop = LoadStop(tenant_id=tenant_id, load_id=load.id, **stop_data)
            db.add(stop)

    await db.commit()
    await db.refresh(load)
    # Re-fetch with relationships for LoadResponse (avoids async lazy-load)
    return await get_load(db, tenant_id, load.id) or load


async def delete_load(db: AsyncSession, tenant_id: int, load_id: int) -> None:
    load = await get_load(db, tenant_id, load_id)
    if not load:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Load not found")

    await db.delete(load)
    await db.commit()


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


async def mark_load_ready(db: AsyncSession, tenant_id: int, load_id: int) -> Load:
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

    load.status = "ready"
    await db.commit()
    await db.refresh(load)
    # Re-fetch with relationships for LoadResponse (avoids async lazy-load)
    return await get_load(db, tenant_id, load.id) or load


async def add_load_note(
    db: AsyncSession, tenant_id: int, load_id: int, body: str, author_user_id: str | None = None
) -> LoadNote:
    load = await get_load(db, tenant_id, load_id)
    if not load:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Load not found")
    note = LoadNote(tenant_id=tenant_id, load_id=load_id, body=body.strip(), author_user_id=author_user_id)
    db.add(note)
    await db.commit()
    await db.refresh(note)
    return note


async def list_load_notes(db: AsyncSession, tenant_id: int, load_id: int) -> list[LoadNote]:
    load = await get_load(db, tenant_id, load_id)
    if not load:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Load not found")
    result = await db.execute(
        select(LoadNote).where(LoadNote.load_id == load_id, LoadNote.tenant_id == tenant_id).order_by(LoadNote.created_at.desc())
    )
    return list(result.scalars().all())
