from __future__ import annotations

from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps.auth import get_current_user
from app.deps.tenant import require_tenant
from app.deps.tenant_db import get_tenant_db
from app.schemas.load import LoadCreate, LoadResponse, LoadUpdate
from app.services import loads as loads_service

router = APIRouter(prefix="/loads", tags=["loads"])


@router.post("", response_model=LoadResponse, status_code=status.HTTP_201_CREATED)
async def create_load(
    payload: LoadCreate,
    tenant_id: int = Depends(require_tenant),
    _user=Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    return await loads_service.create_load(db, tenant_id, payload)


@router.get("", response_model=dict)
async def list_loads(
    tenant_id: int = Depends(require_tenant),
    _user=Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
    status: Optional[List[str]] = Query(None),
    driver_id: int | None = Query(None),
    broker_id: int | None = Query(None),
    pickup_start: date | None = Query(None),
    pickup_end: date | None = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(25, ge=1, le=200),
):
    paged = await loads_service.list_loads(
        db,
        tenant_id=tenant_id,
        statuses=status,
        driver_id=driver_id,
        broker_id=broker_id,
        pickup_start=pickup_start,
        pickup_end=pickup_end,
        page=page,
        size=size,
    )
    items = [LoadResponse.model_validate(item) for item in paged["items"]]
    return {**paged, "items": items}


@router.get("/{load_id}", response_model=LoadResponse)
async def get_load(
    load_id: int,
    tenant_id: int = Depends(require_tenant),
    _user=Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    load = await loads_service.get_load(db, tenant_id, load_id)
    if not load:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Load not found")
    return load


@router.put("/{load_id}", response_model=LoadResponse)
async def update_load(
    load_id: int,
    payload: LoadUpdate,
    tenant_id: int = Depends(require_tenant),
    _user=Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    return await loads_service.update_load(db, tenant_id, load_id, payload)


@router.delete("/{load_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_load(
    load_id: int,
    tenant_id: int = Depends(require_tenant),
    _user=Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    await loads_service.delete_load(db, tenant_id, load_id)
    return {}
