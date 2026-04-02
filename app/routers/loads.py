from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps.auth import get_current_user
from app.deps.tenant import require_tenant
from app.deps.tenant_db import get_tenant_db
from app.schemas.load import LoadCreate, LoadResponse, LoadUpdate, LoadNoteCreate, LoadNoteOut
from app.services import loads as loads_service

router = APIRouter(prefix="/loads", tags=["loads"])


@router.post("", response_model=LoadResponse, status_code=status.HTTP_201_CREATED)
async def create_load(
    payload: LoadCreate,
    tenant_id: int = Depends(require_tenant),
    _user=Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    load = await loads_service.create_load(db, tenant_id, payload)
    return LoadResponse.model_validate(load)


@router.get("", response_model=dict)
async def list_loads(
    tenant_id: int = Depends(require_tenant),
    _user=Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
    status: Optional[List[str]] = Query(None),
    driver_id: int | None = Query(None),
    broker_id: int | None = Query(None),
    truck_id: int | None = Query(None),
    trailer_id: int | None = Query(None),
    search: str | None = Query(None, max_length=120),
    page: int = Query(1, ge=1),
    size: int = Query(25, ge=1, le=200),
):
    paged = await loads_service.list_loads(
        db,
        tenant_id=tenant_id,
        statuses=status,
        driver_id=driver_id,
        broker_id=broker_id,
        truck_id=truck_id,
        trailer_id=trailer_id,
        search=search,
        page=page,
        size=size,
    )
    items = [LoadResponse.model_validate(item) for item in paged["items"]]
    return {**paged, "items": items}


@router.get("/{load_id}", response_model=LoadResponse)
async def get_load_detail(
    load_id: int,
    tenant_id: int = Depends(require_tenant),
    _user=Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    load = await loads_service.get_load(db, tenant_id, load_id)
    if not load:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Load not found")
    return LoadResponse.model_validate(load)


@router.patch("/{load_id}", response_model=LoadResponse)
async def update_load(
    load_id: int,
    payload: LoadUpdate,
    tenant_id: int = Depends(require_tenant),
    _user=Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    load = await loads_service.update_load(db, tenant_id, load_id, payload)
    return LoadResponse.model_validate(load)


@router.post("/{load_id}/confirm-document-snapshot", response_model=LoadResponse)
async def confirm_document_snapshot(
    load_id: int,
    tenant_id: int = Depends(require_tenant),
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    load = await loads_service.confirm_load_customs_document_snapshot(
        db, tenant_id, load_id, confirming_user_id=getattr(user, "user_id", None)
    )
    return LoadResponse.model_validate(load)


@router.post("/{load_id}/mark-ready", response_model=LoadResponse)
async def mark_load_ready(
    load_id: int,
    tenant_id: int = Depends(require_tenant),
    _user=Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    load = await loads_service.mark_load_ready(db, tenant_id, load_id)
    return LoadResponse.model_validate(load)


@router.get("/{load_id}/notes", response_model=list)
async def list_load_notes(
    load_id: int,
    tenant_id: int = Depends(require_tenant),
    _user=Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    notes = await loads_service.list_load_notes(db, tenant_id, load_id)
    return [LoadNoteOut.model_validate(n) for n in notes]


@router.post("/{load_id}/notes", response_model=LoadNoteOut, status_code=status.HTTP_201_CREATED)
async def add_load_note(
    load_id: int,
    payload: LoadNoteCreate,
    tenant_id: int = Depends(require_tenant),
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    note = await loads_service.add_load_note(
        db, tenant_id, load_id, payload.body, author_user_id=getattr(user, "user_id", None)
    )
    return LoadNoteOut.model_validate(note)


@router.delete("/{load_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_load(
    load_id: int,
    tenant_id: int = Depends(require_tenant),
    _user=Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    await loads_service.delete_load(db, tenant_id, load_id)
    return {}
