"""Set load_stops.arrived_at / departed_at once. Does not edit commercial stops or custody."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.load_integrity import WRITABLE_LOAD_STOP_TYPES
from app.constants.trip_dispatch import (
    TRIP_CONTAINER_STATUS_IN_PROGRESS,
    TRIP_LOAD_STATUS_WITHIN_ACTIVE,
)
from app.models.load import LoadStop
from app.models.trip import TripLoad
from app.schemas.load_stop_execution import StopExecutionBody, StopExecutionResponse
from app.services.audit_events import write_audit_event
from app.services.trips import (
    _lock_load_for_membership,
    _lock_trip_for_mutation,
    _validate_execution_signal_source,
)


def _conflict(code: str, detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"detail": detail, "code": code})


def _response(
    *,
    trip_id: int,
    load_id: int,
    stop: LoadStop,
    trip_status: str,
    load_status: str,
    membership_status: str,
    replayed: bool,
) -> StopExecutionResponse:
    return StopExecutionResponse(
        trip_id=trip_id,
        load_id=load_id,
        stop_id=int(stop.id),
        stop_type=str(stop.stop_type),
        arrived_at=stop.arrived_at,
        departed_at=stop.departed_at,
        replayed=replayed,
        load_status=load_status,
        trip_status=trip_status,
        membership_status_within_trip=membership_status,
    )


async def record_stop_arrival(
    db: AsyncSession,
    tenant_id: int,
    trip_id: int,
    load_id: int,
    stop_id: int,
    body: StopExecutionBody,
    *,
    actor_user_id: int | None,
    actor_label: str | None,
    request_id: str | None,
) -> StopExecutionResponse:
    return await _record_stop_execution(
        db,
        tenant_id,
        trip_id,
        load_id,
        stop_id,
        body,
        kind="arrival",
        actor_user_id=actor_user_id,
        actor_label=actor_label,
        request_id=request_id,
    )


async def record_stop_departure(
    db: AsyncSession,
    tenant_id: int,
    trip_id: int,
    load_id: int,
    stop_id: int,
    body: StopExecutionBody,
    *,
    actor_user_id: int | None,
    actor_label: str | None,
    request_id: str | None,
) -> StopExecutionResponse:
    return await _record_stop_execution(
        db,
        tenant_id,
        trip_id,
        load_id,
        stop_id,
        body,
        kind="departure",
        actor_user_id=actor_user_id,
        actor_label=actor_label,
        request_id=request_id,
    )


async def _record_stop_execution(
    db: AsyncSession,
    tenant_id: int,
    trip_id: int,
    load_id: int,
    stop_id: int,
    body: StopExecutionBody,
    *,
    kind: str,
    actor_user_id: int | None,
    actor_label: str | None,
    request_id: str | None,
) -> StopExecutionResponse:
    signal_source = _validate_execution_signal_source(body.source)
    trip = await _lock_trip_for_mutation(db, tenant_id, trip_id)
    load = await _lock_load_for_membership(db, tenant_id, load_id)
    if trip.status != TRIP_CONTAINER_STATUS_IN_PROGRESS:
        raise _conflict(
            "INVALID_TRIP_STATUS_FOR_STOP_EXECUTION",
            f"Trip status '{trip.status}' cannot record stop {kind}",
        )

    membership = await db.scalar(
        select(TripLoad).where(
            TripLoad.tenant_id == tenant_id,
            TripLoad.trip_id == trip_id,
            TripLoad.load_id == load_id,
        )
    )
    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"detail": "No trip_load membership for this load", "code": "TRIP_LOAD_NOT_FOUND"},
        )
    if (
        membership.status_within_trip != TRIP_LOAD_STATUS_WITHIN_ACTIVE
        or membership.completed_at is not None
        or membership.removed_at is not None
    ):
        raise _conflict("MEMBERSHIP_NOT_ACTIVE", "Membership is not active")

    stop = await db.scalar(
        select(LoadStop)
        .where(
            LoadStop.tenant_id == tenant_id,
            LoadStop.load_id == load_id,
            LoadStop.id == stop_id,
        )
        .with_for_update()
    )
    if stop is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"detail": "Stop is not on this Load", "code": "STOP_NOT_FOUND"},
        )
    stop_type = (stop.stop_type or "").strip().upper()
    if stop_type not in WRITABLE_LOAD_STOP_TYPES:
        raise _conflict(
            "INVALID_STOP_TYPE",
            f"Stop type '{stop.stop_type}' cannot record arrival or departure",
        )

    if kind == "departure" and stop.departed_at is not None:
        return _response(
            trip_id=trip_id,
            load_id=load_id,
            stop=stop,
            trip_status=str(trip.status),
            load_status=str(load.status),
            membership_status=str(membership.status_within_trip),
            replayed=True,
        )
    if kind == "departure" and stop.arrived_at is None:
        raise _conflict("DEPARTURE_REQUIRES_ARRIVAL", "Departure requires an arrival timestamp")
    if kind == "arrival" and stop.arrived_at is not None:
        return _response(
            trip_id=trip_id,
            load_id=load_id,
            stop=stop,
            trip_status=str(trip.status),
            load_status=str(load.status),
            membership_status=str(membership.status_within_trip),
            replayed=True,
        )

    occurred_at = body.occurred_at or datetime.now(timezone.utc)
    if occurred_at.tzinfo is None:
        occurred_at = occurred_at.replace(tzinfo=timezone.utc)
    field = "arrived_at" if kind == "arrival" else "departed_at"
    setattr(stop, field, occurred_at)
    await db.flush()

    action = "stop_arrived" if kind == "arrival" else "stop_departed"
    await write_audit_event(
        db,
        tenant_id=tenant_id,
        module="loads",
        entity_type="load_stop",
        entity_id=str(int(stop.id)),
        entity_label=f"load:{load_id} stop:{stop.id}",
        action=action,
        source="api",
        actor_type="user" if actor_user_id is not None else "api",
        actor_user_id=actor_user_id,
        actor_label=actor_label,
        request_id=request_id,
        correlation_id=request_id,
        changed_fields={field: {"before": None, "after": occurred_at.isoformat()}},
        context_json={
            "signal_source": signal_source,
            "trip_id": trip_id,
            "load_id": load_id,
            "stop_id": int(stop.id),
            "notes": body.notes,
        },
        event_at=occurred_at,
        best_effort=False,
    )
    return _response(
        trip_id=trip_id,
        load_id=load_id,
        stop=stop,
        trip_status=str(trip.status),
        load_status=str(load.status),
        membership_status=str(membership.status_within_trip),
        replayed=False,
    )
