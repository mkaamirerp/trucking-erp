"""Tenant-scoped inputs for equipment_assignment_policy.

Open operational trips supply *current* driver–truck and truck–trailer links for
dispatch suggestion only. This is not a substitute for audited hook/drop events
(see MASTER.md checkpoint note); it avoids inferring attachments from completed trips.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.driver import Driver
from app.models.trailer import Trailer
from app.models.trip import Trip
from app.models.truck import Truck
from app.services.equipment_assignment_policy import (
    AssignmentSuggestion,
    DriverTruckLink,
    EquipmentContext,
    TruckTrailerLink,
    suggest_for_driver,
    suggest_for_truck,
)

_OPEN_TRIP_STATUSES = ("planned", "assigned", "in_progress")


async def load_equipment_context(db: AsyncSession, tenant_id: int) -> EquipmentContext:
    trip_rows = (
        await db.execute(
            select(Trip).where(
                Trip.tenant_id == tenant_id,
                Trip.status.in_(_OPEN_TRIP_STATUSES),
            )
        )
    ).scalars().all()

    current_driver_trucks: list[DriverTruckLink] = []
    hooked_trailers: list[TruckTrailerLink] = []
    for trip in trip_rows:
        if trip.driver_id and trip.truck_id:
            current_driver_trucks.append(DriverTruckLink(int(trip.driver_id), int(trip.truck_id)))
        if trip.truck_id and trip.trailer_id:
            hooked_trailers.append(TruckTrailerLink(int(trip.truck_id), int(trip.trailer_id)))

    default_driver_trucks: list[DriverTruckLink] = []
    drivers = (await db.execute(select(Driver).where(Driver.tenant_id == tenant_id))).scalars().all()
    for driver in drivers:
        if not driver.person_id:
            continue
        own_truck = (
            await db.execute(
                select(Truck.id)
                .where(
                    Truck.tenant_id == tenant_id,
                    Truck.owner_person_id == driver.person_id,
                    Truck.status == "active",
                )
                .limit(1)
            )
        ).scalar_one_or_none()
        if own_truck is not None:
            default_driver_trucks.append(DriverTruckLink(int(driver.id), int(own_truck)))

    return EquipmentContext(
        current_driver_trucks=tuple(current_driver_trucks),
        default_driver_trucks=tuple(default_driver_trucks),
        hooked_trailers=tuple(hooked_trailers),
        off_duty_driver_ids=frozenset(),
    )


async def suggest_assignment_for_driver(
    db: AsyncSession,
    tenant_id: int,
    driver_id: int,
) -> AssignmentSuggestion:
    context = await load_equipment_context(db, tenant_id)
    return suggest_for_driver(driver_id, context)


async def suggest_assignment_for_truck(
    db: AsyncSession,
    tenant_id: int,
    truck_id: int,
) -> AssignmentSuggestion:
    context = await load_equipment_context(db, tenant_id)
    return suggest_for_truck(truck_id, context)


def assignment_suggestion_to_hints(suggestion: AssignmentSuggestion, *, anchor_driver_id: int | None = None, anchor_truck_id: int | None = None) -> dict:
    return {
        "driver_id": suggestion.driver_id if suggestion.driver_id is not None else anchor_driver_id,
        "truck_id": suggestion.truck_id if suggestion.truck_id is not None else anchor_truck_id,
        "trailer_id": suggestion.trailer_id,
        "truck_source": suggestion.truck_source,
        "trailer_source": suggestion.trailer_source,
        "driver_source": suggestion.driver_source,
        "warnings": list(suggestion.warnings),
    }
