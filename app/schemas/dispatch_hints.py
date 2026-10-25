"""Read-only hints for dispatch assignment UI (no mutations)."""

from __future__ import annotations

from pydantic import BaseModel


class DriverAssignmentHintsOut(BaseModel):
    """Suggested truck/trailer for a driver via universal equipment policy."""

    truck_id: int | None = None
    trailer_id: int | None = None
    driver_id: int | None = None
    truck_source: str | None = None
    trailer_source: str | None = None
    driver_source: str | None = None
    warnings: list[str] = []


class TruckAssignmentHintsOut(BaseModel):
    """Suggested driver/trailer for a truck via universal equipment policy."""

    driver_id: int | None = None
    truck_id: int | None = None
    trailer_id: int | None = None
    truck_source: str | None = None
    trailer_source: str | None = None
    driver_source: str | None = None
    warnings: list[str] = []


class TruckSuggestedTrailerOut(BaseModel):
    """Only the currently confirmed hooked trailer, never a prior Load."""

    trailer_id: int | None = None
