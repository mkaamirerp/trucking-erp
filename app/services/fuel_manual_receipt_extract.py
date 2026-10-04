"""Manual Fuel Entry — receipt hydration interface (no auto-Process).

OCR is not implemented in this slice. Structured extraction payloads (tests / future
parser) hydrate the shared draft. Uploaded files are stored on the stage as evidence.
"""

from __future__ import annotations

from typing import Any, Mapping

from app.services.fuel_manual_entry_constants import (
    ENTRY_METHOD_RECEIPT,
    PROVENANCE_RECEIPT_EXTRACTED,
)
from app.services.fuel_manual_entry_validation import select_reconciling_unit_price
from app.services.fuel_money import to_optional_decimal

PARSER_VERSION = "manual_receipt_v0_stub"


def hydrate_draft_from_receipt_extraction(
    extraction: Mapping[str, Any],
    *,
    entry_method: str = ENTRY_METHOD_RECEIPT,
) -> dict[str, Any]:
    """Map structured receipt extraction → manual entry draft (shared form shape)."""
    provenance: dict[str, str] = {}
    provider_raw: dict[str, Any] = {
        "entry_method": entry_method,
        "receipt_extraction": dict(extraction),
    }

    def set_field(key: str, value: Any, source: str = PROVENANCE_RECEIPT_EXTRACTED) -> None:
        if value is None:
            return
        text = str(value).strip()
        if not text:
            return
        fields[key] = text
        provenance[key] = source

    fields: dict[str, Any] = {}
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
    set_field("unit_number", extraction.get("unit_number"))

    currency = extraction.get("currency")
    if currency is not None and str(currency).strip():
        set_field("currency", currency)

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
            fields["unit_price"] = format(winner, "f")
            provenance["unit_price"] = "RECEIPT_RECONCILED"
            provider_raw["unit_price_candidates_rejected"] = [format(r, "f") for r in rejected]
        else:
            fields["requires_review"] = True
            fields.setdefault("review_reasons", []).append("UNIT_PRICE_CANDIDATES_UNRECONCILED")

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
        "unit_number": "XXXX",
        "tax_included_note": "13% HST is included in the posted price per litre",
    }
