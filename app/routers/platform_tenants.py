from __future__ import annotations

import asyncio
import os
import re
from pathlib import Path
from datetime import datetime, timezone
from urllib.parse import urlparse, urlunparse

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.config import settings
from app.core.database import get_db
from app.models.platform import PlatformTenant

router = APIRouter(prefix="/api/v1/platform", tags=["platform-tenants"])


def require_admin_header(x_platform_admin_key: str | None = Header(None)) -> None:
    expected = None  # set via env if needed later
    if expected and x_platform_admin_key != expected:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")


@router.get("/tenants")
async def list_tenants(db: AsyncSession = Depends(get_db), _: None = Depends(require_admin_header)):
    rows = (await db.execute(select(PlatformTenant))).scalars().all()
    return [{"id": t.id, "name": t.name, "slug": t.slug, "status": t.status, "db_status": t.db_status} for t in rows]


@router.post("/tenants")
async def create_tenant(body: dict, db: AsyncSession = Depends(get_db), _: None = Depends(require_admin_header)):
    name = body.get("company_name") or body.get("name")
    slug = body.get("slug")
    if not name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="company_name is required")
    if not slug:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="slug is required")
    exists = await db.scalar(select(PlatformTenant).where(PlatformTenant.slug == slug))
    if exists:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Slug already exists")
    tenant = PlatformTenant(
        name=name,
        slug=slug,
        status="PROVISIONING",
        plan=body.get("plan") or body.get("plan_code") or "trial",
        db_status="NOT_PROVISIONED",
    )
    db.add(tenant)
    await db.commit()
    return {"id": tenant.id, "slug": tenant.slug, "status": tenant.status, "db_status": tenant.db_status}


@router.post("/tenants/{tenant_id}/provision")
async def provision_tenant(tenant_id: int, db: AsyncSession = Depends(get_db), _: None = Depends(require_admin_header)):
    admin_url = settings.postgres_admin_url
    if not admin_url:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="POSTGRES_ADMIN_URL is required for provisioning.",
        )
    app_user = settings.tenant_db_app_user
    app_pass = settings.tenant_db_app_password
    if not app_user or not app_pass:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Tenant DB app user credentials are required.",
        )

    # Acquire row lock and move to PROVISIONING atomically
    async with db.begin():
        tenant = (
            await db.execute(
                select(PlatformTenant).where(PlatformTenant.id == tenant_id).with_for_update()
            )
        ).scalar_one_or_none()
        if not tenant:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
        if tenant.db_status == "READY":
            return _provision_response(tenant)
        if tenant.db_status == "PROVISIONING":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Provisioning already in progress")

        safe_slug = _sanitize_db_name(tenant.slug)
        if not safe_slug:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid tenant slug for DB name")
        db_name = f"tenant_{safe_slug}"
        parsed = urlparse(admin_url)

        tenant.db_status = "PROVISIONING"
        tenant.db_last_error = None
        tenant.db_last_error_at = None
        tenant.db_name = db_name
        tenant.db_host = parsed.hostname
        tenant.db_port = parsed.port
        tenant.db_user = app_user

    tenant_db_url = _build_tenant_db_url(admin_url, db_name, app_user, app_pass)

    try:
        await _create_database_if_not_exists(admin_url, db_name)
        await _run_tenant_migrations(tenant_db_url, settings.tenant_alembic_target_rev)
        async with db.begin():
            tenant = (
                await db.execute(
                    select(PlatformTenant).where(PlatformTenant.id == tenant_id).with_for_update()
                )
            ).scalar_one()
            tenant.db_status = "READY"
            tenant.status = "ACTIVE"
            tenant.db_last_error = None
            tenant.db_last_error_at = None
            tenant.provisioned_at = datetime.now(timezone.utc)
    except Exception as exc:
        async with db.begin():
            tenant = (
                await db.execute(
                    select(PlatformTenant).where(PlatformTenant.id == tenant_id).with_for_update()
                )
            ).scalar_one()
            tenant.db_status = "ERROR"
            tenant.db_last_error = str(exc)
            tenant.db_last_error_at = datetime.now(timezone.utc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Provisioning failed: {exc}")

    return _provision_response(tenant)


@router.get("/tenants/{tenant_id}")
async def get_tenant(tenant_id: int, db: AsyncSession = Depends(get_db), _: None = Depends(require_admin_header)):
    tenant = await db.get(PlatformTenant, tenant_id)
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    return {
        "id": tenant.id,
        "name": tenant.name,
        "slug": tenant.slug,
        "status": tenant.status,
        "plan": tenant.plan,
        "db_status": tenant.db_status,
        "db_last_error": tenant.db_last_error,
        "db_last_error_at": tenant.db_last_error_at,
        "provisioned_at": tenant.provisioned_at,
    }


@router.post("/tenants/{tenant_id}/retry-provision")
async def retry_provision(tenant_id: int, db: AsyncSession = Depends(get_db), _: None = Depends(require_admin_header)):
    # Clear error and reuse provisioning flow
    tenant = await db.get(PlatformTenant, tenant_id)
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    if tenant.db_status == "PROVISIONING":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Provisioning already in progress")
    async with db.begin():
        tenant.db_status = "NOT_PROVISIONED"
        tenant.db_last_error = None
        tenant.db_last_error_at = None
    return await provision_tenant(tenant_id, db)


# ---- helpers ----
PROJECT_ROOT = Path(__file__).resolve().parents[2]


async def _create_database_if_not_exists(admin_url: str, db_name: str) -> None:
    engine = create_async_engine(admin_url, isolation_level="AUTOCOMMIT")
    async with engine.connect() as conn:
        try:
            await conn.execute(text(f'CREATE DATABASE "{db_name}"'))
        except Exception as exc:
            # If DB already exists, continue; otherwise re-raise
            if "already exists" not in str(exc):
                raise
    await engine.dispose()


async def _run_tenant_migrations(tenant_db_url: str, target_rev: str) -> None:
    # Run alembic upgrade for tenant schema only (targeting configured tenant head)
    env = os.environ.copy()
    env["DATABASE_URL"] = tenant_db_url
    cmd = ["alembic", "upgrade", target_rev]
    proc = await asyncio.create_subprocess_exec(
        *cmd, cwd=str(PROJECT_ROOT), env=env, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(f"Alembic failed: {stderr.decode().strip() or stdout.decode().strip()}")


def _sanitize_db_name(slug: str) -> str:
    name = slug.lower().replace("-", "_")
    name = re.sub(r"[^a-z0-9_]", "", name)
    return name[:50]


def _build_tenant_db_url(admin_url: str, db_name: str, user: str, password: str) -> str:
    parsed = urlparse(admin_url)
    host = parsed.hostname or "localhost"
    port = f":{parsed.port}" if parsed.port else ""
    netloc = f"{user}:{password}@{host}{port}"
    return urlunparse(parsed._replace(netloc=netloc, path=f"/{db_name}"))


def _provision_response(tenant: PlatformTenant) -> dict:
    return {
        "tenant_id": tenant.id,
        "slug": tenant.slug,
        "status": tenant.status,
        "db_status": tenant.db_status,
        "db_last_error": tenant.db_last_error,
        "db_last_error_at": tenant.db_last_error_at,
        "provisioned_at": tenant.provisioned_at,
        "tenant_portal_url": f"https://{tenant.slug}.truckerp.me",
    }
