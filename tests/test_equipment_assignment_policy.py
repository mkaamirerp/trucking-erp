"""Universal equipment policy: no database required and no legacy Load fallback."""

import pytest

from app.services.equipment_assignment_policy import (
    AssignmentSuggestion,
    DriverTruckLink,
    EquipmentContext,
    TruckTrailerLink,
    suggest_for_driver,
    suggest_for_truck,
)


def test_boston_delivery_keeps_confirmed_hook_on_next_assignment():
    context = EquipmentContext(
        current_driver_trucks=(DriverTruckLink(7, 104),),
        hooked_trailers=(TruckTrailerLink(104, 5307),),
    )
    assert suggest_for_driver(7, context) == AssignmentSuggestion(
        7, 104, 5307, truck_source="current", trailer_source="hooked"
    )
    assert suggest_for_truck(104, context) == AssignmentSuggestion(
        7, 104, 5307, driver_source="current", truck_source="current", trailer_source="hooked"
    )


def test_recorded_drop_clears_trailer_not_driver_or_truck():
    context = EquipmentContext(current_driver_trucks=(DriverTruckLink(7, 104),))
    result = suggest_for_driver(7, context)
    assert (result.driver_id, result.truck_id, result.trailer_id) == (7, 104, None)


def test_off_duty_does_not_detach_verified_equipment():
    context = EquipmentContext(
        current_driver_trucks=(DriverTruckLink(7, 104),),
        hooked_trailers=(TruckTrailerLink(104, 5307),),
        off_duty_driver_ids=frozenset({7}),
    )
    result = suggest_for_driver(7, context)
    assert (result.truck_id, result.trailer_id) == (104, 5307)
    assert "DRIVER_OFF_DUTY" in result.warnings


def test_home_after_release_default_truck_only_no_trailer_carry_over():
    context = EquipmentContext(
        default_driver_trucks=(DriverTruckLink(7, 104),),
        hooked_trailers=(TruckTrailerLink(104, 5307),),
        off_duty_driver_ids=frozenset({7}),
    )
    result = suggest_for_driver(7, context)
    assert (result.driver_id, result.truck_id, result.trailer_id) == (7, 104, None)
    assert result.truck_source == "default"
    assert "DEFAULT_TRUCK_NOT_CONFIRMED_ATTACHED" in result.warnings


def test_city_driver_no_link_no_silent_equipment_guess():
    assert suggest_for_driver(8, EquipmentContext()) == AssignmentSuggestion(8, None, None)


def test_truck_without_current_driver_never_assumes_default_driver():
    context = EquipmentContext(default_driver_trucks=(DriverTruckLink(7, 104),))
    result = suggest_for_truck(104, context)
    assert result.driver_id is None


def test_truck_with_multiple_current_drivers_requires_choice():
    context = EquipmentContext(
        current_driver_trucks=(DriverTruckLink(7, 104), DriverTruckLink(8, 104)),
        hooked_trailers=(TruckTrailerLink(104, 5307),),
    )
    result = suggest_for_truck(104, context)
    assert result.driver_id is None
    assert result.trailer_id == 5307
    assert "MULTIPLE_CURRENT_DRIVERS" in result.warnings


def test_driver_with_multiple_current_trucks_requires_choice():
    context = EquipmentContext(current_driver_trucks=(DriverTruckLink(7, 104), DriverTruckLink(7, 105)))
    result = suggest_for_driver(7, context)
    assert result.truck_id is None
    assert "MULTIPLE_CURRENT_TRUCKS" in result.warnings


def test_default_truck_taken_by_other_driver_is_not_autofilled():
    context = EquipmentContext(
        default_driver_trucks=(DriverTruckLink(7, 104),),
        current_driver_trucks=(DriverTruckLink(8, 104),),
    )
    result = suggest_for_driver(7, context)
    assert result.truck_id is None
    assert "DEFAULT_TRUCK_CURRENTLY_ATTACHED_TO_OTHER_DRIVER" in result.warnings


def test_inconsistent_hook_status_requires_manual_trailer_choice():
    context = EquipmentContext(
        current_driver_trucks=(DriverTruckLink(7, 104),),
        hooked_trailers=(TruckTrailerLink(104, 5307), TruckTrailerLink(104, 6201)),
    )
    result = suggest_for_driver(7, context)
    assert result.trailer_id is None
    assert "MULTIPLE_HOOKED_TRAILERS" in result.warnings


def test_invalid_identifiers_are_rejected():
    with pytest.raises(ValueError):
        suggest_for_driver(0, EquipmentContext())
    with pytest.raises(ValueError):
        suggest_for_truck(-1, EquipmentContext())
