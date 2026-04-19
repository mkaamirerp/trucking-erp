"""
GET   /api/v1/me               — current user identity + theme
PATCH /api/v1/me/preferences   — update per-user preferences (theme)
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select

from app.core.database import get_db
from app.deps.auth import CurrentUser, get_current_user
from app.deps.tenant_db import open_tenant_session_by_id
from app.models.platform import PlatformCompanyProfile, PlatformTenant, PlatformUser
from app.models.tenant_auth import TenantUser
from app.services.tenant_auth_constants import tenant_uses_tenant_db_auth

router = APIRouter(prefix="/api/v1", tags=["Auth"])

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VALID_THEMES: frozenset[str] = frozenset({"dark", "dark-blue"})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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
        return True, ["company_profile"], country

    def _require(label: str, value: str | None) -> None:
        if not value or not str(value).strip():
            missing.append(label)

    address_fields = [
        profile.address_street,
        profile.address_city,
        profile.address_region,
        profile.address_postal,
        profile.address_country,
    ]
    if not all(address_fields):
        missing.append("company_address")

    if country == "US":
        _require("mc_number", profile.mc_number)
        _require("usdot_number", profile.usdot_number)
        _require("w9_upload", profile.w9_storage_key)
    elif country == "CA":
        _require("cvor_number", profile.cvor_number)
        _require("hst_number", profile.hst_number)

    requires_setup = bool(missing)
    return requires_setup, missing, country


def _resolve_theme(current: CurrentUser) -> str:
    """Return the active theme for the current user, falling back to 'dark'."""
    if current.tenant_user is not None:
        return current.tenant_user.theme or "dark"
    return current.user.theme or "dark"


# ---------------------------------------------------------------------------
# GET /api/v1/me
# ---------------------------------------------------------------------------

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
        select(PlatformTenant)
        .options()
        .where(PlatformTenant.id == tenant_id)
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
        "theme": _resolve_theme(user),
    }


# ---------------------------------------------------------------------------
# PATCH /api/v1/me/preferences
# ---------------------------------------------------------------------------

class PreferencesPatchIn(BaseModel):
    theme: str


@router.patch("/me/preferences")
async def patch_me_preferences(
    body: PreferencesPatchIn,
    current: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
) -> dict:
    if body.theme not in VALID_THEMES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid theme '{body.theme}'. Valid values: {sorted(VALID_THEMES)}",
        )

    mode = getattr(current.tenant, "tenant_auth_mode", None) or "platform"

    if tenant_uses_tenant_db_auth(mode) and current.tenant_user is not None:
        # Tenant-auth-mode: theme lives on TenantUser in the tenant DB.
        # Re-fetch within a writable session — the tenant_user on CurrentUser
        # was loaded in a separate session inside get_current_user.
        async for tdb in open_tenant_session_by_id(current.tenant_id):
            tu = await tdb.scalar(
                select(TenantUser).where(
                    TenantUser.tenant_id == current.tenant_id,
                    TenantUser.id == int(current.tenant_user.id),
                )
            )
            if not tu:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="User not found",
                )
            tu.theme = body.theme
            await tdb.commit()
            break
    else:
        # Platform-auth-mode: theme lives on PlatformUser in the platform DB.
        puser = await db.scalar(
            select(PlatformUser).where(PlatformUser.id == str(current.user.id))
        )
        if not puser:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
            )
        puser.theme = body.theme
        await db.commit()

    return {"theme": body.theme}
