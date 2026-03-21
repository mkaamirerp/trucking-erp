"""Pydantic schemas for trailer create/update/response with validation."""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

TRAILER_STATUSES = {"active", "inactive", "retired"}
OWNERSHIP_TYPES = {"company", "owner_operator", "leased"}
TRAILER_TYPES = {
    "dry_van",
    "reefer",
    "flatbed",
    "step_deck",
    "lowboy",
    "tanker",
    "dump",
    "chassis",
    "other",
}
DOOR_TYPES = {"swing", "roll", "curtain"}


def _normalize_vin(v: str | None) -> str | None:
    if v is None:
        return None
    return v.strip().upper() if v.strip() else None


def _normalize_unit_number(v: str | None) -> str | None:
    if v is None:
        return None
    return v.strip() if v.strip() else None


class TrailerBase(BaseModel):
    unit_number: str = Field(..., max_length=50)
    vin: Optional[str] = Field(default=None, max_length=50)
    year: Optional[int] = Field(default=None, ge=1900, le=2100)
    make: Optional[str] = Field(default=None, max_length=100)
    model: Optional[str] = Field(default=None, max_length=100)
    plate_number: Optional[str] = Field(default=None, max_length=50)
    plate_region: Optional[str] = Field(default=None, max_length=20)
    trailer_type: str = Field(default="dry_van", max_length=30)
    length_ft: Optional[int] = Field(default=None, gt=0)
    num_axles: Optional[int] = Field(default=None, gt=0)
    gvwr_lbs: Optional[int] = Field(default=None, gt=0)
    door_type: Optional[str] = Field(default=None, max_length=30)
    reefer_make: Optional[str] = Field(default=None, max_length=100)
    reefer_model: Optional[str] = Field(default=None, max_length=100)
    reefer_serial: Optional[str] = Field(default=None, max_length=100)
    ownership_type: str = Field(default="company", max_length=30)
    owner_person_id: Optional[int] = None
    purchase_date: Optional[date] = None
    purchase_price: Optional[float] = Field(default=None, ge=0)
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
            return _normalize_vin(v) if v.strip() else None
        return _normalize_unit_number(v) if v.strip() else v.strip()

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
        if v not in TRAILER_STATUSES:
            raise ValueError(f"status must be one of {', '.join(sorted(TRAILER_STATUSES))}")
        return v

    @field_validator("trailer_type")
    @classmethod
    def validate_trailer_type(cls, v: str) -> str:
        v = v.strip().lower()
        if v not in TRAILER_TYPES:
            raise ValueError(f"trailer_type must be one of {', '.join(sorted(TRAILER_TYPES))}")
        return v

    @field_validator("door_type")
    @classmethod
    def validate_door_type(cls, v: Optional[str]) -> Optional[str]:
        if v is None or not v.strip():
            return None
        v = v.strip().lower()
        if v not in DOOR_TYPES:
            raise ValueError(f"door_type must be one of {', '.join(sorted(DOOR_TYPES))}")
        return v

    @model_validator(mode="after")
    def reefer_fields_only_when_reefer(self):
        if self.trailer_type != "reefer":
            if self.reefer_make or self.reefer_model or self.reefer_serial:
                raise ValueError(
                    "reefer_make, reefer_model, reefer_serial are only allowed when trailer_type is reefer"
                )
        return self


class TrailerCreate(TrailerBase):
    @field_validator("unit_number")
    @classmethod
    def unit_number_required(cls, v: str) -> str:
        n = _normalize_unit_number(v)
        if not n:
            raise ValueError("unit_number is required")
        return n


class TrailerUpdate(BaseModel):
    unit_number: Optional[str] = Field(default=None, max_length=50)
    vin: Optional[str] = Field(default=None, max_length=50)
    year: Optional[int] = Field(default=None, ge=1900, le=2100)
    make: Optional[str] = Field(default=None, max_length=100)
    model: Optional[str] = Field(default=None, max_length=100)
    plate_number: Optional[str] = Field(default=None, max_length=50)
    plate_region: Optional[str] = Field(default=None, max_length=20)
    trailer_type: Optional[str] = Field(default=None, max_length=30)
    length_ft: Optional[int] = Field(default=None, gt=0)
    num_axles: Optional[int] = Field(default=None, gt=0)
    gvwr_lbs: Optional[int] = Field(default=None, gt=0)
    door_type: Optional[str] = Field(default=None, max_length=30)
    reefer_make: Optional[str] = Field(default=None, max_length=100)
    reefer_model: Optional[str] = Field(default=None, max_length=100)
    reefer_serial: Optional[str] = Field(default=None, max_length=100)
    ownership_type: Optional[str] = Field(default=None, max_length=30)
    owner_person_id: Optional[int] = None
    purchase_date: Optional[date] = None
    purchase_price: Optional[float] = Field(default=None, ge=0)
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
            return _normalize_vin(v) if v.strip() else None
        return _normalize_unit_number(v) if v.strip() else None

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
        if v not in TRAILER_STATUSES:
            raise ValueError(f"status must be one of {', '.join(sorted(TRAILER_STATUSES))}")
        return v

    @field_validator("trailer_type")
    @classmethod
    def validate_trailer_type(cls, v: Optional[str]) -> Optional[str]:
        if v is None or not v.strip():
            return None
        v = v.strip().lower()
        if v not in TRAILER_TYPES:
            raise ValueError(f"trailer_type must be one of {', '.join(sorted(TRAILER_TYPES))}")
        return v

    @field_validator("door_type")
    @classmethod
    def validate_door_type(cls, v: Optional[str]) -> Optional[str]:
        if v is None or not v.strip():
            return None
        v = v.strip().lower()
        if v not in DOOR_TYPES:
            raise ValueError(f"door_type must be one of {', '.join(sorted(DOOR_TYPES))}")
        return v

    @model_validator(mode="after")
    def reefer_fields_only_when_reefer(self):
        tt = self.trailer_type
        if tt and tt != "reefer":
            if self.reefer_make or self.reefer_model or self.reefer_serial:
                raise ValueError(
                    "reefer_make, reefer_model, reefer_serial are only allowed when trailer_type is reefer"
                )
        return self


class TrailerResponse(TrailerBase):
    id: int
    tenant_id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
