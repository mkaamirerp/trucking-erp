import re

def normalize_name(v: str):
    if v is None:
        return v
    v = v.strip()
    v = re.sub(r"\s+", " ", v)
    return v

from datetime import date
from typing import Optional

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator, ConfigDict

from app.core.validators import normalize_phone_number as normalize_phone


class DriverBase(BaseModel):
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(default=None, max_length=50)
    hire_date: Optional[date] = None
    is_active: bool = True
    termination_date: Optional[date] = None

    @field_validator("first_name", "last_name")
    @classmethod
    def v_names(cls, v: str) -> str:
        return normalize_name(v)

    @field_validator("phone")
    @classmethod
    def v_phone(cls, v: Optional[str]) -> Optional[str]:
        return normalize_phone(v)

    @model_validator(mode="after")
    def v_dates(self):
        # termination_date cannot be before hire_date
        if self.hire_date and self.termination_date:
            if self.termination_date < self.hire_date:
                raise ValueError("termination_date cannot be before hire_date")

        # If termination_date is set, driver cannot be active
        if self.termination_date is not None and self.is_active:
            raise ValueError("Driver with termination_date cannot be active")

        # Optional: prevent future dates
        today = date.today()
        if self.hire_date and self.hire_date > today:
            raise ValueError("hire_date cannot be in the future")
        if self.termination_date and self.termination_date > today:
            raise ValueError("termination_date cannot be in the future")

        return self


class DriverCreate(DriverBase):
    pass


class DriverUpdate(BaseModel):
    first_name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    last_name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(default=None, max_length=50)
    hire_date: Optional[date] = None
    is_active: Optional[bool] = None
    termination_date: Optional[date] = None

    @field_validator("first_name", "last_name")
    @classmethod
    def v_names(cls, v: Optional[str]) -> Optional[str]:
        return None if v is None else normalize_name(v)

    @field_validator("phone")
    @classmethod
    def v_phone(cls, v: Optional[str]) -> Optional[str]:
        return normalize_phone(v)


class DriverOut(DriverBase):
    id: int
    model_config = ConfigDict(from_attributes=True)
    # === Cross-field validation ===
    @model_validator(mode="after")
    def validate_active_vs_termination(self):
        if self.termination_date is not None and self.is_active:
            raise ValueError("Driver with termination_date cannot be active")
        return self
