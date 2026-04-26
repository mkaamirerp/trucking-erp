"""Platform-sanitized extraction pattern API (no tenant document values)."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class PlatformExtractionSanitizedPatternOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime
    is_active: bool
    broker_family_key: str
    field_path: str
    source_label_pattern: str
    source_section_pattern: str
    value_shape_class: str
    section_role: str
    positive_count: int
    negative_count: int
    confidence: float | None
    maturity: str
    notes: str | None = None


class PlatformExtractionSanitizedPatternUpsertIn(BaseModel):
    broker_family_key: str = Field(..., min_length=1, max_length=120)
    field_path: str = Field(..., min_length=1, max_length=250)
    source_label_pattern: str = Field(..., min_length=1, max_length=250)
    source_section_pattern: str = Field(default="", max_length=250)
    value_shape_class: str = Field(..., min_length=1, max_length=64)
    section_role: str = Field(default="unknown", max_length=64)
    positive_count: int = Field(default=0, ge=0)
    negative_count: int = Field(default=0, ge=0)
    maturity: str = Field(default="observation", max_length=32)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    notes: Optional[str] = Field(default=None, max_length=2000)
    is_active: bool = True
