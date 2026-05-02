"""Read-only trip workspace (Phase 3A): trip detail + member loads from trip_loads."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.load import NestedDriver, NestedTrailer, NestedTruck


class TripMemberLoadSummary(BaseModel):
    """One row: trip_loads membership + commercial fields from loads."""

    trip_load_id: int
    load_id: int
    status_within_trip: str
    sequence_hint: Optional[int] = None
    added_at: datetime
    removed_at: Optional[datetime] = None
    load_number: str
    broker_name_snapshot: Optional[str] = None
    broker_load_reference: Optional[str] = None
    commodity: Optional[str] = None
    rate: Optional[float] = None
    customer_rate: Optional[float] = None
    stop_route_summary: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)


class TripFirstMemberSummary(BaseModel):
    """First load in display order (sequence_hint, then added_at) among active trip_loads."""

    load_number: str
    broker_name_snapshot: Optional[str] = None
    broker_load_reference: Optional[str] = None
    stop_route_summary: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)


class TripListItemResponse(BaseModel):
    """Read-only row for trip directory."""

    id: int
    trip_number: str
    status: str
    job_type: str
    driver_id: Optional[int] = None
    driver: Optional[NestedDriver] = None
    truck_id: Optional[int] = None
    truck: Optional[NestedTruck] = None
    trailer_id: Optional[int] = None
    trailer: Optional[NestedTrailer] = None
    assigned_at: Optional[datetime] = None
    cancelled_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    member_load_count: int = Field(0, description="Active memberships in trip_loads (removed_at IS NULL).")
    first_member: Optional[TripFirstMemberSummary] = None
    model_config = ConfigDict(from_attributes=True)


class TripListPageResponse(BaseModel):
    items: list[TripListItemResponse]
    page: int
    size: int
    total: int
    model_config = ConfigDict(from_attributes=True)


class TripDetailResponse(BaseModel):
    """Read-only trip container for operations workspace."""

    id: int
    tenant_id: int
    trip_number: str
    status: str
    job_type: str
    driver_id: Optional[int] = None
    driver: Optional[NestedDriver] = None
    truck_id: Optional[int] = None
    truck: Optional[NestedTruck] = None
    trailer_id: Optional[int] = None
    trailer: Optional[NestedTrailer] = None
    assigned_at: Optional[datetime] = None
    cancelled_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    legacy_dispatch_trip_id: Optional[int] = Field(
        default=None,
        description="Debug/internal link to dispatch_trips; not a product identifier.",
    )
    member_loads: list[TripMemberLoadSummary] = Field(default_factory=list)
    model_config = ConfigDict(from_attributes=True)


class CreatePlannedTripBody(BaseModel):
    """Phase 3D: create Trip container; trip number minted server-side."""

    status: Optional[str] = Field(default=None, max_length=32, description="Default planned")
    job_type: Optional[str] = Field(default=None, max_length=32, description="Default freight_load")
    driver_id: Optional[int] = None
    truck_id: Optional[int] = None
    trailer_id: Optional[int] = None
    load_ids: list[int] = Field(default_factory=list, description="Optional loads to attach after trip insert")


class AddTripLoadBody(BaseModel):
    load_id: int
    sequence_hint: Optional[int] = None
