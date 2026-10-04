"""Manual Fuel Entry → fuel_source_batches + fuel_transactions."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Mapping

from app.models.fuel import FuelSourceBatch, FuelTransaction
from app.services.fuel_canonical import (
    BATCH_STATUS_PROCESSING,
    PROVIDER_EVENT_PURCHASE,
    SOURCE_TYPE_MANUAL_DRIVER,
    TZ_SOURCE_DATE_ONLY,
    classify_currency,
    interpret_provider_timestamp,
)
from app.services.fuel_manual_entry_constants import (
    ENTRY_METHOD_DIRECT,
    MANUAL_ENTRY_PROVIDER_CODE,
    PROVENANCE_MANUAL,
)
from app.services.fuel_money import quantize_money, quantize_quantity, quantize_unit_price, to_optional_decimal
from app.services.fuel_nationwide_canonical_projection import finalize_batch

ROW_REVIEW_CONFIRMED = "CONFIRMED"


class FuelManualCanonicalProjectionError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _parse_date(raw: str | None) -> date | None:
    if not raw:
        return None
    text = raw.strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _money_field(draft: Mapping[str, Any], key: str) -> Decimal | None:
    val = to_optional_decimal(draft.get(key))
    return quantize_money(val) if val is not None else None


def build_manual_source_batch(
    *,
    tenant_id: int,
    stage_id: uuid.UUID,
    draft: Mapping[str, Any],
    source_storage_ref: str | None,
    source_hash: str | None,
    reviewed_by: str,
    imported_at: datetime | None = None,
) -> FuelSourceBatch:
    now = imported_at or datetime.now(timezone.utc)
    provider_raw = dict(draft.get("provider_raw") or {})
    entry_method = str(draft.get("entry_method") or provider_raw.get("entry_method") or ENTRY_METHOD_DIRECT)
    provider_raw["entry_method"] = entry_method
    invoice_ref = (draft.get("invoice_reference") or "").strip() or None
    return FuelSourceBatch(
        tenant_id=tenant_id,
        provider_code=MANUAL_ENTRY_PROVIDER_CODE,
        source_type=SOURCE_TYPE_MANUAL_DRIVER,
        invoice_number=invoice_ref,
        invoice_date=_parse_date(str(draft.get("transaction_date") or "")),
        statement_start=_parse_date(str(draft.get("transaction_date") or "")),
        statement_end=_parse_date(str(draft.get("transaction_date") or "")),
        account_reference=(draft.get("card_or_account_id") or "").strip() or None,
        source_storage_ref=source_storage_ref,
        source_hash=source_hash,
        source_import_ref=str(stage_id),
        imported_at=now,
        parser_rule_version="manual_entry_v1",
        provider_profile_code=MANUAL_ENTRY_PROVIDER_CODE,
        status=BATCH_STATUS_PROCESSING,
        reviewed_by=reviewed_by,
        reviewed_at=now,
        created_by=reviewed_by,
    )


def project_manual_draft_to_transaction(
    *,
    tenant_id: int,
    batch_id: int,
    stage_id: uuid.UUID,
    draft: Mapping[str, Any],
    extraction_raw: Mapping[str, Any] | None,
) -> FuelTransaction:
    total = _money_field(draft, "total_amount")
    if total is None:
        raise FuelManualCanonicalProjectionError("TOTAL_REQUIRED", "final amount required to process")

    tx_date = _parse_date(str(draft.get("transaction_date") or ""))
    time_part = (draft.get("transaction_time") or "").strip()
    datetime_source = f"{draft.get('transaction_date')} {time_part}".strip()
    ts = interpret_provider_timestamp(
        source_text=datetime_source or str(draft.get("transaction_date")),
        timezone_source=TZ_SOURCE_DATE_ONLY,
        parsed_date=tx_date,
    )

    cur_raw, cur_iso = classify_currency(str(draft.get("currency") or ""))
    if cur_iso is None:
        raise FuelManualCanonicalProjectionError("CURRENCY_REQUIRED", "currency must map to known ISO code")

    provider_raw: dict[str, Any] = {
        "manual_entry_stage_id": str(stage_id),
        "field_provenance": dict(draft.get("field_provenance") or {}),
        "derived_fields": dict(draft.get("derived_fields") or {}),
        "review_reasons": list(draft.get("review_reasons") or []),
    }
    base = dict(draft.get("provider_raw") or {})
    provider_raw.update(base)
    if extraction_raw:
        provider_raw["receipt_extraction_raw"] = dict(extraction_raw)

    qty_raw = to_optional_decimal(draft.get("quantity"))
    qty = quantize_quantity(qty_raw) if qty_raw is not None else None
    unit_price_raw = to_optional_decimal(draft.get("unit_price"))
    unit_price = quantize_unit_price(unit_price_raw) if unit_price_raw is not None else None
    retail_raw = to_optional_decimal(draft.get("retail_unit_price"))
    retail = quantize_money(retail_raw) if retail_raw is not None else None

    requires_review = bool(draft.get("requires_review"))
    review_reason = None
    reasons = draft.get("review_reasons") or []
    if reasons:
        review_reason = str(reasons[0])

    return FuelTransaction(
        tenant_id=tenant_id,
        batch_id=batch_id,
        source_row_order=1,
        source_row_id=str(stage_id),
        source_vendor=MANUAL_ENTRY_PROVIDER_CODE,
        provider_event_type_raw="PURCHASE",
        provider_event_type=PROVIDER_EVENT_PURCHASE,
        unit_number_snapshot=(draft.get("unit_number") or "").strip() or None,
        card_or_account_id=(draft.get("card_or_account_id") or "").strip() or None,
        driver_name_snapshot=(draft.get("driver_name") or "").strip() or None,
        merchant_site=(draft.get("merchant_site") or "").strip() or None,
        city=(draft.get("city") or "").strip() or None,
        province_state=(draft.get("province_state") or "").strip() or None,
        country=(draft.get("country") or "").strip() or None,
        product=(draft.get("product") or "").strip() or None,
        product_code_raw=(draft.get("product") or "").strip() or None,
        quantity=qty,
        quantity_unit=(draft.get("quantity_unit") or "").strip() or None,
        unit_price=unit_price,
        unit_price_basis="EX_TAX" if unit_price is not None else None,
        currency_raw=cur_raw,
        currency=cur_iso,
        processing_network=(draft.get("processing_network") or "").strip() or None,
        merchant_network=(draft.get("merchant_network") or "").strip() or None,
        provider_discount_amount=_money_field(draft, "provider_discount_amount"),
        pre_tax_amount=_money_field(draft, "pre_tax_amount"),
        gst_amount=_money_field(draft, "gst_amount"),
        hst_amount=_money_field(draft, "hst_amount"),
        pst_amount=_money_field(draft, "pst_amount"),
        qst_amount=_money_field(draft, "qst_amount"),
        retail_amount=retail,
        billed_amount=unit_price,
        total_amount=total,
        provider_transaction_identity=(draft.get("authorization_number") or draft.get("receipt_ticket_number") or "").strip()
        or None,
        provider_reference_raw=(draft.get("receipt_ticket_number") or draft.get("invoice_reference") or "").strip()
        or None,
        provider_reason_raw=(draft.get("notes") or "").strip() or None,
        provider_raw={
            **provider_raw,
            "pump": (draft.get("pump") or "").strip() or None,
            "trailer_number": (draft.get("trailer_number") or "").strip() or None,
        },
        review_status=ROW_REVIEW_CONFIRMED,
        requires_review=requires_review,
        review_reason=review_reason,
        parsed_row_role="TRANSACTION",
        **ts,
    )


__all__ = ["build_manual_source_batch", "finalize_batch", "project_manual_draft_to_transaction"]
