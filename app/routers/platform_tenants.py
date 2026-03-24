from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db_url import to_async_pg_url

from app.core.config import settings
from app.core.database import get_db
from app.models.platform import PlatformTenant
from app.schemas.platform import PlatformTenantOut
from app.services.tenant_provisioning import (
    _build_tenant_db_url,
    _create_database_if_not_exists,
    _run_tenant_migrations,
)

router = APIRouter(prefix="/api/v1/platform", tags=["platform-tenants"])
logger = logging.getLogger(__name__)


def require_admin_header(x_platform_admin_key: str | None = Header(None)) -> None:
    expected = None  # set via env if needed later
    if expected and x_platform_admin_key != expected:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")


@router.get("/tenants", response_model=list[PlatformTenantOut])
async def list_tenants(db: AsyncSession = Depends(get_db), _: None = Depends(require_admin_header)):
    try:
        rows = (await db.execute(select(PlatformTenant))).scalars().all()
    except Exception as exc:
        logger.exception("platform_tenants.list_failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to list platform tenants"
        ) from exc
    return [PlatformTenantOut.model_validate(t) for t in rows]


@router.post("/tenants", response_model=PlatformTenantOut)
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
    await db.refresh(tenant)
    return PlatformTenantOut.model_validate(tenant)


@router.post("/tenants/{tenant_id}/provision")
async def provision_tenant(tenant_id: int, db: AsyncSession = Depends(get_db), _: None = Depends(require_admin_header)):
    raw_admin_url = settings.postgres_admin_url or settings.database_url
    logger.info(
        "postgres_admin_url type=%s value=%r database_url_present=%s",
        type(settings.postgres_admin_url),
        settings.postgres_admin_url,
        bool(settings.database_url),
    )
    admin_url = to_async_pg_url(raw_admin_url)
    if not admin_url:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="POSTGRES_ADMIN_URL is required for provisioning.",
        )
    app_user = settings.tenant_db_app_user
    app_pass = settings.tenant_db_app_password
    if not app_user or not app_pass:
        # Fallback: reuse admin URL credentials if dedicated tenant creds are not set
        parsed_admin = urlparse(admin_url)
        admin_username = parsed_admin.username
        admin_password = parsed_admin.password
        if admin_username and admin_password:
            logger.warning(
                "tenant_db_app_user_password_missing: falling back to admin credentials. "
                "Set TENANT_DB_APP_USER and TENANT_DB_APP_PASSWORD for production."
            )
            app_user = app_user or admin_username
            app_pass = app_pass or admin_password
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

    tenant_db_url = to_async_pg_url(_build_tenant_db_url(admin_url, db_name, app_user, app_pass))

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


@router.get("/tenants/{tenant_id}", response_model=PlatformTenantOut)
async def get_tenant(tenant_id: int, db: AsyncSession = Depends(get_db), _: None = Depends(require_admin_header)):
    try:
        tenant = await db.get(PlatformTenant, tenant_id)
    except Exception as exc:
        logger.exception("platform_tenants.get_failed tenant_id=%s", tenant_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to load platform tenant"
        ) from exc
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    try:
        return PlatformTenantOut.model_validate(tenant)
    except Exception as exc:
        logger.exception("platform_tenants.serialize_failed tenant_id=%s", tenant_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to serialize platform tenant"
        ) from exc


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


# ---- helpers (router-local; DB URL / migrate / create DB shared with signup via tenant_provisioning) ----


def _sanitize_db_name(slug: str) -> str:
    name = slug.lower().replace("-", "_")
    name = re.sub(r"[^a-z0-9_]", "", name)
    return name[:50]


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
