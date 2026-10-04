"""Manual Fuel Entry — provider-neutral intake constants."""

from __future__ import annotations

from typing import Final

MANUAL_ENTRY_PROVIDER_CODE = "MANUAL_ENTRY"

ENTRY_METHOD_DIRECT = "DIRECT"
ENTRY_METHOD_RECEIPT = "RECEIPT"
ENTRY_METHODS: Final[frozenset[str]] = frozenset({ENTRY_METHOD_DIRECT, ENTRY_METHOD_RECEIPT})

PROVENANCE_MANUAL = "MANUAL"
PROVENANCE_RECEIPT_EXTRACTED = "RECEIPT_EXTRACTED"
PROVENANCE_DERIVED = "DERIVED"
PROVENANCE_ADMIN_CORRECTED = "ADMIN_CORRECTED"

STAGE_STATUS_ACTIVE = "ACTIVE"
STAGE_STATUS_PROCESSED = "PROCESSED"
STAGE_STATUS_DISCARDED = "DISCARDED"

REQUIRED_DRAFT_FIELDS: Final[tuple[str, ...]] = (
    "transaction_date",
    "unit_number",
    "product",
    "total_amount",
    "currency",
)

OPTIONAL_DRAFT_FIELDS: Final[tuple[str, ...]] = (
    "transaction_time",
    "driver_name",
    "merchant_site",
    "merchant_network",
    "processing_network",
    "city",
    "province_state",
    "country",
    "quantity",
    "quantity_unit",
    "retail_unit_price",
    "unit_price",
    "pre_tax_amount",
    "provider_discount_amount",
    "gst_amount",
    "hst_amount",
    "pst_amount",
    "qst_amount",
    "card_or_account_id",
    "receipt_ticket_number",
    "authorization_number",
    "pump",
    "invoice_reference",
    "trailer_number",
    "notes",
)
