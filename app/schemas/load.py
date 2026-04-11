"""Load schemas. V1: draft, ready; operational: unassigned, assigned, dispatched, etc."""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional, Sequence

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.broker import BrokerContactOut
from app.schemas.customs_broker import CustomsBrokerSummary, LoadCustomsSnapshotOut

DISPATCH_STATUSES = {
    "draft", "ready",
    "unassigned", "assigned", "dispatched", "arrived_pickup", "in_transit",
    "arrived_delivery", "delivered", "issue_hold",
}
ALLOWED_STATUSES = DISPATCH_STATUSES


# --- LoadStop ---

class LoadStopBase(BaseModel):
    stop_type: str = Field(..., max_length=20)
    sequence: int = Field(default=0, ge=0)
    facility_name: Optional[str] = Field(default=None, max_length=255)
    street: Optional[str] = Field(default=None, max_length=255)
    city: Optional[str] = Field(default=None, max_length=100)
    state_or_province: Optional[str] = Field(default=None, max_length=50)
    postal_code: Optional[str] = Field(default=None, max_length=20)
    country: Optional[str] = Field(default=None, max_length=2)
    reference_number: Optional[str] = Field(default=None, max_length=100)
    appointment_type: Optional[str] = Field(default=None, max_length=50)
    appointment_date: Optional[date] = None
    appointment_time_text: Optional[str] = Field(default=None, max_length=50)
    notes: Optional[str] = None
    commodity_notes: Optional[str] = None


class LoadStopCreate(LoadStopBase):
    pass


class LoadStopUpdate(BaseModel):
    stop_type: Optional[str] = Field(default=None, max_length=20)
    sequence: Optional[int] = Field(default=None, ge=0)
    facility_name: Optional[str] = Field(default=None, max_length=255)
    street: Optional[str] = Field(default=None, max_length=255)
    city: Optional[str] = Field(default=None, max_length=100)
    state_or_province: Optional[str] = Field(default=None, max_length=50)
    postal_code: Optional[str] = Field(default=None, max_length=20)
    country: Optional[str] = Field(default=None, max_length=2)
    reference_number: Optional[str] = Field(default=None, max_length=100)
    appointment_type: Optional[str] = Field(default=None, max_length=50)
    appointment_date: Optional[date] = None
    appointment_time_text: Optional[str] = Field(default=None, max_length=50)
    notes: Optional[str] = None
    commodity_notes: Optional[str] = None


class LoadStopOut(LoadStopBase):
    id: int
    load_id: int
    scheduled_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    model_config = ConfigDict(from_attributes=True)


# --- Load ---

class LoadBase(BaseModel):
    load_number: Optional[str] = Field(default=None, max_length=50)
    customs_broker_id: Optional[int] = None
    broker_id: Optional[int] = None
    broker_contact_id: Optional[int] = None
    broker_name_snapshot: Optional[str] = Field(default=None, max_length=255)
    broker_contact_name_snapshot: Optional[str] = Field(default=None, max_length=255)
    broker_contact_phone_snapshot: Optional[str] = Field(default=None, max_length=50)
    broker_contact_extension_snapshot: Optional[str] = Field(default=None, max_length=20)
    broker_contact_email_snapshot: Optional[str] = Field(default=None, max_length=255)
    broker_load_reference: Optional[str] = Field(default=None, max_length=100)
    driver_id: Optional[int] = None
    truck_id: Optional[int] = None
    trailer_id: Optional[int] = None
    mode: Optional[str] = Field(default=None, max_length=50)
    equipment_type: Optional[str] = Field(default=None, max_length=50)
    trailer_type: Optional[str] = Field(default=None, max_length=50)
    trailer_size: Optional[str] = Field(default=None, max_length=20)
    commodity: Optional[str] = Field(default=None, max_length=255)
    estimated_weight: Optional[int] = Field(default=None, ge=0)
    hazmat_flag: Optional[bool] = False
    temperature_requirement: Optional[str] = Field(default=None, max_length=50)
    pallet_case_count: Optional[str] = Field(default=None, max_length=50)
    internal_notes: Optional[str] = None
    rate: Optional[float] = Field(default=None, ge=0)
    customer_rate: Optional[float] = Field(default=None, ge=0)
    miles: Optional[int] = Field(default=None, ge=0)
    status: str = Field(default="draft", max_length=32)

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        v = v.strip().lower()
        if v not in ALLOWED_STATUSES:
            raise ValueError(f"Status must be one of {', '.join(sorted(ALLOWED_STATUSES))}")
        return v


