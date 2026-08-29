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
    """Update person application by invite token.

    CDL/license fields are persisted only for DRIVER workflow applications.
    """
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


class PersonApplicationReviewPatch(BaseModel):
    """Admin corrections during review (SUBMITTED/APPROVED). Does not replace files or agreement flags."""

    first_name: Optional[str] = Field(None, max_length=100)
    last_name: Optional[str] = Field(None, max_length=100)
    phone: Optional[str] = None
    email: Optional[str] = Field(None, max_length=255)
    address_street: Optional[str] = None
    address_city: Optional[str] = Field(None, max_length=100)
    address_region: Optional[str] = Field(None, max_length=100)
    address_postal: Optional[str] = Field(None, max_length=20)
    zip_code: Optional[str] = Field(None, max_length=20)
    address_country: Optional[str] = Field(None, max_length=10)
    notes: Optional[str] = None
    driver_license_number: Optional[str] = Field(None, max_length=100)
    license_region: Optional[str] = Field(None, max_length=100)
    license_expiry: Optional[date] = None
    middle_name: Optional[str] = Field(None, max_length=100)
    date_of_birth: Optional[date] = None
    license_issue_date: Optional[date] = None
    cdl_class: Optional[str] = Field(None, max_length=20)
    endorsements: Optional[str] = None
    restrictions: Optional[str] = None
    conditions: Optional[str] = None

    model_config = ConfigDict(extra="forbid")

    @field_validator("phone")
    @classmethod
    def v_phone(cls, v: Optional[str]) -> Optional[str]:
        return normalize_phone(v)


class ApplicantApplicationOut(BaseModel):
    """Person application as returned to applicant/admin."""
    id: int
    tenant_id: int
    person_id: Optional[int] = None
    status: str
    source: Optional[str] = None
    application_type: str = Field(
        default="DRIVER",
        description="Workflow key: which applicant form/steps run (e.g. DRIVER vs DISPATCHER).",
    )
    requested_role_code: str = Field(
        default="DRIVER",
        description="Role assigned on admin approval (MVP default often matches application_type; distinct column).",
    )
    reviewed_at: Optional[datetime] = None
    reviewed_by_user_id: Optional[int] = None
    approved_at: Optional[datetime] = None
    approved_by_user_id: Optional[int] = None
    onboarded_at: Optional[datetime] = None
    onboarded_by_user_id: Optional[int] = None
    setup_status: str = Field(
        default="pending",
        description="People-level setup lifecycle: pending | pending_downstream | complete (distinct from application status).",
    )
    current_workflow_lane: str = Field(
        default="processing",
        description="Queue routing: submitted | processing | hr_payroll | complete | rejected (distinct from status/setup_status).",
    )
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
    #: Admin-only: frozen applicant intake at submit (omit on applicant-facing responses if unset).
    intake_submitted_snapshot: Optional[dict[str, Any]] = None
    #: Admin-only: audit entries for review edits.
    intake_review_audit: Optional[list[dict[str, Any]]] = None
    #: True when the applicant request used a document-resume token (post-submit uploads).
    document_resume_active: bool = False

    model_config = ConfigDict(from_attributes=True)


class PersonApplicationDocumentRequest(BaseModel):
    doc_types: list[str] = Field(..., min_length=1, description="Keys matching step-4 document types")
    subject: str = Field(..., min_length=1, max_length=500)
    body: str = Field(..., min_length=1, max_length=16000)


class PersonApplicationDocumentRequestResponse(BaseModel):
    email_sent: bool
    email_error: str | None = None


class DlCaptureSessionOut(BaseModel):
    """Public DL capture resume state. Progress derived from application files only."""

    step: str = Field(description="FRONT | BACK | COMPLETE")
    front_status: str = Field(description="MISSING | FAILED | PROCESSED")
    back_status: str = Field(description="MISSING | FAILED | PROCESSED")
    front_preview_file_id: str | None = None
    back_preview_file_id: str | None = None
    message: str | None = None


class DlCaptureLinkResponse(BaseModel):
    application_id: int
    token: str
    link: str
    expires_at: datetime


class PersonApplicationDocumentAcceptBody(BaseModel):
    doc_type: str = Field(..., min_length=1, max_length=64)
    accepted: bool = Field(..., description="True = admin accepted; False = clear acceptance")


class PersonApplicationListItem(BaseModel):
    """Summary row for person application list."""
    id: int
    tenant_id: int
    status: str
    setup_status: str = Field(
        default="pending",
        description="People-level onboarding setup state (pending | pending_downstream | complete).",
    )
    current_workflow_lane: str = Field(
        default="processing",
        description="Admin queue bucket key: submitted | processing | hr_payroll | complete | rejected.",
    )
    application_type: str = Field(default="DRIVER", description="Applicant workflow (form) key.")
    requested_role_code: str = Field(default="DRIVER", description="Role to assign when approved.")
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    submitted_at: Optional[datetime] = None
    source: Optional[str] = None
    created_at: datetime
    reviewed_at: Optional[datetime] = Field(
        default=None,
        description="First admin engagement (detail open / review started). Used to split Submitted vs Processing on the admin queue.",
    )

    model_config = ConfigDict(from_attributes=True)


class PersonApplicationRejectRequest(BaseModel):
    """Payload for rejecting a person application."""
    rejection_reason: str = Field(..., min_length=1)
