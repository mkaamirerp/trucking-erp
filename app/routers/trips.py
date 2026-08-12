from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps.auth import CurrentUser, get_current_user
from app.deps.tenant import require_tenant
from app.deps.tenant_db import get_tenant_db
from app.schemas.trip_read import (
    AddTripLoadBody,
    CreatePlannedTripBody,
    TripAssignmentBody,
    TripExecutionSignalBody,
    TripDetailResponse,
    TripListPageResponse,
    TripScheduleBody,
)
from app.services import trips as trips_service

router = APIRouter(prefix="/trips", tags=["trips"])


@router.post("", response_model=TripDetailResponse, status_code=status.HTTP_201_CREATED)
async def create_planned_trip(
    body: CreatePlannedTripBody,
    tenant_id: int = Depends(require_tenant),
    _user=Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
) -> TripDetailResponse:
    detail = await trips_service.create_planned_trip(
        db,
        tenant_id,
        status=body.status,
        job_type=body.job_type,
        driver_id=body.driver_id,
        truck_id=body.truck_id,
        trailer_id=body.trailer_id,
        load_ids=body.load_ids,
    )
    await db.commit()
    return detail


@router.post("/{trip_id}/cancel", response_model=TripDetailResponse)
async def cancel_trip(
    trip_id: int,
    tenant_id: int = Depends(require_tenant),
    _user=Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
) -> TripDetailResponse:
    detail = await trips_service.cancel_trip_manual(db, tenant_id, trip_id)
    await db.commit()
    return detail


@router.post("/{trip_id}/loads", response_model=TripDetailResponse)
async def add_load_to_trip(
    trip_id: int,
    body: AddTripLoadBody,
    tenant_id: int = Depends(require_tenant),
    _user=Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
) -> TripDetailResponse:
    detail = await trips_service.add_load_to_trip(
        db, tenant_id, trip_id, body.load_id, sequence_hint=body.sequence_hint
    )
    await db.commit()
    return detail


@router.post("/{trip_id}/loads/{load_id}/remove", response_model=TripDetailResponse)
async def remove_load_from_trip(
    trip_id: int,
    load_id: int,
    tenant_id: int = Depends(require_tenant),
    _user=Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
) -> TripDetailResponse:
    detail = await trips_service.remove_load_from_trip(db, tenant_id, trip_id, load_id)
    await db.commit()
    return detail


@router.post("/{trip_id}/loads/{load_id}/activate", response_model=TripDetailResponse)
async def activate_trip_load(
    trip_id: int,
    load_id: int,
    tenant_id: int = Depends(require_tenant),
    _user=Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
) -> TripDetailResponse:
    """Explicit planned → active membership transition (not Decision 7 execution start)."""
    detail = await trips_service.activate_trip_load_membership(db, tenant_id, trip_id, load_id)
    await db.commit()
    return detail


@router.post("/{trip_id}/loads/{load_id}/complete", response_model=TripDetailResponse)
async def complete_trip_load(
    trip_id: int,
    load_id: int,
    tenant_id: int = Depends(require_tenant),
    _user=Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
) -> TripDetailResponse:
    """Explicit active → completed membership transition (no auto-activate next Trip)."""
    detail = await trips_service.complete_trip_load_membership(db, tenant_id, trip_id, load_id)
    await db.commit()
    return detail


@router.get("", response_model=TripListPageResponse)
async def list_trips(
    tenant_id: int = Depends(require_tenant),
    _user=Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
    search: str | None = Query(None, max_length=120),
    status: str | None = Query(None, max_length=64),
    page: int = Query(1, ge=1),
    size: int = Query(25, ge=1, le=200),
) -> TripListPageResponse:
    data = await trips_service.list_trips(
        db,
        tenant_id,
        search=search,
        status=status,
        page=page,
        size=size,
    )
    return TripListPageResponse(**data)


@router.get("/{trip_id}", response_model=TripDetailResponse)
async def get_trip(
    trip_id: int,
    tenant_id: int = Depends(require_tenant),
    _user=Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
) -> TripDetailResponse:
    detail = await trips_service.get_trip_detail(db, tenant_id, trip_id)
    if not detail:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trip not found")
    return detail


@router.put("/{trip_id}/assignment", response_model=TripDetailResponse)
async def put_trip_assignment(
    trip_id: int,
    body: TripAssignmentBody,
    request: Request,
    tenant_id: int = Depends(require_tenant),
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
) -> TripDetailResponse:
    """Decision 14A: update trip movement assignment only (no loads, custody, or dispatch_trips).

    TODO(RBAC): Matches sibling trip routes (require_tenant + get_current_user) for this slice only;
    tie assignment updates to dispatch/trip-operation permissions when RBAC for trip ops is tightened.
    """
    actor_user_id = int(user.tenant_user.id) if user.tenant_user else None
    actor_label = None if user.tenant_user else f"platform:{user.user.id}"
    rid = getattr(request.state, "request_id", None)
    detail = await trips_service.update_trip_assignment(
        db,
        tenant_id,
        trip_id,
        body,
        actor_user_id=actor_user_id,
        actor_label=actor_label,
        request_id=str(rid) if rid else None,
    )
    await db.commit()
    return detail


@router.put("/{trip_id}/schedule", response_model=TripDetailResponse)
async def put_trip_schedule(
    trip_id: int,
    body: TripScheduleBody,
    tenant_id: int = Depends(require_tenant),
    _user=Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
) -> TripDetailResponse:
    """COMMIT 4a: update planned_start_at / expected_completion_at only."""
    detail = await trips_service.update_trip_schedule(db, tenant_id, trip_id, body)
    await db.commit()
    return detail


@router.post("/{trip_id}/execution-signal", response_model=TripDetailResponse)
async def post_trip_execution_signal(
    trip_id: int,
    body: TripExecutionSignalBody,
    request: Request,
    tenant_id: int = Depends(require_tenant),
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
) -> TripDetailResponse:
    """Decision 7 (slice): start trip execution from an accepted real signal (API-only)."""
    actor_user_id = int(user.tenant_user.id) if user.tenant_user else None
    actor_label = None if user.tenant_user else f"platform:{user.user.id}"
    rid = getattr(request.state, "request_id", None)
    detail = await trips_service.start_trip_execution_from_signal(
        db,
        tenant_id,
        trip_id,
        signal_source=body.source,
        reason_note=body.reason_note,
        signal_at=body.signal_at,
        actor_user_id=actor_user_id,
        actor_label=actor_label,
        request_id=str(rid) if rid else None,
    )
    await db.commit()
    return detail