class LoadCreate(LoadBase):
    stops: Optional[Sequence[LoadStopCreate]] = None

    @model_validator(mode="before")
    @classmethod
    def reject_read_only_trip_fields(cls, data):
        if isinstance(data, dict):
            for k in ("trip_number", "active_dispatch_trip_id"):
                if k in data:
                    raise ValueError(f"{k} is read-only (set by dispatch trip allocation)")
        return data


class LoadUpdate(BaseModel):
    """PATCH body: must include the version the client last read (optimistic concurrency)."""

    expected_concurrency_version: int = Field(..., ge=1, description="Version from last GET; required for CAS write.")
    load_number: Optional[str] = Field(default=None, max_length=50)
    customs_broker_id: Optional[int] = None
    broker_id: Optional[int] = None
    broker_contact_id: Optional[int] = None
    broker_name_snapshot: Optional[str] = Field(default=None, max_length=255)
    broker_contact_name_snapshot: Optional[str] = Field(default=None, max_length=255)
    broker_contact_phone_snapshot: Optional[str] = Field(default=None, max_length=50)
    broker_contact_extension_snapshot: Optional[str] = Field(default=None, max_length=20)
    broker_contact_email_snapshot: Optional[str] = Field(default=None, max_length=255)
    broker_load_reference: Optional[str] = Field(default=None, max_length=100)
    driver_id: Optional[int] = None
    truck_id: Optional[int] = None
    trailer_id: Optional[int] = None
    mode: Optional[str] = Field(default=None, max_length=50)
    equipment_type: Optional[str] = Field(default=None, max_length=50)
    trailer_type: Optional[str] = Field(default=None, max_length=50)
    trailer_size: Optional[str] = Field(default=None, max_length=20)
    commodity: Optional[str] = Field(default=None, max_length=255)
    estimated_weight: Optional[int] = Field(default=None, ge=0)
    hazmat_flag: Optional[bool] = None
    temperature_requirement: Optional[str] = Field(default=None, max_length=50)
    pallet_case_count: Optional[str] = Field(default=None, max_length=50)
    internal_notes: Optional[str] = None
    rate: Optional[float] = Field(default=None, ge=0)
    customer_rate: Optional[float] = Field(default=None, ge=0)
    miles: Optional[int] = Field(default=None, ge=0)
    status: Optional[str] = Field(default=None, max_length=32)
    stops: Optional[Sequence[LoadStopCreate]] = None

    @model_validator(mode="before")
    @classmethod
    def reject_read_only_trip_fields(cls, data):
        if isinstance(data, dict):
            for k in ("trip_number", "active_dispatch_trip_id"):
                if k in data:
                    raise ValueError(f"{k} is read-only (set by dispatch trip allocation)")
        return data

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.strip().lower()
        if v not in ALLOWED_STATUSES:
            raise ValueError(f"Status must be one of {', '.join(sorted(ALLOWED_STATUSES))}")
        return v


class NestedDriver(BaseModel):
    id: int
    first_name: str
    last_name: str
    phone: Optional[str] = None
    email: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)


class NestedBroker(BaseModel):
    id: int
    name: str
    model_config = ConfigDict(from_attributes=True)


class NestedTruck(BaseModel):
    id: int
    unit_number: str
    model_config = ConfigDict(from_attributes=True)


class NestedTrailer(BaseModel):
    id: int
    unit_number: str
    trailer_type: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)


class LoadNoteCreate(BaseModel):
    body: str = Field(..., min_length=1, max_length=5000)


class LoadNoteOut(BaseModel):
    id: int
    body: str
    author_user_id: Optional[str] = None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class LoadMutationConcurrencyBody(BaseModel):
    """POST bodies for load endpoints that mutate the row without a full LoadUpdate."""

    expected_concurrency_version: int = Field(..., ge=1)


class LoadResponse(LoadBase):
    id: int
    concurrency_version: int = 1
    trip_number: Optional[str] = None
    active_dispatch_trip_id: Optional[int] = None
    broker_match_method: Optional[str] = Field(default=None, max_length=32)
    broker_match_confidence_tier: Optional[str] = Field(default=None, max_length=8)
    broker_match_explanation: Optional[str] = None
    review_required: bool = False
    is_duplicate_of_load_id: Optional[int] = None
    driver: Optional[NestedDriver] = None
    broker: Optional[NestedBroker] = None
    broker_contact: Optional[BrokerContactOut] = None
    customs_broker: Optional[CustomsBrokerSummary] = None
    document_snapshot_confirmed_at: Optional[datetime] = None
    document_snapshot_confirmed_by_user_id: Optional[str] = None
    document_snapshot_version: int = 0
    customs_snapshot: Optional[LoadCustomsSnapshotOut] = None
    truck: Optional[NestedTruck] = None
    trailer: Optional[NestedTrailer] = None
    stops: Optional[list[LoadStopOut]] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    model_config = ConfigDict(from_attributes=True)
