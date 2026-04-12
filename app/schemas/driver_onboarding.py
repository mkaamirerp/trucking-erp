# ACTIVE_ONBOARDING_2026Q1
# This module is the current source-of-truth for driver onboarding and review work.

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, EmailStr, Field, ConfigDict, field_validator

from app.core.validators import normalize_phone_number as normalize_phone


class PersonOut(BaseModel):
    """Minimal person record returned on approve (people-first).

    Operational dispatch roster rows are `Driver` entities, created/updated on DRIVER approval.
    """
    id: int
    tenant_id: int
    onboarding_status: str
    first_name: str
    last_name: str
    phone: Optional[str] = None
    email: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


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
    zip_code: Optional[str] = None
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
    person_id: Optional[int] = None
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
    person: PersonOut


# ---- PersonApplication (invite-link) schemas ----

class ApplicantApplicationUpdate(BaseModel):
    """Update person application by invite token."""
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    address_street: Optional[str] = None
    address_city: Optional[str] = None
    address_region: Optional[str] = None
    address_postal: Optional[str] = None
    zip_code: Optional[str] = None
    address_country: Optional[str] = None
    driver_license_number: Optional[str] = None
    license_region: Optional[str] = None
    license_expiry: Optional[date] = None
    notes: Optional[str] = None
    submit: bool = False

    @field_validator("phone")
    @classmethod
    def v_phone(cls, v: Optional[str]) -> Optional[str]:
        return normalize_phone(v)


class ApplicantIntakeRequest(BaseModel):
    """Save or submit intake payload by invite token."""
    intake_payload: dict[str, Any] = Field(default_factory=dict)
    submit: bool = False


class ApplicantApplicationOut(BaseModel):
    """Person application as returned to applicant/admin."""
    id: int
    tenant_id: int
    person_id: Optional[int] = None
    status: str
    source: Optional[str] = None
    application_type: str = "DRIVER"
    requested_role_code: str = "DRIVER"
    reviewed_at: Optional[datetime] = None
    reviewed_by_user_id: Optional[int] = None
    approved_at: Optional[datetime] = None
    approved_by_user_id: Optional[int] = None
    rejection_reason: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    address_street: Optional[str] = None
    address_city: Optional[str] = None
    address_region: Optional[str] = None
    address_postal: Optional[str] = None
    zip_code: Optional[str] = None
    address_country: Optional[str] = None
    driver_license_number: Optional[str] = None
    license_region: Optional[str] = None
    license_expiry: Optional[date] = None
    notes: Optional[str] = None
    submitted_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    intake_payload: Optional[dict[str, Any]] = None

    model_config = ConfigDict(from_attributes=True)


class PersonApplicationListItem(BaseModel):
    """Summary row for person application list."""
    id: int
    tenant_id: int
    status: str
    application_type: str = "DRIVER"
    requested_role_code: str = "DRIVER"
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    submitted_at: Optional[datetime] = None
    source: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PersonApplicationRejectRequest(BaseModel):
    """Payload for rejecting a person application."""
    rejection_reason: str = Field(..., min_length=1)
