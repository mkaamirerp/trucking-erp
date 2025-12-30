from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field


class SignupRequest(BaseModel):
    company_name: str = Field(..., min_length=2, max_length=200)
    email: EmailStr
    admin_first_name: str = Field(..., min_length=1, max_length=100)
    admin_last_name: str = Field(..., min_length=1, max_length=100)
    country: str = Field(..., min_length=2, max_length=2, description="ISO2 country code")
    phone: str | None = Field(None, max_length=50)
    timezone: str | None = Field(default="America/Toronto", max_length=100)
    plan_code: str | None = Field(default="trial", max_length=50)


class SignupResponse(BaseModel):
    tenant_slug: str
    verification_required: bool = True
    verification_token: str | None = None
    message: str = "Signup successful. Please verify your email."


class VerifyRequest(BaseModel):
    token: str


class VerifyResponse(BaseModel):
    message: str
    verified: bool
