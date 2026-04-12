"""Response models for workspace PDF parse (hydration only — no persisted load)."""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class LoadParseDocumentMeta(BaseModel):
    filename: str = Field(..., max_length=512)


class LoadParseReferenceItem(BaseModel):
    kind: str = Field(..., max_length=32)
    value: str = Field(..., max_length=120)


class LoadParseStopItem(BaseModel):
    """Normalized stop for workspace DraftStop hydration (types align with LoadStopWrite)."""

    stop_type: str = Field(..., description="pickup | delivery | drop | other")
    sequence: int = Field(..., ge=0)
    facility_name: Optional[str] = None
    street: Optional[str] = None
    city: Optional[str] = None
    state_or_province: Optional[str] = None
    postal_code: Optional[str] = None
    country: Optional[str] = None
    reference_number: Optional[str] = None
    appointment_type: Optional[str] = None
    appointment_date: Optional[str] = Field(
        default=None, description="YYYY-MM-DD when parseable"
    )
    appointment_time_text: Optional[str] = None
    notes: Optional[str] = None


class LoadParseExtractedFields(BaseModel):
    broker_name_snapshot: Optional[str] = None
    broker_contact_name_snapshot: Optional[str] = None
    broker_contact_phone_snapshot: Optional[str] = None
    broker_contact_email_snapshot: Optional[str] = None
    broker_load_reference: Optional[str] = None
    broker_mc_number_snapshot: Optional[str] = None
    broker_dot_number_snapshot: Optional[str] = None
    mode: Optional[str] = None
    equipment_type: Optional[str] = None
    trailer_type: Optional[str] = None
    trailer_size: Optional[str] = None
    commodity: Optional[str] = None
    estimated_weight: Optional[int] = None
    temperature_requirement: Optional[str] = None
    rate: Optional[float] = None
    customer_rate: Optional[float] = None
    miles: Optional[float] = None
    customs_broker_name: Optional[str] = None
    references: list[LoadParseReferenceItem] = Field(default_factory=list)
    stops: list[LoadParseStopItem] = Field(default_factory=list)


class LoadDocumentParseResponse(BaseModel):
    document: LoadParseDocumentMeta
    extracted: LoadParseExtractedFields
    raw_text: str
    warnings: list[str] = Field(default_factory=list)
    field_confidence: dict[str, str] = Field(default_factory=dict)
    context: dict[str, Any] = Field(default_factory=dict)
