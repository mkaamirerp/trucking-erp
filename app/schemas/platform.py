from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class PlatformTenantCreateIn(BaseModel):
    """POST /api/v1/platform/tenants — platform admin only; extra JSON keys ignored."""

    model_config = ConfigDict(extra="ignore")

    company_name: str | None = None
    name: str | None = None
    slug: str | None = None
    plan: str | None = None
    plan_code: str | None = None


class PlatformTenantOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    slug: str
    status: str
    plan: Optional[str] = None
    db_status: Optional[str] = None
    db_last_error: Optional[str] = None
    db_last_error_at: Optional[datetime] = None
    provisioned_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
