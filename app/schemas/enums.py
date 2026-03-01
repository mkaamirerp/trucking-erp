"""Enums for onboarding workflow: application status, requests, document requirements.

UI mapping (single status column, different views):
- Applicant "ACTION_REQUIRED" = backend status WAITING_ON_DRIVER (applicant can upload requested docs).
- Applicant "Under review" = SUBMITTED | IN_REVIEW | WAITING_INTERNAL.
- Applicant never sees DRAFT; IN_PROGRESS is the editable state (DRAFT in DB is treated as IN_PROGRESS in UI).
"""
from __future__ import annotations

from enum import Enum


class PersonApplicationStatus(str, Enum):
    """Application status. DRAFT kept for existing DB rows; UI shows IN_PROGRESS for both DRAFT and IN_PROGRESS."""

    DRAFT = "DRAFT"  # Legacy; treat as IN_PROGRESS in applicant UI
    IN_PROGRESS = "IN_PROGRESS"  # Applicant editing (autosave)
    SUBMITTED = "SUBMITTED"  # Applicant locked, in admin queue
    IN_REVIEW = "IN_REVIEW"  # Admin actively reviewing
    WAITING_ON_DRIVER = "WAITING_ON_DRIVER"  # Admin requested docs from applicant (= applicant ACTION_REQUIRED)
    WAITING_INTERNAL = "WAITING_INTERNAL"  # Waiting vendor/internal checks
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class PersonApplicationRequestStatus(str, Enum):
    OPEN = "OPEN"
    UPLOADED = "UPLOADED"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class PersonApplicationRequestType(str, Enum):
    CRIMINAL_RECORD = "CRIMINAL_RECORD"
    DRUG_TEST = "DRUG_TEST"
    MVR = "MVR"
    MEDICAL_CARD = "MEDICAL_CARD"
    EMPLOYMENT_VERIFICATION = "EMPLOYMENT_VERIFICATION"
    OTHER = "OTHER"


class DocumentRequirementScopeType(str, Enum):
    ROLE = "ROLE"
    FORM = "FORM"


class DocumentRequirementVisibility(str, Enum):
    APPLICANT = "APPLICANT"
    ADMIN_ONLY = "ADMIN_ONLY"


class DocumentRequirementStage(str, Enum):
    SUBMIT = "SUBMIT"  # Must exist at submission time
    POST_SUBMIT = "POST_SUBMIT"  # Can be requested later during review
