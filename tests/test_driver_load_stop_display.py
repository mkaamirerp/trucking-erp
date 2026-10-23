"""Null-safe driver upcoming-load stop display (minimal ready loads, no stops)."""

from types import SimpleNamespace

from app.routers.drivers import _find_load_stop, _normalize_load_stop_type


def test_normalize_load_stop_type_handles_none() -> None:
    assert _normalize_load_stop_type(None) == ""
    assert _normalize_load_stop_type("pickup") == "PICKUP"


def test_find_load_stop_empty_stops() -> None:
    assert _find_load_stop(None, "PICKUP") is None
    assert _find_load_stop([], "PICKUP") is None


def test_find_load_stop_null_stop_type_does_not_crash() -> None:
    stop = SimpleNamespace(stop_type=None, appointment_date=None, city="A", facility_name=None)
    assert _find_load_stop([stop], "PICKUP") is None
    stop_pickup = SimpleNamespace(stop_type="PICKUP", appointment_date="2026-01-01", city="A", facility_name=None)
    found = _find_load_stop([stop, stop_pickup], "PICKUP")
    assert found is stop_pickup
