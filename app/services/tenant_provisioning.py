from __future__ import annotations

import asyncio
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Union
from urllib.parse import urlparse, urlsplit, urlunsplit

from fastapi import HTTPException, status
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.config import settings
from app.models.platform import PlatformTenant

PROJECT_ROOT = Path(__file__).resolve().parents[2]


async def provision_tenant_db(tenant_id: int, db: AsyncSession, *, activate: bool = True) -> PlatformTenant:
    raw_admin_url = settings.postgres_admin_url or settings.database_url
    admin_url = _ensure_asyncpg_url(raw_admin_url)
    if not admin_url:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="POSTGRES_ADMIN_URL is required for provisioning.",
        )

    app_user = settings.tenant_db_app_user
    app_pass = settings.tenant_db_app_password
    if not app_user or not app_pass:
        parsed_admin = urlparse(admin_url)
        admin_username = parsed_admin.username
        admin_password = parsed_admin.password
        if admin_username and admin_password:
            app_user = app_user or admin_username
            app_pass = app_pass or admin_password
    if not app_user or not app_pass:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Tenant DB app user credentials are required.",
        )

    async with db.begin():
        tenant = (
            await db.execute(
                select(PlatformTenant).where(PlatformTenant.id == tenant_id).with_for_update()
            )
        ).scalar_one_or_none()
        if not tenant:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
        if tenant.db_status == "READY":
            if activate and tenant.status != "ACTIVE":
                tenant.status = "ACTIVE"
                if tenant.provisioned_at is None:
                    tenant.provisioned_at = datetime.now(timezone.utc)
            tenant.db_last_error = None
            tenant.db_last_error_at = None
            return tenant
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

    tenant_db_url = _ensure_asyncpg_url(_build_tenant_db_url(admin_url, db_name, app_user, app_pass))

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
            if activate:
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

    return tenant


async def _create_database_if_not_exists(admin_url: str, db_name: str) -> None:
    engine = create_async_engine(_ensure_asyncpg_url(admin_url), isolation_level="AUTOCOMMIT")
    async with engine.connect() as conn:
        try:
            await conn.execute(text(f'CREATE DATABASE "{db_name}"'))
        except Exception as exc:
            if "already exists" not in str(exc):
                raise
    await engine.dispose()


async def _run_tenant_migrations(tenant_db_url: str, target_rev: str) -> None:
    env = os.environ.copy()
    # Tenant Alembic env.py reads ONLY ALEMBIC_TENANT_DATABASE_URL.
    # Without this, signup provisioning may fail or migrate the wrong DB.
    env["ALEMBIC_TENANT_DATABASE_URL"] = tenant_db_url
    env["DATABASE_URL"] = tenant_db_url
    env["TENANT_DATABASE_URL"] = tenant_db_url
    cmd = ["python", "-m", "alembic", "-c", "alembic_tenant.ini", "upgrade", target_rev]
    proc = await asyncio.create_subprocess_exec(
        *cmd, cwd=str(PROJECT_ROOT), env=env, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(f"Alembic failed: {stderr.decode().strip() or stdout.decode().strip()}")


def _sanitize_db_name(slug: str) -> str:
    raw = (slug or "").strip().lower()
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,62}", raw):
        return ""
    name = raw.replace("-", "_")
    name = re.sub(r"[^a-z0-9_]", "", name)
    return name[:50]


def _build_tenant_db_url(admin_url: str, db_name: str, user: str, password: str) -> str:
    parsed = urlsplit(admin_url)
    if not parsed.hostname:
        raise ValueError("Invalid postgres admin URL")

    netloc = f"{user}:{password}@{parsed.hostname}"
    if parsed.port:
        netloc = f"{netloc}:{parsed.port}"
    return urlunsplit((parsed.scheme, netloc, f"/{db_name}", parsed.query, parsed.fragment))


def _ensure_asyncpg_url(url: Union[str, bytes]) -> str:
    if url is None:
        return ""
    if isinstance(url, (bytes, bytearray, memoryview)):
        url = bytes(url).decode("utf-8", errors="strict")

    parsed = urlsplit(url)
    scheme = parsed.scheme
    if scheme in {"postgres", "postgresql"}:
        scheme = f"{scheme}+asyncpg"
        return urlunsplit((scheme, parsed.netloc, parsed.path, parsed.query, parsed.fragment))
    return url
