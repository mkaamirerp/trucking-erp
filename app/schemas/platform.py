from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


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
