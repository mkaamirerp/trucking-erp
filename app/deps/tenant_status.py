from __future__ import annotations

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps.tenant import require_tenant
from app.models.platform import PlatformTenant


async def require_active_tenant(
    tenant_id: int = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
) -> int:
    tenant = await db.scalar(select(PlatformTenant).where(PlatformTenant.id == tenant_id))
    if not tenant or tenant.status != "ACTIVE":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant inactive or not found",
        )
    return tenant_id
