"""
Idempotent sync: platform members -> tenant_users, tenant_workspace_members, platform_tenant_user_map.

Uses a direct tenant DB URL (no Host / ACTIVE guard). Callers: provision READY repair, CLI sync script.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import AsyncSessionLocal
from app.core.db_url import to_async_pg_url
from app.models.platform import (
    PlatformTenantMember,
    PlatformUser,
    PlatformTenantUserMap,
    TenantMembership,
)
from app.models.tenant_auth import TenantUser, TenantWorkspaceMember
from app.utils.auth_identity import normalize_auth_email


async def sync_tenant_auth_from_platform_members(tenant_id: int, tenant_db_url: str) -> None:
    """
    For each PlatformTenantMember with TenantMembership, upsert tenant auth rows and map.
    Mirrors app.scripts.sync_tenant_auth_from_platform loops; does not require tenant.status == ACTIVE.
    """
    async_url = to_async_pg_url(tenant_db_url)
    engine = create_async_engine(async_url)
    SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with AsyncSessionLocal() as pdb:
        members = (
            await pdb.scalars(
                select(PlatformTenantMember).where(PlatformTenantMember.tenant_id == int(tenant_id))
            )
        ).all()

    try:
        for ptm in members:
            async with AsyncSessionLocal() as pdb_r:
                user = await pdb_r.scalar(select(PlatformUser).where(PlatformUser.id == str(ptm.platform_user_id)))
                if not user:
                    continue
                tm = await pdb_r.scalar(
                    select(TenantMembership).where(
                        TenantMembership.user_id == user.id,
                        TenantMembership.tenant_id == int(tenant_id),
                    )
                )
                if not tm:
                    continue
                email_norm = normalize_auth_email(user.email)
                if not email_norm:
                    continue
                twm_status = "active" if (tm.status or "").lower() == "active" else (tm.status or "invited")

            async with SessionLocal() as tdb:
                tu = await tdb.scalar(
                    select(TenantUser).where(
                        TenantUser.tenant_id == int(tenant_id),
                        TenantUser.email_norm == email_norm,
                    )
                )
                if not tu:
                    tu = TenantUser(
                        tenant_id=int(tenant_id),
                        email_norm=email_norm,
                        first_name=user.first_name,
                        last_name=user.last_name,
                        password_hash=user.password_hash,
                        password_reset_token_hash=user.password_reset_token_hash,
                        password_reset_expires_at=user.password_reset_expires_at,
                        session_version=int(getattr(user, "session_version", 1) or 1),
                        status="ACTIVE" if getattr(user, "status", "ACTIVE") == "ACTIVE" else "DISABLED",
                    )
                    tdb.add(tu)
                    await tdb.flush()
                else:
                    tu.password_hash = user.password_hash
                    tu.password_reset_token_hash = user.password_reset_token_hash
                    tu.password_reset_expires_at = user.password_reset_expires_at
                    tu.session_version = int(getattr(user, "session_version", 1) or 1)
                    tu.first_name = user.first_name
                    tu.last_name = user.last_name

                twm = await tdb.scalar(
                    select(TenantWorkspaceMember).where(
                        TenantWorkspaceMember.tenant_id == int(tenant_id),
                        TenantWorkspaceMember.tenant_user_id == tu.id,
                    )
                )
                role = ptm.role or "TENANT_MEMBER"
                if not twm:
                    twm = TenantWorkspaceMember(
                        tenant_id=int(tenant_id),
                        tenant_user_id=tu.id,
                        status=twm_status,
                        role=role,
                    )
                    tdb.add(twm)
                else:
                    twm.status = twm_status
                    twm.role = role

                await tdb.commit()
                tenant_uid = int(tu.id)

            async with AsyncSessionLocal() as pdb_w:
                existing = await pdb_w.scalar(
                    select(PlatformTenantUserMap).where(
                        PlatformTenantUserMap.tenant_id == int(tenant_id),
                        PlatformTenantUserMap.platform_user_id == str(user.id),
                    )
                )
                if not existing:
                    pdb_w.add(
                        PlatformTenantUserMap(
                            platform_user_id=str(user.id),
                            tenant_id=int(tenant_id),
                            tenant_user_id=tenant_uid,
                        )
                    )
                    await pdb_w.commit()
    finally:
        await engine.dispose()
