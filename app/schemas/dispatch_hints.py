"""Read-only hints for dispatch assignment UI (no mutations)."""

from __future__ import annotations

from pydantic import BaseModel


class DriverAssignmentHintsOut(BaseModel):
    """Suggested truck/trailer for a driver from recent assignments and fleet ownership."""

    truck_id: int | None = None
    trailer_id: int | None = None


class TruckSuggestedTrailerOut(BaseModel):
    """Trailer seen most recently on a load with this truck."""

    trailer_id: int | None = None
