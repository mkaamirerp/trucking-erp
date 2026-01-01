from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field, ConfigDict


class EmployeeBase(BaseModel):
    model_config = ConfigDict(extra="ignore")

    payee_id: Optional[int] = Field(default=None, gt=0)
    employee_number: Optional[str] = Field(default=None, max_length=255)
    employee_code: Optional[str] = Field(default=None, max_length=255)  # legacy alias
    hire_date: Optional[date] = None
    termination_date: Optional[date] = None
    employment_type: str = Field(default="FULL_TIME", max_length=255)
    is_active: bool = True


class EmployeeCreate(EmployeeBase):
    pass


class EmployeeUpdate(BaseModel):
    payee_id: Optional[int] = Field(default=None, gt=0)
    employee_number: Optional[str] = Field(default=None, max_length=255)
    employee_code: Optional[str] = Field(default=None, max_length=255)
    hire_date: Optional[date] = None
    termination_date: Optional[date] = None
    employment_type: Optional[str] = Field(default=None, max_length=255)
    is_active: Optional[bool] = None


class EmployeeOut(EmployeeBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime
