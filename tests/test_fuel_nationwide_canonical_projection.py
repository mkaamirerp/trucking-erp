"""Nationwide provider-native rows -> TruckERP canonical projection."""

from __future__ import annotations

import uuid
from decimal import Decimal
from pathlib import Path

from app.services.fuel_nationwide_canonical_projection import (
    FuelNationwideCanonicalProjectionError,
    assert_nationwide_canonical_money_gate,
    build_fuel_source_batch,
    project_nationwide_rows_to_canonical,
)
from app.services.fuel_nationwide_effective import build_effective_nationwide_rows
from app.services.fuel_nationwide_extraction import extract_nationwide_rows_from_digital_pdf
from app.services.fuel_nationwide_import import ROW_HEADER, ROW_TRANSACTION
from app.services.fuel_nationwide_source_reconciliation import reconcile_nationwide_source_rows


REPO = Path(__file__).resolve().parents[1]
NW_PDF = REPO / "docs" / "fixtures" / "fuel" / "nationwide_fuel.pdf"


def _project_fixture():
    extracted, _warnings, _version = extract_nationwide_rows_from_digital_pdf(
        NW_PDF.read_bytes()
    )

    import_id = uuid.uuid4()

    raw_rows = []
    for i, row in enumerate(extracted, start=1):
        raw_rows.append(
            {
                "id": i,
                "stage_id": str(import_id),
                "row_type": row.row_type,
                "source_page": row.source_page,
                "source_row_number": i,
                **row.fields,
            }
        )

    effective_rows = build_effective_nationwide_rows(raw_rows)

    header = next(r for r in effective_rows if r["row_type"] == ROW_HEADER)

    batch = build_fuel_source_batch(
        tenant_id=53,
        import_id=import_id,
        header=header,
        source_hash="test-sha",
        source_storage_ref="test-key",
        parser_version="NATIONWIDE:test",
        reviewed_by="pytest",
    )
    batch.id = 1

    id_map = {int(r["id"]): 1000 + int(r["id"]) for r in raw_rows}

    txns, controls = project_nationwide_rows_to_canonical(
        tenant_id=53,
        batch=batch,
        import_id=import_id,
        raw_rows=raw_rows,
        effective_rows=effective_rows,
        fuel_nationwide_id_by_stage_row_id=id_map,
    )

    return batch, txns, controls


def test_nationwide_canonical_batch_dates_preserve_source_semantics() -> None:
    batch, _, _ = _project_fixture()

    assert batch.invoice_number == "20250522B-06142026"
    assert batch.invoice_date is None
    assert batch.statement_start.isoformat() == "2026-06-08"
    assert batch.statement_end.isoformat() == "2026-06-14"
    assert batch.due_date.isoformat() == "2026-06-15"


def test_nationwide_canonical_quantity_and_price_semantics() -> None:
    _, txns, _ = _project_fixture()

    assert len(txns) == 12

    cad = [t for t in txns if t.currency == "CAD"]
    usd = [t for t in txns if t.currency == "USD"]

    assert len(cad) == 1
    assert len(usd) == 11

    assert all(t.quantity_unit == "litres" for t in cad)
    assert all(t.unit_price_basis == "EX_TAX" for t in cad)

    assert all(t.quantity_unit == "gallons" for t in usd)
    assert all(t.unit_price_basis == "FINAL_GALLON_PRICE" for t in usd)

    assert sum(t.total_amount or Decimal("0") for t in cad) == Decimal("1263.85")
    assert sum(t.total_amount or Decimal("0") for t in usd) == Decimal("5197.67")


def test_nationwide_canonical_known_rows() -> None:
    _, txns, _ = _project_fixture()

    cad = next(t for t in txns if t.currency == "CAD")
    assert cad.unit_number_snapshot == "788"
    assert cad.quantity == Decimal("674.1700")
    assert cad.quantity_unit == "litres"
    assert cad.unit_price == Decimal("1.659000")
    assert cad.unit_price_basis == "EX_TAX"
    assert cad.total_amount == Decimal("1263.8500")
    assert cad.merchant_network == "Esso"

    usd = next(
        t
        for t in txns
        if t.unit_number_snapshot == "794"
        and t.currency == "USD"
    )
    assert usd.quantity == Decimal("154.2700")
    assert usd.quantity_unit == "gallons"
    assert usd.unit_price == Decimal("4.685000")
    assert usd.unit_price_basis == "FINAL_GALLON_PRICE"
    assert usd.provider_discount_amount == Decimal("34.5600")
    assert usd.total_amount == Decimal("722.7500")


