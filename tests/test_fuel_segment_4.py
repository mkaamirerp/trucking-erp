"""Fuel Segment 4: owner-operator fuel pricing (Decimal, effective-dated)."""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from app.models.fuel import FuelOwnerOperatorPricingRule, FuelTransaction
from app.services.fuel_canonical import SOURCE_HYDRATION_FORBIDDEN_FIELDS
from app.services.fuel_historical_resolution import FuelHistoryOverlapError
from app.services.fuel_money import FuelFloatForbidden
from app.services.fuel_oo_pricing import (
    MODE_FIXED_DISCOUNT,
    MODE_FULL_PROVIDER_DISCOUNT,
    MODE_NO_DISCOUNT,
    MODE_PERCENT_OF_PROVIDER_DISCOUNT,
    PROVIDER_IMMUTABLE_AMOUNT_FIELDS,
    STATUS_CALCULATED,
    STATUS_NOT_APPLICABLE_COMPANY_DRIVER,
    STATUS_REVIEW_AMBIGUOUS_DATE_ONLY,
    STATUS_REVIEW_INVALID_RULE,
    STATUS_REVIEW_MISSING_INPUT,
    STATUS_REVIEW_MISSING_POINT_IN_TIME,
    STATUS_REVIEW_MISSING_RULE,
    STATUS_REVIEW_MULTIPLE_RULES,
    assert_oo_pricing_rules_have_no_overlap,
    assert_proposed_oo_pricing_rule_no_overlap,
    calculate_oo_fuel_charge,
    oo_pricing_result_as_derived_fields,
    price_fuel_transaction_for_oo,
    resolve_oo_pricing_rule,
)


def _dt(y: int, m: int, d: int, hh: int = 0, mm: int = 0) -> datetime:
    return datetime(y, m, d, hh, mm, tzinfo=timezone.utc)


def test_pricing_rule_table_and_txn_provenance_columns() -> None:
    assert FuelOwnerOperatorPricingRule.__tablename__ == "fuel_oo_pricing_rules"
    rule_cols = FuelOwnerOperatorPricingRule.__table__.c
    assert rule_cols["pricing_mode"].nullable is False
    assert rule_cols["effective_from"].nullable is False
    assert rule_cols["effective_to"].nullable is True
    assert rule_cols["fixed_discount_per_unit"].type.precision == 14
    assert rule_cols["fixed_discount_per_unit"].type.scale == 6
    assert rule_cols["percent_of_provider_discount"].type.precision == 10
    assert rule_cols["percent_of_provider_discount"].type.scale == 6

    txn_cols = FuelTransaction.__table__.c
    for name in (
        "oo_pricing_mode",
        "oo_pricing_rule_id",
        "oo_pricing_rule_version",
        "oo_charge_unit_price",
        "oo_benefit_per_unit",
        "oo_pricing_status",
        "oo_pricing_reason",
        "oo_pricing_inputs_json",
        "owner_operator_charge_amount",
    ):
        assert name in txn_cols
        assert name in SOURCE_HYDRATION_FORBIDDEN_FIELDS


def test_example_fixed_discount_concept_from_design() -> None:
    """Pump 3.00, provider disc 0.25, O/O benefit 0.05 → charge 2.95."""
    result = calculate_oo_fuel_charge(
        pricing_mode=MODE_FIXED_DISCOUNT,
        pump_unit_price=Decimal("3.00"),
        quantity=Decimal("100"),
        provider_discount_per_unit=Decimal("0.25"),
        fixed_discount_per_unit=Decimal("0.05"),
        pricing_rule_id=7,
        pricing_rule_version="v1",
    )
    assert result.status == STATUS_CALCULATED
    assert result.pump_unit_price == Decimal("3.000000")
    assert result.provider_discount_per_unit == Decimal("0.250000")
    assert result.provider_cost_per_unit == Decimal("2.750000")
    assert result.oo_benefit_per_unit == Decimal("0.050000")
    assert result.oo_charge_unit_price == Decimal("2.950000")
    assert result.owner_operator_charge_amount == Decimal("295.0000")
    assert result.pricing_rule_id == 7
    assert result.pricing_rule_version == "v1"
    assert result.provider_fields_unchanged is True


