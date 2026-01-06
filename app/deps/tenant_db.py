from __future__ import annotations

import os
from typing import AsyncGenerator, Dict

from fastapi import Request, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import AsyncSessionLocal  # platform session
from app.models.platform import PlatformTenant

_ENGINE_CACHE: Dict[str, object] = {}


def _swap_db(url: str, db_name: str) -> str:
    base, _sep, _old = url.rpartition("/")
    return f"{base}/{db_name}" if base else url


async def get_tenant_db(request: Request) -> AsyncGenerator[AsyncSession, None]:
    tenant_id = getattr(request.state, "tenant_id", None)
    if tenant_id is None:
        raise HTTPException(status_code=400, detail="Tenant context missing")

    # lookup tenant in PLATFORM DB
    async with AsyncSessionLocal() as platform_db:
        tenant = await platform_db.scalar(
            select(PlatformTenant).where(PlatformTenant.id == int(tenant_id)).limit(1)
        )

    if not tenant or tenant.status != "ACTIVE" or tenant.db_status != "READY":
        raise HTTPException(status_code=403, detail="Tenant inactive or not found")

    template = os.getenv("POSTGRES_ADMIN_URL") or os.getenv("TENANT_DATABASE_URL") or os.getenv("DATABASE_URL")
    if not template:
        raise HTTPException(status_code=503, detail="DB config missing")

    tenant_url = _swap_db(template, tenant.db_name)

    engine = _ENGINE_CACHE.get(tenant_url)
    if engine is None:
        engine = create_async_engine(tenant_url, pool_pre_ping=True)
        _ENGINE_CACHE[tenant_url] = engine

    SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with SessionLocal() as tenant_db:
        yield tenant_db
