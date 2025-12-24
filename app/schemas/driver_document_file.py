from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel, Field


class DriverDocumentFileBase(BaseModel):
    storage_key: str = Field(..., max_length=1024)
    original_filename: str | None = Field(default=None, max_length=255)
    content_type: str | None = Field(default=None, max_length=100)

    file_size_bytes: int | None = None
    sha256: str | None = Field(default=None, max_length=64)

    is_active: bool = True


class DriverDocumentFileCreate(DriverDocumentFileBase):
    pass


class DriverDocumentFileOut(DriverDocumentFileBase):
    id: int
    driver_document_id: int
    uploaded_at: datetime

    class Config:
        from_attributes = True
