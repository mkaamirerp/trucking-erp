"""
Pre-cutover verification: platform vs tenant auth row counts and credential parity.

If this reports errors after a failed dual-write, restore trust before rollback:

  python -m app.scripts.reconcile_tenant_auth_before_rollback --tenant-id=<id>

That runs a full idempotent sync from platform → tenant auth, then re-runs these checks.
"""

from __future__ import annotations

from sqlalchemy import func, select

from app.core.database import AsyncSessionLocal
from app.deps.tenant_db import open_tenant_session_by_id
from app.models.platform import PlatformTenantMember, PlatformTenantUserMap, PlatformUser, TenantMembership
from app.models.tenant_auth import TenantUser, TenantWorkspaceMember


async def collect_tenant_auth_cutover_errors(tenant_id: int) -> list[str]:
    """
    Return human-readable errors; empty list means checks passed.
    Used by CLI and tests (same logic as ops pre-cutover).
    """
    errors: list[str] = []
    async with AsyncSessionLocal() as pdb:
        n_ptm = int(
            (
                await pdb.scalar(
                    select(func.count()).select_from(PlatformTenantMember).where(
                        PlatformTenantMember.tenant_id == int(tenant_id)
                    )
                )
            )
            or 0
        )
        n_map = int(
            (
                await pdb.scalar(
                    select(func.count()).select_from(PlatformTenantUserMap).where(
                        PlatformTenantUserMap.tenant_id == int(tenant_id)
                    )
                )
            )
            or 0
        )

    async for tdb in open_tenant_session_by_id(int(tenant_id)):
        n_tu = int(
            (
                await tdb.scalar(
                    select(func.count())
                    .select_from(TenantUser)
                    .where(TenantUser.tenant_id == int(tenant_id))
                )
            )
            or 0
        )
        n_twm = int(
            (
                await tdb.scalar(
                    select(func.count())
                    .select_from(TenantWorkspaceMember)
                    .where(TenantWorkspaceMember.tenant_id == int(tenant_id))
                )
            )
            or 0
        )
        break

    if n_map != n_ptm:
        errors.append(f"platform_tenant_user_map count {n_map} != platform_tenant_members {n_ptm}")
    if n_tu < n_ptm:
        errors.append(f"tenant_users {n_tu} < platform members {n_ptm}")
    if n_twm < n_ptm:
        errors.append(f"tenant_workspace_members {n_twm} < platform members {n_ptm}")

    async with AsyncSessionLocal() as pdb:
        members = (
            await pdb.scalars(select(PlatformTenantMember).where(PlatformTenantMember.tenant_id == int(tenant_id)))
        ).all()
        for ptm in members:
            user = await pdb.scalar(select(PlatformUser).where(PlatformUser.id == str(ptm.platform_user_id)))
            if not user:
                errors.append(f"missing PlatformUser for ptm platform_user_id={ptm.platform_user_id}")
                continue
            tm = await pdb.scalar(
                select(TenantMembership).where(
                    TenantMembership.user_id == user.id,
                    TenantMembership.tenant_id == int(tenant_id),
                )
            )
            if not tm:
                errors.append(f"missing TenantMembership user={user.id}")
            pmap = await pdb.scalar(
                select(PlatformTenantUserMap).where(
                    PlatformTenantUserMap.tenant_id == int(tenant_id),
                    PlatformTenantUserMap.platform_user_id == str(user.id),
                )
            )
            if not pmap:
                errors.append(f"missing PlatformTenantUserMap platform_user_id={user.id}")
                continue
            async for tdb in open_tenant_session_by_id(int(tenant_id)):
                tu = await tdb.scalar(
                    select(TenantUser).where(
                        TenantUser.tenant_id == int(tenant_id),
                        TenantUser.id == int(pmap.tenant_user_id),
                    )
                )
                if not tu:
                    errors.append(f"missing TenantUser id={pmap.tenant_user_id}")
                elif (user.password_hash or "") != (tu.password_hash or ""):
                    errors.append(f"password_hash drift platform_user={user.id} tenant_user={tu.id}")
                elif int(getattr(user, "session_version", 1)) != int(getattr(tu, "session_version", 1)):
                    errors.append(f"session_version drift platform_user={user.id} tenant_user={tu.id}")
                break

    return errors
