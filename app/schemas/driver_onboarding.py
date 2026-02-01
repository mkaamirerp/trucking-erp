from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, EmailStr, Field, ConfigDict, field_validator

from app.core.validators import normalize_phone_number as normalize_phone
from app.schemas.driver import DriverOut


class DriverOnboardingStatus(str, Enum):
    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class DriverOnboardingSubmissionBase(BaseModel):
    first_name: str = Field(..., min_length=1)
    last_name: str = Field(..., min_length=1)
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    address_street: Optional[str] = None
    address_city: Optional[str] = None
    address_region: Optional[str] = None
    address_postal: Optional[str] = None
    address_country: Optional[str] = None
    driver_license_number: Optional[str] = None
    license_region: Optional[str] = None
    license_expiry: Optional[date] = None
    notes: Optional[str] = None

    @field_validator("phone")
    @classmethod
    def v_phone(cls, v: Optional[str]) -> Optional[str]:
        return normalize_phone(v)


class DriverOnboardingSubmissionCreate(DriverOnboardingSubmissionBase):
    submit: bool = False


class DriverOnboardingSubmissionOut(DriverOnboardingSubmissionBase):
    id: int
    tenant_id: int
    created_by_user_id: int
    status: DriverOnboardingStatus
    source: str
    submitted_at: Optional[datetime] = None
    reviewed_at: Optional[datetime] = None
    reviewed_by_user_id: Optional[int] = None
    rejection_reason: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DriverOnboardingCreateResponse(BaseModel):
    submission: DriverOnboardingSubmissionOut
    missing_required_documents: list[str]


class DriverOnboardingRejectRequest(BaseModel):
    rejection_reason: str = Field(..., min_length=1)


class DriverOnboardingApproveResponse(BaseModel):
    submission: DriverOnboardingSubmissionOut
    driver: DriverOut
