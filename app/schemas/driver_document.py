from __future__ import annotations

from datetime import date, datetime
from pydantic import BaseModel, Field


class DriverDocumentBase(BaseModel):
    doc_type: str = Field(..., max_length=50)
    title: str | None = Field(default=None, max_length=255)

    issue_date: date | None = None
    expiry_date: date | None = None

    status: str = Field(default="ACTIVE", max_length=30)
    notes: str | None = None

    is_current: bool = True


class DriverDocumentCreate(DriverDocumentBase):
    pass


class DriverDocumentUpdate(BaseModel):
    # allow partial updates
    title: str | None = Field(default=None, max_length=255)
    issue_date: date | None = None
    expiry_date: date | None = None
    status: str | None = Field(default=None, max_length=30)
    notes: str | None = None
    is_current: bool | None = None


class DriverDocumentOut(DriverDocumentBase):
    id: int
    driver_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
