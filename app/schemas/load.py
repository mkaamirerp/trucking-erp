"""Load schemas with dispatch status model (LOCKED)."""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

DISPATCH_STATUSES = {
    "unassigned", "assigned", "dispatched", "arrived_pickup", "in_transit",
    "arrived_delivery", "delivered", "issue_hold",
}
ALLOWED_STATUSES = DISPATCH_STATUSES


class LoadBase(BaseModel):
    load_number: str = Field(..., max_length=50)
    broker_id: Optional[int] = None
    driver_id: Optional[int] = None
    truck_id: Optional[int] = None
    trailer_id: Optional[int] = None
    pickup_date: Optional[date] = None
    delivery_date: Optional[date] = None
    pickup_time: Optional[datetime] = None
    delivery_time: Optional[datetime] = None
    pickup_location: Optional[str] = Field(default=None, max_length=255)
    delivery_location: Optional[str] = Field(default=None, max_length=255)
    equipment_type: Optional[str] = Field(default=None, max_length=50)
    rate: Optional[float] = Field(default=None, ge=0)
    customer_rate: Optional[float] = Field(default=None, ge=0)
    miles: Optional[int] = Field(default=None, ge=0)
    status: str = Field(default="unassigned", max_length=32)

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        v = v.strip().lower()
        if v not in ALLOWED_STATUSES:
            raise ValueError(f"Status must be one of {', '.join(sorted(ALLOWED_STATUSES))}")
        return v


class LoadCreate(LoadBase):
    pass


class LoadUpdate(BaseModel):
    load_number: Optional[str] = Field(default=None, max_length=50)
    broker_id: Optional[int] = None
    driver_id: Optional[int] = None
    truck_id: Optional[int] = None
    trailer_id: Optional[int] = None
    pickup_date: Optional[date] = None
    delivery_date: Optional[date] = None
    pickup_time: Optional[datetime] = None
    delivery_time: Optional[datetime] = None
    pickup_location: Optional[str] = Field(default=None, max_length=255)
    delivery_location: Optional[str] = Field(default=None, max_length=255)
    equipment_type: Optional[str] = Field(default=None, max_length=50)
    rate: Optional[float] = Field(default=None, ge=0)
    customer_rate: Optional[float] = Field(default=None, ge=0)
    miles: Optional[int] = Field(default=None, ge=0)
    status: Optional[str] = Field(default=None, max_length=32)

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


class LoadResponse(LoadBase):
    id: int
    driver: Optional[NestedDriver] = None
    broker: Optional[NestedBroker] = None
    truck: Optional[NestedTruck] = None
    trailer: Optional[NestedTrailer] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    model_config = ConfigDict(from_attributes=True)
