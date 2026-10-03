"""Nationwide Process → fuel_source_batches + fuel_transactions + fuel_source_controls."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Mapping

from app.models.fuel import FuelSourceBatch, FuelSourceControl, FuelTransaction
from app.services.fuel_canonical import (
    BATCH_STATUS_FINALIZED,
    BATCH_STATUS_PROCESSING,
    PROVIDER_EVENT_PURCHASE,
    SOURCE_TYPE_PDF,
    TZ_SOURCE_DATE_ONLY,
    TZ_SOURCE_UNKNOWN,
    classify_currency,
    interpret_provider_timestamp,
)
from app.services.fuel_controls import (
    CONTROL_SCOPE_CARD,
    CONTROL_SCOPE_CURRENCY,
    CONTROL_SCOPE_INVOICE,
    CONTROL_SCOPE_STATEMENT,
    CONTROL_SCOPE_TAX,
    CONTROL_TYPE_CARD_TOTAL,
    CONTROL_TYPE_CURRENCY_TOTAL,
    CONTROL_TYPE_INVOICE_SUMMARY,
    CONTROL_TYPE_INVOICE_TOTAL,
    CONTROL_TYPE_PROVIDER_DECLARED_TOTAL,
    CONTROL_TYPE_STATEMENT_TOTAL,
    CONTROL_TYPE_TAX_CONTROL,
    CONTROL_TYPE_UNIT_SUBTOTAL,
)
from app.services.fuel_money import (
    quantize_money,
    quantize_quantity,
    quantize_unit_price,
    to_optional_decimal,
)
from app.services.fuel_nationwide_import import (
    NATIONWIDE_PROVIDER_CODE,
    NATIONWIDE_SOURCE_FIELD_NAMES,
    ROW_CONTROL,
    ROW_HEADER,
    ROW_TRANSACTION,
)
from app.services.fuel_nationwide_source_reconciliation import parse_nationwide_decimal

NATIONWIDE_VENDOR = NATIONWIDE_PROVIDER_CODE
CLASSIFICATION_STATUS_UNMAPPED = "UNMAPPED"


class FuelNationwideCanonicalProjectionError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _row_get(row: Mapping[str, Any], key: str) -> str | None:
    val = row.get(key)
    if val is None or val == "":
        return None
    return str(val)


def _money_decimal(raw: Any) -> Decimal | None:
    dec, err = parse_nationwide_decimal(raw)
    if err or dec is None:
        return None
    return quantize_money(dec)


def _quantity_decimal(raw: Any) -> Decimal | None:
    dec, err = parse_nationwide_decimal(raw)
    if err or dec is None:
        return None
    return quantize_quantity(dec)


def _unit_price_decimal(raw: Any) -> Decimal | None:
    dec, err = parse_nationwide_decimal(raw)
    if err or dec is None:
        return None
    return quantize_unit_price(dec)


def _parsed_discount_total(raw: Any) -> Decimal | None:
    if raw is None:
        return None
    if isinstance(raw, str) and raw.strip() == "":
        return None
    dec, err = parse_nationwide_decimal(raw)
    if err or dec is None:
        return None
    return dec


def _derive_nationwide_retail_unit_price(
    *,
    billed_unit_price: Decimal | None,
    quantity: Decimal | None,
    usa_discount_total: Decimal | None,
) -> Decimal | None:
    if billed_unit_price is None:
        return None
    if quantity is None or quantity == 0:
        return None
    if usa_discount_total is None:
        return None
    if usa_discount_total == 0:
        return billed_unit_price
    return quantize_unit_price(billed_unit_price + (usa_discount_total / quantity))


def _parse_statement_date(raw: str | None) -> date | None:
    if not raw:
        return None
    text = str(raw).strip().split()[0]
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def _provider_timestamp_fields(dt_raw: str | None) -> dict[str, Any]:
    if not dt_raw or not str(dt_raw).strip():
        return {
            "transaction_datetime_source": "",
            "transaction_timezone_source": TZ_SOURCE_UNKNOWN,
            "transaction_timezone": None,
            "transaction_utc_offset": None,
            "transaction_date": None,
            "transaction_datetime": None,
        }
    source = str(dt_raw).strip()
    return interpret_provider_timestamp(
        source_text=source,
        timezone_source=TZ_SOURCE_DATE_ONLY,
        parsed_date=_parse_statement_date(source),
        parsed_datetime=None,
    )


def _raw_provider_payload(
    raw_row: Mapping[str, Any],
    *,
    fuel_nationwide_id: int | None,
    import_id: uuid.UUID,
) -> dict[str, Any]:
    fields = {
        k: raw_row.get(k)
        for k in NATIONWIDE_SOURCE_FIELD_NAMES
        if raw_row.get(k) is not None and str(raw_row.get(k)).strip() != ""
    }
    return {
        "source_vendor": NATIONWIDE_VENDOR,
        "row_type": raw_row.get("row_type"),
        "import_id": str(import_id),
        "fuel_nationwide_id": fuel_nationwide_id,
        "source_page": raw_row.get("source_page"),
        "source_row_number": raw_row.get("source_row_number"),
        "fields": fields,
    }


def build_fuel_source_batch(
    *,
    tenant_id: int,
    import_id: uuid.UUID,
    header: Mapping[str, Any],
    source_hash: str | None,
    source_storage_ref: str,
    parser_version: str | None,
    reviewed_by: str,
    imported_at: datetime | None = None,
) -> FuelSourceBatch:
    now = imported_at or datetime.now(timezone.utc)
    return FuelSourceBatch(
        tenant_id=tenant_id,
        provider_code=NATIONWIDE_VENDOR,
        source_type=SOURCE_TYPE_PDF,
        invoice_number=_row_get(header, "invoice_number"),
        # Nationwide source evidence provides a statement period, not a distinct
        # invoice date. Do not manufacture invoice_date from statement_start.
        invoice_date=None,
        statement_start=_parse_statement_date(_row_get(header, "invoice_start_date")),
        statement_end=_parse_statement_date(_row_get(header, "invoice_end_date")),
        due_date=_parse_statement_date(_row_get(header, "due_date")),
        account_reference=_row_get(header, "account_code"),
        source_storage_ref=source_storage_ref,
        source_hash=source_hash,
        source_import_ref=str(import_id),
        imported_at=now,
        parser_rule_version=parser_version,
        provider_profile_code=NATIONWIDE_VENDOR,
        status=BATCH_STATUS_PROCESSING,
        reviewed_by=reviewed_by,
        reviewed_at=now,
        created_by=reviewed_by,
    )


def _quantity_unit(currency: str | None) -> str | None:
    if currency == "CAD":
        return "litres"
    if currency == "USD":
        return "gallons"
    return None


def _unit_price_basis(currency: str | None) -> str | None:
    if currency == "CAD":
        return "EX_TAX"
    if currency == "USD":
        return "FINAL_GALLON_PRICE"
    return None


def _build_purchase_transaction(
    *,
    tenant_id: int,
    batch_id: int,
    effective: Mapping[str, Any],
    raw: Mapping[str, Any],
    fuel_nationwide_id: int,
    import_id: uuid.UUID,
) -> FuelTransaction:
    ts = _provider_timestamp_fields(_row_get(effective, "transaction_date"))
    cur_raw = _row_get(effective, "currency")
    _, cur_iso = classify_currency(cur_raw)
    total = _money_decimal(effective.get("total"))
    if total is None:
        raise FuelNationwideCanonicalProjectionError(
            "PURCHASE_TOTAL_MISSING",
            f"purchase row {fuel_nationwide_id} missing total",
        )
    quantity = to_optional_decimal(_row_get(effective, "volume"))
    billed_unit = _unit_price_decimal(_row_get(effective, "ex_gst_per_unit"))
    discount_total = _parsed_discount_total(effective.get("usa_discount"))
    retail_unit = _derive_nationwide_retail_unit_price(
        billed_unit_price=billed_unit,
        quantity=quantity,
        usa_discount_total=discount_total,
    )
    provider_raw = _raw_provider_payload(
        effective, fuel_nationwide_id=fuel_nationwide_id, import_id=import_id
    )
    if (
        retail_unit is not None
        and billed_unit is not None
        and discount_total is not None
        and discount_total != 0
    ):
        provider_raw = {
            **provider_raw,
            "derived_canonical": {
                "retail_unit_price": format(retail_unit, "f"),
                "formula": "billed_unit_price + provider_discount_amount / quantity",
            },
        }
    return FuelTransaction(
        tenant_id=tenant_id,
        batch_id=batch_id,
        source_row_order=int(raw.get("source_row_number") or 0),
        source_row_id=str(fuel_nationwide_id),
        source_vendor=NATIONWIDE_VENDOR,
        account_reference=_row_get(effective, "account_code"),
        provider_event_type_raw="PURCHASE",
        provider_event_type=PROVIDER_EVENT_PURCHASE,
        unit_number_snapshot=_row_get(effective, "unit_number"),
        card_or_account_id=_row_get(effective, "card_number"),
        driver_name_snapshot=None,
        city=_row_get(effective, "city"),
        province_state=_row_get(effective, "prov_st"),
        product=_row_get(effective, "product"),
        product_code_raw=_row_get(effective, "product"),
        quantity=quantity,
        quantity_unit=_quantity_unit(cur_iso),
        unit_price=billed_unit,
        unit_price_basis=_unit_price_basis(cur_iso),
        billed_amount=quantize_money(billed_unit) if billed_unit is not None else None,
        retail_amount=quantize_money(retail_unit) if retail_unit is not None else None,
        total_amount=total,
        currency_raw=cur_raw,
        currency=cur_iso,
        merchant_network=_row_get(effective, "network"),
        provider_discount_amount=_money_decimal(effective.get("usa_discount")),
        missed_discount_amount=_money_decimal(effective.get("missed_disc")),
        out_of_network_fee=_money_decimal(effective.get("oon_fees")),
        classification=None,
        classification_status=CLASSIFICATION_STATUS_UNMAPPED,
        provider_raw=provider_raw,
        review_status="CONFIRMED",
        parsed_row_role="TRANSACTION",
        **ts,
    )


def _control_scope_for_type(control_type: str) -> str:
    return {
        CONTROL_TYPE_CARD_TOTAL: CONTROL_SCOPE_CARD,
        CONTROL_TYPE_CURRENCY_TOTAL: CONTROL_SCOPE_CURRENCY,
        CONTROL_TYPE_INVOICE_TOTAL: CONTROL_SCOPE_INVOICE,
        CONTROL_TYPE_INVOICE_SUMMARY: CONTROL_SCOPE_INVOICE,
        CONTROL_TYPE_STATEMENT_TOTAL: CONTROL_SCOPE_STATEMENT,
        CONTROL_TYPE_TAX_CONTROL: CONTROL_SCOPE_TAX,
        CONTROL_TYPE_PROVIDER_DECLARED_TOTAL: CONTROL_SCOPE_INVOICE,
        CONTROL_TYPE_UNIT_SUBTOTAL: CONTROL_SCOPE_INVOICE,
    }.get(control_type, CONTROL_SCOPE_INVOICE)


def _declared_for_control(row: Mapping[str, Any]) -> Decimal | None:
    if row.get("declared_amount"):
        return _money_decimal(row.get("declared_amount"))
    line = row.get("control_line_raw")
    if not line:
        return None
    import re

    m = re.search(r"\$([\d,]+\.\d{2})", str(line))
    if m:
        return _money_decimal(m.group(1))
    return None


def project_nationwide_rows_to_canonical(
    *,
    tenant_id: int,
    batch: FuelSourceBatch,
    import_id: uuid.UUID,
    raw_rows: list[Mapping[str, Any]],
    effective_rows: list[Mapping[str, Any]],
    fuel_nationwide_id_by_stage_row_id: dict[int, int],
) -> tuple[list[FuelTransaction], list[FuelSourceControl]]:
    transactions: list[FuelTransaction] = []
    controls: list[FuelSourceControl] = []
    header = next((r for r in effective_rows if r.get("row_type") == ROW_HEADER), {})

    for raw, eff in zip(raw_rows, effective_rows, strict=True):
        stage_id = int(raw["id"])
        nw_id = fuel_nationwide_id_by_stage_row_id[stage_id]
        row_type = eff.get("row_type")
        if row_type == ROW_TRANSACTION:
            transactions.append(
                _build_purchase_transaction(
                    tenant_id=tenant_id,
                    batch_id=batch.id,
                    effective=eff,
                    raw=raw,
                    fuel_nationwide_id=nw_id,
                    import_id=import_id,
                )
            )
        elif row_type == ROW_CONTROL:
            control_type = str(eff.get("control_type") or "UNKNOWN")
            label = _row_get(eff, "control_line_raw") or _row_get(eff, "row_label") or control_type
            declared = _declared_for_control(eff)
            if control_type == CONTROL_TYPE_TAX_CONTROL and eff.get("gst"):
                declared = _money_decimal(eff.get("gst"))
            cur_raw = _row_get(eff, "currency")
            _, cur_iso = classify_currency(cur_raw)
            controls.append(
                FuelSourceControl(
                    tenant_id=tenant_id,
                    batch_id=batch.id,
                    source_vendor=NATIONWIDE_VENDOR,
                    account_reference=_row_get(header, "account_code"),
                    provider_control_identity=f"{control_type}:{label}:{nw_id}",
                    control_label_raw=label,
                    control_type_raw=label,
                    control_type=control_type,
                    control_scope_raw=_control_scope_for_type(control_type),
                    control_scope=_control_scope_for_type(control_type),
                    scope_card_or_account_id=_row_get(eff, "card_number"),
                    invoice_number=_row_get(header, "invoice_number"),
                    source_row_order=int(raw.get("source_row_number") or 0),
                    source_row_id=str(nw_id),
                    currency_raw=cur_raw,
                    currency=cur_iso,
                    quantity=_quantity_decimal(eff.get("control_volume")),
                    discount_amount=_money_decimal(eff.get("usa_discount")),
                    declared_amount=declared,
                    gst_amount=_money_decimal(eff.get("gst")),
                    pst_amount=_money_decimal(eff.get("pst")),
                    provider_raw=_raw_provider_payload(eff, fuel_nationwide_id=nw_id, import_id=import_id),
                    review_status="CONFIRMED",
                    parsed_row_role="CONTROL",
                )
            )
    return transactions, controls


def assert_nationwide_canonical_money_gate(
    transactions: list[FuelTransaction],
    controls: list[FuelSourceControl],
    *,
    expected_transaction_count: int,
    source_reconciliation: Any,
) -> None:
    if len(transactions) != expected_transaction_count:
        raise FuelNationwideCanonicalProjectionError(
            "CANONICAL_TXN_COUNT",
            f"expected {expected_transaction_count} transactions, got {len(transactions)}",
        )

    for t in transactions:
        if t.total_amount is None:
            raise FuelNationwideCanonicalProjectionError(
                "CANONICAL_TOTAL_MISSING",
                f"transaction {t.id} missing total_amount",
            )

    def _controls_of_type(control_type: str) -> list[FuelSourceControl]:
        return [c for c in controls if c.control_type == control_type]

    if source_reconciliation.usd_provider_control is not None:
        usd_controls = [
            c
            for c in _controls_of_type(CONTROL_TYPE_CURRENCY_TOTAL)
            if c.currency == "USD"
        ]
        if len(usd_controls) != 1:
            raise FuelNationwideCanonicalProjectionError(
                "USD_CONTROL_MISSING",
                f"expected 1 USD CURRENCY_TOTAL control, got {len(usd_controls)}",
            )

        expected = _money_decimal(source_reconciliation.usd_provider_control)
        actual = usd_controls[0].declared_amount
        if expected is None or actual is None or quantize_money(actual) != expected:
            raise FuelNationwideCanonicalProjectionError(
                "USD_CONTROL_MISMATCH",
                f"canonical USD control {actual} != source control {expected}",
            )

    if source_reconciliation.cad_ex_tax_control is not None:
        ex_tax_controls = [
            c
            for c in _controls_of_type(CONTROL_TYPE_INVOICE_SUMMARY)
            if (c.control_label_raw or "").casefold().startswith("total ex-gst")
        ]
        if len(ex_tax_controls) != 1:
            raise FuelNationwideCanonicalProjectionError(
                "CAD_EX_TAX_CONTROL_MISSING",
                f"expected 1 canonical CAD Ex-GST control, got {len(ex_tax_controls)}",
            )

        expected = _money_decimal(source_reconciliation.cad_ex_tax_control)
        actual = ex_tax_controls[0].declared_amount
        if expected is None or actual is None or quantize_money(actual) != expected:
            raise FuelNationwideCanonicalProjectionError(
                "CAD_EX_TAX_CONTROL_MISMATCH",
                f"canonical CAD Ex-GST control {actual} != source control {expected}",
            )

    if source_reconciliation.cad_gst is not None:
        gst_controls = [
            c
            for c in _controls_of_type(CONTROL_TYPE_TAX_CONTROL)
            if c.gst_amount is not None
        ]
        if len(gst_controls) != 1:
            raise FuelNationwideCanonicalProjectionError(
                "CAD_GST_CONTROL_MISSING",
                f"expected 1 canonical GST control, got {len(gst_controls)}",
            )

        expected = _money_decimal(source_reconciliation.cad_gst)
        actual = gst_controls[0].gst_amount
        if expected is None or actual is None or quantize_money(actual) != expected:
            raise FuelNationwideCanonicalProjectionError(
                "CAD_GST_CONTROL_MISMATCH",
                f"canonical GST control {actual} != source control {expected}",
            )

    if source_reconciliation.cad_pst is not None:
        pst_controls = [
            c
            for c in _controls_of_type(CONTROL_TYPE_TAX_CONTROL)
            if c.pst_amount is not None
        ]
        if len(pst_controls) != 1:
            raise FuelNationwideCanonicalProjectionError(
                "CAD_PST_CONTROL_MISSING",
                f"expected 1 canonical PST control, got {len(pst_controls)}",
            )

        expected = _money_decimal(source_reconciliation.cad_pst)
        actual = pst_controls[0].pst_amount
        if expected is None or actual is None or quantize_money(actual) != expected:
            raise FuelNationwideCanonicalProjectionError(
                "CAD_PST_CONTROL_MISMATCH",
                f"canonical PST control {actual} != source control {expected}",
            )

    if source_reconciliation.cad_subtotal is not None:
        subtotal_controls = [
            c
            for c in _controls_of_type(CONTROL_TYPE_PROVIDER_DECLARED_TOTAL)
            if (c.control_label_raw or "").casefold().startswith("subtotal")
        ]
        if len(subtotal_controls) != 1:
            raise FuelNationwideCanonicalProjectionError(
                "CAD_SUBTOTAL_CONTROL_MISSING",
                f"expected 1 canonical CAD subtotal control, got {len(subtotal_controls)}",
            )

        expected = _money_decimal(source_reconciliation.cad_subtotal)
        actual = subtotal_controls[0].declared_amount
        if expected is None or actual is None or quantize_money(actual) != expected:
            raise FuelNationwideCanonicalProjectionError(
                "CAD_SUBTOTAL_CONTROL_MISMATCH",
                f"canonical CAD subtotal {actual} != source control {expected}",
            )

    expected_card_totals = sorted(
        (
            str(item.get("card_number") or ""),
            str(item.get("currency") or ""),
            _money_decimal(item.get("declared_amount")),
        )
        for item in source_reconciliation.card_controls
    )

    canonical_card_totals = sorted(
        (
            str(c.scope_card_or_account_id or ""),
            str(c.currency or ""),
            quantize_money(c.declared_amount)
            if c.declared_amount is not None
            else None,
        )
        for c in controls
        if c.control_type == CONTROL_TYPE_CARD_TOTAL
    )

    if expected_card_totals != canonical_card_totals:
        raise FuelNationwideCanonicalProjectionError(
            "CARD_CONTROLS_MISMATCH",
            "canonical Nationwide CARD_TOTAL controls do not match validated source controls",
        )


def finalize_batch(batch: FuelSourceBatch, *, reviewed_by: str) -> None:
    now = datetime.now(timezone.utc)
    batch.status = BATCH_STATUS_FINALIZED
    batch.finalized_by = reviewed_by
    batch.finalized_at = now
    batch.updated_by = reviewed_by
