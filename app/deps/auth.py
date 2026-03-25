from __future__ import annotations

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps.tenant_db import open_tenant_session_by_id
from app.models.platform import (
    PlatformTenant,
    PlatformTenantMember,
    PlatformTenantUserMap,
    PlatformUser,
)
from app.models.tenant_auth import TenantUser, TenantWorkspaceMember
from app.services.tenant_auth_constants import tenant_uses_tenant_db_auth
from app.utils.jwt_auth import TokenType, decode_token, extract_sv, get_token_from_request


async def get_current_platform_user(request: Request, db: AsyncSession = Depends(get_db)) -> PlatformUser:
    """
    Authenticated platform user from access JWT only. No tenant host or membership required
    (used for POST /auth/workspaces before a new tenant exists).
    """
    token, _ = get_token_from_request(request)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    payload = decode_token(token, expected_type=TokenType.ACCESS)
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token claims")

    sv = extract_sv(payload)
    if sv is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session")

    user = await db.scalar(select(PlatformUser).where(PlatformUser.id == str(user_id)))
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    if getattr(user, "status", "ACTIVE") != "ACTIVE":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is deactivated")
    if int(getattr(user, "session_version", 1) or 1) != int(sv):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired")

    return user


class CurrentUser:
    def __init__(
        self,
        user: PlatformUser,
        tenant: PlatformTenant,
        role: str | None,
        member_id: int | None,
        *,
        tenant_user: TenantUser | None = None,
        tenant_local_member_id: int | None = None,
    ):
        self.user = user
        self.tenant = tenant
        self.role = role
        self.member_id = member_id
        self.tenant_user = tenant_user
        self.tenant_local_member_id = tenant_local_member_id

    @property
    def user_id(self) -> str:
        return str(self.user.id)

    @property
    def tenant_id(self) -> int:
        return int(self.tenant.id)

    @property
    def tenant_slug(self) -> str:
        return self.tenant.slug


async def get_current_user(request: Request, db: AsyncSession = Depends(get_db)) -> CurrentUser:
    token, _ = get_token_from_request(request)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    payload = decode_token(token, expected_type=TokenType.ACCESS)
    user_id_sub = payload.get("sub")
    jwt_tenant_id = payload.get("tenant_id")
    roles = payload.get("roles") or []
    role = roles[0] if roles else None

    if not user_id_sub:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token claims")

    tenant_id = getattr(request.state, "tenant_id", None)
    if tenant_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Tenant context required")

    if jwt_tenant_id is not None and int(jwt_tenant_id) != int(tenant_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Session workspace does not match this host; open the app from your workspace URL.",
        )

    sv = extract_sv(payload)
    if sv is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session")

    tenant = await db.scalar(
        select(PlatformTenant).options(selectinload(PlatformTenant.company_profile)).where(PlatformTenant.id == int(tenant_id))
    )
    if not tenant:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Tenant not found")

    mode = getattr(tenant, "tenant_auth_mode", None) or "platform"

    if tenant_uses_tenant_db_auth(mode):
        try:
            tu_id = int(user_id_sub)
        except (TypeError, ValueError):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session")

        async for tdb in open_tenant_session_by_id(int(tenant_id)):
            tu = await tdb.scalar(
                select(TenantUser).where(TenantUser.tenant_id == int(tenant_id), TenantUser.id == tu_id)
            )
            if not tu or (tu.status or "").upper() != "ACTIVE":
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

            if int(getattr(tu, "session_version", 1) or 1) != int(sv):
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired")

            twm = await tdb.scalar(
                select(TenantWorkspaceMember).where(
                    TenantWorkspaceMember.tenant_id == int(tenant_id),
                    TenantWorkspaceMember.tenant_user_id == tu_id,
                    TenantWorkspaceMember.status == "active",
                )
            )
            if not twm:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="User does not have access to this tenant",
                )
            if twm.role:
                role = twm.role
            break

        pmap = await db.scalar(
            select(PlatformTenantUserMap).where(
                PlatformTenantUserMap.tenant_id == int(tenant_id),
                PlatformTenantUserMap.tenant_user_id == tu_id,
            )
        )
        if not pmap:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Account mapping incomplete; contact support.",
            )
        puser = await db.scalar(select(PlatformUser).where(PlatformUser.id == str(pmap.platform_user_id)))
        if not puser or getattr(puser, "status", "ACTIVE") != "ACTIVE":
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

        ptm = await db.scalar(
            select(PlatformTenantMember).where(
                PlatformTenantMember.platform_user_id == puser.id,
                PlatformTenantMember.tenant_id == tenant.id,
            )
        )
        return CurrentUser(
            user=puser,
            tenant=tenant,
            role=role,
            member_id=ptm.id if ptm else None,
            tenant_user=tu,
            tenant_local_member_id=twm.id,
        )

    user = await db.scalar(select(PlatformUser).where(PlatformUser.id == str(user_id_sub)))
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    if getattr(user, "status", "ACTIVE") != "ACTIVE":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is deactivated")

    if int(getattr(user, "session_version", 1) or 1) != int(sv):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired")

    membership = await db.scalar(
        select(PlatformTenantMember).where(
            PlatformTenantMember.platform_user_id == user.id,
            PlatformTenantMember.tenant_id == tenant.id,
        )
    )
    if not membership:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User not part of tenant")

    if membership.role:
        role = membership.role

    return CurrentUser(user=user, tenant=tenant, role=role, member_id=membership.id if membership else None)
