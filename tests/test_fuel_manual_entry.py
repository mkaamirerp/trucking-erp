"""Manual Fuel Entry — validation, receipt hydration, canonical projection."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.models.fuel import FuelSourceBatch
from app.services.fuel_canonical import BATCH_STATUS_FINALIZED, SOURCE_TYPE_MANUAL_DRIVER
from app.services.fuel_manual_canonical_projection import (
    build_manual_source_batch,
    project_manual_draft_to_transaction,
)
from app.services.fuel_manual_entry_constants import MANUAL_ENTRY_PROVIDER_CODE
from app.services.fuel_manual_entry_validation import (
    FuelManualEntryValidationError,
    validate_and_prepare_draft,
)
from app.services.fuel_manual_receipt_extract import (
    hydrate_draft_from_receipt_extraction,
    loves_fixture_extraction,
    pilot_fixture_extraction,
)
from app.schemas.fuel import (
    fuel_transaction_to_canonical_out,
    fuel_transaction_to_operational_out,
)
from app.services.fuel_nationwide_canonical_projection import finalize_batch
from app.services.fuel_processed_read import _summary_from_batch


def _minimal_draft(**overrides: str) -> dict:
    base = {
        "transaction_date": "2026-09-01",
        "unit_number": "1100",
        "product": "DIESEL",
        "total_amount": "100.00",
        "currency": "USD",
        "entry_method": "DIRECT",
        "field_provenance": {},
        "derived_fields": {},
        "provider_raw": {"entry_method": "DIRECT"},
    }
    base.update(overrides)
    return base


def test_minimum_required_fields_only() -> None:
    draft = validate_and_prepare_draft(_minimal_draft(), strict=True)
    assert draft["total_amount"] == "100.00"
    assert "quantity" not in draft or draft.get("quantity") is None


def test_quantity_price_total_valid() -> None:
    draft = validate_and_prepare_draft(
        _minimal_draft(quantity="10", unit_price="10.50", total_amount="105.00"),
        strict=True,
    )
    assert draft["unit_price"] == "10.50"


def test_derive_price_from_quantity_and_total() -> None:
    draft = validate_and_prepare_draft(
        _minimal_draft(quantity="10", total_amount="105.00"),
        strict=True,
    )
    assert Decimal(draft["unit_price"]) == Decimal("10.50")
    assert draft["derived_fields"]["unit_price"] == "DERIVED"


def test_no_quantity_or_price_allowed() -> None:
    draft = validate_and_prepare_draft(_minimal_draft(), strict=True)
    assert draft.get("quantity") is None
    assert draft.get("unit_price") is None


def test_tax_reconciliation_when_supplied() -> None:
    draft = validate_and_prepare_draft(
        _minimal_draft(
            pre_tax_amount="100.00",
            gst_amount="5.00",
            total_amount="105.00",
            currency="CAD",
        ),
        strict=True,
    )
    assert draft["gst_amount"] == "5.00"


def test_unknown_tax_stays_null() -> None:
    draft = validate_and_prepare_draft(_minimal_draft(), strict=True)
    assert draft.get("gst_amount") is None
    assert draft.get("hst_amount") is None


def test_receipt_loves_projection_maps_canonical_fields() -> None:
    import uuid

    from app.services.fuel_manual_receipt_extract import (
        hydrate_draft_from_receipt_extraction,
        loves_fixture_extraction,
    )

    draft = validate_and_prepare_draft(
        {**hydrate_draft_from_receipt_extraction(loves_fixture_extraction()), "currency": "USD"},
        strict=True,
    )
    stage_id = uuid.uuid4()
    txn = project_manual_draft_to_transaction(
        tenant_id=1,
        batch_id=1,
        stage_id=stage_id,
        draft=draft,
        extraction_raw=loves_fixture_extraction(),
    )
    assert txn.merchant_site == "Love's"
    assert txn.site_number == "790"
    assert txn.quantity is not None
    assert txn.unit_price is not None
    assert txn.billed_amount is not None
    assert txn.retail_amount is not None
    assert txn.pre_tax_amount == Decimal("1050.0200")
    assert txn.provider_transaction_identity == "A255392626"
    assert txn.provider_reference_raw == "99967251"
    assert txn.provider_raw.get("pump") == "24"
    assert txn.provider_raw.get("trailer_number") == "13006"
    assert txn.provider_raw.get("entry_method") == "RECEIPT"


def test_process_projection_populates_canonical_transaction() -> None:
    import uuid

    draft = validate_and_prepare_draft(
        _minimal_draft(quantity="172.445", unit_price="6.089", total_amount="1050.02"),
        strict=True,
    )
    stage_id = uuid.uuid4()
    batch = build_manual_source_batch(
        tenant_id=1,
        stage_id=stage_id,
        draft=draft,
        source_storage_ref=None,
        source_hash=None,
        reviewed_by="tester",
    )
    assert batch.provider_code == MANUAL_ENTRY_PROVIDER_CODE
    assert batch.source_type == SOURCE_TYPE_MANUAL_DRIVER

    txn = project_manual_draft_to_transaction(
        tenant_id=1,
        batch_id=99,
        stage_id=stage_id,
        draft=draft,
        extraction_raw=None,
    )
    assert txn.total_amount == Decimal("1050.0200")
    assert txn.quantity is not None
    assert txn.unit_price is not None
    assert txn.source_vendor == MANUAL_ENTRY_PROVIDER_CODE


def test_processed_summary_includes_manual_entry_provider() -> None:
    batch = FuelSourceBatch(
        tenant_id=1,
        provider_code=MANUAL_ENTRY_PROVIDER_CODE,
        source_type=SOURCE_TYPE_MANUAL_DRIVER,
        status=BATCH_STATUS_FINALIZED,
    )
    batch.id = 1
    summary = _summary_from_batch(batch, transactions=[], controls=[])
    assert summary["provider_code"] == MANUAL_ENTRY_PROVIDER_CODE


def test_loves_receipt_hydration_qty_price_total() -> None:
    draft = hydrate_draft_from_receipt_extraction(loves_fixture_extraction())
    prepared = validate_and_prepare_draft(
        {**draft, "currency": "USD", "unit_number": "1100"},
        strict=True,
    )
    assert prepared["unit_price"] == "6.089"
    assert prepared["total_amount"] == "1050.02"


def test_pilot_receipt_selects_reconciling_price_and_flags_masked_vehicle() -> None:
    draft = hydrate_draft_from_receipt_extraction(pilot_fixture_extraction())
    prepared = validate_and_prepare_draft({**draft, "currency": "CAD"}, strict=False)
    assert prepared["unit_price"] == "2.699"
    raw = prepared.get("provider_raw") or {}
    assert "2.709" in str(raw.get("unit_price_candidates_rejected", []))
    assert prepared.get("requires_review") is True
    assert prepared.get("unit_number") is None
    assert raw.get("vehicle_id_source_evidence") == "XXXX"
    assert "VEHICLE_ID_MASKED" in (prepared.get("review_reasons") or [])


def test_pilot_tax_included_does_not_force_zero_hst_amount() -> None:
    draft = hydrate_draft_from_receipt_extraction(pilot_fixture_extraction())
    assert draft.get("hst_amount") is None
    assert "tax_included_note" in (draft.get("provider_raw") or {})


def test_qty_price_total_mismatch_raises() -> None:
    with pytest.raises(FuelManualEntryValidationError) as exc:
        validate_and_prepare_draft(
            _minimal_draft(quantity="10", unit_price="9.00", total_amount="105.00"),
            strict=True,
        )
    assert exc.value.code == "QTY_PRICE_TOTAL_MISMATCH"


def test_canonical_transaction_dto_exposes_iso_currency() -> None:
    import uuid

    draft = validate_and_prepare_draft(
        {**hydrate_draft_from_receipt_extraction(loves_fixture_extraction()), "currency": "USD"},
        strict=True,
    )
    txn = project_manual_draft_to_transaction(
        tenant_id=1,
        batch_id=1,
        stage_id=uuid.uuid4(),
        draft=draft,
        extraction_raw=loves_fixture_extraction(),
    )
    txn.id = 1
    txn.currency = "USD"
    txn.currency_raw = "USD"
    canonical = fuel_transaction_to_canonical_out(txn)
    assert canonical.currency == "USD"
    assert canonical.currency_raw == "USD"


def test_operational_dto_exposes_receipt_identity_fields() -> None:
    import uuid

    draft = validate_and_prepare_draft(
        {
            **hydrate_draft_from_receipt_extraction(loves_fixture_extraction()),
            "currency": "USD",
            "card_or_account_id": "ending 7145",
        },
        strict=True,
    )
    txn = project_manual_draft_to_transaction(
        tenant_id=1,
        batch_id=1,
        stage_id=uuid.uuid4(),
        draft=draft,
        extraction_raw=loves_fixture_extraction(),
    )
    txn.id = 1
    operational = fuel_transaction_to_operational_out(txn)
    assert operational.provider_transaction_identity == "A255392626"
    assert operational.provider_reference_raw == "99967251"
    assert operational.merchant_site == "Love's"
    assert operational.site_number == "790"
    assert operational.card_or_account_id == "ending 7145"
