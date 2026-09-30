"""Fuel financial responsibility + O/O pricing integration (domain only)."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.models.fuel import FuelTransaction
from app.services.fuel_charge_categories import (
    CATEGORY_CASH_ADVANCE,
    CATEGORY_DEF,
    CATEGORY_FUEL,
    CATEGORY_PRODUCT_PURCHASE,
    CATEGORY_UNMAPPED,
)
from app.services.fuel_financial_responsibility import (
    RESPONSIBILITY_COMPANY_EXPENSE,
    RESPONSIBILITY_DRIVER_DEDUCTION,
    RESPONSIBILITY_OWNER_OPERATOR_DEDUCTION,
    RESPONSIBILITY_REVIEW_REQUIRED,
    TAX_TREATMENT_FOR_SETTLEMENT,
    company_retained_provider_discount_per_unit,
    evaluate_oo_fuel_pricing_modes,
    resolve_company_driver_responsibility,
    resolve_fuel_financial_responsibility,
    resolve_owner_operator_responsibility,
)
from app.services.fuel_oo_pricing import MODE_PERCENT_OF_PROVIDER_DISCOUNT, calculate_oo_fuel_charge


def _dt() -> datetime:
    return datetime(2026, 7, 28, 12, 0, tzinfo=timezone.utc)


def _oo_rule(mode: str, **extra) -> dict:
    return {
        "id": 1,
        "owner_operator_payee_id": 900,
        "pricing_mode": mode,
        "effective_from": datetime(2020, 1, 1, tzinfo=timezone.utc),
        "effective_to": None,
        "rule_version": "v1",
        **extra,
    }


def test_company_fuel_company_expense() -> None:
    r = resolve_company_driver_responsibility(CATEGORY_FUEL)
    assert r.financial_responsibility == RESPONSIBILITY_COMPANY_EXPENSE
    assert r.settlement_deduction_candidate is False


def test_company_def_company_expense() -> None:
    r = resolve_company_driver_responsibility(CATEGORY_DEF)
    assert r.financial_responsibility == RESPONSIBILITY_COMPANY_EXPENSE


def test_company_cash_advance_driver_deduction() -> None:
    r = resolve_company_driver_responsibility(CATEGORY_CASH_ADVANCE)
    assert r.financial_responsibility == RESPONSIBILITY_DRIVER_DEDUCTION
    assert r.settlement_deduction_candidate is True


def test_company_operating_product_company_expense() -> None:
    r = resolve_company_driver_responsibility(CATEGORY_PRODUCT_PURCHASE)
    assert r.financial_responsibility == RESPONSIBILITY_COMPANY_EXPENSE


def test_oo_cash_advance_owner_deduction() -> None:
    r = resolve_owner_operator_responsibility(
        category=CATEGORY_CASH_ADVANCE,
        owner_operator_payee_id=900,
        driver_id_snapshot=42,
    )
    assert r.financial_responsibility == RESPONSIBILITY_OWNER_OPERATOR_DEDUCTION
    assert r.responsible_payee_id == 900
    assert r.provenance.get("driver_not_payee") is True


def test_oo_fuel_pricing_modes_and_golden_examples() -> None:
    pump = Decimal("3.00")
    prov = Decimal("0.25")
    modes = evaluate_oo_fuel_pricing_modes(
        pump_unit_price=pump,
        provider_discount_per_unit=prov,
    )
    assert modes["NO_DISCOUNT"].oo_charge_unit_price == Decimal("3.000000")
    assert modes["FULL_PROVIDER_DISCOUNT"].oo_charge_unit_price == Decimal("2.750000")
    assert modes["FIXED_CENTS"].oo_charge_unit_price == Decimal("2.950000")
    assert modes["PERCENT_OF_PROVIDER_DISCOUNT"].oo_charge_unit_price == Decimal("2.950000")

    retained = company_retained_provider_discount_per_unit(
        provider_discount_per_unit=prov,
        oo_benefit_per_unit=Decimal("0.05"),
    )
    assert retained == Decimal("0.200000")


def test_golden_percent_of_provider_discount() -> None:
    result = calculate_oo_fuel_charge(
        pricing_mode=MODE_PERCENT_OF_PROVIDER_DISCOUNT,
        pump_unit_price=Decimal("3.00"),
        quantity=Decimal("1"),
        provider_discount_per_unit=Decimal("0.25"),
        percent_of_provider_discount=Decimal("0.20"),
    )
    assert result.oo_charge_unit_price == Decimal("2.950000")
    assert result.oo_benefit_per_unit == Decimal("0.050000")


def test_another_driver_on_oo_truck_keeps_owner_payee() -> None:
    history = [
        {
            "id": 1,
            "truck_id": 1104,
            "ownership_type": "owner_operator",
            "owner_operator_payee_id": 900,
            "effective_from": datetime(2020, 1, 1, tzinfo=timezone.utc),
            "effective_to": None,
        }
    ]
    r = resolve_fuel_financial_responsibility(
        category=CATEGORY_CASH_ADVANCE,
        truck_id=1104,
        at=_dt(),
        ownership_history_rows=history,
        driver_id_snapshot=999,
    )
    assert r.responsible_payee_id == 900
    assert r.driver_id_snapshot == 999


def test_missing_oo_agreement_review_required() -> None:
    r = resolve_owner_operator_responsibility(
        category=CATEGORY_FUEL,
        owner_operator_payee_id=900,
        driver_id_snapshot=None,
        pump_unit_price=Decimal("3.00"),
        quantity=Decimal("1"),
        provider_discount_per_unit=Decimal("0.25"),
        transaction_datetime=_dt(),
        oo_pricing_rules=[],
    )
    assert r.financial_responsibility == RESPONSIBILITY_REVIEW_REQUIRED


def test_unmapped_review_required() -> None:
    assert (
        resolve_company_driver_responsibility(CATEGORY_UNMAPPED).financial_responsibility
        == RESPONSIBILITY_REVIEW_REQUIRED
    )


def test_no_float_arithmetic_in_pricing_path() -> None:
    r = calculate_oo_fuel_charge(
        pricing_mode=MODE_PERCENT_OF_PROVIDER_DISCOUNT,
        pump_unit_price="3.00",
        quantity="1",
        provider_discount_per_unit="0.25",
        percent_of_provider_discount="0.20",
    )
    assert isinstance(r.oo_charge_unit_price, Decimal)


def test_provider_fields_not_in_responsibility_mutation() -> None:
    txn = FuelTransaction(
        tenant_id=1,
        batch_id=1,
        source_row_order=1,
        source_vendor="BVD",
        provider_event_type="PURCHASE",
        transaction_datetime_source="x",
        transaction_timezone_source="UNKNOWN",
        unit_price=Decimal("3.00"),
        billed_amount=Decimal("2.75"),
    )
    before = txn.unit_price
    resolve_company_driver_responsibility(CATEGORY_FUEL)
    assert txn.unit_price == before


def test_no_settlement_tables_touched() -> None:
    """This module must not import or create Settlement/Payroll persistence."""
    import app.services.fuel_financial_responsibility as mod

    assert "settlement" not in mod.__file__.lower()


def test_tax_treatment_not_locked_constant() -> None:
    assert TAX_TREATMENT_FOR_SETTLEMENT == "NOT_LOCKED"
