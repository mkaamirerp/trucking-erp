"""Fuel Segment 3: historical truck / ownership / card-account resolution."""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from app.models.fuel import FuelCardAccountAssignment
from app.models.truck_history import TruckOwnershipHistory, TruckUnitNumberHistory
from app.services.fuel_historical_resolution import (
    STATUS_RESOLVED,
    STATUS_REVIEW_MISSING_INPUT,
    STATUS_REVIEW_MULTIPLE_MATCH,
    STATUS_REVIEW_ZERO_MATCH,
    resolve_card_account_assignment,
    resolve_fuel_transaction_historical_links,
    resolve_ownership_at,
    resolve_truck_from_unit_history,
    resolution_point_in_time,
)


def _dt(y: int, m: int, d: int, hh: int = 0, mm: int = 0) -> datetime:
    return datetime(y, m, d, hh, mm, tzinfo=timezone.utc)


def test_history_tables_exist_with_effective_dating() -> None:
    assert TruckUnitNumberHistory.__tablename__ == "truck_unit_number_history"
    assert TruckOwnershipHistory.__tablename__ == "truck_ownership_history"
    assert FuelCardAccountAssignment.__tablename__ == "fuel_card_account_assignments"
    for model in (TruckUnitNumberHistory, TruckOwnershipHistory, FuelCardAccountAssignment):
        cols = model.__table__.c
        assert cols["effective_from"].nullable is False
        assert cols["effective_to"].nullable is True
        assert "tenant_id" in cols


def test_unit_history_resolves_exact_truck_and_ignores_current_unit() -> None:
    history = [
        {
            "id": 1,
            "truck_id": 100,
            "unit_number": "1100",
            "effective_from": _dt(2026, 1, 1),
            "effective_to": _dt(2026, 6, 1),
        },
        {
            "id": 2,
            "truck_id": 100,
            "unit_number": "2100",
            "effective_from": _dt(2026, 6, 1),
            "effective_to": None,
        },
        {
            "id": 3,
            "truck_id": 200,
            "unit_number": "1100",
            "effective_from": _dt(2026, 6, 1),
            "effective_to": None,
        },
    ]
    early = resolve_truck_from_unit_history(
        unit_number_snapshot="1100",
        at=_dt(2026, 3, 15, 12),
        history_rows=history,
        current_trucks_by_unit={"1100": 999},
    )
    assert early.status == STATUS_RESOLVED
    assert early.value["truck_id"] == 100
    late = resolve_truck_from_unit_history(
        unit_number_snapshot="1100",
        at=_dt(2026, 7, 1),
        history_rows=history,
        current_trucks_by_unit={"1100": 100},
    )
    assert late.status == STATUS_RESOLVED
    assert late.value["truck_id"] == 200
    missing = resolve_truck_from_unit_history(
        unit_number_snapshot="9999",
        at=_dt(2026, 7, 1),
        history_rows=history,
        current_trucks_by_unit={"9999": 555},
    )
    assert missing.status == STATUS_REVIEW_ZERO_MATCH
    assert missing.requires_review is True


def test_unit_history_multiple_match_is_review() -> None:
    history = [
        {
            "id": 1,
            "truck_id": 100,
            "unit_number": "788",
            "effective_from": _dt(2026, 1, 1),
            "effective_to": None,
        },
        {
            "id": 2,
            "truck_id": 101,
            "unit_number": "788",
            "effective_from": _dt(2026, 1, 1),
            "effective_to": None,
        },
    ]
    out = resolve_truck_from_unit_history(
        unit_number_snapshot="788",
        at=_dt(2026, 6, 9),
        history_rows=history,
    )
    assert out.status == STATUS_REVIEW_MULTIPLE_MATCH
    assert set(out.matched_ids) == {100, 101}


def test_ownership_resolves_by_transaction_time_not_current() -> None:
    history = [
        {
            "id": 10,
            "truck_id": 100,
            "ownership_type": "company",
            "owner_operator_payee_id": None,
            "effective_from": _dt(2025, 1, 1),
            "effective_to": _dt(2026, 5, 1),
        },
        {
            "id": 11,
            "truck_id": 100,
            "ownership_type": "owner_operator",
            "owner_operator_payee_id": 77,
            "effective_from": _dt(2026, 5, 1),
            "effective_to": None,
        },
    ]
    before = resolve_ownership_at(
        truck_id=100,
        at=_dt(2026, 4, 30, 23),
        history_rows=history,
        current_ownership={"ownership_type": "owner_operator", "owner_operator_payee_id": 77},
    )
    assert before.status == STATUS_RESOLVED
    assert before.value["ownership_type"] == "company"
    assert before.value["owner_operator_payee_id"] is None
    after = resolve_ownership_at(
        truck_id=100,
        at=_dt(2026, 5, 1, 0),
        history_rows=history,
        current_ownership={"ownership_type": "company", "owner_operator_payee_id": None},
    )
    assert after.status == STATUS_RESOLVED
    assert after.value["ownership_type"] == "owner_operator"
    assert after.value["owner_operator_payee_id"] == 77


