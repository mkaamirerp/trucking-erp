from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.models.platform import PlatformCompanyProfile, PlatformTenant
from app.deps.auth import CurrentUser, get_current_user

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
    user: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
) -> dict:
    tenant_id = user.tenant_id
    roles = [user.role.upper()] if user.role else []
    try:
        user_id: int | str = int(user.user_id)
    except (TypeError, ValueError):
        user_id = user.user_id

    tenant: PlatformTenant | None = await db.scalar(
        select(PlatformTenant).options(selectinload(PlatformTenant.company_profile)).where(PlatformTenant.id == tenant_id)
    )
    requires_setup, missing_fields, country = _account_setup_missing(tenant)

    company_profile = None
    if tenant and tenant.company_profile:
        p = tenant.company_profile
        company_profile = {
            "legal_name": p.legal_name,
            "address": {
                "street": p.address_street,
                "city": p.address_city,
                "region": p.address_region,
                "postal": p.address_postal,
                "country": p.address_country,
            },
        }

    return {
        "user_id": user_id,
        "tenant_id": tenant_id,
        "roles": roles,
        "requires_account_setup": requires_setup,
        "account_setup_missing": missing_fields,
        "country_code": country,
        "tenant_slug": tenant.slug if tenant else None,
        "company_profile": company_profile,
    }
