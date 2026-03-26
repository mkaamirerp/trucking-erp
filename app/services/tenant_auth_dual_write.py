"""Dual-write platform_users <-> tenant_users on credential changes when tenant uses tenant DB auth."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.platform import PlatformUser, PlatformTenantUserMap
from app.models.tenant_auth import TenantUser
from app.services.tenant_auth_constants import tenant_uses_tenant_db_auth
from app.utils.password import hash_password

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


async def mirror_tenant_user_credentials_to_platform(
    *,
    platform_db: AsyncSession,
    tenant_id: int,
    tenant_user: TenantUser,
    mirror_password: bool = True,
    mirror_session: bool = True,
) -> None:
    """After tenant_users row is committed, copy credential fields to platform_users via map."""
    pmap = await platform_db.scalar(
        select(PlatformTenantUserMap).where(
            PlatformTenantUserMap.tenant_id == int(tenant_id),
            PlatformTenantUserMap.tenant_user_id == int(tenant_user.id),
        )
    )
    if not pmap:
        msg = (
            f"dual_write_missing_map tenant_id={tenant_id} tenant_user_id={tenant_user.id} "
            "cannot mirror credentials to platform"
        )
        logger.critical(msg)
        raise RuntimeError(msg)

    puser = await platform_db.get(PlatformUser, pmap.platform_user_id)
    if not puser:
        msg = f"dual_write_missing_platform_user id={pmap.platform_user_id}"
        logger.critical(msg)
        raise RuntimeError(msg)

    if mirror_password:
        puser.password_hash = tenant_user.password_hash
    if mirror_session:
        puser.session_version = int(tenant_user.session_version)
    puser.password_reset_token_hash = tenant_user.password_reset_token_hash
    puser.password_reset_expires_at = tenant_user.password_reset_expires_at
    await platform_db.commit()


async def apply_password_and_session_version_tenant_primary(
    *,
    platform_db: AsyncSession,
    tenant_db: AsyncSession,
    tenant_id: int,
    tenant_user: TenantUser,
    new_password_plain: str | None = None,
    bump_session: bool = True,
    defer_tenant_commit: bool = False,
) -> None:
    """
    Update tenant_user then mirror to platform_users via map. Any failure after tenant commit
    raises — caller should treat as reconciliation-required.

    When defer_tenant_commit=True, only mutates objects in tenant_db; caller must commit tenant,
    refresh tenant_user, then call mirror_tenant_user_credentials_to_platform (e.g. to bundle
    invite consumption + password in one tenant transaction).
    """
    if new_password_plain:
        tenant_user.password_hash = hash_password(new_password_plain)
        tenant_user.password_reset_token_hash = None
        tenant_user.password_reset_expires_at = None
    if bump_session:
        tenant_user.session_version = int(getattr(tenant_user, "session_version", 1) or 1) + 1
    if defer_tenant_commit:
        return
    await tenant_db.commit()
    await tenant_db.refresh(tenant_user)

    await mirror_tenant_user_credentials_to_platform(
        platform_db=platform_db,
        tenant_id=tenant_id,
        tenant_user=tenant_user,
        mirror_password=bool(new_password_plain),
        mirror_session=bump_session,
    )


async def apply_password_and_session_version_platform_primary(
    *,
    platform_db: AsyncSession,
    tenant_db: AsyncSession,
    tenant_id: int,
    platform_user: PlatformUser,
    tenant_auth_mode: str,
    new_password_plain: str | None = None,
    bump_session: bool = True,
) -> None:
    """Update platform user first; mirror to tenant_users if map exists and tenant DB auth is active."""
    if new_password_plain:
        platform_user.password_hash = hash_password(new_password_plain)
        platform_user.password_reset_token_hash = None
        platform_user.password_reset_expires_at = None
    if bump_session:
        platform_user.session_version = int(getattr(platform_user, "session_version", 1) or 1) + 1
    await platform_db.commit()
    await platform_db.refresh(platform_user)

    if not tenant_uses_tenant_db_auth(tenant_auth_mode):
        return

    pmap = await platform_db.scalar(
        select(PlatformTenantUserMap).where(
            PlatformTenantUserMap.tenant_id == int(tenant_id),
            PlatformTenantUserMap.platform_user_id == str(platform_user.id),
        )
    )
    if not pmap:
        msg = (
            f"dual_write_missing_map tenant_id={tenant_id} platform_user_id={platform_user.id} "
            "tenant_auth_mode=tenant requires map row"
        )
        logger.critical(msg)
        raise RuntimeError(msg)

    tu = await tenant_db.scalar(
        select(TenantUser).where(
            TenantUser.tenant_id == int(tenant_id),
            TenantUser.id == int(pmap.tenant_user_id),
        )
    )
    if not tu:
        msg = f"dual_write_missing_tenant_user id={pmap.tenant_user_id}"
        logger.critical(msg)
        raise RuntimeError(msg)

    if new_password_plain:
        tu.password_hash = platform_user.password_hash
    if bump_session:
        tu.session_version = int(platform_user.session_version)
    tu.password_reset_token_hash = platform_user.password_reset_token_hash
    tu.password_reset_expires_at = platform_user.password_reset_expires_at
    await tenant_db.commit()


async def mirror_reset_tokens_to_platform(
    *,
    platform_db: AsyncSession,
    platform_user_id: str,
    token_hash: str | None,
    expires_at,
) -> None:
    puser = await platform_db.get(PlatformUser, platform_user_id)
    if not puser:
        msg = f"dual_write_reset_missing_platform_user id={platform_user_id}"
        logger.critical(msg)
        raise RuntimeError(msg)
    puser.password_reset_token_hash = token_hash
    puser.password_reset_expires_at = expires_at
    await platform_db.commit()


async def mirror_reset_tokens_to_tenant(
    *,
    tenant_db: AsyncSession,
    tenant_id: int,
    tenant_user_id: int,
    token_hash: str | None,
    expires_at,
) -> None:
    tu = await tenant_db.scalar(
        select(TenantUser).where(TenantUser.tenant_id == int(tenant_id), TenantUser.id == int(tenant_user_id))
    )
    if not tu:
        msg = f"dual_write_reset_missing_tenant_user id={tenant_user_id}"
        logger.critical(msg)
        raise RuntimeError(msg)
    tu.password_reset_token_hash = token_hash
    tu.password_reset_expires_at = expires_at
    await tenant_db.commit()
