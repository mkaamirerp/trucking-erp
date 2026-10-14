"""Isolated driver/truck/trailer rows for integration tests (tenant_pytest)."""

from __future__ import annotations

import uuid

from typing import Any, Protocol

from httpx import AsyncClient


class FleetResourceTracker(Protocol):
    def track_driver(self, driver_id: int) -> None: ...
    def track_truck(self, truck_id: int) -> None: ...
    def track_trailer(self, trailer_id: int) -> None: ...


async def api_create_integration_fleet_bundle(
    client: AsyncClient,
    headers: dict[str, str],
    tag: str,
    *,
    tracker: FleetResourceTracker | None = None,
) -> tuple[int, int, int]:
    """Create one active driver, truck, and trailer.

    Each resource is registered on the tracker immediately after successful create so
    partial failure (e.g. trailer create fails) still tears down driver/truck.
    """
    suffix = uuid.uuid4().hex[:10]
    dr = await client.post(
        "/api/v1/drivers",
        headers=headers,
        json={
            "first_name": tag[:20] or "Int",
            "last_name": f"T{suffix[:6]}",
            "phone": "+15555550100",
            "is_active": True,
        },
    )
    if dr.status_code != 201:
        raise AssertionError(f"create driver failed: {dr.status_code} {dr.text}")
    driver_id = int(dr.json()["id"])
    if tracker is not None:
        tracker.track_driver(driver_id)

    vin = f"1{suffix.upper()}Z{uuid.uuid4().hex[:8].upper()}"[:17]
    tr = await client.post(
        "/api/v1/trucks",
        headers=headers,
        json={
            "unit_number": f"UT-{suffix}",
            "vin": vin,
            "status": "active",
        },
    )
    if tr.status_code != 201:
        raise AssertionError(f"create truck failed: {tr.status_code} {tr.text}")
    truck_id = int(tr.json()["id"])
    if tracker is not None:
        tracker.track_truck(truck_id)

    rr = await client.post(
        "/api/v1/trailers",
        headers=headers,
        json={
            "unit_number": f"TR-{suffix}",
            "status": "active",
        },
    )
    if rr.status_code != 201:
        raise AssertionError(f"create trailer failed: {rr.status_code} {rr.text}")
    trailer_id = int(rr.json()["id"])
    if tracker is not None:
        tracker.track_trailer(trailer_id)

    return driver_id, truck_id, trailer_id
