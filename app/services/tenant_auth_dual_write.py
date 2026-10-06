"""Dual-write platform_users <-> tenant_users on credential changes when tenant uses tenant DB auth."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.platform import PlatformTenant, PlatformUser, PlatformTenantUserMap
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


async def mirror_committed_platform_credentials_to_tenant_user(
    *,
    tenant_db: AsyncSession,
    tenant_id: int,
    tenant_user_id: int,
    platform_user: PlatformUser,
    commit: bool = True,
) -> TenantUser:
    """Copy platform password/session/reset fields onto the mapped tenant_user."""
    tu = await tenant_db.scalar(
        select(TenantUser).where(
            TenantUser.tenant_id == int(tenant_id),
            TenantUser.id == int(tenant_user_id),
        )
    )
    if not tu:
        msg = f"dual_write_missing_tenant_user id={tenant_user_id}"
        logger.critical(msg)
        raise RuntimeError(msg)
    tu.password_hash = platform_user.password_hash
    tu.session_version = int(getattr(platform_user, "session_version", 1) or 1)
    tu.password_reset_token_hash = platform_user.password_reset_token_hash
    tu.password_reset_expires_at = platform_user.password_reset_expires_at
    if commit:
        await tenant_db.commit()
    return tu


def _tenant_user_credential_snapshot(tu: TenantUser) -> dict:
    return {
        "password_hash": tu.password_hash,
        "session_version": int(getattr(tu, "session_version", 1) or 1),
        "password_reset_token_hash": tu.password_reset_token_hash,
        "password_reset_expires_at": tu.password_reset_expires_at,
    }


def _restore_tenant_user_credentials(tu: TenantUser, snap: dict) -> None:
    tu.password_hash = snap["password_hash"]
    tu.session_version = snap["session_version"]
    tu.password_reset_token_hash = snap["password_reset_token_hash"]
    tu.password_reset_expires_at = snap["password_reset_expires_at"]


def _apply_reset_credentials(tu: TenantUser, *, password_hash: str, session_version: int) -> None:
    tu.password_hash = password_hash
    tu.session_version = int(session_version)
    tu.password_reset_token_hash = None
    tu.password_reset_expires_at = None


async def _aclose_quietly(agen) -> None:
    if agen is None:
        return
    try:
        await agen.aclose()
    except Exception:
        logger.exception("apex_reset tenant session close failed")


async def _hold_tenant_session(open_tenant_session, tenant_id: int):
    agen = open_tenant_session(int(tenant_id))
    try:
        session = await agen.__anext__()
    except BaseException:
        await _aclose_quietly(agen)
        raise
    return agen, session


async def tenant_auth_maps_for_platform_user(
    platform_db: AsyncSession,
    platform_user_id: str,
) -> list[tuple[int, int]]:
    """
    Deterministic list of (tenant_id, tenant_user_id) for tenant-auth workspaces mapped to this user.
    Does not pick a single tenant when several exist; callers must apply the same credential to all.
    """
    maps = (
        await platform_db.execute(
            select(PlatformTenantUserMap)
            .where(PlatformTenantUserMap.platform_user_id == str(platform_user_id))
            .order_by(PlatformTenantUserMap.tenant_id.asc(), PlatformTenantUserMap.tenant_user_id.asc())
        )
    ).scalars().all()
    out: list[tuple[int, int]] = []
    for pmap in maps:
        pt = await platform_db.get(PlatformTenant, int(pmap.tenant_id))
        if not pt or not tenant_uses_tenant_db_auth(getattr(pt, "tenant_auth_mode", None)):
            continue
        out.append((int(pmap.tenant_id), int(pmap.tenant_user_id)))
    return out


async def apply_apex_password_reset_sync_mapped_tenants(
    *,
    platform_db: AsyncSession,
    platform_user: PlatformUser,
    new_password_plain: str,
    open_tenant_session,
) -> list[int]:
    """
    Apex/marketing-host reset: update every mapped tenant-auth workspace, then PlatformUser.

    Safety: do not commit platform password/session_version/reset-token until every tenant
    preflight succeeded and every tenant commit succeeded. If a later tenant fails after an
    earlier tenant commit, compensate already-committed tenants back to their pre-reset snapshot.
    A reported failure leaves the platform reset token usable.
    """
    platform_snap = _tenant_user_credential_snapshot(platform_user)
    new_hash = hash_password(new_password_plain)
    new_sv = int(getattr(platform_user, "session_version", 1) or 1) + 1
    targets = await tenant_auth_maps_for_platform_user(platform_db, str(platform_user.id))

    if not targets:
        platform_user.password_hash = new_hash
        platform_user.session_version = new_sv
        platform_user.password_reset_token_hash = None
        platform_user.password_reset_expires_at = None
        await platform_db.commit()
        await platform_db.refresh(platform_user)
        return []

    held: list[dict] = []
    committed: list[dict] = []

    async def _rollback_session(tdb) -> None:
        rb = getattr(tdb, "rollback", None)
        if callable(rb):
            await rb()

    try:
        for tenant_id, tenant_user_id in targets:
            agen, tdb = await _hold_tenant_session(open_tenant_session, int(tenant_id))
            item = {
                "tenant_id": int(tenant_id),
                "tenant_user_id": int(tenant_user_id),
                "agen": agen,
                "tdb": tdb,
                "tu": None,
                "snapshot": None,
            }
            held.append(item)
            tu = await tdb.scalar(
                select(TenantUser).where(
                    TenantUser.tenant_id == int(tenant_id),
                    TenantUser.id == int(tenant_user_id),
                )
            )
            if not tu:
                msg = f"dual_write_missing_tenant_user id={tenant_user_id}"
                logger.critical(msg)
                raise RuntimeError(msg)
            item["tu"] = tu
            item["snapshot"] = _tenant_user_credential_snapshot(tu)

        try:
            for item in held:
                _apply_reset_credentials(item["tu"], password_hash=new_hash, session_version=new_sv)
                flush = getattr(item["tdb"], "flush", None)
                if callable(flush):
                    await flush()
        except Exception:
            logger.exception("apex_reset tenant prepare/flush failed; rolling back uncommitted tenant sessions")
            for item in held:
                try:
                    await _rollback_session(item["tdb"])
                except Exception:
                    logger.exception("apex_reset tenant rollback failed tenant_id=%s", item["tenant_id"])
            raise

        for item in held:
            try:
                await item["tdb"].commit()
            except Exception:
                logger.exception(
                    "apex_reset tenant commit failed tenant_id=%s; compensating earlier tenants",
                    item["tenant_id"],
                )
                try:
                    await _rollback_session(item["tdb"])
                except Exception:
                    logger.exception("apex_reset tenant rollback failed tenant_id=%s", item["tenant_id"])
                await _compensate_committed_apex_reset_tenants(committed)
                raise
            committed.append(item)

        platform_user.password_hash = new_hash
        platform_user.session_version = new_sv
        platform_user.password_reset_token_hash = None
        platform_user.password_reset_expires_at = None
        try:
            await platform_db.commit()
        except Exception:
            logger.exception("apex_reset platform commit failed; restoring platform snapshot and compensating tenants")
            _restore_tenant_user_credentials(platform_user, platform_snap)
            try:
                await _rollback_session(platform_db)
            except Exception:
                logger.exception("apex_reset platform rollback failed")
            await _compensate_committed_apex_reset_tenants(committed)
            raise
        await platform_db.refresh(platform_user)
        return [int(item["tenant_id"]) for item in held]
    finally:
        for item in held:
            await _aclose_quietly(item.get("agen"))


async def _compensate_committed_apex_reset_tenants(committed: list[dict]) -> None:
    failures: list[int] = []
    for item in committed:
        try:
            _restore_tenant_user_credentials(item["tu"], item["snapshot"])
            await item["tdb"].commit()
        except Exception:
            failures.append(int(item["tenant_id"]))
            logger.critical(
                "apex_reset compensate failed tenant_id=%s; platform credentials were not committed; "
                "reset token remains usable but this tenant may have drifted",
                item["tenant_id"],
            )
    if failures:
        raise RuntimeError(
            "apex_reset_compensate_failed tenant_ids=" + ",".join(str(i) for i in failures)
        )


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
