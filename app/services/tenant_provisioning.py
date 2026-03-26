from __future__ import annotations

import asyncio
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse, urlsplit, urlunsplit

from fastapi import HTTPException, status
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.db_url import to_async_pg_url
from app.models.platform import PlatformTenant, PlatformTenantUserMap, PlatformUser
from app.services.tenant_schema_validation import validate_tenant_schema_strict

PROJECT_ROOT = Path(__file__).resolve().parents[2]
logger = logging.getLogger(__name__)


async def _repair_tenant_auth_after_ready_if_needed(tenant: PlatformTenant, tenant_id: int) -> None:
    """
    Half-failed provision: DB marked READY but tenant_users / twm / map may be missing.
    Re-run idempotent full-member sync (same as CLI sync). Safe on every READY short-circuit.

    Future optimization (not implemented): if map vs member counts match and spot-checks pass,
    skip full sync for large workspaces; today we favor correctness over latency.
    """
    if not tenant.db_name:
        logger.warning("tenant_auth_ready_repair_skipped_no_db_name tenant_id=%s", tenant_id)
        return

    raw_admin_url = settings.postgres_admin_url or settings.database_url
    if not raw_admin_url:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database URL not configured for tenant auth repair.",
        )
    admin_url = to_async_pg_url(raw_admin_url)
    app_user = settings.tenant_db_app_user
    app_pass = settings.tenant_db_app_password
    if not app_user or not app_pass:
        parsed_admin = urlparse(admin_url)
        if parsed_admin.username and parsed_admin.password:
            app_user = app_user or parsed_admin.username
            app_pass = app_pass or parsed_admin.password
    if not app_user or not app_pass:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Tenant DB app credentials are required for auth repair.",
        )

    tenant_db_url = to_async_pg_url(_build_tenant_db_url(admin_url, tenant.db_name, app_user, app_pass))
    try:
        from app.services.tenant_auth_sync_core import sync_tenant_auth_from_platform_members

        await sync_tenant_auth_from_platform_members(int(tenant_id), tenant_db_url)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("tenant_auth_ready_repair_failed tenant_id=%s", tenant_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Workspace database is ready but tenant auth rows could not be reconciled. "
                "Run: python -m app.scripts.sync_tenant_auth_from_platform --tenant-id=<id>"
            ),
        ) from exc


async def backfill_tenant_creator_person(tenant_slug: str, platform_user_id: str) -> bool:
    """
    Ensure a people row (and OWNER role) exists in the tenant DB for the given platform user.
    Use when a tenant was provisioned without creator seed (e.g. before this existed, or company-setup flow).
    Returns True if a row was created, False if already existed or tenant/user not found.
    """
    async with AsyncSessionLocal() as db:
        tenant = await db.scalar(
            select(PlatformTenant).where(PlatformTenant.slug == tenant_slug.strip().lower())
        )
        if not tenant or not tenant.db_name:
            return False
        user = await db.get(PlatformUser, platform_user_id)
        if not user:
            return False
        tenant_id = int(tenant.id)
    raw_admin_url = settings.postgres_admin_url or settings.database_url
    admin_url = to_async_pg_url(raw_admin_url)
    parsed = urlparse(admin_url)
    app_user = settings.tenant_db_app_user or parsed.username
    app_pass = settings.tenant_db_app_password or parsed.password
    if not app_user or not app_pass:
        return False
    tenant_db_url = to_async_pg_url(
        _build_tenant_db_url(admin_url, tenant.db_name, app_user, app_pass)
    )
    tu_id = await _seed_tenant_creator(
        tenant_db_url=tenant_db_url,
        tenant_id=tenant_id,
        platform_user_id=platform_user_id,
        first_name=user.first_name or "",
        last_name=user.last_name or "",
        email=user.email or "",
        password_hash=user.password_hash,
        session_version=int(getattr(user, "session_version", 1) or 1),
    )
    if tu_id is None:
        return False
    async with AsyncSessionLocal() as pdb:
        existing = await pdb.scalar(
            select(PlatformTenantUserMap).where(
                PlatformTenantUserMap.tenant_id == tenant_id,
                PlatformTenantUserMap.platform_user_id == str(platform_user_id),
            )
        )
        if not existing:
            pdb.add(
                PlatformTenantUserMap(
                    platform_user_id=str(platform_user_id),
                    tenant_id=tenant_id,
                    tenant_user_id=int(tu_id),
                )
            )
            await pdb.commit()
    return True


