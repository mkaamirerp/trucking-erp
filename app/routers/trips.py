from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps.auth import get_current_user
from app.deps.tenant import require_tenant
from app.deps.tenant_db import get_tenant_db
from app.schemas.trip_read import (
    AddTripLoadBody,
    CreatePlannedTripBody,
    TripDetailResponse,
    TripListPageResponse,
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
