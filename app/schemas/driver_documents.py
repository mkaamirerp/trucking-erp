from __future__ import annotations

from datetime import date, datetime
from pydantic import BaseModel, Field


class DriverDocumentCreate(BaseModel):
    driver_id: int
    doc_type: str = Field(..., max_length=50)
    title: str | None = Field(default=None, max_length=255)
    issue_date: date | None = None
    expiry_date: date | None = None
    status: str = Field(default="ACTIVE", max_length=30)
    notes: str | None = None
    is_current: bool = True


class DriverDocumentOut(BaseModel):
    id: int
    driver_id: int
    doc_type: str
    title: str | None
    issue_date: date | None
    expiry_date: date | None
    status: str
    notes: str | None
    is_current: bool

    is_active: bool
    deactivated_at: datetime | None
    deactivated_reason: str | None

    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class DriverDocumentFileOut(BaseModel):
    id: int
    driver_document_id: int
    storage_key: str
    original_filename: str | None
    content_type: str | None
    file_size_bytes: int | None
    sha256: str | None
    is_active: bool
    uploaded_at: datetime

    class Config:
        from_attributes = True
