from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class FutureMovementPlanLineIn(BaseModel):
    load_id: int
    sequence_hint: Optional[int] = None
    inbound_trip_id: Optional[int] = None


class FutureMovementPlanLineOut(BaseModel):
    id: int
    load_id: int
    sequence_hint: Optional[int] = None
    inbound_trip_id: Optional[int] = None
    load_number: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)


class FutureMovementPlanCreate(BaseModel):
    origin_kind: str = Field(default="manual", max_length=32)
    pickup_terminal_id: Optional[int] = None
    planned_start_at: Optional[datetime] = None
    expected_completion_at: Optional[datetime] = None
    driver_id: Optional[int] = None
    truck_id: Optional[int] = None
    trailer_id: Optional[int] = None
    notes: Optional[str] = None
    lines: list[FutureMovementPlanLineIn] = Field(default_factory=list)


class FutureMovementPlanUpdate(BaseModel):
    pickup_terminal_id: Optional[int] = None
    planned_start_at: Optional[datetime] = None
    expected_completion_at: Optional[datetime] = None
    driver_id: Optional[int] = None
    truck_id: Optional[int] = None
    trailer_id: Optional[int] = None
    notes: Optional[str] = None
    lines: Optional[list[FutureMovementPlanLineIn]] = None
    concurrency_version: int = Field(..., ge=1)


class FutureMovementPlanOut(BaseModel):
    id: int
    tenant_id: int
    status: str
    origin_kind: str
    pickup_terminal_id: Optional[int] = None
    planned_start_at: Optional[datetime] = None
    expected_completion_at: Optional[datetime] = None
    driver_id: Optional[int] = None
    truck_id: Optional[int] = None
    trailer_id: Optional[int] = None
    converted_trip_id: Optional[int] = None
    converted_trip_number: Optional[str] = None
    notes: Optional[str] = None
    concurrency_version: int
    created_at: datetime
    updated_at: datetime
    lines: list[FutureMovementPlanLineOut] = Field(default_factory=list)
    model_config = ConfigDict(from_attributes=True)


class FutureMovementPlanListPage(BaseModel):
    items: list[FutureMovementPlanOut]
    page: int
    size: int
    total: int


class FutureMovementPlanCancelBody(BaseModel):
    concurrency_version: int = Field(..., ge=1)


class FutureMovementConvertBody(BaseModel):
    driver_id: int
    truck_id: Optional[int] = None
    trailer_id: Optional[int] = None
    conversion_idempotency_key: Optional[str] = Field(default=None, max_length=128)
    concurrency_version: int = Field(..., ge=1)


class YardDropInstructionBody(BaseModel):
    inbound_trip_id: int
    terminal_id: int
    notes: Optional[str] = Field(default=None, max_length=2000)
