"""Tracing metadata on generated pay run items (reference_code + optional load trip read-model).

Tests the helper only. In generate_pay_run, load resolution uses a transitional
numeric reference_code → load id rule; see docs/PAYROLL_TRIP_TRACING.md.
"""

from types import SimpleNamespace

from app.routers.pay_runs import _pay_run_item_metadata


def test_metadata_reference_only_when_no_load():
    entry = SimpleNamespace(reference_code="ABC-1")
    assert _pay_run_item_metadata(entry, None) == {"reference_code": "ABC-1"}


def test_metadata_includes_trip_when_load_provided():
    entry = SimpleNamespace(reference_code="42")
    load = SimpleNamespace(id=42, trip_number="T-100", active_dispatch_trip_id=99)
    assert _pay_run_item_metadata(entry, load) == {
        "reference_code": "42",
        "load_id": 42,
        "trip_number": "T-100",
        "dispatch_trip_id": 99,
    }


def test_metadata_omits_empty_trip_fields():
    entry = SimpleNamespace(reference_code="x")
    load = SimpleNamespace(id=1, trip_number=None, active_dispatch_trip_id=None)
    assert _pay_run_item_metadata(entry, load) == {"reference_code": "x", "load_id": 1}
