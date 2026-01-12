from __future__ import annotations

import re
from typing import Optional

from pydantic import BaseModel, EmailStr, Field, field_validator, constr


class SlugAvailabilityResponse(BaseModel):
    available: bool
    slug: str
    suggestions: list[str] | None = None


class SignupRequest(BaseModel):
    first_name: constr(min_length=1, max_length=100)
    last_name: constr(min_length=1, max_length=100)
    email: EmailStr
    confirm_email: EmailStr
    phone: Optional[constr(min_length=5, max_length=50)] = None
    company_name: constr(min_length=1, max_length=150)
    slug: constr(min_length=3, max_length=63)
    country: constr(min_length=2, max_length=2)
    password: constr(min_length=10)
    confirm_password: constr(min_length=10)
    plan: str = "trial"
    accept_terms: bool
    is_owner_or_admin: bool

    @field_validator("confirm_email")
    @classmethod
    def emails_match(cls, v: EmailStr, info):
        data = info.data
        if data.get("email") and v != data.get("email"):
            raise ValueError("Emails do not match")
        return v

    @field_validator("confirm_password")
    @classmethod
    def passwords_match(cls, v: str, info):
        data = info.data
        if data.get("password") and v != data.get("password"):
            raise ValueError("Passwords do not match")
        return v

    @field_validator("slug")
    @classmethod
    def slug_format(cls, v: str):
        from app.utils.slug import normalize_slug

        normalized = normalize_slug(v)
        if not re.match(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$", normalized):
            raise ValueError("Slug must contain only lowercase letters, numbers, and hyphens")
        return normalized

    @field_validator("accept_terms")
    @classmethod
    def terms_accepted(cls, v: bool):
        if not v:
            raise ValueError("You must accept the terms and conditions")
        return v

    @field_validator("is_owner_or_admin")
    @classmethod
    def owner_confirmed(cls, v: bool):
        if not v:
            raise ValueError("You must confirm you are authorized to create this workspace")
        return v

    @field_validator("country")
    @classmethod
    def normalize_country(cls, v: str):
        value = v.strip().upper()
        if value not in {"CA", "US"}:
            raise ValueError("Unsupported country (currently only CA/US are supported)")
        return value


class SignupResponse(BaseModel):
    success: bool = True
    message: str
    user_id: str
    tenant_id: int
    email: EmailStr
    debug_otp: str | None = None


class VerifyOTPRequest(BaseModel):
    email: EmailStr
    otp: constr(min_length=4, max_length=10)


class VerifyOTPResponse(BaseModel):
    message: str
    verified: bool
    requires_company_setup: bool
    workspace_url: str
    tenant_id: int | None = None
    slug: str | None = None


class CompanyAddress(BaseModel):
    street: constr(min_length=1, max_length=255)
    city: constr(min_length=1, max_length=100)
    region: constr(min_length=1, max_length=100)
    postal: constr(min_length=1, max_length=20)
    country: constr(min_length=2, max_length=2)

    @field_validator("country")
    @classmethod
    def normalize_country(cls, v: str):
        value = v.strip().upper()
        if value not in {"CA", "US"}:
            raise ValueError("Unsupported country for company address")
        return value


class CompanySetupRequest(BaseModel):
    legal_name: constr(min_length=1, max_length=255)
    address: CompanyAddress
    usdot_number: Optional[str] = None
    mc_number: Optional[str] = None
    cvor_number: Optional[str] = None
    operator_license: Optional[str] = None
    hst_number: Optional[str] = None
    w9_storage_key: Optional[str] = None
    w9_original_filename: Optional[str] = None

    @field_validator("cvor_number")
    @classmethod
    def canada_requires_cvor(cls, v: Optional[str], info):
        addr = info.data.get("address")
        if addr and getattr(addr, "country", "").upper() == "CA" and not v:
            raise ValueError("CVOR number is required for Canadian carriers")
        return v

    @field_validator("usdot_number")
    @classmethod
    def ca_us_requires_usdot(cls, v: Optional[str], info):
        addr = info.data.get("address")
        if addr and addr.country in {"CA", "US"} and not v:
            raise ValueError("USDOT number is required for CA/US carriers")
        return v

    @field_validator("mc_number")
    @classmethod
    def mc_requirements(cls, v: Optional[str], info):
        addr = info.data.get("address")
        country = getattr(addr, "country", "").upper() if addr else ""
        if country == "US" and not v:
            raise ValueError("MC number is required for US carriers")
        return v

    @field_validator("hst_number")
    @classmethod
    def canada_requires_hst(cls, v: Optional[str], info):
        addr = info.data.get("address")
        country = getattr(addr, "country", "").upper() if addr else ""
        if country == "CA" and not v:
            raise ValueError("HST number is required for Canadian carriers")
        return v

    @field_validator("w9_storage_key")
    @classmethod
    def us_requires_w9(cls, v: Optional[str], info):
        addr = info.data.get("address")
        country = getattr(addr, "country", "").upper() if addr else ""
        if country == "US" and not v:
            raise ValueError("W9 upload is required for US carriers")
        return v


class CompanySetupResponse(BaseModel):
    tenant_status: str
    db_status: str | None = None
    dashboard_url: str
