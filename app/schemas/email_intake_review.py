"""API shapes for email intake review spine (thread-scoped)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class EmailIntakeReviewEventOut(BaseModel):
    id: int
    event_type: str
    actor_kind: str
    actor_tenant_user_id: int | None = None
    actor_platform_user_id: str | None = None
    old_value_json: dict[str, Any] | None = None
    new_value_json: dict[str, Any] | None = None
    reason_code: str | None = None
    payload_note: str | None = None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class EmailIntakeReviewOut(BaseModel):
    id: int
    tenant_id: int
    email_thread_id: int
    primary_code: str
    detail_json: dict[str, Any] | None = None
    status: str
    claimed_by_tenant_user_id: int | None = None
    claimed_at: datetime | None = None
    resolved_at: datetime | None = None
    dismissed_at: datetime | None = None
    last_routing_reason_snapshot: str | None = None
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


class EmailIntakeReviewCardOut(BaseModel):
    """Lightweight summary for thread GET (no event list)."""

    id: int
    primary_code: str
    detail_json: dict[str, Any] | None = None
    status: str
    claimed_by_tenant_user_id: int | None = None
    claimed_at: datetime | None = None
    resolved_at: datetime | None = None
    dismissed_at: datetime | None = None
    model_config = ConfigDict(from_attributes=True)


class EmailIntakeReviewBundleOut(BaseModel):
    review: EmailIntakeReviewOut | None = None
    events: list[EmailIntakeReviewEventOut] = Field(default_factory=list)


class DuplicateLinkPriorBody(BaseModel):
    """Link this thread to the prior load suggested by duplicate review detail (or override with the same id)."""

    prior_load_id: int | None = Field(
        default=None,
        description="Must match review detail ``prior_load_id`` when that field is set.",
    )


class DuplicateConfirmBody(BaseModel):
    note: str | None = Field(default=None, max_length=8000)
