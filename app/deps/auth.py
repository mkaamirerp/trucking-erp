from __future__ import annotations

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.platform import PlatformTenant, PlatformTenantMember, PlatformUser
from app.utils.jwt_auth import decode_token, get_token_from_request, TokenType


class CurrentUser:
    def __init__(self, user: PlatformUser, tenant: PlatformTenant, role: str | None, member_id: int | None):
        self.user = user
        self.tenant = tenant
        self.role = role
        self.member_id = member_id

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
    user_id = payload.get("sub")
    jwt_tenant_id = payload.get("tenant_id")
    roles = payload.get("roles") or []
    role = roles[0] if roles else None

    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token claims")

    # Use tenant from request (URL/subdomain) when set by middleware; else JWT tenant
    tenant_id = getattr(request.state, "tenant_id", None)
    if tenant_id is None and jwt_tenant_id is not None:
        tenant_id = int(jwt_tenant_id)
    if tenant_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Tenant context required")

    user = await db.scalar(select(PlatformUser).where(PlatformUser.id == str(user_id)))
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    tenant = await db.scalar(
        select(PlatformTenant).options(selectinload(PlatformTenant.company_profile)).where(PlatformTenant.id == int(tenant_id))
    )
    if not tenant:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Tenant not found")

    membership = await db.scalar(
        select(PlatformTenantMember).where(
            PlatformTenantMember.platform_user_id == user.id, PlatformTenantMember.tenant_id == tenant.id
        )
    )
    if not membership:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User not part of tenant")

    # Override role from membership if available
    if membership.role:
        role = membership.role

    return CurrentUser(user=user, tenant=tenant, role=role, member_id=membership.id if membership else None)
