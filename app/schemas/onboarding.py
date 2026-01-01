from __future__ import annotations

from datetime import date
from typing import Optional
from pydantic import BaseModel, Field


class DriverLicenseOCRRequest(BaseModel):
    # Placeholder: accept optional references to uploaded files if available later
    file_tokens: Optional[list[str]] = None


class DriverLicenseOCRSuggestion(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    license_number: Optional[str] = None
    license_class: Optional[str] = None
    issue_date: Optional[date] = None
    expiry_date: Optional[date] = None
    issuing_country: Optional[str] = None
    address: Optional[str] = None
    raw_ocr_text: Optional[str] = None


class DriverLicenseOCRResponse(BaseModel):
    suggestions: DriverLicenseOCRSuggestion | dict = Field(default_factory=dict)


class DriverLicenseConfirmRequest(BaseModel):
    driver_id: int
    issuing_country: str = Field(..., max_length=10)
    issuing_region: Optional[str] = Field(default=None, max_length=100)
    license_number: str = Field(..., max_length=100)
    license_class: Optional[str] = Field(default=None, max_length=50)
    license_issue_date: Optional[date] = None
    license_expiry_date: date
    notes: Optional[str] = None
    raw_ocr_text: Optional[str] = None
    file_tokens: Optional[list[str]] = None


class DriverLicenseConfirmResponse(BaseModel):
    driver_id: int
    document_id: int
    doc_type: str
    license_number: Optional[str] = None
    license_class: Optional[str] = None
    license_expiry_date: Optional[date] = None
    issuing_country: Optional[str] = None