def test_all_four_pricing_modes() -> None:
    pump = Decimal("3.00")
    prov = Decimal("0.25")
    qty = Decimal("10")

    none = calculate_oo_fuel_charge(
        pricing_mode=MODE_NO_DISCOUNT,
        pump_unit_price=pump,
        quantity=qty,
        provider_discount_per_unit=prov,
    )
    assert none.oo_benefit_per_unit == Decimal("0.000000")
    assert none.oo_charge_unit_price == Decimal("3.000000")
    assert none.owner_operator_charge_amount == Decimal("30.0000")

    full = calculate_oo_fuel_charge(
        pricing_mode=MODE_FULL_PROVIDER_DISCOUNT,
        pump_unit_price=pump,
        quantity=qty,
        provider_discount_per_unit=prov,
    )
    assert full.oo_benefit_per_unit == Decimal("0.250000")
    assert full.oo_charge_unit_price == Decimal("2.750000")
    assert full.owner_operator_charge_amount == Decimal("27.5000")

    fixed = calculate_oo_fuel_charge(
        pricing_mode=MODE_FIXED_DISCOUNT,
        pump_unit_price=pump,
        quantity=qty,
        provider_discount_per_unit=prov,
        fixed_discount_per_unit=Decimal("0.05"),
    )
    assert fixed.oo_charge_unit_price == Decimal("2.950000")

    pct = calculate_oo_fuel_charge(
        pricing_mode=MODE_PERCENT_OF_PROVIDER_DISCOUNT,
        pump_unit_price=pump,
        quantity=qty,
        provider_discount_per_unit=prov,
        percent_of_provider_discount=Decimal("0.20"),  # 20% of 0.25 = 0.05
    )
    assert pct.oo_benefit_per_unit == Decimal("0.050000")
    assert pct.oo_charge_unit_price == Decimal("2.950000")
    assert pct.owner_operator_charge_amount == Decimal("29.5000")


def test_never_infer_provider_discount() -> None:
    missing = calculate_oo_fuel_charge(
        pricing_mode=MODE_FULL_PROVIDER_DISCOUNT,
        pump_unit_price=Decimal("3.00"),
        quantity=Decimal("1"),
        provider_discount_per_unit=None,
    )
    assert missing.status == STATUS_REVIEW_MISSING_INPUT
    assert missing.reason == "MISSING_PROVIDER_DISCOUNT"
    assert missing.owner_operator_charge_amount is None

    pct_missing = calculate_oo_fuel_charge(
        pricing_mode=MODE_PERCENT_OF_PROVIDER_DISCOUNT,
        pump_unit_price=Decimal("3.00"),
        quantity=Decimal("1"),
        provider_discount_per_unit=None,
        percent_of_provider_discount=Decimal("0.5"),
    )
    assert pct_missing.status == STATUS_REVIEW_MISSING_INPUT


def test_company_driver_no_oo_charge() -> None:
    result = price_fuel_transaction_for_oo(
        owner_operator_payee_id=None,
        ownership_type="company",
        financial_responsibility="company_driver",
        is_company_driver=True,
        transaction_datetime=_dt(2026, 3, 1, 12),
        transaction_date=None,
        pump_unit_price=Decimal("3.00"),
        quantity=Decimal("10"),
        provider_discount_per_unit=Decimal("0.25"),
        rules=[],
    )
    assert result.status == STATUS_NOT_APPLICABLE_COMPANY_DRIVER
    assert result.owner_operator_charge_amount is None
    fields = oo_pricing_result_as_derived_fields(result)
    assert fields["owner_operator_charge_amount"] is None
    assert PROVIDER_IMMUTABLE_AMOUNT_FIELDS.isdisjoint(fields.keys())


