"""Equipment context wiring for shared assignment policy."""

from app.services.equipment_assignment_policy import (
    DriverTruckLink,
    EquipmentContext,
    TruckTrailerLink,
    suggest_for_driver,
)


def test_policy_wiring_example_boston_carry_trailer():
    ctx = EquipmentContext(
        current_driver_trucks=(DriverTruckLink(1, 10),),
        hooked_trailers=(TruckTrailerLink(10, 20),),
    )
    s = suggest_for_driver(1, ctx)
    assert s.driver_id == 1
    assert s.truck_id == 10
    assert s.trailer_id == 20
