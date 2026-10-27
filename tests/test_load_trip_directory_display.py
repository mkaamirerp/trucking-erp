"""Read-model trip driver label. Does not write Load assignment columns."""

from app.services.loads import trip_driver_display_name


def test_trip_driver_display_name_joins_first_and_last() -> None:
    assert trip_driver_display_name("Pat", "Driver") == "Pat Driver"


def test_trip_driver_display_name_blank_when_trip_has_no_driver() -> None:
    assert trip_driver_display_name(None, None) is None
    assert trip_driver_display_name("  ", "") is None