def test_effective_dated_rule_resolution_not_today() -> None:
    rules = [
        {
            "id": 1,
            "owner_operator_payee_id": 50,
            "pricing_mode": MODE_NO_DISCOUNT,
            "fixed_discount_per_unit": None,
            "percent_of_provider_discount": None,
            "rule_version": "old",
            "effective_from": _dt(2026, 1, 1),
            "effective_to": _dt(2026, 6, 1),
        },
        {
            "id": 2,
            "owner_operator_payee_id": 50,
            "pricing_mode": MODE_FIXED_DISCOUNT,
            "fixed_discount_per_unit": Decimal("0.05"),
            "percent_of_provider_discount": None,
            "rule_version": "new",
            "effective_from": _dt(2026, 6, 1),
            "effective_to": None,
        },
    ]
    historical = price_fuel_transaction_for_oo(
        owner_operator_payee_id=50,
        ownership_type="owner_operator",
        financial_responsibility="owner_operator",
        is_company_driver=False,
        transaction_datetime=_dt(2026, 3, 15, 10),
        transaction_date=None,
        pump_unit_price=Decimal("3.00"),
        quantity=Decimal("10"),
        provider_discount_per_unit=Decimal("0.25"),
        rules=rules,
    )
    assert historical.status == STATUS_CALCULATED
    assert historical.pricing_rule_id == 1
    assert historical.pricing_mode == MODE_NO_DISCOUNT
    assert historical.oo_charge_unit_price == Decimal("3.000000")

    boundary = price_fuel_transaction_for_oo(
        owner_operator_payee_id=50,
        ownership_type="owner_operator",
        financial_responsibility="owner_operator",
        is_company_driver=False,
        transaction_datetime=_dt(2026, 6, 1, 0),
        transaction_date=None,
        pump_unit_price=Decimal("3.00"),
        quantity=Decimal("10"),
        provider_discount_per_unit=Decimal("0.25"),
        rules=rules,
    )
    assert boundary.pricing_rule_id == 2
    assert boundary.oo_charge_unit_price == Decimal("2.950000")


def test_open_ended_rule_covers_future() -> None:
    rules = [
        {
            "id": 9,
            "owner_operator_payee_id": 1,
            "pricing_mode": MODE_FULL_PROVIDER_DISCOUNT,
            "effective_from": _dt(2025, 1, 1),
            "effective_to": None,
            "rule_version": "open",
        }
    ]
    result = price_fuel_transaction_for_oo(
        owner_operator_payee_id=1,
        ownership_type="owner_operator",
        financial_responsibility="owner_operator",
        is_company_driver=False,
        transaction_datetime=_dt(2026, 9, 1),
        transaction_date=None,
        pump_unit_price=Decimal("3.00"),
        quantity=Decimal("1"),
        provider_discount_per_unit=Decimal("0.25"),
        rules=rules,
    )
    assert result.status == STATUS_CALCULATED
    assert result.oo_charge_unit_price == Decimal("2.750000")


def test_missing_and_multiple_rules_are_review() -> None:
    empty = price_fuel_transaction_for_oo(
        owner_operator_payee_id=99,
        ownership_type="owner_operator",
        financial_responsibility="owner_operator",
        is_company_driver=False,
        transaction_datetime=_dt(2026, 3, 1),
        transaction_date=None,
        pump_unit_price=Decimal("3.00"),
        quantity=Decimal("1"),
        provider_discount_per_unit=Decimal("0.25"),
        rules=[],
    )
    assert empty.status == STATUS_REVIEW_MISSING_RULE

    overlapping = [
        {
            "id": 1,
            "owner_operator_payee_id": 99,
            "pricing_mode": MODE_NO_DISCOUNT,
            "effective_from": _dt(2026, 1, 1),
            "effective_to": None,
        },
        {
            "id": 2,
            "owner_operator_payee_id": 99,
            "pricing_mode": MODE_FIXED_DISCOUNT,
            "fixed_discount_per_unit": Decimal("0.01"),
            "effective_from": _dt(2026, 2, 1),
            "effective_to": None,
        },
    ]
    multi = price_fuel_transaction_for_oo(
        owner_operator_payee_id=99,
        ownership_type="owner_operator",
        financial_responsibility="owner_operator",
        is_company_driver=False,
        transaction_datetime=_dt(2026, 3, 1),
        transaction_date=None,
        pump_unit_price=Decimal("3.00"),
        quantity=Decimal("1"),
        provider_discount_per_unit=Decimal("0.25"),
        rules=overlapping,
    )
    assert multi.status == STATUS_REVIEW_MULTIPLE_RULES
    assert multi.owner_operator_charge_amount is None


