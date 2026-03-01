from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
from fastapi.encoders import jsonable_encoder

from app.deps.tenant import require_tenant
from app.deps.tenant_db import get_tenant_db
from app.models.truck import Truck

router = APIRouter(prefix="/fleet", tags=["fleet"])


@router.get("", response_model=List[dict])
async def get_fleet(
    db: AsyncSession = Depends(get_tenant_db),
    tenant_id: int = Depends(require_tenant),
):
    result = await db.execute(select(Truck).where(Truck.tenant_id == tenant_id))
    rows = result.scalars().all()
    return jsonable_encoder(rows)
