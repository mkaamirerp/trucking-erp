"""Pydantic schemas for truck create/update/response with validation."""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

TRUCK_STATUSES = {"active", "inactive", "in_shop", "retired"}
OWNERSHIP_TYPES = {"company", "owner_operator", "leased"}
FUEL_TYPES = {"diesel", "gas", "cng", "electric"}
TRANSMISSION_TYPES = {"manual", "automatic", "automated_manual"}


def _normalize_vin(v: str | None) -> str | None:
    if v is None:
        return None
    return v.strip().upper() if v.strip() else None


def _normalize_unit_number(v: str | None) -> str | None:
    if v is None:
        return None
    return v.strip() if v.strip() else None


class TruckBase(BaseModel):
    unit_number: str = Field(..., max_length=50)
    vin: str = Field(..., max_length=50)
    year: Optional[int] = Field(default=None, ge=1900, le=2100)
    make: Optional[str] = Field(default=None, max_length=100)
    model: Optional[str] = Field(default=None, max_length=100)
    color: Optional[str] = Field(default=None, max_length=50)
    plate_number: Optional[str] = Field(default=None, max_length=50)
    plate_region: Optional[str] = Field(default=None, max_length=20)
    ownership_type: str = Field(default="company", max_length=30)
    owner_person_id: Optional[int] = None
    purchase_date: Optional[date] = None
    purchase_price: Optional[float] = Field(default=None, ge=0)
    engine_make: Optional[str] = Field(default=None, max_length=100)
    engine_model: Optional[str] = Field(default=None, max_length=100)
    engine_serial: Optional[str] = Field(default=None, max_length=100)
    horsepower: Optional[int] = Field(default=None, gt=0)
    fuel_type: Optional[str] = Field(default=None, max_length=30)
    transmission: Optional[str] = Field(default=None, max_length=30)
    num_axles: Optional[int] = Field(default=None, gt=0)
    gvwr_lbs: Optional[int] = Field(default=None, gt=0)
    odometer_at_purchase: Optional[int] = Field(default=None, ge=0)
    current_odometer: Optional[int] = Field(default=None, ge=0)
    odometer_last_updated: Optional[datetime] = None
    insurance_carrier: Optional[str] = Field(default=None, max_length=255)
    insurance_policy_number: Optional[str] = Field(default=None, max_length=100)
    insurance_expiry: Optional[date] = None
    status: str = Field(default="active", max_length=30)
    notes: Optional[str] = Field(default=None, max_length=5000)

    @field_validator("vin", "unit_number", mode="before")
    @classmethod
    def normalize_strings(cls, v: str | None, info) -> str | None:
        if v is None or not isinstance(v, str):
            return v
        if info.field_name == "vin":
            return (v or "").strip().upper()
        return (v or "").strip()

    @field_validator("ownership_type")
    @classmethod
    def validate_ownership_type(cls, v: str) -> str:
        v = v.strip().lower()
        if v not in OWNERSHIP_TYPES:
            raise ValueError(f"ownership_type must be one of {', '.join(sorted(OWNERSHIP_TYPES))}")
        return v

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        v = v.strip().lower()
        if v not in TRUCK_STATUSES:
            raise ValueError(f"status must be one of {', '.join(sorted(TRUCK_STATUSES))}")
        return v

    @field_validator("fuel_type")
    @classmethod
    def validate_fuel_type(cls, v: Optional[str]) -> Optional[str]:
        if v is None or not v.strip():
            return None
        v = v.strip().lower()
        if v not in FUEL_TYPES:
            raise ValueError(f"fuel_type must be one of {', '.join(sorted(FUEL_TYPES))}")
        return v

    @field_validator("transmission")
    @classmethod
    def validate_transmission(cls, v: Optional[str]) -> Optional[str]:
        if v is None or not v.strip():
            return None
        v = v.strip().lower()
        if v not in TRANSMISSION_TYPES:
            raise ValueError(f"transmission must be one of {', '.join(sorted(TRANSMISSION_TYPES))}")
        return v

    @model_validator(mode="after")
    def odometer_last_updated_requires_current(self):
        if self.odometer_last_updated is not None and self.current_odometer is None:
            raise ValueError("odometer_last_updated requires current_odometer")
        return self