def test_date_only_without_provider_timezone_is_review_not_utc_midnight() -> None:
    """DATE_ONLY must not invent UTC midnight to pick a rule."""
    # Rule boundary at 2026-06-01 00:00 UTC. Invented UTC midnight for DATE_ONLY
    # 2026-06-01 would land exactly on the handoff and silently choose rule B.
    rules = [
        {
            "id": 1,
            "owner_operator_payee_id": 5,
            "pricing_mode": MODE_NO_DISCOUNT,
            "effective_from": _dt(2026, 1, 1),
            "effective_to": _dt(2026, 6, 1),
            "rule_version": "pre",
        },
        {
            "id": 2,
            "owner_operator_payee_id": 5,
            "pricing_mode": MODE_FIXED_DISCOUNT,
            "fixed_discount_per_unit": Decimal("0.05"),
            "effective_from": _dt(2026, 6, 1),
            "effective_to": None,
            "rule_version": "post",
        },
    ]
    no_tz = price_fuel_transaction_for_oo(
        owner_operator_payee_id=5,
        ownership_type="owner_operator",
        financial_responsibility="owner_operator",
        is_company_driver=False,
        transaction_datetime=None,
        transaction_date=date(2026, 6, 1),
        provider_timezone=None,
        pump_unit_price=Decimal("3.00"),
        quantity=Decimal("1"),
        provider_discount_per_unit=None,
        rules=rules,
    )
    assert no_tz.status == STATUS_REVIEW_AMBIGUOUS_DATE_ONLY
    assert no_tz.owner_operator_charge_amount is None
    assert no_tz.pricing_rule_id is None

    missing = price_fuel_transaction_for_oo(
        owner_operator_payee_id=5,
        ownership_type="owner_operator",
        financial_responsibility="owner_operator",
        is_company_driver=False,
        transaction_datetime=None,
        transaction_date=None,
        pump_unit_price=Decimal("3.00"),
        quantity=Decimal("1"),
        provider_discount_per_unit=None,
        rules=rules,
    )
    assert missing.status == STATUS_REVIEW_MISSING_POINT_IN_TIME


def test_date_only_with_provider_timezone_requires_full_day_unambiguous_rule() -> None:
    from zoneinfo import ZoneInfo

    toronto = ZoneInfo("America/Toronto")
    # Local handoff at Toronto midnight 2026-06-01 == 2026-06-01 04:00 UTC (EDT).
    local_handoff = datetime(2026, 6, 1, 0, 0, tzinfo=toronto)
    rules = [
        {
            "id": 1,
            "owner_operator_payee_id": 5,
            "pricing_mode": MODE_NO_DISCOUNT,
            "effective_from": datetime(2026, 1, 1, 0, 0, tzinfo=toronto),
            "effective_to": local_handoff,
            "rule_version": "may",
        },
        {
            "id": 2,
            "owner_operator_payee_id": 5,
            "pricing_mode": MODE_FIXED_DISCOUNT,
            "fixed_discount_per_unit": Decimal("0.05"),
            "effective_from": local_handoff,
            "effective_to": None,
            "rule_version": "june",
        },
    ]
    # DATE_ONLY June 1 Toronto: full local day covered only by rule 2.
    june1 = price_fuel_transaction_for_oo(
        owner_operator_payee_id=5,
        ownership_type="owner_operator",
        financial_responsibility="owner_operator",
        is_company_driver=False,
        transaction_datetime=None,
        transaction_date=date(2026, 6, 1),
        provider_timezone="America/Toronto",
        pump_unit_price=Decimal("3.00"),
        quantity=Decimal("10"),
        provider_discount_per_unit=Decimal("0.25"),
        rules=rules,
    )
    assert june1.status == STATUS_CALCULATED
    assert june1.pricing_rule_id == 2
    assert june1.oo_charge_unit_price == Decimal("2.950000")

    # Invented UTC midnight for June 1 would be 2026-06-01 00:00 UTC = still May 31
    # evening in Toronto, which is covered by rule 1 — proving UTC midnight is wrong.
    invented_utc_midnight = _dt(2026, 6, 1, 0)
    assert invented_utc_midnight.astimezone(toronto).date() == date(2026, 5, 31)
    wrong_if_utc = resolve_oo_pricing_rule(
        owner_operator_payee_id=5,
        at=invented_utc_midnight,
        rules=rules,
    )
    assert wrong_if_utc[0] == STATUS_CALCULATED
    assert wrong_if_utc[1]["id"] == 1

    # Mid-day rule change within the source date → REVIEW.
    noon_change = [
        {
            "id": 10,
            "owner_operator_payee_id": 5,
            "pricing_mode": MODE_NO_DISCOUNT,
            "effective_from": datetime(2026, 4, 1, 0, 0, tzinfo=toronto),
            "effective_to": datetime(2026, 4, 15, 12, 0, tzinfo=toronto),
        },
        {
            "id": 11,
            "owner_operator_payee_id": 5,
            "pricing_mode": MODE_FIXED_DISCOUNT,
            "fixed_discount_per_unit": Decimal("0.01"),
            "effective_from": datetime(2026, 4, 15, 12, 0, tzinfo=toronto),
            "effective_to": None,
        },
    ]
    ambiguous = price_fuel_transaction_for_oo(
        owner_operator_payee_id=5,
        ownership_type="owner_operator",
        financial_responsibility="owner_operator",
        is_company_driver=False,
        transaction_datetime=None,
        transaction_date=date(2026, 4, 15),
        provider_timezone="America/Toronto",
        pump_unit_price=Decimal("3.00"),
        quantity=Decimal("1"),
        provider_discount_per_unit=None,
        rules=noon_change,
    )
    assert ambiguous.status == STATUS_REVIEW_AMBIGUOUS_DATE_ONLY


