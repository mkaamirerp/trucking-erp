from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

ROLE_CHOICES = [
    "DRIVER",
    "DISPATCHER",
    "MANAGER",
    "SAFETY",
    "ACCOUNTING",
    "MECHANIC",
    "OWNER",
    "HR",
]


class EmployeeRoleBase(BaseModel):
    role: str = Field(..., max_length=50)
    is_primary: bool = False


class EmployeeRoleCreate(EmployeeRoleBase):
    pass


class EmployeeRoleOut(EmployeeRoleBase):
    id: int
    employee_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
