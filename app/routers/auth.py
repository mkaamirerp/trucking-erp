from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from app.utils.jwt_auth import TokenType, create_access_token, create_refresh_token, decode_token
from app.core.config import settings
from app.deps.auth import get_current_user, CurrentUser
from app.models.platform import PlatformTenant, PlatformTenantMember, PlatformUser
from app.routers.me import _account_setup_missing
from app.core.database import get_db
from app.utils.password import verify_password
from app.deps.tenant import require_tenant
from pydantic import BaseModel, EmailStr

router = APIRouter(prefix="/api/v1/auth", tags=["Auth"])


def _cookie_params(token_type: str) -> dict:
    secure = bool(settings.secure_cookies)
    domain = settings.cookie_domain or (f".{settings.base_domain}" if settings.base_domain else None)
    max_age = settings.jwt_access_minutes * 60 if token_type == TokenType.ACCESS else settings.jwt_refresh_days * 24 * 3600
    base = {
        "httponly": True,
        "secure": secure,
        "samesite": settings.jwt_same_site,
        "domain": domain,
        "max_age": max_age,
    }
    if token_type == TokenType.REFRESH:
        base["path"] = "/api/v1/auth/refresh"
    else:
        base["path"] = "/"
    return base


def _workspace_url(request: Request, slug: str, path_suffix: str = "/dashboard") -> str:
    """
    Build a workspace URL using subdomain pattern: https://{slug}.{base_domain}/{path}
    """
    base_domain = settings.base_domain or request.url.hostname or "localhost"
    scheme = request.url.scheme or "https"
    suffix = path_suffix if path_suffix.startswith("/") else f"/{path_suffix}"
    return f"{scheme}://{slug}.{base_domain}{suffix}"


@router.post("/refresh")
async def refresh(request: Request, response: Response):
    token = request.cookies.get("refresh_token")
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing refresh token")
    payload = decode_token(token, expected_type=TokenType.REFRESH)
    user_id = payload.get("sub")
    tenant_id = payload.get("tenant_id")
    tenant_slug = payload.get("tenant_slug")
    roles = payload.get("roles") or []
    if not user_id or not tenant_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    access = create_access_token(user_id=user_id, tenant_id=tenant_id, tenant_slug=tenant_slug, roles=roles)
    new_refresh = create_refresh_token(user_id=user_id, tenant_id=tenant_id, tenant_slug=tenant_slug, roles=roles)

    response.set_cookie("access_token", access, **_cookie_params(TokenType.ACCESS))
    response.set_cookie("refresh_token", new_refresh, **_cookie_params(TokenType.REFRESH))
    return {"ok": True}


@router.post("/logout")
async def logout(response: Response):
    # Clear cookies
    params_access = _cookie_params(TokenType.ACCESS)
    params_refresh = _cookie_params(TokenType.REFRESH)
    response.set_cookie("access_token", "", max_age=0, expires=0, **params_access)
    response.set_cookie("refresh_token", "", max_age=0, expires=0, **params_refresh)
    return {"ok": True}


@router.get("/me")
async def auth_me(current: CurrentUser = Depends(get_current_user), db=Depends(get_db)):
    tenant = current.tenant
    requires_setup, missing_fields, country = _account_setup_missing(tenant)
    return {
        "user_id": current.user.id,
        "email": current.user.email,
        "first_name": current.user.first_name,
        "last_name": current.user.last_name,
        "tenant_id": tenant.id,
        "tenant_slug": tenant.slug,
        "tenant_name": tenant.name,
        "role": current.role,
        "email_verified": bool(getattr(current.user, "is_email_verified", True)),
        "requires_account_setup": requires_setup,
        "account_setup_missing": missing_fields,
        "country_code": country,
    }


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


@router.post("/login")
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    tenant_id: int = Depends(require_tenant),
    db=Depends(get_db),
):
    user: PlatformUser | None = await db.scalar(select(PlatformUser).where(PlatformUser.email == payload.email.lower()))
    if not user or not user.password_hash or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

    membership: PlatformTenantMember | None = await db.scalar(
        select(PlatformTenantMember).where(
            PlatformTenantMember.platform_user_id == user.id, PlatformTenantMember.tenant_id == tenant_id
        )
    )
    if not membership:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User not part of this workspace")

    tenant: PlatformTenant | None = await db.scalar(
        select(PlatformTenant).options(selectinload(PlatformTenant.company_profile)).where(PlatformTenant.id == tenant_id)
    )
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    if tenant.status != "ACTIVE" or tenant.db_status != "READY":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tenant not ready")

    roles = [membership.role] if membership.role else []
    access = create_access_token(user_id=user.id, tenant_id=tenant.id, tenant_slug=tenant.slug, roles=roles)
    refresh = create_refresh_token(user_id=user.id, tenant_id=tenant.id, tenant_slug=tenant.slug, roles=roles)

    response.set_cookie("access_token", access, **_cookie_params(TokenType.ACCESS))
    response.set_cookie("refresh_token", refresh, **_cookie_params(TokenType.REFRESH))

    workspace_url = _workspace_url(request, tenant.slug, "/dashboard")
    return {"ok": True, "workspace_url": workspace_url}