def test_card_assignment_later_move_does_not_rewrite_history() -> None:
    rows = [
        {
            "id": 1,
            "provider_code": "NATIONWIDE",
            "account_reference": "20250522B",
            "card_or_account_id": "XXXXX07588",
            "truck_id": 794,
            "driver_id": 10,
            "owner_operator_payee_id": 50,
            "effective_from": _dt(2026, 1, 1),
            "effective_to": _dt(2026, 6, 10),
        },
        {
            "id": 2,
            "provider_code": "NATIONWIDE",
            "account_reference": "20250522B",
            "card_or_account_id": "XXXXX07588",
            "truck_id": 900,
            "driver_id": 11,
            "owner_operator_payee_id": 51,
            "effective_from": _dt(2026, 6, 10),
            "effective_to": None,
        },
    ]
    historical = resolve_card_account_assignment(
        provider_code="NATIONWIDE",
        card_or_account_id="XXXXX07588",
        account_reference="20250522B",
        at=_dt(2026, 6, 8),
        assignment_rows=rows,
        current_assignment={"truck_id": 900, "driver_id": 11},
    )
    assert historical.status == STATUS_RESOLVED
    assert historical.value["truck_id"] == 794
    assert historical.value["driver_id"] == 10
    assert historical.value["owner_operator_payee_id"] == 50
    current_day = resolve_card_account_assignment(
        provider_code="NATIONWIDE",
        card_or_account_id="XXXXX07588",
        account_reference="20250522B",
        at=_dt(2026, 6, 11),
        assignment_rows=rows,
    )
    assert current_day.value["truck_id"] == 900
    none = resolve_card_account_assignment(
        provider_code="NATIONWIDE",
        card_or_account_id="MISSING",
        account_reference=None,
        at=_dt(2026, 6, 8),
        assignment_rows=rows,
        current_assignment={"truck_id": 1},
    )
    assert none.status == STATUS_REVIEW_ZERO_MATCH


def test_date_only_transaction_uses_date_probe_not_current_fallback() -> None:
    at = resolution_point_in_time(
        transaction_datetime=None,
        transaction_date=date(2026, 6, 8),
    )
    assert at == _dt(2026, 6, 8)
    history = [
        {
            "id": 1,
            "truck_id": 794,
            "unit_number": "794",
            "effective_from": _dt(2026, 1, 1),
            "effective_to": None,
        }
    ]
    out = resolve_truck_from_unit_history(
        unit_number_snapshot="794",
        at=at,
        history_rows=history,
        current_trucks_by_unit={"794": 1},
    )
    assert out.status == STATUS_RESOLVED
    assert out.value["truck_id"] == 794


def test_combined_resolution_requires_review_when_unit_missing() -> None:
    result = resolve_fuel_transaction_historical_links(
        unit_number_snapshot=None,
        card_or_account_id="XXXXX07588",
        source_vendor="NATIONWIDE",
        account_reference=None,
        transaction_datetime=_dt(2026, 6, 8, 14),
        transaction_date=date(2026, 6, 8),
        unit_history_rows=[],
        ownership_history_rows=[],
        card_assignment_rows=[],
        current_trucks_by_unit={"794": 1},
    )
    assert result["truck"].status == STATUS_REVIEW_MISSING_INPUT
    assert result["ownership"].status == STATUS_REVIEW_MISSING_INPUT
    assert result["card_assignment"].status == STATUS_REVIEW_ZERO_MATCH


def test_half_open_boundary_exact_handoff_is_deterministic() -> None:
    """At effective_to of row A / effective_from of row B, only B covers."""
    from app.services.fuel_historical_resolution import interval_covers

    boundary = _dt(2026, 6, 1, 0)
    row_a = {
        "id": 1,
        "truck_id": 100,
        "unit_number": "1100",
        "effective_from": _dt(2026, 1, 1),
        "effective_to": boundary,
    }
    row_b = {
        "id": 2,
        "truck_id": 200,
        "unit_number": "1100",
        "effective_from": boundary,
        "effective_to": None,
    }
    assert interval_covers(row_a, _dt(2026, 5, 31, 23, 59)) is True
    assert interval_covers(row_a, boundary) is False
    assert interval_covers(row_b, boundary) is True
    at_boundary = resolve_truck_from_unit_history(
        unit_number_snapshot="1100",
        at=boundary,
        history_rows=[row_a, row_b],
    )
    assert at_boundary.status == STATUS_RESOLVED
    assert at_boundary.value["truck_id"] == 200
    just_before = resolve_truck_from_unit_history(
        unit_number_snapshot="1100",
        at=_dt(2026, 5, 31, 23, 59),
        history_rows=[row_a, row_b],
    )
    assert just_before.value["truck_id"] == 100


