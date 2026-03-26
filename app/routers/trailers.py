"""Trailer API router - tenant-safe CRUD for inventory-only fleet."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps.auth import get_current_user
from app.deps.tenant import require_tenant
from app.deps.tenant_db import get_tenant_db
from app.schemas.trailer import TrailerCreate, TrailerResponse, TrailerUpdate
from app.services import trailers as trailers_service

router = APIRouter(prefix="/trailers", tags=["trailers"])


@router.post("", response_model=TrailerResponse, status_code=status.HTTP_201_CREATED)
async def create_trailer(
    payload: TrailerCreate,
    tenant_id: int = Depends(require_tenant),
    _user=Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    return await trailers_service.create_trailer(db, tenant_id, payload)


@router.get("", response_model=dict)
async def list_trailers(
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
    paged = await trailers_service.list_trailers(
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
    items = [TrailerResponse.model_validate(item) for item in paged["items"]]
    return {**paged, "items": items}


@router.get("/{trailer_id}", response_model=TrailerResponse)
async def get_trailer(
    trailer_id: int,
    tenant_id: int = Depends(require_tenant),
    _user=Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    trailer = await trailers_service.get_trailer(db, tenant_id, trailer_id)
    if not trailer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trailer not found")
    return trailer


@router.patch("/{trailer_id}", response_model=TrailerResponse)
async def update_trailer(
    trailer_id: int,
    payload: TrailerUpdate,
    tenant_id: int = Depends(require_tenant),
    _user=Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    return await trailers_service.update_trailer(db, tenant_id, trailer_id, payload)
