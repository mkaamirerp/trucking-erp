"""Manual Fuel Entry — receipt OCR/parse → shared draft hydration (never auto-Process)."""

from __future__ import annotations

from typing import Any, Mapping

from app.services.fuel_manual_entry_constants import (
    ENTRY_METHOD_RECEIPT,
    PROVENANCE_RECEIPT_EXTRACTED,
)
from app.services.fuel_manual_entry_validation import select_reconciling_unit_price
from app.services.fuel_manual_receipt_mask import is_masked_vehicle_id
from app.services.fuel_manual_receipt_ocr import receipt_text_from_upload
from app.services.fuel_manual_receipt_parse import parse_receipt_text
from app.services.fuel_money import to_optional_decimal

PARSER_VERSION = "manual_receipt_v1"
PARSER_VERSION_AI = "manual_receipt_v1_openai"


def extract_manual_fuel_receipt_from_upload(
    file_bytes: bytes,
    filename: str | None,
) -> dict[str, Any]:
    """Heuristic OCR/parse only (deterministic tests). Production uses async variant."""
    text, ocr_warnings = receipt_text_from_upload(file_bytes, filename)
    parsed = parse_receipt_text(text)
    return _package_extraction(
        file_bytes,
        filename,
        parsed=parsed,
        ocr_warnings=ocr_warnings,
        raw_text=text,
        extraction_method="heuristic",
        parser_version=PARSER_VERSION,
    )


async def extract_manual_fuel_receipt_from_upload_async(
    file_bytes: bytes,
    filename: str | None,
) -> dict[str, Any]:
    """OCR + heuristic parse; merges OpenAI extraction when API key is configured."""
    from app.services.fuel_manual_receipt_ai import (
        extract_receipt_fields_via_openai,
        openai_configured,
    )

    text, ocr_warnings = receipt_text_from_upload(file_bytes, filename)
    parsed_heuristic = parse_receipt_text(text)
    parsed = dict(parsed_heuristic)
    extraction_method = "heuristic"
    parser_version = PARSER_VERSION
    ai_warnings: list[str] = []

    if openai_configured():
        try:
            ai_fields = await extract_receipt_fields_via_openai(file_bytes, filename, text)
            if ai_fields:
                parsed = _merge_extraction(parsed_heuristic, ai_fields)
                extraction_method = "openai+heuristic"
                parser_version = PARSER_VERSION_AI
        except Exception as exc:  # noqa: BLE001 — fallback to heuristic
            ai_warnings.append(f"openai_extract_failed: {type(exc).__name__}")

    warnings = list(ocr_warnings) + ai_warnings
    return _package_extraction(
        file_bytes,
        filename,
        parsed=parsed,
        ocr_warnings=warnings,
        raw_text=text,
        extraction_method=extraction_method,
        parser_version=parser_version,
    )


def _merge_extraction(heuristic: dict[str, Any], ai: dict[str, Any]) -> dict[str, Any]:
    """AI wins on non-null fields; heuristic fills gaps."""
    out = dict(heuristic)
    for key, val in ai.items():
        if val is None:
            continue
        if isinstance(val, list) and not val:
            continue
        if isinstance(val, str) and not val.strip():
            continue
        out[key] = val
    return out


def _package_extraction(
    file_bytes: bytes,
    filename: str | None,
    *,
    parsed: dict[str, Any],
    ocr_warnings: list[str],
    raw_text: str,
    extraction_method: str,
    parser_version: str,
) -> dict[str, Any]:
    _ = file_bytes, filename
    return {
        **parsed,
        "parser_version": parser_version,
        "extraction_method": extraction_method,
        "raw_text": raw_text,
        "ocr_warnings": ocr_warnings,
    }


