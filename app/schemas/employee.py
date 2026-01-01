from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field


class EmployeeBase(BaseModel):
    employee_code: str = Field(..., max_length=50)
    first_name: str = Field(..., max_length=100)
    last_name: str = Field(..., max_length=100)
    phone: Optional[str] = Field(default=None, max_length=50)
    email: Optional[EmailStr] = None
    hire_date: Optional[date] = None
    is_active: bool = True
    termination_date: Optional[date] = None


class EmployeeCreate(EmployeeBase):
    pass


class EmployeeUpdate(BaseModel):
    employee_code: Optional[str] = Field(default=None, max_length=50)
    first_name: Optional[str] = Field(default=None, max_length=100)
    last_name: Optional[str] = Field(default=None, max_length=100)
    phone: Optional[str] = Field(default=None, max_length=50)
    email: Optional[EmailStr] = None
    hire_date: Optional[date] = None
    is_active: Optional[bool] = None
    termination_date: Optional[date] = None


class EmployeeOut(EmployeeBase):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
