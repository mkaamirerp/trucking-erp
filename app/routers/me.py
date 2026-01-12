from __future__ import annotations

from fastapi import APIRouter, Depends, Header, Request, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.models.platform import PlatformCompanyProfile, PlatformTenant
from app.deps.tenant import require_tenant

router = APIRouter(prefix="/api/v1", tags=["Auth"])


def _account_setup_missing(tenant: PlatformTenant | None) -> tuple[bool, list[str], str | None]:
    """
    Returns (requires_setup, missing_fields, country_code)
    """
    if not tenant:
        return True, ["tenant_not_found"], None

    profile: PlatformCompanyProfile | None = tenant.company_profile
    country = (tenant.country_code or "").upper() or None

    missing: list[str] = []
    if not profile:
        # If no profile exists yet, require everything
        return True, ["company_profile"], country

    def _require(label: str, value: str | None) -> None:
        if not value or not str(value).strip():
            missing.append(label)

    # Address fields
    address_fields = [
        profile.address_street,
        profile.address_city,
        profile.address_region,
        profile.address_postal,
        profile.address_country,
    ]
    if not all(address_fields):
        missing.append("company_address")

    # Country-specific requirements
    if country == "US":
        _require("mc_number", profile.mc_number)
        _require("usdot_number", profile.usdot_number)
        _require("w9_upload", profile.w9_storage_key)
    elif country == "CA":
        _require("cvor_number", profile.cvor_number)
        _require("hst_number", profile.hst_number)

    requires_setup = bool(missing)
    return requires_setup, missing, country


@router.get("/me")
async def get_me(
    request: Request,
    x_tenant_roles: str | None = Header(None),
    x_user_id: str | None = Header(None),
    tenant_id: int = Depends(require_tenant),
    db=Depends(get_db),
) -> dict:
    roles = []
    user_id: int | None = None
    # Prefer values set by middleware (JWT)
    if hasattr(request.state, "roles"):
        roles = [r.upper() for r in getattr(request.state, "roles") or []]
    elif x_tenant_roles:
        roles = [r.strip().upper() for r in (x_tenant_roles or "").split(",") if r.strip()]

    if hasattr(request.state, "user_id"):
        try:
            # UUIDs allowed; keep as string if not int
            user_id = int(getattr(request.state, "user_id"))
        except (TypeError, ValueError):
            user_id = getattr(request.state, "user_id")
    elif x_user_id:
        try:
            user_id = int(x_user_id)
        except ValueError:
            user_id = x_user_id

    if user_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    tenant: PlatformTenant | None = await db.scalar(
        select(PlatformTenant).options(selectinload(PlatformTenant.company_profile)).where(PlatformTenant.id == tenant_id)
    )
    requires_setup, missing_fields, country = _account_setup_missing(tenant)

    return {
        "user_id": user_id,
        "tenant_id": tenant_id,
        "roles": roles,
        "requires_account_setup": requires_setup,
        "account_setup_missing": missing_fields,
        "country_code": country,
        "tenant_slug": tenant.slug if tenant else None,
    }
