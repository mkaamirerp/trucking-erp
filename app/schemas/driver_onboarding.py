from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, EmailStr, Field, ConfigDict, field_validator

from app.core.validators import normalize_phone_number as normalize_phone


class ExtractionStatus(str, Enum):
    EXTRACTING = "EXTRACTING"
    EXTRACTED = "EXTRACTED"
    EXTRACTION_FAILED = "EXTRACTION_FAILED"


class PersonOut(BaseModel):
    """Minimal person record returned on approve (people-first; no driver row)."""
    id: int
    tenant_id: int
    onboarding_status: str
    first_name: str
    last_name: str
    phone: Optional[str] = None
    email: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class DriverOnboardingStatus(str, Enum):
    """Application status. DRAFT/IN_PROGRESS both mean editable; UI maps DRAFT to IN_PROGRESS for applicant."""

    DRAFT = "DRAFT"
    IN_PROGRESS = "IN_PROGRESS"
    SUBMITTED = "SUBMITTED"
    IN_REVIEW = "IN_REVIEW"
    WAITING_ON_DRIVER = "WAITING_ON_DRIVER"
    WAITING_INTERNAL = "WAITING_INTERNAL"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class DriverOnboardingSubmissionBase(BaseModel):
    first_name: Optional[str] = Field(None, min_length=0)
    last_name: Optional[str] = Field(None, min_length=0)
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
    middle_name: Optional[str] = None

    @field_validator("phone")
    @classmethod
    def v_phone(cls, v: Optional[str]) -> Optional[str]:
        if v is None or (isinstance(v, str) and not v.strip()):
            return None
        return normalize_phone(v)


class DriverOnboardingSubmissionCreate(DriverOnboardingSubmissionBase):
    submit: bool = False


class DriverOnboardingSubmissionOut(DriverOnboardingSubmissionBase):
    id: int
    tenant_id: int
    created_by_user_id: int = 0
    status: DriverOnboardingStatus
    source: str = "driver_portal"
    extraction_status: Optional[str] = None
    extraction_result_json: Optional[Any] = None
    license_uploads_json: Optional[Any] = None
    submitted_at: Optional[datetime] = None
    reviewed_at: Optional[datetime] = None
    reviewed_by_user_id: Optional[int] = None
    rejection_reason: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=False)


class DriverOnboardingCreateResponse(BaseModel):
    submission: DriverOnboardingSubmissionOut
    missing_required_documents: list[str]


class DriverOnboardingRejectRequest(BaseModel):
    rejection_reason: str = Field(..., min_length=1)


class DriverOnboardingApproveResponse(BaseModel):
    submission: DriverOnboardingSubmissionOut
    person: Optional[PersonOut] = None


class LicenseUploadResponse(BaseModel):
    """Response after uploading license file(s); includes extraction_status for polling."""
    submission_id: int
    extraction_status: str
    inputs: dict[str, Any]
    message: str = "License uploaded. Extraction started."
