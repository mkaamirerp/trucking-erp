"""Custody Slice 2 — operational transitions (accept / yard-handoff / take-custody).

Lock order: Trip FOR UPDATE → Load FOR UPDATE → event/snapshot/TripLoad.
Does not start Trip execution or mutate Load commercial status.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.custody import (
    CUSTODY_EVENT_TRIP_ACCEPT,
    CUSTODY_EVENT_TRIP_TAKEOVER,
    CUSTODY_EVENT_YARD_HANDOFF,
    CUSTODY_OWNER_TERMINAL,
    CUSTODY_OWNER_TRIP,
    CUSTODY_OWNER_UNKNOWN,
    CUSTODY_PLACEMENT_ON_TRAILER,
    CUSTODY_PLACEMENT_STAGED,
    CUSTODY_SOURCE_API,
)
from app.constants.trip_dispatch import (
    TRIP_CONTAINER_STATUS_ASSIGNED,
    TRIP_CONTAINER_STATUS_CANCELLED,
    TRIP_CONTAINER_STATUS_COMPLETED,
    TRIP_CONTAINER_STATUS_IN_PROGRESS,
    TRIP_LOAD_STATUS_WITHIN_ACTIVE,
    TRIP_LOAD_STATUS_WITHIN_COMPLETED,
    TRIP_LOAD_STATUS_WITHIN_PLANNED,
    TRIP_LOAD_STATUS_WITHIN_REMOVED,
)
from app.models.load import Load
from app.models.load_custody_event import LoadCustodyEvent
from app.models.terminal import Terminal
from app.models.trip import Trip, TripLoad
from app.schemas.custody import (
    AcceptCustodyBody,
    CustodyTransitionResponse,
    LoadCustodyEventResponse,
    LoadCustodySnapshotResponse,
    TakeCustodyBody,
    YardHandoffBody,
)
from app.services.trips import (
    _activate_trip_load_membership_locked,
    _complete_trip_load_membership_locked,
    _lock_load_for_membership,
    _lock_trip_for_mutation,
    _raise_if_trip_already_completed,
)


def _conflict(code: str, detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={"detail": detail, "code": code},
    )


def _snapshot_from_load(load: Load) -> LoadCustodySnapshotResponse:
    return LoadCustodySnapshotResponse(
        load_id=int(load.id),
        custody_owner=load.custody_owner,
        custody_trip_id=load.custody_trip_id,
        custody_terminal_id=load.custody_terminal_id,
        custody_placement=load.custody_placement,
        custody_trailer_id=load.custody_trailer_id,
        custody_since_at=load.custody_since_at,
        last_custody_event_id=load.last_custody_event_id,
    )


def _transition_response(
    *,
    load: Load,
    trip: Trip,
    tl: TripLoad,
    event: LoadCustodyEvent,
    replayed: bool,
) -> CustodyTransitionResponse:
    return CustodyTransitionResponse(
        load_id=int(load.id),
        trip_id=int(trip.id),
        trip_status=str(trip.status),
        load_status=str(load.status),
        membership_status_within_trip=str(tl.status_within_trip),
        active_trip_id=int(load.active_trip_id) if load.active_trip_id is not None else None,
        snapshot=_snapshot_from_load(load),
        event=LoadCustodyEventResponse.model_validate(event),
        replayed=replayed,
    )


async def _get_trip_load(
    db: AsyncSession, tenant_id: int, trip_id: int, load_id: int
) -> TripLoad | None:
    return await db.scalar(
        select(TripLoad).where(
            TripLoad.tenant_id == tenant_id,
            TripLoad.trip_id == trip_id,
            TripLoad.load_id == load_id,
        )
    )


def _is_open_active(tl: TripLoad) -> bool:
    return (
        tl.status_within_trip == TRIP_LOAD_STATUS_WITHIN_ACTIVE
        and tl.completed_at is None
        and tl.removed_at is None
    )


def _is_open_planned(tl: TripLoad) -> bool:
    return (
        tl.status_within_trip == TRIP_LOAD_STATUS_WITHIN_PLANNED
        and tl.completed_at is None
        and tl.removed_at is None
    )


def _is_completed_membership(tl: TripLoad) -> bool:
    return tl.status_within_trip == TRIP_LOAD_STATUS_WITHIN_COMPLETED and tl.completed_at is not None


def _raise_if_membership_removed(tl: TripLoad) -> None:
    if tl.status_within_trip == TRIP_LOAD_STATUS_WITHIN_REMOVED or tl.removed_at is not None:
        raise _conflict("MEMBERSHIP_ALREADY_REMOVED", "Membership was removed")


def _raise_if_membership_completed(tl: TripLoad) -> None:
    if tl.status_within_trip == TRIP_LOAD_STATUS_WITHIN_COMPLETED or tl.completed_at is not None:
        raise _conflict("MEMBERSHIP_ALREADY_COMPLETED", "Completed membership cannot be activated")


def _require_trip_not_terminal(trip: Trip) -> None:
    _raise_if_trip_already_completed(trip)
    if trip.status == TRIP_CONTAINER_STATUS_CANCELLED:
        raise _conflict("TRIP_CANCELLED", "Trip is cancelled")


def _require_trip_eligible_for_custody(trip: Trip) -> None:
    if trip.status not in (TRIP_CONTAINER_STATUS_ASSIGNED, TRIP_CONTAINER_STATUS_IN_PROGRESS):
        raise _conflict(
            "INVALID_TRIP_STATUS_FOR_ACTIVATE",
            f"Trip status '{trip.status}' cannot accept/take custody",
        )
    if trip.status == TRIP_CONTAINER_STATUS_ASSIGNED and (
        trip.driver_id is None or trip.truck_id is None or trip.trailer_id is None
    ):
        raise _conflict(
            "TRIP_ASSIGNMENT_INCOMPLETE",
            "Driver, truck, and trailer must be assigned before custody transitions",
        )
    if trip.trailer_id is None:
        raise _conflict("TRIP_TRAILER_REQUIRED", "Trip trailer is required for custody transitions")


async def _find_event_by_idempotency(
    db: AsyncSession, tenant_id: int, load_id: int, key: str
) -> LoadCustodyEvent | None:
    return await db.scalar(
        select(LoadCustodyEvent).where(
            LoadCustodyEvent.tenant_id == tenant_id,
            LoadCustodyEvent.load_id == load_id,
            LoadCustodyEvent.idempotency_key == key,
        )
    )


async def _get_event_by_id(
    db: AsyncSession, tenant_id: int, event_id: int | None
) -> LoadCustodyEvent | None:
    if event_id is None:
        return None
    return await db.scalar(
        select(LoadCustodyEvent).where(
            LoadCustodyEvent.tenant_id == tenant_id,
            LoadCustodyEvent.id == event_id,
        )
    )


async def _append_event(
    db: AsyncSession,
    *,
    tenant_id: int,
    load_id: int,
    event_type: str,
    occurred_at: datetime,
    custody_owner_after: str,
    placement_after: str,
    trip_id: int | None,
    terminal_id: int | None,
    trailer_id: int | None,
    actor_user_id: int | None,
    notes: str | None,
    idempotency_key: str | None,
) -> LoadCustodyEvent:
    ev = LoadCustodyEvent(
        tenant_id=tenant_id,
        load_id=load_id,
        event_type=event_type,
        occurred_at=occurred_at,
        recorded_at=datetime.now(timezone.utc),
        custody_owner_after=custody_owner_after,
        placement_after=placement_after,
        trip_id=trip_id,
        terminal_id=terminal_id,
        trailer_id=trailer_id,
        actor_user_id=actor_user_id,
        source=CUSTODY_SOURCE_API,
        notes=notes,
        idempotency_key=idempotency_key,
    )
    db.add(ev)
    try:
        await db.flush()
    except IntegrityError as exc:
        raise _conflict(
            "IDEMPOTENCY_KEY_CONFLICT",
            "idempotency_key already used for a different custody event on this Load",
        ) from exc
    return ev


def _apply_snapshot(
    load: Load,
    *,
    owner: str,
    trip_id: int | None,
    terminal_id: int | None,
    placement: str,
    trailer_id: int | None,
    since: datetime,
    event_id: int,
) -> None:
    load.custody_owner = owner
    load.custody_trip_id = trip_id
    load.custody_terminal_id = terminal_id
    load.custody_placement = placement
    load.custody_trailer_id = trailer_id
    load.custody_since_at = since
    load.last_custody_event_id = event_id


# ---------------------------------------------------------------------------
# accept-custody
# ---------------------------------------------------------------------------


async def accept_load_custody(
    db: AsyncSession,
    tenant_id: int,
    trip_id: int,
    load_id: int,
    body: AcceptCustodyBody | None = None,
    *,
    actor_user_id: int | None = None,
) -> CustodyTransitionResponse:
    body = body or AcceptCustodyBody()
    trip = await _lock_trip_for_mutation(db, tenant_id, trip_id)
    load = await _lock_load_for_membership(db, tenant_id, load_id)
    _require_trip_not_terminal(trip)

    tl = await _get_trip_load(db, tenant_id, trip_id, load_id)
    if tl is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"detail": "No trip_load membership for this load", "code": "TRIP_LOAD_NOT_FOUND"},
        )

    # State-based replay
    if (
        _is_open_active(tl)
        and load.custody_owner == CUSTODY_OWNER_TRIP
        and load.custody_trip_id == trip_id
    ):
        last = await _get_event_by_id(db, tenant_id, load.last_custody_event_id)
        if last is not None and last.event_type == CUSTODY_EVENT_TRIP_ACCEPT and last.trip_id == trip_id:
            if body.idempotency_key and last.idempotency_key and last.idempotency_key != body.idempotency_key:
                # Different key on already-complete accept — treat as conflict only if key exists on another event
                existing = await _find_event_by_idempotency(db, tenant_id, load_id, body.idempotency_key)
                if existing is not None and int(existing.id) != int(last.id):
                    raise _conflict(
                        "IDEMPOTENCY_KEY_CONFLICT",
                        "idempotency_key already used for a different custody event on this Load",
                    )
            return _transition_response(load=load, trip=trip, tl=tl, event=last, replayed=True)

    if body.idempotency_key:
        existing = await _find_event_by_idempotency(db, tenant_id, load_id, body.idempotency_key)
        if existing is not None:
            if (
                existing.event_type == CUSTODY_EVENT_TRIP_ACCEPT
                and existing.trip_id == trip_id
                and _is_open_active(tl)
                and load.custody_owner == CUSTODY_OWNER_TRIP
                and load.custody_trip_id == trip_id
            ):
                return _transition_response(load=load, trip=trip, tl=tl, event=existing, replayed=True)
            raise _conflict(
                "IDEMPOTENCY_KEY_CONFLICT",
                "idempotency_key already used for a different custody event on this Load",
            )

    _raise_if_membership_removed(tl)
    _raise_if_membership_completed(tl)
    if not _is_open_planned(tl):
        raise _conflict("MEMBERSHIP_NOT_PLANNED", "Membership is not planned")

    other_active = await db.scalar(
        select(TripLoad).where(
            TripLoad.tenant_id == tenant_id,
            TripLoad.load_id == load_id,
            TripLoad.status_within_trip == TRIP_LOAD_STATUS_WITHIN_ACTIVE,
            TripLoad.completed_at.is_(None),
            TripLoad.removed_at.is_(None),
        )
    )
    if other_active is not None:
        raise _conflict("LOAD_ACTIVE_ON_OTHER_TRIP", "Load already active on another trip")

    _require_trip_eligible_for_custody(trip)

    if load.custody_owner != CUSTODY_OWNER_UNKNOWN:
        if load.custody_owner == CUSTODY_OWNER_TERMINAL:
            raise _conflict(
                "INVALID_CUSTODY_STATE",
                "Cannot accept-custody while Load is in terminal custody; use take-custody",
            )
        raise _conflict(
            "INVALID_CUSTODY_STATE",
            f"Accept-custody requires custody_owner=unknown (got '{load.custody_owner}')",
        )

    occurred_at = body.occurred_at or datetime.now(timezone.utc)
    trailer_id = int(trip.trailer_id)
    ev = await _append_event(
        db,
        tenant_id=tenant_id,
        load_id=load_id,
        event_type=CUSTODY_EVENT_TRIP_ACCEPT,
        occurred_at=occurred_at,
        custody_owner_after=CUSTODY_OWNER_TRIP,
        placement_after=CUSTODY_PLACEMENT_ON_TRAILER,
        trip_id=trip_id,
        terminal_id=None,
        trailer_id=trailer_id,
        actor_user_id=actor_user_id,
        notes=body.notes,
        idempotency_key=body.idempotency_key,
    )
    _apply_snapshot(
        load,
        owner=CUSTODY_OWNER_TRIP,
        trip_id=trip_id,
        terminal_id=None,
        placement=CUSTODY_PLACEMENT_ON_TRAILER,
        trailer_id=trailer_id,
        since=occurred_at,
        event_id=int(ev.id),
    )
    await db.flush()

    tl = await _activate_trip_load_membership_locked(
        db, tenant_id, trip, load, require_trailer=True
    )
    await db.refresh(load)
    return _transition_response(load=load, trip=trip, tl=tl, event=ev, replayed=False)


# ---------------------------------------------------------------------------
# yard-handoff
# ---------------------------------------------------------------------------


async def yard_handoff_load_custody(
    db: AsyncSession,
    tenant_id: int,
    trip_id: int,
    load_id: int,
    body: YardHandoffBody,
    *,
    actor_user_id: int | None = None,
) -> CustodyTransitionResponse:
    if body.placement not in (CUSTODY_PLACEMENT_ON_TRAILER, CUSTODY_PLACEMENT_STAGED):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "detail": "placement must be on_trailer or staged",
                "code": "INVALID_PLACEMENT",
            },
        )

    trip = await _lock_trip_for_mutation(db, tenant_id, trip_id)
    load = await _lock_load_for_membership(db, tenant_id, load_id)
    _require_trip_not_terminal(trip)

    tl = await _get_trip_load(db, tenant_id, trip_id, load_id)
    if tl is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"detail": "No trip_load membership for this load", "code": "TRIP_LOAD_NOT_FOUND"},
        )

    # State-based replay
    if (
        _is_completed_membership(tl)
        and load.custody_owner == CUSTODY_OWNER_TERMINAL
        and load.custody_terminal_id == body.terminal_id
        and load.custody_placement == body.placement
    ):
        last = await _get_event_by_id(db, tenant_id, load.last_custody_event_id)
        if (
            last is not None
            and last.event_type == CUSTODY_EVENT_YARD_HANDOFF
            and last.trip_id == trip_id
            and last.terminal_id == body.terminal_id
            and last.placement_after == body.placement
        ):
            if body.idempotency_key and last.idempotency_key and last.idempotency_key != body.idempotency_key:
                existing = await _find_event_by_idempotency(db, tenant_id, load_id, body.idempotency_key)
                if existing is not None and int(existing.id) != int(last.id):
                    raise _conflict(
                        "IDEMPOTENCY_KEY_CONFLICT",
                        "idempotency_key already used for a different custody event on this Load",
                    )
            return _transition_response(load=load, trip=trip, tl=tl, event=last, replayed=True)

    if body.idempotency_key:
        existing = await _find_event_by_idempotency(db, tenant_id, load_id, body.idempotency_key)
        if existing is not None:
            if (
                existing.event_type == CUSTODY_EVENT_YARD_HANDOFF
                and existing.trip_id == trip_id
                and existing.terminal_id == body.terminal_id
                and existing.placement_after == body.placement
                and _is_completed_membership(tl)
                and load.custody_owner == CUSTODY_OWNER_TERMINAL
                and load.custody_terminal_id == body.terminal_id
            ):
                return _transition_response(load=load, trip=trip, tl=tl, event=existing, replayed=True)
            raise _conflict(
                "IDEMPOTENCY_KEY_CONFLICT",
                "idempotency_key already used for a different custody event on this Load",
            )

    _raise_if_membership_removed(tl)
    if not _is_open_active(tl):
        raise _conflict("MEMBERSHIP_NOT_ACTIVE", "Membership is not active")

    if load.custody_owner != CUSTODY_OWNER_TRIP or load.custody_trip_id != trip_id:
        raise _conflict(
            "CUSTODY_SNAPSHOT_MISMATCH",
            "Load custody snapshot must be trip custody on this Trip for yard-handoff",
        )
    if load.active_trip_id != trip_id:
        raise _conflict(
            "CUSTODY_SNAPSHOT_MISMATCH",
            "loads.active_trip_id must equal this Trip for yard-handoff",
        )

    terminal = await db.scalar(
        select(Terminal).where(Terminal.tenant_id == tenant_id, Terminal.id == body.terminal_id)
    )
    if terminal is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"detail": "Terminal not found", "code": "TERMINAL_NOT_FOUND"},
        )
    if not terminal.is_active:
        raise _conflict("TERMINAL_INACTIVE", "Terminal is inactive")

    retained_trailer: int | None = None
    if body.placement == CUSTODY_PLACEMENT_ON_TRAILER:
        current_trailer = load.custody_trailer_id
        trip_trailer = trip.trailer_id
        if current_trailer is None:
            raise _conflict(
                "TRAILER_MISMATCH",
                "on_trailer handoff requires current custody_trailer_id",
            )
        if trip_trailer is None or int(current_trailer) != int(trip_trailer):
            raise _conflict(
                "TRAILER_MISMATCH",
                "on_trailer handoff requires custody trailer to match inbound Trip.trailer_id",
            )
        if body.trailer_id is not None and int(body.trailer_id) != int(current_trailer):
            raise _conflict(
                "TRAILER_MISMATCH",
                "Requested trailer_id does not match current custody trailer",
            )
        retained_trailer = int(current_trailer)
    else:
        # staged clears trailer; body trailer_id if provided must not invent a transfer
        if body.trailer_id is not None:
            raise _conflict(
                "TRAILER_MISMATCH",
                "staged handoff clears trailer; do not supply trailer_id",
            )
        retained_trailer = None

    occurred_at = body.occurred_at or datetime.now(timezone.utc)
    ev = await _append_event(
        db,
        tenant_id=tenant_id,
        load_id=load_id,
        event_type=CUSTODY_EVENT_YARD_HANDOFF,
        occurred_at=occurred_at,
        custody_owner_after=CUSTODY_OWNER_TERMINAL,
        placement_after=body.placement,
        trip_id=trip_id,
        terminal_id=int(terminal.id),
        trailer_id=retained_trailer,
        actor_user_id=actor_user_id,
        notes=body.notes,
        idempotency_key=body.idempotency_key,
    )
    _apply_snapshot(
        load,
        owner=CUSTODY_OWNER_TERMINAL,
        trip_id=None,
        terminal_id=int(terminal.id),
        placement=body.placement,
        trailer_id=retained_trailer,
        since=occurred_at,
        event_id=int(ev.id),
    )
    await db.flush()

    tl = await _complete_trip_load_membership_locked(db, tenant_id, trip, load)
    await db.refresh(load)
    return _transition_response(load=load, trip=trip, tl=tl, event=ev, replayed=False)


# ---------------------------------------------------------------------------
# take-custody
# ---------------------------------------------------------------------------


async def take_load_custody(
    db: AsyncSession,
    tenant_id: int,
    trip_id: int,
    load_id: int,
    body: TakeCustodyBody | None = None,
    *,
    actor_user_id: int | None = None,
) -> CustodyTransitionResponse:
    body = body or TakeCustodyBody()
    trip = await _lock_trip_for_mutation(db, tenant_id, trip_id)
    load = await _lock_load_for_membership(db, tenant_id, load_id)
    _require_trip_not_terminal(trip)

    tl = await _get_trip_load(db, tenant_id, trip_id, load_id)
    if tl is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"detail": "No trip_load membership for this load", "code": "TRIP_LOAD_NOT_FOUND"},
        )

    # State-based replay
    if (
        _is_open_active(tl)
        and load.custody_owner == CUSTODY_OWNER_TRIP
        and load.custody_trip_id == trip_id
    ):
        last = await _get_event_by_id(db, tenant_id, load.last_custody_event_id)
        if last is not None and last.event_type == CUSTODY_EVENT_TRIP_TAKEOVER and last.trip_id == trip_id:
            if body.idempotency_key and last.idempotency_key and last.idempotency_key != body.idempotency_key:
                existing = await _find_event_by_idempotency(db, tenant_id, load_id, body.idempotency_key)
                if existing is not None and int(existing.id) != int(last.id):
                    raise _conflict(
                        "IDEMPOTENCY_KEY_CONFLICT",
                        "idempotency_key already used for a different custody event on this Load",
                    )
            return _transition_response(load=load, trip=trip, tl=tl, event=last, replayed=True)

    if body.idempotency_key:
        existing = await _find_event_by_idempotency(db, tenant_id, load_id, body.idempotency_key)
        if existing is not None:
            if (
                existing.event_type == CUSTODY_EVENT_TRIP_TAKEOVER
                and existing.trip_id == trip_id
                and _is_open_active(tl)
                and load.custody_owner == CUSTODY_OWNER_TRIP
                and load.custody_trip_id == trip_id
            ):
                return _transition_response(load=load, trip=trip, tl=tl, event=existing, replayed=True)
            raise _conflict(
                "IDEMPOTENCY_KEY_CONFLICT",
                "idempotency_key already used for a different custody event on this Load",
            )

    _raise_if_membership_removed(tl)
    _raise_if_membership_completed(tl)
    if not _is_open_planned(tl):
        raise _conflict("MEMBERSHIP_NOT_PLANNED", "Membership is not planned")

    other_active = await db.scalar(
        select(TripLoad).where(
            TripLoad.tenant_id == tenant_id,
            TripLoad.load_id == load_id,
            TripLoad.status_within_trip == TRIP_LOAD_STATUS_WITHIN_ACTIVE,
            TripLoad.completed_at.is_(None),
            TripLoad.removed_at.is_(None),
        )
    )
    if other_active is not None:
        raise _conflict("LOAD_ACTIVE_ON_OTHER_TRIP", "Load already active on another trip")

    if load.custody_owner != CUSTODY_OWNER_TERMINAL or load.custody_terminal_id is None:
        raise _conflict(
            "INVALID_CUSTODY_STATE",
            "Take-custody requires terminal custody with custody_terminal_id set",
        )

    _require_trip_eligible_for_custody(trip)
    outbound_trailer = int(trip.trailer_id)

    if load.custody_placement == CUSTODY_PLACEMENT_ON_TRAILER:
        if load.custody_trailer_id is None:
            raise _conflict(
                "TRAILER_MISMATCH",
                "Terminal on_trailer custody missing custody_trailer_id",
            )
        if int(load.custody_trailer_id) != outbound_trailer:
            raise _conflict(
                "TRAILER_MISMATCH",
                "Outbound Trip trailer differs from terminal on_trailer custody; "
                "explicit trailer_transfer is not implemented yet",
            )
    elif load.custody_placement == CUSTODY_PLACEMENT_STAGED:
        pass  # pickup onto Trip B trailer allowed
    else:
        raise _conflict(
            "INVALID_CUSTODY_STATE",
            f"Unsupported terminal placement '{load.custody_placement}' for take-custody",
        )

    occurred_at = body.occurred_at or datetime.now(timezone.utc)
    ev = await _append_event(
        db,
        tenant_id=tenant_id,
        load_id=load_id,
        event_type=CUSTODY_EVENT_TRIP_TAKEOVER,
        occurred_at=occurred_at,
        custody_owner_after=CUSTODY_OWNER_TRIP,
        placement_after=CUSTODY_PLACEMENT_ON_TRAILER,
        trip_id=trip_id,
        terminal_id=None,
        trailer_id=outbound_trailer,
        actor_user_id=actor_user_id,
        notes=body.notes,
        idempotency_key=body.idempotency_key,
    )
    _apply_snapshot(
        load,
        owner=CUSTODY_OWNER_TRIP,
        trip_id=trip_id,
        terminal_id=None,
        placement=CUSTODY_PLACEMENT_ON_TRAILER,
        trailer_id=outbound_trailer,
        since=occurred_at,
        event_id=int(ev.id),
    )
    await db.flush()

    tl = await _activate_trip_load_membership_locked(
        db, tenant_id, trip, load, require_trailer=True
    )
    await db.refresh(load)
    return _transition_response(load=load, trip=trip, tl=tl, event=ev, replayed=False)
