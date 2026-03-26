from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps.auth import get_current_user
from app.deps.tenant import require_tenant
from app.deps.tenant_db import get_tenant_db
from app.schemas.broker import BrokerCreate, BrokerResponse, BrokerUpdate
from app.services import brokers as brokers_service

router = APIRouter(prefix="/brokers", tags=["brokers"])


@router.post("", response_model=BrokerResponse, status_code=status.HTTP_201_CREATED)
async def create_broker(
    payload: BrokerCreate,
    tenant_id: int = Depends(require_tenant),
    _user=Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    return await brokers_service.create_broker(db, tenant_id, payload)


@router.get("", response_model=dict)
async def list_brokers(
    tenant_id: int = Depends(require_tenant),
    _user=Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
    page: int = Query(1, ge=1),
    size: int = Query(25, ge=1, le=200),
):
    paged = await brokers_service.list_brokers(db, tenant_id, page=page, size=size)
    items = [BrokerResponse.model_validate(item) for item in paged["items"]]
    return {**paged, "items": items}


@router.get("/{broker_id}", response_model=BrokerResponse)
async def get_broker(
    broker_id: int,
    tenant_id: int = Depends(require_tenant),
    _user=Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    broker = await brokers_service.get_broker(db, tenant_id, broker_id)
    if not broker:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Broker not found")
    return broker


@router.put("/{broker_id}", response_model=BrokerResponse)
async def update_broker(
    broker_id: int,
    payload: BrokerUpdate,
    tenant_id: int = Depends(require_tenant),
    _user=Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    return await brokers_service.update_broker(db, tenant_id, broker_id, payload)


@router.delete("/{broker_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_broker(
    broker_id: int,
    tenant_id: int = Depends(require_tenant),
    _user=Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    await brokers_service.delete_broker(db, tenant_id, broker_id)
    return {}