def test_nationwide_canonical_controls_preserve_structured_card_facts() -> None:
    _, _, controls = _project_fixture()

    usd_card = next(
        c
        for c in controls
        if c.control_type == "CARD_TOTAL"
        and c.scope_card_or_account_id == "XXXXX07588"
    )
    assert usd_card.currency == "USD"
    assert usd_card.quantity == Decimal("154.2700")
    assert usd_card.discount_amount == Decimal("34.5600")
    assert usd_card.declared_amount == Decimal("722.7500")

    cad_card = next(
        c
        for c in controls
        if c.control_type == "CARD_TOTAL"
        and c.scope_card_or_account_id == "XXXXX87195"
        and c.currency == "CAD"
    )
    assert cad_card.quantity == Decimal("674.1700")
    assert cad_card.gst_amount == Decimal("145.4000")
    assert cad_card.discount_amount == Decimal("0.0000")
    assert cad_card.declared_amount == Decimal("1263.8500")


def test_nationwide_total_volume_control_is_structured_quantity() -> None:
    _, _, controls = _project_fixture()

    volume = next(
        c
        for c in controls
        if c.control_type == "UNIT_SUBTOTAL"
        and c.control_label_raw == "Total Volume 674.17"
    )

    assert volume.quantity == Decimal("674.1700")


def test_nationwide_canonical_gate_proves_source_controls_survive() -> None:
    _batch, txns, controls = _project_fixture()

    extracted, _warnings, _version = extract_nationwide_rows_from_digital_pdf(
        NW_PDF.read_bytes()
    )
    raw = []
    for i, row in enumerate(extracted, start=1):
        raw.append(
            {
                "id": i,
                "row_type": row.row_type,
                **row.fields,
            }
        )
    effective = build_effective_nationwide_rows(raw)
    reconciliation = reconcile_nationwide_source_rows(effective)
    assert reconciliation.passed is True

    assert_nationwide_canonical_money_gate(
        txns,
        controls,
        expected_transaction_count=12,
        source_reconciliation=reconciliation,
    )


def test_nationwide_canonical_gate_rejects_lost_usd_control() -> None:
    _, txns, controls = _project_fixture()

    extracted, _warnings, _version = extract_nationwide_rows_from_digital_pdf(
        NW_PDF.read_bytes()
    )
    raw = []
    for i, row in enumerate(extracted, start=1):
        raw.append(
            {
                "id": i,
                "row_type": row.row_type,
                **row.fields,
            }
        )
    effective = build_effective_nationwide_rows(raw)
    reconciliation = reconcile_nationwide_source_rows(effective)
    assert reconciliation.passed is True

    controls = [
        c
        for c in controls
        if not (c.control_type == "CURRENCY_TOTAL" and c.currency == "USD")
    ]

    import pytest

    with pytest.raises(
        FuelNationwideCanonicalProjectionError,
        match="USD CURRENCY_TOTAL",
    ):
        assert_nationwide_canonical_money_gate(
            txns,
            controls,
            expected_transaction_count=12,
            source_reconciliation=reconciliation,
        )


def test_nationwide_canonical_gate_rejects_one_missing_card_control() -> None:
    _, txns, controls = _project_fixture()

    extracted, _warnings, _version = extract_nationwide_rows_from_digital_pdf(
        NW_PDF.read_bytes()
    )

    raw = []
    for i, row in enumerate(extracted, start=1):
        raw.append(
            {
                "id": i,
                "row_type": row.row_type,
                **row.fields,
            }
        )

    effective = build_effective_nationwide_rows(raw)
    reconciliation = reconcile_nationwide_source_rows(effective)

    assert reconciliation.passed is True
    assert len(reconciliation.card_controls) > 1

    removed = False
    reduced_controls = []

    for control in controls:
        if (
            not removed
            and control.control_type == "CARD_TOTAL"
            and control.currency == "USD"
        ):
            removed = True
            continue

        reduced_controls.append(control)

    assert removed is True

    import pytest

    with pytest.raises(
        FuelNationwideCanonicalProjectionError,
        match="CARD_TOTAL controls do not match",
    ):
        assert_nationwide_canonical_money_gate(
            txns,
            reduced_controls,
            expected_transaction_count=12,
            source_reconciliation=reconciliation,
        )
