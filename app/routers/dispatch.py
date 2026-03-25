"""Dispatch board API - tenant-safe."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps.auth import get_current_user
from app.deps.tenant_status import require_active_tenant
from app.deps.tenant import require_tenant
from app.deps.tenant_db import get_tenant_db
from app.schemas.load import LoadResponse
from app.services import loads as loads_service

router = APIRouter(
    prefix="/dispatch",
    tags=["dispatch"],
    dependencies=[Depends(require_active_tenant)],
)


@router.get("/board", response_model=dict)
async def get_dispatch_board(
    tenant_id: int = Depends(require_tenant),
    _user=Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
    search: Optional[str] = Query(None),
):
    """Loads grouped by dispatch status for board columns. No pagination."""
    grouped = await loads_service.list_loads_for_board(db, tenant_id=tenant_id, search=search)
    return {
        status_key: [LoadResponse.model_validate(load) for load in items]
        for status_key, items in grouped.items()
    }