def test_open_ended_period_covers_future_points() -> None:
    history = [
        {
            "id": 1,
            "truck_id": 100,
            "ownership_type": "owner_operator",
            "owner_operator_payee_id": 77,
            "effective_from": _dt(2026, 1, 1),
            "effective_to": None,
        }
    ]
    out = resolve_ownership_at(truck_id=100, at=_dt(2099, 1, 1), history_rows=history)
    assert out.status == STATUS_RESOLVED
    assert out.value["owner_operator_payee_id"] == 77


def test_overlap_write_validation_rejects_same_key_overlap_not_adjacent() -> None:
    from app.services.fuel_historical_resolution import (
        FuelHistoryOverlapError,
        HISTORY_KIND_CARD,
        HISTORY_KIND_OWNERSHIP,
        HISTORY_KIND_UNIT,
        assert_history_rows_have_no_overlap,
        assert_proposed_history_row_no_overlap,
        intervals_overlap,
    )

    assert intervals_overlap(_dt(2026, 1, 1), _dt(2026, 6, 1), _dt(2026, 6, 1), None) is False
    assert intervals_overlap(_dt(2026, 1, 1), None, _dt(2026, 3, 1), _dt(2026, 4, 1)) is True

    overlapping_unit = [
        {
            "id": 1,
            "truck_id": 100,
            "unit_number": "1100",
            "effective_from": _dt(2026, 1, 1),
            "effective_to": _dt(2026, 7, 1),
        },
        {
            "id": 2,
            "truck_id": 200,
            "unit_number": "1100",
            "effective_from": _dt(2026, 6, 1),
            "effective_to": None,
        },
    ]
    with pytest.raises(FuelHistoryOverlapError, match="unit_number"):
        assert_history_rows_have_no_overlap(overlapping_unit, kind=HISTORY_KIND_UNIT)

    # Same truck with two overlapping unit numbers is also invalid.
    overlapping_truck_units = [
        {
            "id": 1,
            "truck_id": 100,
            "unit_number": "1100",
            "effective_from": _dt(2026, 1, 1),
            "effective_to": None,
        },
        {
            "id": 2,
            "truck_id": 100,
            "unit_number": "2100",
            "effective_from": _dt(2026, 3, 1),
            "effective_to": None,
        },
    ]
    with pytest.raises(FuelHistoryOverlapError, match="truck_id"):
        assert_history_rows_have_no_overlap(overlapping_truck_units, kind=HISTORY_KIND_UNIT)

    adjacent_ok = [
        {
            "id": 1,
            "truck_id": 100,
            "unit_number": "1100",
            "effective_from": _dt(2026, 1, 1),
            "effective_to": _dt(2026, 6, 1),
        },
        {
            "id": 2,
            "truck_id": 100,
            "unit_number": "2100",
            "effective_from": _dt(2026, 6, 1),
            "effective_to": None,
        },
    ]
    assert_history_rows_have_no_overlap(adjacent_ok, kind=HISTORY_KIND_UNIT)

    with pytest.raises(FuelHistoryOverlapError, match="ownership"):
        assert_proposed_history_row_no_overlap(
            kind=HISTORY_KIND_OWNERSHIP,
            proposed={
                "id": 99,
                "truck_id": 100,
                "ownership_type": "company",
                "effective_from": _dt(2026, 4, 1),
                "effective_to": None,
            },
            existing_rows=[
                {
                    "id": 1,
                    "truck_id": 100,
                    "ownership_type": "owner_operator",
                    "effective_from": _dt(2026, 1, 1),
                    "effective_to": None,
                }
            ],
        )

    with pytest.raises(FuelHistoryOverlapError, match="card"):
        assert_history_rows_have_no_overlap(
            [
                {
                    "id": 1,
                    "provider_code": "BVD",
                    "account_reference": None,
                    "card_or_account_id": "4237111",
                    "effective_from": _dt(2026, 1, 1),
                    "effective_to": None,
                },
                {
                    "id": 2,
                    "provider_code": "BVD",
                    "account_reference": None,
                    "card_or_account_id": "4237111",
                    "effective_from": _dt(2026, 2, 1),
                    "effective_to": _dt(2026, 3, 1),
                },
            ],
            kind=HISTORY_KIND_CARD,
        )


def test_overlap_at_resolution_time_is_review_never_silent_pick() -> None:
    history = [
        {
            "id": 1,
            "truck_id": 100,
            "unit_number": "1100",
            "effective_from": _dt(2026, 1, 1),
            "effective_to": _dt(2026, 8, 1),
        },
        {
            "id": 2,
            "truck_id": 200,
            "unit_number": "1100",
            "effective_from": _dt(2026, 5, 1),
            "effective_to": None,
        },
    ]
    out = resolve_truck_from_unit_history(
        unit_number_snapshot="1100",
        at=_dt(2026, 6, 1),
        history_rows=history,
    )
    assert out.status == STATUS_REVIEW_MULTIPLE_MATCH
    assert set(out.matched_ids) == {100, 200}
