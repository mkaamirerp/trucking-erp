"""Truck API router - tenant-safe CRUD for inventory-only fleet."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps.auth import get_current_user
from app.deps.tenant import require_tenant
from app.deps.tenant_db import get_tenant_db
from app.models.load import Load
from app.schemas.dispatch_hints import TruckSuggestedTrailerOut
from app.schemas.truck import TruckCreate, TruckResponse, TruckUpdate
from app.services import trucks as trucks_service

router = APIRouter(prefix="/trucks", tags=["trucks"])


@router.post("", response_model=TruckResponse, status_code=status.HTTP_201_CREATED)
async def create_truck(
    payload: TruckCreate,
    tenant_id: int = Depends(require_tenant),
    _user=Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    return await trucks_service.create_truck(db, tenant_id, payload)


@router.get("", response_model=dict)
async def list_trucks(
    tenant_id: int = Depends(require_tenant),
    _user=Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
    status_filter: Optional[list[str]] = Query(None, alias="status"),
    ownership_type: Optional[str] = Query(None),
    unit_number: Optional[str] = Query(None),
    vin: Optional[str] = Query(None),
    plate_number: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(25, ge=1, le=200),
):
    paged = await trucks_service.list_trucks(
        db,
        tenant_id=tenant_id,
        status_filter=status_filter,
        ownership_type=ownership_type,
        unit_number=unit_number,
        vin=vin,
        plate_number=plate_number,
        page=page,
        size=size,
    )
    items = [TruckResponse.model_validate(item) for item in paged["items"]]
    return {**paged, "items": items}


@router.get("/{truck_id}/suggested-trailer", response_model=TruckSuggestedTrailerOut)
async def get_truck_suggested_trailer(
    truck_id: int,
    tenant_id: int = Depends(require_tenant),
    _user=Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    truck = await trucks_service.get_truck(db, tenant_id, truck_id)
    if not truck:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Truck not found")

    stmt = (
        select(Load.trailer_id)
        .where(
            Load.tenant_id == tenant_id,
            Load.truck_id == truck_id,
            Load.trailer_id.isnot(None),
        )
        .order_by(Load.updated_at.desc())
        .limit(1)
    )
    tid = (await db.execute(stmt)).scalar_one_or_none()
    return TruckSuggestedTrailerOut(trailer_id=tid)


@router.get("/{truck_id}", response_model=TruckResponse)
async def get_truck(
    truck_id: int,
    tenant_id: int = Depends(require_tenant),
    _user=Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    truck = await trucks_service.get_truck(db, tenant_id, truck_id)
    if not truck:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Truck not found")
    return truck


@router.patch("/{truck_id}", response_model=TruckResponse)
async def update_truck(
    truck_id: int,
    payload: TruckUpdate,
    tenant_id: int = Depends(require_tenant),
    _user=Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    return await trucks_service.update_truck(db, tenant_id, truck_id, payload)
