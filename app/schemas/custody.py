"""Custody / terminal schemas (Slice 1 foundation)."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class LoadCustodySnapshotResponse(BaseModel):
    """Current custody read-model on a Load (derived from last event after bootstrap/mutations)."""

    load_id: int
    custody_owner: str
    custody_trip_id: Optional[int] = None
    custody_terminal_id: Optional[int] = None
    custody_placement: str
    custody_trailer_id: Optional[int] = None
    custody_since_at: Optional[datetime] = None
    last_custody_event_id: Optional[int] = None
    model_config = ConfigDict(from_attributes=True)


class LoadCustodyEventResponse(BaseModel):
    id: int
    tenant_id: int
    load_id: int
    event_type: str
    occurred_at: datetime
    recorded_at: datetime
    custody_owner_after: str
    placement_after: str
    trip_id: Optional[int] = None
    terminal_id: Optional[int] = None
    trailer_id: Optional[int] = None
    actor_user_id: Optional[int] = None
    source: str
    notes: Optional[str] = None
    idempotency_key: Optional[str] = None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class LoadCustodyEventListResponse(BaseModel):
    items: list[LoadCustodyEventResponse]
    total: int = Field(description="Total events for this load (tenant-scoped)")


class TerminalResponse(BaseModel):
    id: int
    tenant_id: int
    name: str
    street: Optional[str] = None
    city: Optional[str] = None
    state_or_province: Optional[str] = None
    postal_code: Optional[str] = None
    country: Optional[str] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


class TerminalListResponse(BaseModel):
    items: list[TerminalResponse]


class TerminalCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    street: Optional[str] = Field(default=None, max_length=255)
    city: Optional[str] = Field(default=None, max_length=100)
    state_or_province: Optional[str] = Field(default=None, max_length=50)
    postal_code: Optional[str] = Field(default=None, max_length=20)
    country: Optional[str] = Field(default=None, max_length=50)
    is_active: bool = True
    model_config = ConfigDict(extra="forbid")


class TerminalUpdate(BaseModel):
    """Partial update. Soft-deactivate via is_active=false (no hard delete)."""

    name: Optional[str] = Field(default=None, min_length=1, max_length=128)
    street: Optional[str] = Field(default=None, max_length=255)
    city: Optional[str] = Field(default=None, max_length=100)
    state_or_province: Optional[str] = Field(default=None, max_length=50)
    postal_code: Optional[str] = Field(default=None, max_length=20)
    country: Optional[str] = Field(default=None, max_length=50)
    is_active: Optional[bool] = None
    model_config = ConfigDict(extra="forbid")
