from __future__ import annotations

import re
from typing import Optional

from pydantic import BaseModel, EmailStr, Field, field_validator, constr


class SlugAvailabilityResponse(BaseModel):
    available: bool
    slug: str
    suggestions: list[str] | None = None
    error: Optional[str] = None


class SignupFieldAvailabilityResponse(BaseModel):
    """Public pre-submit signup checks. Intentionally reveals whether email/phone are already registered (UX)."""

    available: bool
    normalized: str


# ---- Single-step signup (no OTP). Creates workspace, provisions DB, logs user in. ----
# Strict input rules: names required & trimmed, email RFC-valid, phone 7–15 digits, password min 12 (NIST).


def _normalize_phone_digits(value: str) -> str:
    """Strip to digits only; used for length check (E.164-style: 7–15 digits)."""
    return re.sub(r"\D", "", value) if value else ""


class SignupAddress(BaseModel):
    """Company address collected at signup; stored on platform and reused at company-setup."""

    street: str = Field(..., min_length=1, max_length=255)
    city: str = Field(..., min_length=1, max_length=100)
    region: str = Field(..., min_length=1, max_length=100)
    postal: str = Field(..., min_length=1, max_length=20)
    country: str = Field(..., min_length=2, max_length=2)

    @field_validator("country")
    @classmethod
    def normalize_country(cls, v: str):
        value = (v or "").strip().upper()
        if value not in {"CA", "US"}:
            raise ValueError("Country must be US or CA")
        return value


class SignupRequest(BaseModel):
    """Signup: workspace + email + password + name/phone/company/address. Stored on platform; company-setup only adds DOT/MC/CVOR."""

    workspace_slug: str = Field(..., min_length=3, max_length=63, description="URL-safe workspace identifier")
    email: EmailStr
    password: str = Field(..., min_length=12, max_length=256, description="Min 12 characters (NIST recommendation)")
    first_name: str = Field(..., min_length=1, max_length=100, description="Required, non-empty, trimmed")
    last_name: str = Field(..., min_length=1, max_length=100, description="Required, non-empty, trimmed")
    phone: str = Field(..., min_length=1, max_length=30, description="Required; normalized to 7–15 digits (E.164)")
    company_legal_name: str = Field(..., min_length=1, max_length=255, description="Required company/legal name")
    address: SignupAddress

    @field_validator("workspace_slug")
    @classmethod
    def slug_format(cls, v: str):
        from app.utils.slug import normalize_slug

        normalized = normalize_slug(v)
        if not re.match(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$", normalized):
            raise ValueError("Slug must contain only lowercase letters, numbers, and hyphens")
        return normalized

    @field_validator("first_name", "last_name", "company_legal_name")
    @classmethod
    def trim_non_empty(cls, v: str):
        s = (v or "").strip()
        if not s:
            raise ValueError("Required; cannot be empty or whitespace")
        return s

    @field_validator("phone")
    @classmethod
    def phone_digits_7_15(cls, v: str):
        s = (v or "").strip()
        if not s:
            raise ValueError("Phone is required")
        digits = _normalize_phone_digits(s)
        if len(digits) < 7 or len(digits) > 15:
            raise ValueError("Phone must have 7–15 digits (E.164)")
        return s


class SignupResponse(BaseModel):
    """Returned after signup. When requires_otp=True, no tenant/redirect yet; after verify-otp backend sets auth cookie."""

    success: bool = True
    requires_otp: bool = False
    signup_id: str | None = None  # UUID (public_id of onboarding payload); passed to verify-otp / resend-otp
    tenant_slug: str | None = None
    redirect_url: str | None = None


class VerifyOTPRequest(BaseModel):
    email: EmailStr
    otp: constr(min_length=4, max_length=10)
    signup_id: str | None = None  # UUID preferred; fall-back to email-based lookup when absent


class ResendOTPRequest(BaseModel):
    email: EmailStr
    signup_id: str | None = None  # UUID preferred lookup key


class VerifyOTPResponse(BaseModel):
    message: str
    verified: bool
    requires_company_setup: bool
    workspace_url: str
    company_setup_url: str | None = None  # Explicit URL for frontend redirect when setup required
    dashboard_url: str | None = None  # URL when setup already complete
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
    company_phone: Optional[str] = None
    company_email: Optional[str] = None
    usdot_number: Optional[str] = None
    mc_number: Optional[str] = None
    cvor_number: Optional[str] = None
    operator_license: Optional[str] = None
    hst_number: Optional[str] = None
    w9_storage_key: Optional[str] = None
    w9_original_filename: Optional[str] = None

    @field_validator("usdot_number")
    @classmethod
    def usdot_format(cls, v: Optional[str]):
        if not v or not (s := v.strip()):
            return v
        if not re.match(r"^\d{1,8}$", s):
            raise ValueError("USDOT must be 1–8 digits (US)")
        return s

    @field_validator("mc_number")
    @classmethod
    def mc_format(cls, v: Optional[str]):
        if not v or not (s := v.strip()):
            return v
        if not re.match(r"^\d{6,7}$", s):
            raise ValueError("MC must be 6–7 digits (US)")
        return s

    @field_validator("cvor_number")
    @classmethod
    def cvor_format(cls, v: Optional[str]):
        if not v or not (s := v.strip()):
            return v
        if not re.match(r"^\d{9}$", s):
            raise ValueError("CVOR must be exactly 9 digits (CA/ON)")
        return s

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


# ---- Setup prefill (from onboarding payload); read-only at step 3 ----


class SetupPrefillResponse(BaseModel):
    """Prefill from signup payload (read-only). required_remaining_fields = country-driven editable inputs."""

    prefill: dict = Field(..., description="Read-only: company_legal_name, country, owner email, address from step 1")
    required_remaining_fields: list[str] = Field(..., description="Country-driven: address, usdot_number, mc_number, cvor_number, etc.")
    country: Optional[str] = None
