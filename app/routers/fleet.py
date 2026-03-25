"""Legacy fleet list - returns trucks. Use /api/v1/trucks for full CRUD."""

from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps.auth import get_current_user
from app.deps.tenant import require_tenant
from app.deps.tenant_status import require_active_tenant
from app.deps.tenant_db import get_tenant_db
from app.models.truck import Truck
from app.schemas.truck import TruckResponse

router = APIRouter(
    prefix="/fleet",
    tags=["fleet"],
    dependencies=[Depends(require_active_tenant), Depends(get_current_user)],
)


@router.get("", response_model=List[TruckResponse])
async def get_fleet(
    db: AsyncSession = Depends(get_tenant_db),
    tenant_id: int = Depends(require_tenant),
):
    result = await db.execute(select(Truck).where(Truck.tenant_id == tenant_id).order_by(Truck.id.desc()))
    trucks = result.scalars().all()
    return [TruckResponse.model_validate(t) for t in trucks]