def test_overlap_write_validation_for_pricing_rules() -> None:
    existing = [
        {
            "owner_operator_payee_id": 10,
            "effective_from": _dt(2026, 1, 1),
            "effective_to": _dt(2026, 6, 1),
        }
    ]
    assert_oo_pricing_rules_have_no_overlap(existing)
    with pytest.raises(FuelHistoryOverlapError):
        assert_proposed_oo_pricing_rule_no_overlap(
            proposed={
                "owner_operator_payee_id": 10,
                "effective_from": _dt(2026, 5, 1),
                "effective_to": None,
            },
            existing_rules=existing,
        )
    # Adjacent handoff OK
    assert_proposed_oo_pricing_rule_no_overlap(
        proposed={
            "owner_operator_payee_id": 10,
            "effective_from": _dt(2026, 6, 1),
            "effective_to": None,
        },
        existing_rules=existing,
    )


def test_invalid_percent_and_float_rejected() -> None:
    bad = calculate_oo_fuel_charge(
        pricing_mode=MODE_PERCENT_OF_PROVIDER_DISCOUNT,
        pump_unit_price=Decimal("3.00"),
        quantity=Decimal("1"),
        provider_discount_per_unit=Decimal("0.25"),
        percent_of_provider_discount=Decimal("1.5"),
    )
    assert bad.status == STATUS_REVIEW_INVALID_RULE
    assert bad.reason == "PERCENT_OUT_OF_RANGE"

    with pytest.raises(FuelFloatForbidden):
        calculate_oo_fuel_charge(
            pricing_mode=MODE_NO_DISCOUNT,
            pump_unit_price=3.0,  # noqa: intentional float
            quantity=Decimal("1"),
        )


def test_derived_fields_do_not_touch_provider_amounts() -> None:
    result = calculate_oo_fuel_charge(
        pricing_mode=MODE_FIXED_DISCOUNT,
        pump_unit_price=Decimal("3.00"),
        quantity=Decimal("2"),
        fixed_discount_per_unit=Decimal("0.05"),
        pricing_rule_id=3,
        pricing_rule_version="v2",
    )
    fields = oo_pricing_result_as_derived_fields(result)
    assert fields["oo_pricing_status"] == STATUS_CALCULATED
    assert fields["oo_pricing_rule_id"] == 3
    assert "total_amount" not in fields
    assert "unit_price" not in fields
    assert "retail_amount" not in fields
    assert "currency" not in fields
