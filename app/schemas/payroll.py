from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

PAY_PERIOD_STATUSES = {"DRAFT", "OPEN", "CLOSED"}
PAY_TYPES = {"PER_MILE", "HOURLY", "PERCENTAGE", "SALARY"}
ENTRY_TYPES = {"MILES", "HOURS", "GROSS", "ADJUSTMENT", "DEDUCTION"}


class PayPeriodBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    start_date: date
    end_date: date

    @model_validator(mode="after")
    def validate_dates(self):
        if self.end_date < self.start_date:
            raise ValueError("end_date cannot be before start_date")
        return self


class PayPeriodCreate(PayPeriodBase):
    pass


class PayPeriodUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    start_date: Optional[date] = None
    end_date: Optional[date] = None

    @model_validator(mode="after")
    def validate_dates(self):
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("end_date cannot be before start_date")
        return self


class PayPeriodOut(PayPeriodBase):
    id: int
    status: str
    closed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PayProfileBase(BaseModel):
    driver_id: int
    pay_type: str
    rate_amount: Optional[Decimal] = Field(default=None, gt=Decimal("0"))
    rate_unit: Optional[str] = Field(default=None, max_length=30)
    percentage_basis_points: Optional[int] = Field(default=None, ge=0, le=10000)
    currency: str = Field(default="USD", max_length=10)
    notes: Optional[str] = None
    effective_start: date = Field(default_factory=date.today)
    effective_end: Optional[date] = None
    is_active: bool = True

    @field_validator("pay_type")
    @classmethod
    def v_pay_type(cls, v: str) -> str:
        vv = (v or "").strip().upper()
        if vv not in PAY_TYPES:
            raise ValueError(f"pay_type must be one of {sorted(PAY_TYPES)}")
        return vv

    @model_validator(mode="after")
    def validate_effective_dates(self):
        if self.effective_end and self.effective_end < self.effective_start:
            raise ValueError("effective_end cannot be before effective_start")
        return self

    @model_validator(mode="after")
    def validate_rate_fields(self):
        if self.pay_type in {"PER_MILE", "HOURLY", "SALARY"} and self.rate_amount is None:
            raise ValueError("rate_amount is required for this pay_type")
        if self.pay_type == "PERCENTAGE" and self.percentage_basis_points is None:
            raise ValueError("percentage_basis_points is required for percentage pay_type")
        return self


class PayProfileCreate(PayProfileBase):
    pass


class PayProfileUpdate(BaseModel):
    rate_amount: Optional[Decimal] = Field(default=None, gt=Decimal("0"))
    rate_unit: Optional[str] = Field(default=None, max_length=30)
    percentage_basis_points: Optional[int] = Field(default=None, ge=0, le=10000)
    currency: Optional[str] = Field(default=None, max_length=10)
    notes: Optional[str] = None
    effective_start: Optional[date] = None
    effective_end: Optional[date] = None
    is_active: Optional[bool] = None

    @model_validator(mode="after")
    def validate_effective_dates(self):
        if self.effective_start and self.effective_end and self.effective_end < self.effective_start:
            raise ValueError("effective_end cannot be before effective_start")
        return self


class PayProfileOut(PayProfileBase):
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PayEntryBase(BaseModel):
    pay_period_id: int
    driver_id: int
    work_date: date
    pay_profile_id: Optional[int] = None
    entry_type: str
    quantity: Optional[Decimal] = Field(default=None, gt=Decimal("0"))
    rate_amount: Optional[Decimal] = Field(default=None, gt=Decimal("0"))
    amount: Optional[Decimal] = Field(default=None)
    reference_code: Optional[str] = Field(default=None, max_length=100)
    notes: Optional[str] = None

    @field_validator("entry_type")
    @classmethod
    def v_entry_type(cls, v: str) -> str:
        vv = (v or "").strip().upper()
        if vv not in ENTRY_TYPES:
            raise ValueError(f"entry_type must be one of {sorted(ENTRY_TYPES)}")
        return vv

    @model_validator(mode="after")
    def validate_amounts(self):
        if self.amount is None and (self.quantity is None or self.rate_amount is None):
            raise ValueError("Provide amount or both quantity and rate_amount")
        return self


class PayEntryCreate(PayEntryBase):
    pass


class PayEntryUpdate(BaseModel):
    quantity: Optional[Decimal] = Field(default=None, gt=Decimal("0"))
    rate_amount: Optional[Decimal] = Field(default=None, gt=Decimal("0"))
    amount: Optional[Decimal] = None
    reference_code: Optional[str] = Field(default=None, max_length=100)
    notes: Optional[str] = None

    @model_validator(mode="after")
    def validate_amounts(self):
        if self.amount is None and self.quantity is None and self.rate_amount is None:
            raise ValueError("Provide at least one field to update")
        return self


class PayEntryOut(PayEntryBase):
    id: int
    is_manual: bool
    status: str
    is_active: bool
    created_by: Optional[str] = None
    updated_by: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PayDriverSummary(BaseModel):
    driver_id: int
    miles: Decimal = Decimal("0")
    hours: Decimal = Decimal("0")
    earnings: Decimal = Decimal("0")
    deductions: Decimal = Decimal("0")
    net: Decimal = Decimal("0")


class PayPeriodSummary(BaseModel):
    pay_period_id: int
    status: str
    totals: list[PayDriverSummary]
