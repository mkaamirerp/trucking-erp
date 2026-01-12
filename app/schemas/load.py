from __future__ import annotations

from datetime import date
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

ALLOWED_STATUSES = {"planned", "assigned", "picked_up", "delivered", "invoiced", "cancelled"}


class LoadBase(BaseModel):
    load_number: str = Field(..., max_length=50)
    broker_id: Optional[int] = None
    driver_id: Optional[int] = None
    pickup_date: Optional[date] = None
    delivery_date: Optional[date] = None
    pickup_location: Optional[str] = Field(default=None, max_length=255)
    delivery_location: Optional[str] = Field(default=None, max_length=255)
    rate: Optional[float] = Field(default=None, ge=0)
    miles: Optional[int] = Field(default=None, ge=0)
    status: str = Field(default="planned", max_length=32)

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
    pickup_date: Optional[date] = None
    delivery_date: Optional[date] = None
    pickup_location: Optional[str] = Field(default=None, max_length=255)
    delivery_location: Optional[str] = Field(default=None, max_length=255)
    rate: Optional[float] = Field(default=None, ge=0)
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


from datetime import datetime


class LoadResponse(LoadBase):
    id: int
    driver: Optional[NestedDriver] = None
    broker: Optional[NestedBroker] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)
