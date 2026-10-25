"""Universal read-only equipment assignment suggestions.

This module makes no database writes and never infers physical attachments
from completed Trips, Load legacy mirrors, asset ownership, or duty status.
Callers must provide tenant-scoped, confirmed *current* bindings. Historical
Trips and default-truck relationships are different sources of evidence.

A suggestion is not an assignment: any UI must show it before confirmation,
and the Trip service remains the only operational assignment writer.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class DriverTruckLink:
    driver_id: int
    truck_id: int


@dataclass(frozen=True)
class TruckTrailerLink:
    truck_id: int
    trailer_id: int


@dataclass(frozen=True)
class EquipmentContext:
    """Authoritative current state supplied by a tenant-scoped repository.

    `current_driver_trucks` is physical/operational attachment, NOT all Trips.
    `default_driver_trucks` is a preference, NOT a current attachment.
    `hooked_trailers` is physical attachment confirmed after any last drop.
    Off-duty is a separate fact and never detaches equipment by itself.
    """

    current_driver_trucks: tuple[DriverTruckLink, ...] = ()
    default_driver_trucks: tuple[DriverTruckLink, ...] = ()
    hooked_trailers: tuple[TruckTrailerLink, ...] = ()
    off_duty_driver_ids: frozenset[int] = frozenset()


@dataclass(frozen=True)
class AssignmentSuggestion:
    driver_id: int | None
    truck_id: int | None
    trailer_id: int | None
    truck_source: Literal["current", "default"] | None = None
    driver_source: Literal["current"] | None = None
    trailer_source: Literal["hooked"] | None = None
    warnings: tuple[str, ...] = ()


def _unique_ids(values: list[int]) -> list[int]:
    return sorted(set(values))


def _trailer_for_truck(context: EquipmentContext, truck_id: int) -> tuple[int | None, bool]:
    trailer_ids = _unique_ids(
        [link.trailer_id for link in context.hooked_trailers if link.truck_id == truck_id]
    )
    if len(trailer_ids) == 1:
        return trailer_ids[0], False
    return None, len(trailer_ids) > 1


def suggest_for_driver(driver_id: int, context: EquipmentContext) -> AssignmentSuggestion:
    """Suggest confirmed current truck/trailer, or default truck alone.

    Never pull a hooked trailer through *only* a default-truck association.
    A released driver may have a usual truck but no current attachment.
    """
    if driver_id <= 0:
        raise ValueError("driver_id must be positive")
    warnings: list[str] = []
    if driver_id in context.off_duty_driver_ids:
        warnings.append("DRIVER_OFF_DUTY")

    current = _unique_ids(
        [link.truck_id for link in context.current_driver_trucks if link.driver_id == driver_id]
    )
    if len(current) > 1:
        warnings.append("MULTIPLE_CURRENT_TRUCKS")
        return AssignmentSuggestion(driver_id, None, None, warnings=tuple(warnings))
    if len(current) == 1:
        truck_id = current[0]
        trailer_id, ambiguous = _trailer_for_truck(context, truck_id)
        if ambiguous:
            warnings.append("MULTIPLE_HOOKED_TRAILERS")
        return AssignmentSuggestion(
            driver_id, truck_id, trailer_id,
            truck_source="current",
            trailer_source="hooked" if trailer_id is not None else None,
            warnings=tuple(warnings),
        )

    default = _unique_ids(
        [link.truck_id for link in context.default_driver_trucks if link.driver_id == driver_id]
    )
    if len(default) > 1:
        warnings.append("MULTIPLE_DEFAULT_TRUCKS")
    if len(default) == 1:
        truck_id = default[0]
        other_users = _unique_ids([
            link.driver_id for link in context.current_driver_trucks
            if link.truck_id == truck_id and link.driver_id != driver_id
        ])
        if other_users:
            warnings.append("DEFAULT_TRUCK_CURRENTLY_ATTACHED_TO_OTHER_DRIVER")
            return AssignmentSuggestion(driver_id, None, None, warnings=tuple(warnings))
        warnings.append("DEFAULT_TRUCK_NOT_CONFIRMED_ATTACHED")
        return AssignmentSuggestion(
            driver_id, truck_id, None, truck_source="default", warnings=tuple(warnings)
        )
    return AssignmentSuggestion(driver_id, None, None, warnings=tuple(warnings))


def suggest_for_truck(truck_id: int, context: EquipmentContext) -> AssignmentSuggestion:
    """Find uniquely current driver and hooked trailer for a selected truck.

    Default driver links do NOT establish who is driving the truck today.
    """
    if truck_id <= 0:
        raise ValueError("truck_id must be positive")
    warnings: list[str] = []
    drivers = _unique_ids([
        link.driver_id for link in context.current_driver_trucks if link.truck_id == truck_id
    ])
    driver_id = drivers[0] if len(drivers) == 1 else None
    if len(drivers) > 1:
        warnings.append("MULTIPLE_CURRENT_DRIVERS")
    if driver_id is not None and driver_id in context.off_duty_driver_ids:
        warnings.append("DRIVER_OFF_DUTY")
    trailer_id, ambiguous = _trailer_for_truck(context, truck_id)
    if ambiguous:
        warnings.append("MULTIPLE_HOOKED_TRAILERS")
    return AssignmentSuggestion(
        driver_id, truck_id, trailer_id,
        driver_source="current" if driver_id is not None else None,
        truck_source="current" if driver_id is not None else None,
        trailer_source="hooked" if trailer_id is not None else None,
        warnings=tuple(warnings),
    )