def hydrate_draft_from_receipt_extraction(
    extraction: Mapping[str, Any],
    *,
    entry_method: str = ENTRY_METHOD_RECEIPT,
) -> dict[str, Any]:
    """Map structured receipt extraction → manual entry draft (shared form shape)."""
    provenance: dict[str, str] = {}
    provider_raw: dict[str, Any] = {
        "entry_method": entry_method,
        "receipt_extraction": {k: v for k, v in extraction.items() if k != "raw_text"},
    }
    if extraction.get("raw_text"):
        provider_raw["receipt_source_text"] = extraction.get("raw_text")

    def set_field(key: str, value: Any, source: str = PROVENANCE_RECEIPT_EXTRACTED) -> None:
        if value is None:
            return
        text = str(value).strip()
        if not text:
            return
        fields[key] = text
        provenance[key] = source

    fields: dict[str, Any] = {}
    review_reasons: list[str] = []
    requires_review = False

    set_field("transaction_date", extraction.get("transaction_date"))
    set_field("transaction_time", extraction.get("transaction_time"))
    set_field("merchant_site", extraction.get("vendor") or extraction.get("merchant_site"))
    set_field("merchant_network", extraction.get("store_number") or extraction.get("merchant_network"))
    set_field("city", extraction.get("city"))
    set_field("province_state", extraction.get("province_state"))
    set_field("product", extraction.get("product"))
    set_field("quantity", extraction.get("quantity"))
    set_field("quantity_unit", extraction.get("quantity_unit"))
    set_field("pre_tax_amount", extraction.get("pre_tax_amount") or extraction.get("subtotal"))
    set_field("total_amount", extraction.get("total_amount") or extraction.get("final_total"))
    set_field("card_or_account_id", extraction.get("card"))
    set_field("receipt_ticket_number", extraction.get("receipt_ticket_number") or extraction.get("receipt_number"))
    set_field("authorization_number", extraction.get("authorization_number"))
    set_field("pump", extraction.get("pump"))
    set_field("invoice_reference", extraction.get("invoice_reference") or extraction.get("invoice_number"))
    set_field("trailer_number", extraction.get("trailer_number"))
    set_field("notes", extraction.get("notes"))
    if extraction.get("company"):
        provider_raw["company_name"] = str(extraction.get("company"))

    vehicle_raw = extraction.get("vehicle_id") or extraction.get("unit_number")
    if vehicle_raw:
        vehicle_s = str(vehicle_raw).strip()
        if is_masked_vehicle_id(vehicle_s):
            provider_raw["vehicle_id_source_evidence"] = vehicle_s
            requires_review = True
            review_reasons.append("VEHICLE_ID_MASKED")
        else:
            set_field("unit_number", vehicle_s)

    currency = extraction.get("currency")
    if currency is not None and str(currency).strip():
        set_field("currency", currency)
    else:
        requires_review = True
        review_reasons.append("CURRENCY_NOT_ON_RECEIPT")

    candidates = extraction.get("unit_price_candidates") or []
    if extraction.get("unit_price") and not candidates:
        set_field("unit_price", extraction.get("unit_price"))
    elif candidates:
        provider_raw["unit_price_candidates"] = [str(c) for c in candidates]
        qty = to_optional_decimal(extraction.get("quantity"))
        total = to_optional_decimal(fields.get("total_amount"))
        prices = [to_optional_decimal(c) for c in candidates]
        prices = [p for p in prices if p is not None]
        winner, rejected = select_reconciling_unit_price(qty, prices, total)
        if winner is not None:
            fields["unit_price"] = format(winner.normalize(), "f")
            provenance["unit_price"] = "RECEIPT_RECONCILED"
            provider_raw["unit_price_candidates_rejected"] = [
                format(r.normalize(), "f") for r in rejected if r is not None
            ]
        else:
            requires_review = True
            review_reasons.append("UNIT_PRICE_CANDIDATES_UNRECONCILED")

    tax_note = extraction.get("tax_included_note") or extraction.get("tax_note")
    if tax_note:
        provider_raw["tax_included_note"] = str(tax_note)
    printed_sales_tax = extraction.get("printed_sales_tax")
    if printed_sales_tax is not None:
        provider_raw["printed_sales_tax"] = str(printed_sales_tax)

    # Do not map printed 0.00 sales tax to gst/hst when tax is included in posted price.
    if extraction.get("gst_amount"):
        set_field("gst_amount", extraction.get("gst_amount"))
    if extraction.get("hst_amount"):
        set_field("hst_amount", extraction.get("hst_amount"))

    fields["field_provenance"] = provenance
    fields["provider_raw"] = provider_raw
    fields["entry_method"] = entry_method
    if requires_review:
        fields["requires_review"] = True
    if review_reasons:
        fields["review_reasons"] = review_reasons
    return fields


def loves_fixture_extraction() -> dict[str, Any]:
    return {
        "vendor": "Love's",
        "store_number": "790",
        "city": "Summerton",
        "province_state": "SC",
        "transaction_date": "2026-09-12",
        "receipt_ticket_number": "99967251",
        "product": "TRKDS / diesel",
        "pump": "24",
        "quantity": "172.445",
        "quantity_unit": "gallons",
        "unit_price": "6.089",
        "pre_tax_amount": "1050.02",
        "printed_sales_tax": "0.00",
        "total_amount": "1050.02",
        "card": "ending 7145",
        "authorization_number": "A255392626",
        "unit_number": "1100",
        "trailer_number": "13006",
        "invoice_reference": "41868",
    }


def pilot_fixture_extraction() -> dict[str, Any]:
    return {
        "vendor": "Pilot",
        "store_number": "862",
        "city": "Ayr",
        "province_state": "ON",
        "transaction_date": "2026-09-18",
        "receipt_number": "6404935",
        "product": "Truck Diesel",
        "pump": "18",
        "quantity": "397.399",
        "quantity_unit": "litres",
        "unit_price_candidates": ["2.699", "2.709"],
        "pre_tax_amount": "1072.58",
        "printed_sales_tax": "0.00",
        "total_amount": "1072.58",
        "card": "ending 7002",
        "authorization_number": "153118",
        "vehicle_id": "XXXX",
        "tax_included_note": "13% HST is included in the posted price per litre",
    }
