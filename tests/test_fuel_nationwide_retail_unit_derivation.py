"""Nationwide canonical retail unit price derivation (billed + discount/qty)."""

from __future__ import annotations

import uuid
from decimal import Decimal

from app.services.fuel_nationwide_canonical_projection import (
    _build_purchase_transaction,
    _derive_nationwide_retail_unit_price,
)


def _fultonville_effective(**overrides: str) -> dict[str, str]:
    base = {
        "transaction_date": "2026-06-11",
        "volume": "7.21",
        "ex_gst_per_unit": "4.629",
        "total": "33.38",
        "currency": "USD",
        "usa_discount": "5.92",
        "unit_number": "793",
        "card_number": "XXXXX97103",
        "city": "FULTONVILLE",
        "prov_st": "NY",
        "product": "REEFER",
        "network": "TA-Petro",
        "missed_disc": "0.00",
    }
    base.update(overrides)
    return base


def test_nationwide_fultonville_derived_retail_unit_price() -> None:
    txn = _build_purchase_transaction(
        tenant_id=1,
        batch_id=1,
        effective=_fultonville_effective(),
        raw={"source_row_number": 1},
        fuel_nationwide_id=42,
        import_id=uuid.uuid4(),
    )

    assert txn.quantity == Decimal("7.21")
    assert txn.quantity_unit == "gallons"
    assert txn.unit_price == Decimal("4.629000")
    assert txn.billed_amount == Decimal("4.6290")
    assert txn.retail_amount == Decimal("5.4501")
    assert txn.provider_discount_amount == Decimal("5.9200")
    assert txn.total_amount == Decimal("33.3800")
    assert txn.currency == "USD"
    assert txn.provider_raw.get("derived_canonical", {}).get("formula") == (
        "billed_unit_price + provider_discount_amount / quantity"
    )


def test_nationwide_zero_usa_discount_retail_equals_billed() -> None:
    txn = _build_purchase_transaction(
        tenant_id=1,
        batch_id=1,
        effective=_fultonville_effective(usa_discount="0.00"),
        raw={"source_row_number": 1},
        fuel_nationwide_id=43,
        import_id=uuid.uuid4(),
    )

    assert txn.unit_price == Decimal("4.629000")
    assert txn.billed_amount == Decimal("4.6290")
    assert txn.retail_amount == Decimal("4.6290")
    assert txn.provider_discount_amount == Decimal("0.0000")
    assert "derived_canonical" not in txn.provider_raw


def test_nationwide_missing_discount_does_not_fabricate_retail() -> None:
    effective = _fultonville_effective()
    del effective["usa_discount"]

    txn = _build_purchase_transaction(
        tenant_id=1,
        batch_id=1,
        effective=effective,
        raw={"source_row_number": 1},
        fuel_nationwide_id=44,
        import_id=uuid.uuid4(),
    )

    assert txn.billed_amount == Decimal("4.6290")
    assert txn.retail_amount is None


def test_nationwide_zero_quantity_does_not_fabricate_retail() -> None:
    txn = _build_purchase_transaction(
        tenant_id=1,
        batch_id=1,
        effective=_fultonville_effective(volume="0"),
        raw={"source_row_number": 1},
        fuel_nationwide_id=45,
        import_id=uuid.uuid4(),
    )

    assert txn.billed_amount == Decimal("4.6290")
    assert txn.retail_amount is None


def test_derive_helper_formula_matches_fultonville() -> None:
    retail = _derive_nationwide_retail_unit_price(
        billed_unit_price=Decimal("4.629000"),
        quantity=Decimal("7.21"),
        usa_discount_total=Decimal("5.92"),
    )
    assert retail == Decimal("5.450082")
