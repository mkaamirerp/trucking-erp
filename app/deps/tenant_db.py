from __future__ import annotations

from typing import AsyncGenerator, Dict

from fastapi import Request, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import AsyncSessionLocal  # platform session
from app.core.config import settings
from app.core.db_url import to_async_pg_url
from app.models.platform import PlatformTenant

_ENGINE_CACHE: Dict[str, object] = {}

# Keep one checked-out idle connection per tenant that actually serves traffic.
# Default QueuePool is pool_size=5 / max_overflow=10 (up to 15 per tenant), which
# exhausts Postgres max_connections=100 when the outbox sweeper touches every
# ACTIVE/READY tenant.
_TENANT_ENGINE_KWARGS = {
    "pool_pre_ping": True,
    "pool_size": 1,
    "max_overflow": 4,
    "pool_timeout": 30,
}


def _get_or_create_tenant_engine(tenant_url: str):
    engine = _ENGINE_CACHE.get(tenant_url)
    if engine is None:
        engine = create_async_engine(tenant_url, **_TENANT_ENGINE_KWARGS)
        _ENGINE_CACHE[tenant_url] = engine
    return engine


def _tenant_url_for_db_name(db_name: str) -> str:
    template = getattr(settings, "postgres_admin_url", None) or settings.database_url
    if not template:
        raise HTTPException(status_code=503, detail="DB config missing")
    return _swap_db(to_async_pg_url(template), db_name)


async def dispose_cached_engine_for_tenant_id(tenant_id: int) -> None:
    """Drop a cached tenant engine so leftover DBs do not hold idle connections."""
    async with AsyncSessionLocal() as platform_db:
        tenant = await platform_db.scalar(
            select(PlatformTenant).where(PlatformTenant.id == int(tenant_id)).limit(1)
        )
    if not tenant or not tenant.db_name:
        return
    try:
        tenant_url = _tenant_url_for_db_name(tenant.db_name)
    except HTTPException:
        return
    engine = _ENGINE_CACHE.pop(tenant_url, None)
    if engine is not None:
        await engine.dispose()


async def open_tenant_session_by_id(tenant_id: int) -> AsyncGenerator[AsyncSession, None]:
    """Open tenant DB session by tenant_id. Use when request.state.tenant_id is not yet set (e.g. OAuth callback)."""
    async with AsyncSessionLocal() as platform_db:
        tenant = await platform_db.scalar(
            select(PlatformTenant).where(PlatformTenant.id == int(tenant_id)).limit(1)
        )
    if not tenant or tenant.status != "ACTIVE" or tenant.db_status != "READY":
        raise HTTPException(status_code=403, detail="Tenant inactive or not found")
    if not tenant.db_name:
        raise HTTPException(status_code=403, detail="Tenant DB not provisioned")
    tenant_url = _tenant_url_for_db_name(tenant.db_name)
    if "localhost" in tenant_url or "127.0.0.1" in tenant_url:
        raise RuntimeError(f"Tenant DB URL resolved to localhost: {tenant_url}")
    engine = _get_or_create_tenant_engine(tenant_url)
    SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with SessionLocal() as session:
        yield session


def _swap_db(url: str, db_name: str) -> str:
    """
    Swap the database name portion of a URL, keeping scheme/creds/host/port intact.

    Works for URLs like:
      postgresql+asyncpg://user:pass@host:5432/some_db
    """
    base, _sep, _old = url.rpartition("/")
    return f"{base}/{db_name}" if base else url


async def get_tenant_db(request: Request) -> AsyncGenerator[AsyncSession, None]:
    tenant_id = getattr(request.state, "tenant_id", None)
    if tenant_id is None:
        raise HTTPException(status_code=400, detail="Tenant context missing")

    # Lookup tenant in PLATFORM DB
    async with AsyncSessionLocal() as platform_db:
        tenant = await platform_db.scalar(
            select(PlatformTenant).where(PlatformTenant.id == int(tenant_id)).limit(1)
        )

    # Enforce tenant readiness
    if not tenant or tenant.status != "ACTIVE" or tenant.db_status != "READY":
        raise HTTPException(status_code=403, detail="Tenant inactive or not found")

    if not tenant.db_name:
        raise HTTPException(status_code=403, detail="Tenant DB not provisioned")

    # IMPORTANT:
    # Use a stable template URL (host/creds/port) and dynamically swap in tenant.db_name.
    # Do NOT rely on TENANT_DATABASE_URL as a single-DB setting (breaks multi-tenant).
    tenant_url = _tenant_url_for_db_name(tenant.db_name)
    if "localhost" in tenant_url or "127.0.0.1" in tenant_url:
        raise RuntimeError(f"Tenant DB URL resolved to localhost: {tenant_url}")

    engine = _get_or_create_tenant_engine(tenant_url)

    SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with SessionLocal() as tenant_db:
        yield tenant_db


async def get_tenant_db_for_tools(request: Request) -> AsyncGenerator[AsyncSession, None]:
    """
    Same as get_tenant_db but only requires tenant to exist and have db_name.
    Used by DB Inspector so you can view a tenant DB even if status != ACTIVE or db_status != READY.
    """
    tenant_id = getattr(request.state, "tenant_id", None)
    if tenant_id is None:
        raise HTTPException(status_code=400, detail="Tenant context missing")

    async with AsyncSessionLocal() as platform_db:
        tenant = await platform_db.scalar(
            select(PlatformTenant).where(PlatformTenant.id == int(tenant_id)).limit(1)
        )

    if not tenant:
        raise HTTPException(status_code=403, detail="Tenant not found")

    if not tenant.db_name:
        raise HTTPException(status_code=403, detail="Tenant DB not provisioned")

    tenant_url = _tenant_url_for_db_name(tenant.db_name)
    if "localhost" in tenant_url or "127.0.0.1" in tenant_url:
        raise RuntimeError(f"Tenant DB URL resolved to localhost: {tenant_url}")

    engine = _get_or_create_tenant_engine(tenant_url)

    SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with SessionLocal() as tenant_db:
        yield tenant_db