async def provision_tenant_db(
    tenant_id: int,
    db: AsyncSession,
    *,
    activate: bool = True,
    creator_platform_user_id: Optional[str] = None,
    creator_first_name: Optional[str] = None,
    creator_last_name: Optional[str] = None,
    creator_email: Optional[str] = None,
) -> PlatformTenant:
    raw_admin_url = settings.postgres_admin_url or settings.database_url
    admin_url = to_async_pg_url(raw_admin_url)
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

    # Use the session without starting a new transaction (caller may already have one open, e.g. verify_otp).
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
        await _repair_tenant_auth_after_ready_if_needed(tenant, int(tenant_id))
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
    await db.flush()

    tenant_db_url = to_async_pg_url(_build_tenant_db_url(admin_url, db_name, app_user, app_pass))

    try:
        await _create_database_if_not_exists(admin_url, db_name)
        await _run_tenant_migrations(tenant_db_url, settings.tenant_alembic_target_rev)

        # Validate schema after migrations (fail-closed: catch migration conflicts/drift early)
        validate_tenant_schema_strict(tenant_db_url)

        tenant_user_id: int | None = None
        if creator_platform_user_id is not None and creator_first_name is not None and creator_last_name is not None:
            pu = await db.get(PlatformUser, str(creator_platform_user_id))
            tenant_user_id = await _seed_tenant_creator(
                tenant_db_url=tenant_db_url,
                tenant_id=tenant_id,
                platform_user_id=str(creator_platform_user_id),
                first_name=creator_first_name or "",
                last_name=creator_last_name or "",
                email=creator_email or "",
                password_hash=getattr(pu, "password_hash", None) if pu else None,
                session_version=int(getattr(pu, "session_version", 1) or 1) if pu else 1,
            )
        if tenant_user_id is not None and creator_platform_user_id:
            existing_map = await db.scalar(
                select(PlatformTenantUserMap).where(
                    PlatformTenantUserMap.tenant_id == int(tenant_id),
                    PlatformTenantUserMap.platform_user_id == str(creator_platform_user_id),
                )
            )
            if not existing_map:
                db.add(
                    PlatformTenantUserMap(
                        platform_user_id=str(creator_platform_user_id),
                        tenant_id=int(tenant_id),
                        tenant_user_id=int(tenant_user_id),
                    )
                )
            await db.flush()
        # Re-fetch tenant and set READY (same session; caller will commit)
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
        # Re-fetch and mark ERROR (same session; caller may commit or roll back)
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


async def _seed_tenant_creator(
    tenant_db_url: str,
    tenant_id: int,
    platform_user_id: str,
    first_name: str,
    last_name: str,
    email: str,
    *,
    password_hash: str | None = None,
    session_version: int = 1,
) -> int | None:
    """
    Insert creator as people + person_roles (OWNER), tenant_users, tenant_workspace_members (active admin).
    Idempotent: upserts tenant auth rows; creates person only if missing.
    Returns tenant_users.id, or None if email_norm is empty.
    """
    from app.utils.auth_identity import normalize_auth_email

    email_norm = normalize_auth_email(email)
    if not email_norm:
        return None

    engine = create_async_engine(to_async_pg_url(tenant_db_url))
    async with engine.begin() as conn:
        res = await conn.execute(
            text(
                "SELECT id FROM people WHERE tenant_id = :tid AND platform_user_id = :uid LIMIT 1"
            ),
            {"tid": tenant_id, "uid": platform_user_id},
        )
        person_id = res.scalar_one_or_none()
        if person_id is None:
            result = await conn.execute(
                text(
                    """
                    INSERT INTO people (tenant_id, first_name, last_name, email, is_active, created_at, updated_at, platform_user_id)
                    VALUES (:tenant_id, :first_name, :last_name, :email, true, now(), now(), :platform_user_id)
                    RETURNING id
                    """
                ),
                {
                    "tenant_id": tenant_id,
                    "first_name": first_name,
                    "last_name": last_name,
                    "email": email or None,
                    "platform_user_id": platform_user_id,
                },
            )
            person_id = result.scalar_one()
            await conn.execute(
                text(
                    """
                    INSERT INTO person_roles (tenant_id, person_id, role_code, is_primary, is_active, created_at, updated_at)
                    VALUES (:tenant_id, :person_id, 'OWNER', true, true, now(), now())
                    """
                ),
                {"tenant_id": tenant_id, "person_id": person_id},
            )

        tu_res = await conn.execute(
            text(
                """
                INSERT INTO tenant_users (
                    tenant_id, email_norm, first_name, last_name, password_hash, session_version, status, person_id, created_at, updated_at
                )
                VALUES (
                    :tenant_id, :email_norm, :first_name, :last_name, :password_hash, :session_version, 'ACTIVE', :person_id, now(), now()
                )
                ON CONFLICT (tenant_id, email_norm)
                DO UPDATE SET
                    first_name = EXCLUDED.first_name,
                    last_name = EXCLUDED.last_name,
                    password_hash = COALESCE(EXCLUDED.password_hash, tenant_users.password_hash),
                    session_version = EXCLUDED.session_version,
                    person_id = COALESCE(EXCLUDED.person_id, tenant_users.person_id),
                    updated_at = now()
                RETURNING id
                """
            ),
            {
                "tenant_id": tenant_id,
                "email_norm": email_norm,
                "first_name": first_name,
                "last_name": last_name,
                "password_hash": password_hash,
                "session_version": session_version,
                "person_id": person_id,
            },
        )
        tenant_user_id = int(tu_res.scalar_one())

        await conn.execute(
            text(
                """
                INSERT INTO tenant_workspace_members (
                    tenant_id, tenant_user_id, status, role, created_at, updated_at
                )
                VALUES (
                    :tenant_id, :tenant_user_id, 'active', 'TENANT_ADMIN', now(), now()
                )
                ON CONFLICT (tenant_id, tenant_user_id)
                DO UPDATE SET
                    status = 'active',
                    role = EXCLUDED.role,
                    updated_at = now()
                """
            ),
            {"tenant_id": tenant_id, "tenant_user_id": tenant_user_id},
        )

    await engine.dispose()
    return tenant_user_id


async def _create_database_if_not_exists(admin_url: str, db_name: str) -> None:
    engine = create_async_engine(to_async_pg_url(admin_url), isolation_level="AUTOCOMMIT")
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
