"""Manual fuel receipt extraction + hydration acceptance tests."""

from __future__ import annotations

import json
import os
from decimal import Decimal
from pathlib import Path

import pytest

from app.services.fuel_manual_canonical_projection import project_manual_draft_to_transaction
from app.services.fuel_manual_entry_validation import validate_and_prepare_draft
from app.services.fuel_manual_receipt_extract import (
    extract_manual_fuel_receipt_from_upload,
    hydrate_draft_from_receipt_extraction,
    loves_fixture_extraction,
    pilot_fixture_extraction,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "fuel_manual_receipt"


def _hydrated_from_fixture_text(name: str) -> dict:
    raw = (FIXTURES / name).read_bytes()
    extraction = extract_manual_fuel_receipt_from_upload(raw, name)
    return hydrate_draft_from_receipt_extraction(extraction)


def test_loves_text_extraction_and_hydration() -> None:
    draft = _hydrated_from_fixture_text("loves_receipt.txt")
    assert draft["merchant_site"] == "Love's"
    assert draft["quantity"] == "172.445"
    assert draft["quantity_unit"] == "gallons"
    assert draft["unit_price"] == "6.089"
    assert draft["total_amount"] == "1050.02"
    assert draft["unit_number"] == "1100"
    assert draft["pump"] == "24"
    assert draft["receipt_ticket_number"] == "99967251"
    assert draft["authorization_number"] == "A255392626"
    assert draft["trailer_number"] == "13006"
    assert draft["invoice_reference"] == "41868"
    assert "currency" not in draft or not draft.get("currency")
    assert "CURRENCY_NOT_ON_RECEIPT" in (draft.get("review_reasons") or [])


def test_pilot_text_extraction_price_reconciliation_and_masked_unit() -> None:
    draft = _hydrated_from_fixture_text("pilot_receipt.txt")
    assert draft["merchant_site"] == "Pilot"
    assert draft["quantity"] == "397.399"
    assert draft["unit_price"] == "2.699"
    assert draft["total_amount"] == "1072.58"
    assert draft.get("unit_number") is None
    raw = draft.get("provider_raw") or {}
    assert raw.get("vehicle_id_source_evidence") == "XXXX"
    assert "2.709" in str(raw.get("unit_price_candidates_rejected", []))
    assert "tax_included_note" in raw
    assert "HST" in raw["tax_included_note"]
    assert draft.get("hst_amount") is None
    assert raw.get("printed_sales_tax") == "0.00"
    assert "VEHICLE_ID_MASKED" in (draft.get("review_reasons") or [])


def test_loves_structured_fixture_hydration() -> None:
    draft = hydrate_draft_from_receipt_extraction(loves_fixture_extraction())
    prepared = validate_and_prepare_draft({**draft, "currency": "USD"}, strict=True)
    assert prepared["unit_price"] == "6.089"
    assert prepared["total_amount"] == "1050.02"


def test_pilot_structured_fixture_reconciles_2_699() -> None:
    draft = hydrate_draft_from_receipt_extraction(pilot_fixture_extraction())
    assert draft["unit_price"] == "2.699"
    raw = draft.get("provider_raw") or {}
    assert "2.709" in str(raw.get("unit_price_candidates_rejected", []))
    assert draft.get("unit_number") is None
    assert raw.get("vehicle_id_source_evidence") == "XXXX"


def test_pilot_tax_included_note_not_zero_hst() -> None:
    draft = hydrate_draft_from_receipt_extraction(pilot_fixture_extraction())
    assert draft.get("hst_amount") is None
    assert "tax_included_note" in (draft.get("provider_raw") or {})


def test_receipt_upload_extract_hydrates_draft_fields() -> None:
    extraction = extract_manual_fuel_receipt_from_upload(
        (FIXTURES / "loves_receipt.txt").read_bytes(),
        "loves_receipt.txt",
    )
    assert extraction.get("parser_version")
    assert extraction.get("raw_text")
    draft = hydrate_draft_from_receipt_extraction(extraction)
    assert draft["entry_method"] == "RECEIPT"
    assert draft["product"]
    assert draft["total_amount"]


def test_process_path_from_pilot_hydrated_draft() -> None:
    import uuid

    draft = hydrate_draft_from_receipt_extraction(pilot_fixture_extraction())
    prepared = validate_and_prepare_draft(
        {**draft, "currency": "CAD", "unit_number": "1100"},
        strict=True,
    )
    txn = project_manual_draft_to_transaction(
        tenant_id=1,
        batch_id=1,
        stage_id=uuid.uuid4(),
        draft=prepared,
        extraction_raw=pilot_fixture_extraction(),
    )
    assert txn.unit_price == Decimal("2.699000")
    assert txn.total_amount == Decimal("1072.5800")
    assert txn.unit_number_snapshot == "1100"


@pytest.mark.asyncio
@pytest.mark.skipif(not os.environ.get("OPENAI_API_KEY"), reason="OPENAI_API_KEY required")
async def test_loves_mobile_jpg_openai_extraction() -> None:
    from app.services.fuel_manual_receipt_extract import (
        extract_manual_fuel_receipt_from_upload_async,
        hydrate_draft_from_receipt_extraction,
    )

    raw = (FIXTURES / "loves_receipt_mobile.jpg").read_bytes()
    extraction = await extract_manual_fuel_receipt_from_upload_async(raw, "loves_receipt_mobile.jpg")
    assert extraction.get("extraction_method", "").startswith("openai")
    draft = hydrate_draft_from_receipt_extraction(extraction)
    assert draft.get("merchant_site") and "love" in draft["merchant_site"].lower()
    assert draft.get("quantity") == "172.445" or draft.get("total_amount") == "1050.02"
    assert draft.get("unit_number") == "1100" or draft.get("receipt_ticket_number")


def test_loves_mobile_jpg_fixture_present() -> None:
    path = FIXTURES / "loves_receipt_mobile.jpg"
    assert path.is_file()
    assert path.stat().st_size > 10_000


def test_show_hydrated_drafts_json_for_acceptance() -> None:
    """Documents acceptance payloads (not a behavioral assertion)."""
    loves = _hydrated_from_fixture_text("loves_receipt.txt")
    pilot = _hydrated_from_fixture_text("pilot_receipt.txt")
    # Keep keys stable for human review in test output when needed.
    assert json.dumps(loves, default=str)
    assert json.dumps(pilot, default=str)
