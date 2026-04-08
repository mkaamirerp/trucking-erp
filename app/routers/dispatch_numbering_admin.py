"""Admin API: tenant dispatch trip number prefix (tenant DB)."""

from __future__ import annotations

from pydantic import BaseModel, Field

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps.admin import is_tenant_admin
from app.deps.auth import CurrentUser, get_current_user
from app.deps.entitlements import require_entitlement
from app.deps.tenant import require_tenant
from app.deps.tenant_db import get_tenant_db
from app.services import dispatch_trips as dispatch_trips_service

router = APIRouter(
    prefix="/api/v1/admin/dispatch-numbering",
    tags=["Tenant Admin"],
    dependencies=[Depends(require_entitlement("admin_sensitive"))],
)


class DispatchNumberingOut(BaseModel):
    trip_number_prefix: str | None = None
    prefix_locked: bool = False


class DispatchNumberingPut(BaseModel):
    trip_number_prefix: str = Field(..., min_length=1, max_length=32)


@router.get("", response_model=DispatchNumberingOut)
async def get_dispatch_numbering(
    tenant_id: int = Depends(require_tenant),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    if not is_tenant_admin(current_user.role):
        raise HTTPException(status_code=403, detail="Admin role required")
    row = await dispatch_trips_service.get_numbering_public(db, tenant_id)
    if not row:
        return DispatchNumberingOut(trip_number_prefix=None, prefix_locked=False)
    prefix = (row.trip_number_prefix or "").strip() or None
    return DispatchNumberingOut(
        trip_number_prefix=prefix,
        prefix_locked=row.prefix_locked_at is not None,
    )


@router.put("", response_model=DispatchNumberingOut)
async def put_dispatch_numbering(
    body: DispatchNumberingPut,
    tenant_id: int = Depends(require_tenant),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    if not is_tenant_admin(current_user.role):
        raise HTTPException(status_code=403, detail="Admin role required")
    await dispatch_trips_service.lock_trip_prefix(db, tenant_id, body.trip_number_prefix)
    await db.commit()
    row = await dispatch_trips_service.get_numbering_public(db, tenant_id)
    assert row is not None
    return DispatchNumberingOut(
        trip_number_prefix=(row.trip_number_prefix or "").strip(),
        prefix_locked=True,
    )
