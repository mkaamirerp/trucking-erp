"""Operational arrival and departure for an existing Load stop."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class StopExecutionBody(BaseModel):
    """Record one stop execution event. source matches the Trip execution-signal vocabulary."""

    model_config = ConfigDict(extra="forbid")

    source: str = Field(..., max_length=64)
    occurred_at: datetime | None = None
    notes: str | None = Field(default=None, max_length=2000)


class UnloadingExecutionResponse(BaseModel):
    trip_id: int
    load_id: int
    stop_id: int
    stop_type: str
    arrived_at: datetime | None
    departed_at: datetime | None
    unloading_started_at: datetime | None
    unloading_completed_at: datetime | None
    replayed: bool
    load_status: str
    trip_status: str
    membership_status_within_trip: str


class StopExecutionResponse(BaseModel):
    trip_id: int
    load_id: int
    stop_id: int
    stop_type: str
    arrived_at: datetime | None
    departed_at: datetime | None
    replayed: bool
    load_status: str
    trip_status: str
    membership_status_within_trip: str
