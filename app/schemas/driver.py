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
    issuing_country: Optional[str] = Field(default=None, max_length=10)
    issuing_region: Optional[str] = Field(default=None, max_length=100)
    license_number: Optional[str] = Field(default=None, max_length=100)
    license_class: Optional[str] = Field(default=None, max_length=50)
    license_issue_date: Optional[date] = None
    license_expiry_date: Optional[date] = None

    @field_validator("first_name", "last_name")
    @classmethod
    def v_names(cls, v: str) -> str:
        return normalize_name(v)

    @field_validator("phone")
    @classmethod
    def v_phone(cls, v: Optional[str]) -> Optional[str]:
        return normalize_phone(v)
    @field_validator("issuing_country")
    @classmethod
    def v_country(cls, v: Optional[str]) -> Optional[str]:
        return v.upper() if v else v

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
    issuing_country: Optional[str] = Field(default=None, max_length=10)
    issuing_region: Optional[str] = Field(default=None, max_length=100)
    license_number: Optional[str] = Field(default=None, max_length=100)
    license_class: Optional[str] = Field(default=None, max_length=50)
    license_issue_date: Optional[date] = None
    license_expiry_date: Optional[date] = None

    @field_validator("first_name", "last_name")
    @classmethod
    def v_names(cls, v: Optional[str]) -> Optional[str]:
        return None if v is None else normalize_name(v)

    @field_validator("phone")
    @classmethod
    def v_phone(cls, v: Optional[str]) -> Optional[str]:
        return normalize_phone(v)


def _driver_attrs_to_dict(obj: object) -> dict:
    """Build a dict from an ORM-like object for output coercion. No SQLAlchemy import."""
    today = date.today()
    keys = (
        "id", "first_name", "last_name", "email", "phone", "hire_date", "is_active",
        "termination_date", "issuing_country", "issuing_region", "license_number",
        "license_class", "license_issue_date", "license_expiry_date",
    )
    out = {}
    for key in keys:
        if hasattr(obj, key):
            v = getattr(obj, key, None)
            if key in ("first_name", "last_name") and (v is None or (isinstance(v, str) and not v.strip())):
                v = " "  # satisfy min_length=1 for names
            if key in ("email", "phone") and v is not None and isinstance(v, str) and not v.strip():
                v = None  # optional fields: empty string -> None
            # Coerce email that would fail EmailStr (e.g. @demo.local) so driver still serializes
            if key == "email" and v is not None and isinstance(v, str):
                if ".local" in v.lower() or "@" not in v or len(v) < 5:
                    v = None
            # Coerce phone that would fail normalize_phone (7–15 digits) so driver still serializes
            if key == "phone" and v is not None and isinstance(v, str):
                digits = re.sub(r"\D", "", v)
                if len(digits) < 7 or len(digits) > 15:
                    v = None
            # Coerce future dates so DriverBase.v_dates doesn't fail on output
            if key in ("hire_date", "termination_date", "license_issue_date", "license_expiry_date") and v is not None:
                if hasattr(v, "year") and v > today:
                    v = today
            out[key] = v
    # DriverBase requires first_name, last_name
    out.setdefault("first_name", " ")
    out.setdefault("last_name", " ")
    out.setdefault("is_active", True)
    return out


class DriverOut(DriverBase):
    id: int
    model_config = ConfigDict(from_attributes=True)

    # Coerce before base validators run so bad DB state (termination_date + is_active) does not 500 the API
    @model_validator(mode="before")
    @classmethod
    def coerce_terminated_for_output(cls, data: object) -> object:
        if isinstance(data, dict):
            if data.get("termination_date") is not None:
                return {**data, "is_active": False}
            return data
        # ORM/object: normalize to dict so DriverBase validators see consistent state
        d = _driver_attrs_to_dict(data)
        if d.get("termination_date") is not None:
            d["is_active"] = False
        return d


class DriverListOut(BaseModel):
    """Permissive list/summary output: no EmailStr/phone/date validators so list never skips rows."""
    id: int
    first_name: str = ""
    last_name: str = ""
    email: Optional[str] = None
    phone: Optional[str] = None
    hire_date: Optional[date] = None
    is_active: bool = True
    termination_date: Optional[date] = None
    issuing_country: Optional[str] = None
    issuing_region: Optional[str] = None
    license_number: Optional[str] = None
    license_class: Optional[str] = None
    license_issue_date: Optional[date] = None
    license_expiry_date: Optional[date] = None
    model_config = ConfigDict(from_attributes=True)


def driver_row_to_list_out(d: object) -> DriverListOut:
    """Build DriverListOut from ORM row; never raises (uses safe coercion)."""
    d = _driver_attrs_to_dict(d)
    if d.get("termination_date") is not None:
        d["is_active"] = False
    return DriverListOut.model_validate(d)
