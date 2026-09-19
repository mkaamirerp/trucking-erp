"""Fuel Segment 2: provider control totals as reconciliation evidence, not purchases."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest
from pydantic import ValidationError
from sqlalchemy import Numeric, UniqueConstraint

from app.models.fuel import FuelSourceBatch, FuelSourceControl, FuelTransaction
from app.schemas.fuel import FuelSourceControlHydration, FuelSourceControlOut
from app.services.fuel_canonical import classify_currency
from app.services.fuel_controls import (
    CONTROL_SCOPE_CARD,
    CONTROL_SCOPE_CURRENCY,
    CONTROL_SCOPE_INVOICE,
    CONTROL_SCOPE_UNKNOWN,
    CONTROL_TYPE_CARD_TOTAL,
    CONTROL_TYPE_INVOICE_SUMMARY,
    CONTROL_TYPE_TAX_CONTROL,
    CONTROL_TYPE_UNKNOWN,
    CONTROL_TYPES,
    FuelControlRowError,
    assert_no_source_row_double_count,
    assert_row_may_hydrate_as_transaction,
    classify_control_scope,
    classify_control_type,
    classify_source_row_role,
    purchase_total_from_transactions,
    route_provider_source_rows,
)
from app.services.fuel_money import MONEY_PRECISION, QUANTITY_PRECISION, FuelFloatForbidden


def _numeric(col_name: str) -> Numeric:
    col = FuelSourceControl.__table__.c[col_name]
    assert isinstance(col.type, Numeric)
    return col.type


def test_control_table_is_not_the_transaction_table() -> None:
    assert FuelSourceControl.__tablename__ == "fuel_source_controls"
    assert FuelTransaction.__tablename__ == "fuel_transactions"
    assert FuelSourceControl.__tablename__ != FuelTransaction.__tablename__
    assert FuelSourceControl.__tablename__ != FuelSourceBatch.__tablename__


def test_control_locked_numeric_precision() -> None:
    for col in (
        "declared_amount",
        "tax_amount",
        "hst_amount",
        "gst_amount",
        "pst_amount",
        "qst_amount",
        "discount_amount",
        "pre_tax_amount",
    ):
        assert (_numeric(col).precision, _numeric(col).scale) == MONEY_PRECISION
    assert (_numeric("quantity").precision, _numeric("quantity").scale) == QUANTITY_PRECISION


def test_control_tenant_batch_fk_and_indexes() -> None:
    names = {c.name for c in FuelSourceControl.__table__.constraints if getattr(c, "name", None)}
    assert "uq_fuel_source_controls_tenant_id_id" in names
    assert "fk_fuel_source_controls_batch_tenant" in names
    assert "ck_fuel_source_controls_provider_raw_object" in names
    assert "ck_fuel_source_controls_control_type" in names
    assert "ck_fuel_source_controls_control_scope" in names
    type_ck = [c for c in FuelSourceControl.__table__.constraints if c.name == "ck_fuel_source_controls_control_type"]
    sql = str(type_ck[0].sqltext)
    for code in CONTROL_TYPES:
        assert code in sql
    index_names = {ix.name for ix in FuelSourceControl.__table__.indexes}
    assert "ix_fuel_source_controls_tenant_id" in index_names
    assert "ix_fuel_source_controls_tenant_batch" in index_names
    assert "ix_fuel_source_controls_tenant_type" in index_names
    assert "ix_fuel_source_controls_tenant_currency" in index_names
    row_ix = [
        ix
        for ix in FuelSourceControl.__table__.indexes
        if ix.name == "uq_fuel_source_controls_tenant_batch_source_row_order"
    ]
    assert len(row_ix) == 1
    assert row_ix[0].unique is True


def test_multiple_controls_share_a_batch_without_universal_hierarchy() -> None:
    cols = FuelSourceControl.__table__.c
    assert cols["batch_id"].nullable is False
    assert cols["source_row_order"].nullable is True
    assert cols["control_scope"].nullable is False
    assert cols["scope_card_or_account_id"].nullable is True
    assert cols["scope_unit_number_snapshot"].nullable is True
    assert cols["invoice_number"].nullable is True
    uq_source = [
        c
        for c in FuelSourceControl.__table__.constraints
        if isinstance(c, UniqueConstraint) and c.name == "uq_fuel_source_controls_tenant_batch_source_row_order"
    ]
    assert uq_source == []


def test_control_type_raw_vs_canonical_and_unknown_is_review_capable() -> None:
    raw, canonical = classify_control_type("CARD_TOTAL")
    assert raw == "CARD_TOTAL"
    assert canonical == CONTROL_TYPE_CARD_TOTAL
    raw, canonical = classify_control_type("INVOICE_SUMMARY")
    assert canonical == CONTROL_TYPE_INVOICE_SUMMARY
    raw, canonical = classify_control_type("GST")
    assert raw == "GST"
    assert canonical == CONTROL_TYPE_TAX_CONTROL
    raw, canonical = classify_control_type("WEIRD_FOOTER")
    assert raw == "WEIRD_FOOTER"
    assert canonical == CONTROL_TYPE_UNKNOWN
    assert canonical != CONTROL_TYPE_CARD_TOTAL
    scope_raw, scope = classify_control_scope("card")
    assert scope_raw == "card"
    assert scope == CONTROL_SCOPE_CARD
    scope_raw, scope = classify_control_scope("not-a-scope")
    assert scope_raw == "not-a-scope"
    assert scope == CONTROL_SCOPE_UNKNOWN


def test_card_total_and_invoice_summary_with_money_are_not_purchases() -> None:
    rows = [
        {
            "row_type": "TRANSACTION",
            "source_row_order": 1,
            "total_amount": Decimal("722.7500"),
            "currency_raw": "USD",
        },
        {
            "row_type": "CARD_TOTAL",
            "source_row_order": 2,
            "source_label": "XXXXX87115 Total",
            "control_scope": "CARD",
            "declared_amount": Decimal("1263.8500"),
            "gst_amount": Decimal("145.4000"),
            "currency_raw": "CAD",
        },
        {
            "row_type": "INVOICE_SUMMARY",
            "source_row_order": 3,
            "control_scope": "INVOICE",
            "declared_amount": Decimal("5197.6900"),
            "currency_raw": "USD",
        },
    ]
    routed = route_provider_source_rows(rows)
    assert len(routed["transactions"]) == 1
    assert routed["transactions"][0]["source_row_order"] == 1
    assert {c["control_type"] for c in routed["controls"]} == {
        CONTROL_TYPE_CARD_TOTAL,
        CONTROL_TYPE_INVOICE_SUMMARY,
    }
    purchase = purchase_total_from_transactions(r.get("total_amount") for r in routed["transactions"])
    assert purchase == Decimal("722.7500")
    control_money = [c["declared_amount"] for c in routed["controls"]]
    assert Decimal("1263.8500") in control_money
    assert Decimal("5197.6900") in control_money
    assert purchase != sum(control_money, Decimal("0"))
    card = next(c for c in routed["controls"] if c["control_type"] == CONTROL_TYPE_CARD_TOTAL)
    assert card["gst_amount"] == Decimal("145.4000")
    assert card["requires_review"] is False
    with pytest.raises(FuelControlRowError, match="must not hydrate fuel_transactions"):
        assert_row_may_hydrate_as_transaction(row_type_raw="CARD_TOTAL", amount=Decimal("1263.85"))
    with pytest.raises(FuelControlRowError, match="must not hydrate fuel_transactions"):
        assert_row_may_hydrate_as_transaction(row_type_raw="INVOICE_SUMMARY", amount=Decimal("5197.69"))
    assert_row_may_hydrate_as_transaction(row_type_raw="TRANSACTION", amount=Decimal("722.75"))


def test_nationwide_card_total_label_is_control_even_without_row_type() -> None:
    role = classify_source_row_role(
        source_label="XXXXX87115 Total",
        amount=Decimal("1263.85"),
    )
    assert role == "CONTROL"
    routed = route_provider_source_rows(
        [
            {
                "source_label": "XXXXX07588 Total",
                "source_row_order": 9,
                "control_scope": "CARD",
                "amount": Decimal("722.75"),
                "currency_raw": "USD",
            }
        ]
    )
    assert routed["transactions"] == []
    assert routed["controls"][0]["control_type"] == CONTROL_TYPE_CARD_TOTAL
    assert purchase_total_from_transactions(r.get("total_amount") for r in routed["transactions"]) == Decimal("0.0000")


def test_unknown_control_with_money_is_not_a_purchase() -> None:
    routed = route_provider_source_rows(
        [
            {
                "row_type": "WEIRD_FOOTER",
                "source_row_order": 4,
                "total_amount": Decimal("99.9900"),
                "currency_raw": "USD",
            }
        ]
    )
    assert routed["transactions"] == []
    control = routed["controls"][0]
    assert control["control_type"] == CONTROL_TYPE_UNKNOWN
    assert control["control_type_raw"] == "WEIRD_FOOTER"
    assert control["requires_review"] is True
    assert control["declared_amount"] == Decimal("99.9900")
    assert purchase_total_from_transactions([]) == Decimal("0.0000")
    with pytest.raises(FuelControlRowError):
        assert_row_may_hydrate_as_transaction(row_type_raw="WEIRD_FOOTER", amount=Decimal("99.99"))


def test_same_source_row_cannot_be_transaction_and_control() -> None:
    with pytest.raises(FuelControlRowError, match="both"):
        assert_no_source_row_double_count([1, 2], [2, 3])
    assert_no_source_row_double_count([1, 2], [3, None])
    with pytest.raises(FuelControlRowError, match="both"):
        route_provider_source_rows(
            [
                {"row_type": "TRANSACTION", "source_row_order": 5, "total_amount": Decimal("1.0000")},
                {"row_type": "CARD_TOTAL", "source_row_order": 5, "declared_amount": Decimal("1.0000")},
            ]
        )


def test_control_currency_raw_preserved_and_float_rejected() -> None:
    raw, canonical = classify_currency("CN")
    assert raw == "CN"
    assert canonical == "CAD"
    routed = route_provider_source_rows(
        [
            {
                "row_type": "CURRENCY_TOTAL",
                "control_scope": "CURRENCY",
                "currency_raw": "CN",
                "declared_amount": Decimal("3421.0100"),
                "source_row_order": 8,
            }
        ]
    )
    assert routed["controls"][0]["currency_raw"] == "CN"
    assert routed["controls"][0]["currency"] == "CAD"
    assert routed["controls"][0]["control_scope"] == CONTROL_SCOPE_CURRENCY
    with pytest.raises(FuelFloatForbidden):
        route_provider_source_rows(
            [{"row_type": "CARD_TOTAL", "declared_amount": 1263.85, "control_scope": "CARD"}]
        )
    with pytest.raises(ValidationError):
        FuelSourceControlHydration(
            source_vendor="NATIONWIDE",
            declared_amount=1263.85,  # type: ignore[arg-type]
        )


def test_control_hydration_forbids_purchase_and_derived_fields() -> None:
    assert "total_amount" not in FuelSourceControlHydration.model_fields
    assert "owner_operator_charge_amount" not in FuelSourceControlHydration.model_fields
    source = FuelSourceControlHydration(
        source_vendor="NATIONWIDE",
        control_type_raw="CARD_TOTAL",
        control_scope_raw="CARD",
        control_label_raw="XXXXX87115 Total",
        source_row_order=12,
        source_row_id="card-total-87115",
        currency_raw="CAD",
        declared_amount=Decimal("1263.8500"),
        gst_amount=Decimal("145.4000"),
        provider_raw={"label": "XXXXX87115 Total", "GST": "145.40", "Total": "1263.85"},
    )
    dumped = source.model_dump()
    assert dumped["declared_amount"] == Decimal("1263.8500")
    assert "total_amount" not in dumped
    with pytest.raises(ValidationError):
        FuelSourceControlHydration(
            source_vendor="NATIONWIDE",
            total_amount=Decimal("1263.8500"),
        )


def test_control_out_serializes_decimal_strings_and_raw_sidecar() -> None:
    row = SimpleNamespace(
        id=21,
        tenant_id=53,
        batch_id=4,
        source_vendor="BVD",
        account_reference=None,
        provider_control_identity="invoice-972201-final",
        control_label_raw="Final total",
        control_type_raw="Final total",
        control_type="INVOICE_TOTAL",
        control_scope_raw="invoice",
        control_scope=CONTROL_SCOPE_INVOICE,
        scope_card_or_account_id=None,
        scope_unit_number_snapshot=None,
        scope_product_raw=None,
        invoice_number="972201",
        source_row_order=20,
        source_row_id="bvd-final",
        currency_raw="CN",
        currency="CAD",
        quantity=Decimal("1474.0000"),
        declared_amount=Decimal("3421.0100"),
        tax_amount=Decimal("393.5700"),
        hst_amount=Decimal("393.5700"),
        gst_amount=None,
        pst_amount=None,
        qst_amount=None,
        discount_amount=None,
        pre_tax_amount=Decimal("3027.4400"),
        provider_raw={"Quantity total": "1474.00", "Final total": "3421.01", "CUR": "CN"},
        requires_review=False,
        review_reason=None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    out = FuelSourceControlOut.model_validate(row)
    dumped = out.model_dump(mode="json")
    assert dumped["declared_amount"] == "3421.0100"
    assert dumped["quantity"] == "1474.0000"
    assert dumped["currency_raw"] == "CN"
    assert dumped["currency"] == "CAD"
    assert dumped["provider_raw"]["Final total"] == "3421.01"
    assert dumped["batch_id"] == 4
    assert dumped["id"] == 21


def test_ingestion_rejects_control_after_transaction_same_source_row() -> None:
    from app.services.fuel_ingestion import (
        MemoryFuelIngestionStore,
        hydrate_as_control,
        ingest_source_row,
    )

    store = MemoryFuelIngestionStore()
    ingest_source_row(
        tenant_id=53,
        batch_id=4,
        store=store,
        row={
            "row_type": "TRANSACTION",
            "source_row_order": 7,
            "total_amount": Decimal("722.7500"),
        },
    )
    with pytest.raises(FuelControlRowError, match="already stored as a fuel_transaction"):
        ingest_source_row(
            tenant_id=53,
            batch_id=4,
            store=store,
            row={
                "row_type": "CARD_TOTAL",
                "source_row_order": 7,
                "control_scope": "CARD",
                "declared_amount": Decimal("722.7500"),
            },
        )
    with pytest.raises(FuelControlRowError, match="already stored as a fuel_transaction"):
        hydrate_as_control(
            tenant_id=53,
            batch_id=4,
            store=store,
            row={
                "row_type": "INVOICE_SUMMARY",
                "source_row_order": 7,
                "declared_amount": Decimal("1.0000"),
            },
        )


def test_ingestion_rejects_transaction_after_control_same_source_row() -> None:
    from app.services.fuel_ingestion import (
        MemoryFuelIngestionStore,
        hydrate_as_transaction,
        ingest_source_row,
    )

    store = MemoryFuelIngestionStore()
    ingest_source_row(
        tenant_id=53,
        batch_id=4,
        store=store,
        row={
            "row_type": "CARD_TOTAL",
            "source_row_order": 8,
            "control_scope": "CARD",
            "declared_amount": Decimal("1263.8500"),
        },
    )
    with pytest.raises(FuelControlRowError, match="already stored as a fuel_source_control"):
        ingest_source_row(
            tenant_id=53,
            batch_id=4,
            store=store,
            row={
                "row_type": "TRANSACTION",
                "source_row_order": 8,
                "total_amount": Decimal("1263.8500"),
            },
        )
    with pytest.raises(FuelControlRowError, match="must not hydrate fuel_transactions"):
        hydrate_as_transaction(
            tenant_id=53,
            batch_id=4,
            store=store,
            row={
                "row_type": "CARD_TOTAL",
                "source_row_order": 9,
                "declared_amount": Decimal("10.0000"),
            },
        )
    with pytest.raises(FuelControlRowError, match="already stored as a fuel_source_control"):
        hydrate_as_transaction(
            tenant_id=53,
            batch_id=4,
            store=store,
            row={
                "row_type": "TRANSACTION",
                "source_row_order": 8,
                "total_amount": Decimal("1263.8500"),
            },
        )
    ingest_source_row(
        tenant_id=53,
        batch_id=4,
        store=store,
        row={"row_type": "TRANSACTION", "source_row_order": 10, "total_amount": Decimal("1.0000")},
    )
    assert store.transaction_source_row_exists(53, 4, 10)
    assert not store.control_source_row_exists(53, 4, 10)
