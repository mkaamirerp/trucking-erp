from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class AuditEventOut(BaseModel):
    id: int
    event_at: datetime
    actor_user_id: int | None = None
    actor_label: str | None = None
    module: str
    entity_type: str
    entity_id: str
    entity_label: str | None = None
    action: str
    request_id: str | None = None
    correlation_id: str | None = None
    source: str
    visibility: str
    changed_fields: dict[str, Any] = Field(default_factory=dict)

