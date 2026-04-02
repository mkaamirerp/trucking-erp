from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps.auth import get_current_user
from app.deps.tenant import require_tenant
from app.deps.tenant_db import get_tenant_db
from app.schemas.customs_broker import (
    CustomsBrokerContactCreate,
    CustomsBrokerContactOut,
    CustomsBrokerContactUpdate,
    CustomsBrokerCreate,
    CustomsBrokerResponse,
    CustomsBrokerUpdate,
)
from app.services import customs_brokers as customs_service

router = APIRouter(prefix="/customs-brokers", tags=["customs-brokers"])


@router.get("/search", response_model=dict)
async def search_customs_brokers(
    q: str = Query(..., min_length=1, max_length=200),
    tenant_id: int = Depends(require_tenant),
    _user=Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
    page: int = Query(1, ge=1),
    size: int = Query(25, ge=1, le=200),
):
    paged = await customs_service.search_customs_brokers(db, tenant_id, q, page=page, size=size)
    items = [CustomsBrokerResponse.model_validate(x) for x in paged["items"]]
    return {**paged, "items": items}


@router.post("", response_model=CustomsBrokerResponse, status_code=status.HTTP_201_CREATED)
async def create_customs_broker(
    payload: CustomsBrokerCreate,
    tenant_id: int = Depends(require_tenant),
    _user=Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    return await customs_service.create_customs_broker(db, tenant_id, payload)


@router.get("", response_model=dict)
async def list_customs_brokers(
    tenant_id: int = Depends(require_tenant),
    _user=Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
    page: int = Query(1, ge=1),
    size: int = Query(25, ge=1, le=200),
    include_inactive: bool = Query(False),
):
    paged = await customs_service.list_customs_brokers(
        db, tenant_id, include_inactive=include_inactive, page=page, size=size
    )
    items = [CustomsBrokerResponse.model_validate(x) for x in paged["items"]]
    return {**paged, "items": items}


@router.get("/{broker_id}", response_model=CustomsBrokerResponse)
async def get_customs_broker(
    broker_id: int,
    tenant_id: int = Depends(require_tenant),
    _user=Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    row = await customs_service.get_customs_broker(db, tenant_id, broker_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customs broker not found")
    return row


@router.patch("/{broker_id}", response_model=CustomsBrokerResponse)
async def update_customs_broker(
    broker_id: int,
    payload: CustomsBrokerUpdate,
    tenant_id: int = Depends(require_tenant),
    _user=Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    return await customs_service.update_customs_broker(db, tenant_id, broker_id, payload)


@router.delete("/{broker_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_customs_broker(
    broker_id: int,
    tenant_id: int = Depends(require_tenant),
    _user=Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    await customs_service.soft_delete_customs_broker(db, tenant_id, broker_id)
    return {}


@router.get("/{broker_id}/contacts", response_model=list[CustomsBrokerContactOut])
async def list_customs_broker_contacts(
    broker_id: int,
    tenant_id: int = Depends(require_tenant),
    _user=Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
    include_inactive: bool = Query(False),
):
    rows = await customs_service.list_contacts(db, tenant_id, broker_id, include_inactive=include_inactive)
    return [CustomsBrokerContactOut.model_validate(r) for r in rows]


@router.post(
    "/{broker_id}/contacts",
    response_model=CustomsBrokerContactOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_customs_broker_contact(
    broker_id: int,
    payload: CustomsBrokerContactCreate,
    tenant_id: int = Depends(require_tenant),
    _user=Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    row = await customs_service.create_contact(db, tenant_id, broker_id, payload)
    return row


@router.get("/{broker_id}/contacts/{contact_id}", response_model=CustomsBrokerContactOut)
async def get_customs_broker_contact(
    broker_id: int,
    contact_id: int,
    tenant_id: int = Depends(require_tenant),
    _user=Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    row = await customs_service.get_contact(db, tenant_id, broker_id, contact_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")
    return row


@router.patch("/{broker_id}/contacts/{contact_id}", response_model=CustomsBrokerContactOut)
async def update_customs_broker_contact(
    broker_id: int,
    contact_id: int,
    payload: CustomsBrokerContactUpdate,
    tenant_id: int = Depends(require_tenant),
    _user=Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    return await customs_service.update_contact(db, tenant_id, broker_id, contact_id, payload)


@router.delete("/{broker_id}/contacts/{contact_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_customs_broker_contact(
    broker_id: int,
    contact_id: int,
    tenant_id: int = Depends(require_tenant),
    _user=Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    await customs_service.soft_delete_contact(db, tenant_id, broker_id, contact_id)
    return {}