class TruckCreate(TruckBase):
    @field_validator("vin")
    @classmethod
    def vin_required(cls, v: str) -> str:
        n = (v or "").strip().upper()
        if not n:
            raise ValueError("vin is required")
        return n

    @field_validator("unit_number")
    @classmethod
    def unit_number_required(cls, v: str) -> str:
        n = (v or "").strip()
        if not n:
            raise ValueError("unit_number is required")
        return n


class TruckUpdate(BaseModel):
    unit_number: Optional[str] = Field(default=None, max_length=50)
    vin: Optional[str] = Field(default=None, max_length=50)
    year: Optional[int] = Field(default=None, ge=1900, le=2100)
    make: Optional[str] = Field(default=None, max_length=100)
    model: Optional[str] = Field(default=None, max_length=100)
    color: Optional[str] = Field(default=None, max_length=50)
    plate_number: Optional[str] = Field(default=None, max_length=50)
    plate_region: Optional[str] = Field(default=None, max_length=20)
    ownership_type: Optional[str] = Field(default=None, max_length=30)
    owner_person_id: Optional[int] = None
    purchase_date: Optional[date] = None
    purchase_price: Optional[float] = Field(default=None, ge=0)
    engine_make: Optional[str] = Field(default=None, max_length=100)
    engine_model: Optional[str] = Field(default=None, max_length=100)
    engine_serial: Optional[str] = Field(default=None, max_length=100)
    horsepower: Optional[int] = Field(default=None, gt=0)
    fuel_type: Optional[str] = Field(default=None, max_length=30)
    transmission: Optional[str] = Field(default=None, max_length=30)
    num_axles: Optional[int] = Field(default=None, gt=0)
    gvwr_lbs: Optional[int] = Field(default=None, gt=0)
    odometer_at_purchase: Optional[int] = Field(default=None, ge=0)
    current_odometer: Optional[int] = Field(default=None, ge=0)
    odometer_last_updated: Optional[datetime] = None
    insurance_carrier: Optional[str] = Field(default=None, max_length=255)
    insurance_policy_number: Optional[str] = Field(default=None, max_length=100)
    insurance_expiry: Optional[date] = None
    status: Optional[str] = Field(default=None, max_length=30)
    notes: Optional[str] = Field(default=None, max_length=5000)

    @field_validator("vin", "unit_number", mode="before")
    @classmethod
    def normalize_strings(cls, v: str | None, info) -> str | None:
        if v is None or not isinstance(v, str):
            return v
        if info.field_name == "vin":
            s = v.strip().upper()
            return s if s else None
        s = v.strip()
        return s if s else None

    @field_validator("ownership_type")
    @classmethod
    def validate_ownership_type(cls, v: Optional[str]) -> Optional[str]:
        if v is None or not v.strip():
            return None
        v = v.strip().lower()
        if v not in OWNERSHIP_TYPES:
            raise ValueError(f"ownership_type must be one of {', '.join(sorted(OWNERSHIP_TYPES))}")
        return v

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: Optional[str]) -> Optional[str]:
        if v is None or not v.strip():
            return None
        v = v.strip().lower()
        if v not in TRUCK_STATUSES:
            raise ValueError(f"status must be one of {', '.join(sorted(TRUCK_STATUSES))}")
        return v

    @field_validator("fuel_type")
    @classmethod
    def validate_fuel_type(cls, v: Optional[str]) -> Optional[str]:
        if v is None or not v.strip():
            return None
        v = v.strip().lower()
        if v not in FUEL_TYPES:
            raise ValueError(f"fuel_type must be one of {', '.join(sorted(FUEL_TYPES))}")
        return v

    @field_validator("transmission")
    @classmethod
    def validate_transmission(cls, v: Optional[str]) -> Optional[str]:
        if v is None or not v.strip():
            return None
        v = v.strip().lower()
        if v not in TRANSMISSION_TYPES:
            raise ValueError(f"transmission must be one of {', '.join(sorted(TRANSMISSION_TYPES))}")
        return v

    @model_validator(mode="after")
    def odometer_last_updated_requires_current(self):
        if self.odometer_last_updated is not None and self.current_odometer is None:
            raise ValueError("odometer_last_updated requires current_odometer")
        return self


class TruckResponse(TruckBase):
    id: int
    tenant_id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
