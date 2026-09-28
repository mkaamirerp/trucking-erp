"""BVD Process → FuelSourceBatch + fuel_transactions + fuel_source_controls (Segment A)."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Mapping

from app.models.fuel import FuelSourceBatch, FuelSourceControl, FuelTransaction
from app.services.fuel_bvd_extraction import (
    ROW_EXPRESS_SUBTOTAL,
    ROW_EXPRESS_TRANSACTION,
    ROW_GRAND_TOTAL,
    ROW_HEADER,
    ROW_PAGE1_SUMMARY,
    ROW_TRANSACTION,
    ROW_TRANSACTION_SUBTOTAL,
)
from app.services.fuel_bvd_import import BVD_SOURCE_FIELD_NAMES
from app.services.fuel_bvd_source_reconciliation import parse_bvd_decimal
from app.services.fuel_canonical import (
    BATCH_STATUS_FINALIZED,
    BATCH_STATUS_PROCESSING,
    PROVIDER_EVENT_OTHER,
    PROVIDER_EVENT_PURCHASE,
    SOURCE_TYPE_PDF,
    TZ_SOURCE_PROVIDER_LOCAL_NO_ZONE,
    TZ_SOURCE_UNKNOWN,
    classify_currency,
    interpret_provider_timestamp,
)
from app.services.fuel_controls import (
    CONTROL_SCOPE_CARD,
    CONTROL_SCOPE_GROUP,
    CONTROL_SCOPE_INVOICE,
    CONTROL_SCOPE_PRODUCT,
    CONTROL_TYPE_CARD_TOTAL,
    CONTROL_TYPE_GROUP_SUBTOTAL,
    CONTROL_TYPE_INVOICE_TOTAL,
    CONTROL_TYPE_PRODUCT_SUBTOTAL,
    assert_no_source_row_double_count,
)
from app.services.fuel_money import quantize_money, to_optional_decimal

BVD_VENDOR = "BVD"
SECTION_FUEL_CARD = "FUEL_CARD_TRANSACTIONS"
SECTION_EXPRESS = "EXPRESS"
CLASSIFICATION_STATUS_UNMAPPED = "UNMAPPED"

MONEY_ROW_TYPES = frozenset({ROW_TRANSACTION, ROW_EXPRESS_TRANSACTION})


class FuelBvdCanonicalProjectionError(Exception):
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
    dec, err = parse_bvd_decimal(raw)
    if err or dec is None:
        return None
    return quantize_money(dec)


def _parse_statement_date(raw: str | None) -> date | None:
    if not raw:
        return None
    text = str(raw).strip()
    if not text:
        return None
    if " " in text:
        text = text.split()[0]
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
    try:
        return interpret_provider_timestamp(
            source_text=source,
            timezone_source=TZ_SOURCE_PROVIDER_LOCAL_NO_ZONE,
            parsed_date=_parse_statement_date(source),
            parsed_datetime=None,
        )
    except Exception:
        return {
            "transaction_datetime_source": source,
            "transaction_timezone_source": TZ_SOURCE_UNKNOWN,
            "transaction_timezone": None,
            "transaction_utc_offset": None,
            "transaction_date": _parse_statement_date(source),
            "transaction_datetime": None,
        }


def _raw_provider_payload(
    raw_row: Mapping[str, Any],
    *,
    fuel_bvd_id: int | None,
    import_id: uuid.UUID,
) -> dict[str, Any]:
    fields = {
        k: raw_row.get(k)
        for k in BVD_SOURCE_FIELD_NAMES
        if raw_row.get(k) is not None and str(raw_row.get(k)).strip() != ""
    }
    return {
        "source_vendor": BVD_VENDOR,
        "row_type": raw_row.get("row_type"),
        "import_id": str(import_id),
        "fuel_bvd_id": fuel_bvd_id,
        "source_page": raw_row.get("source_page"),
        "source_row_number": raw_row.get("source_row_number"),
        "fields": fields,
    }


def _control_provider_payload(
    raw_row: Mapping[str, Any],
    *,
    fuel_bvd_id: int | None,
    import_id: uuid.UUID,
    control_type: str,
    control_scope: str,
) -> dict[str, Any]:
    base = _raw_provider_payload(raw_row, fuel_bvd_id=fuel_bvd_id, import_id=import_id)
    base["control_type"] = control_type
    base["control_scope"] = control_scope
    return base


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
        provider_code=BVD_VENDOR,
        source_type=SOURCE_TYPE_PDF,
        invoice_number=_row_get(header, "invoice_number"),
        invoice_date=_parse_statement_date(_row_get(header, "invoice_date")),
        statement_start=_parse_statement_date(_row_get(header, "start_date")),
        statement_end=_parse_statement_date(_row_get(header, "end_date")),
        due_date=_parse_statement_date(_row_get(header, "due_date")),
        source_storage_ref=source_storage_ref,
        source_hash=source_hash,
        source_import_ref=str(import_id),
        imported_at=now,
        parser_rule_version=parser_version,
        provider_profile_code=BVD_VENDOR,
        status=BATCH_STATUS_PROCESSING,
        reviewed_by=reviewed_by,
        reviewed_at=now,
        finalized_by=None,
        finalized_at=None,
        created_by=reviewed_by,
    )


def _build_purchase_transaction(
    *,
    tenant_id: int,
    batch_id: int,
    effective: Mapping[str, Any],
    raw: Mapping[str, Any],
    fuel_bvd_id: int,
    import_id: uuid.UUID,
) -> FuelTransaction:
    ts = _provider_timestamp_fields(_row_get(effective, "transaction_date"))
    cur_raw, cur_iso = classify_currency(_row_get(effective, "cur"))
    if cur_iso is None and cur_raw and cur_raw.upper() == "US":
        cur_iso = "USD"
    total = _money_decimal(effective.get("final_amt"))
    if total is None:
        raise FuelBvdCanonicalProjectionError(
            "PURCHASE_TOTAL_MISSING",
            f"purchase row {fuel_bvd_id} missing final_amt",
        )
    return FuelTransaction(
        tenant_id=tenant_id,
        batch_id=batch_id,
        provider_transaction_identity=_row_get(effective, "auth_code"),
        source_row_order=int(raw.get("source_row_number") or 0),
        source_row_id=str(fuel_bvd_id),
        source_vendor=BVD_VENDOR,
        account_reference=_row_get(effective, "card_number"),
        provider_event_type_raw="PURCHASE",
        provider_event_type=PROVIDER_EVENT_PURCHASE,
        provider_section_raw=SECTION_FUEL_CARD,
        unit_number_snapshot=_row_get(effective, "unit_number"),
        card_or_account_id=_row_get(effective, "card_number"),
        driver_name_snapshot=_row_get(effective, "driver_name"),
        site_number=_row_get(effective, "site_number"),
        site_name=_row_get(effective, "site_name"),
        city=_row_get(effective, "site_city"),
        province_state=_row_get(effective, "prov_st"),
        product_code_raw=_row_get(effective, "prod"),
        product=_row_get(effective, "prod"),
        quantity=to_optional_decimal(_row_get(effective, "qty") or None) if _row_get(effective, "qty") else None,
        unit_price=to_optional_decimal(_row_get(effective, "billed") or None) if _row_get(effective, "billed") else None,
        provider_discount_rate=to_optional_decimal(_row_get(effective, "disc_rate") or None)
        if _row_get(effective, "disc_rate")
        else None,
        provider_discount_amount=_money_decimal(effective.get("disc_amt")),
        hst_amount=_money_decimal(effective.get("hst")),
        gst_amount=_money_decimal(effective.get("gst")),
        pst_amount=_money_decimal(effective.get("pst")),
        qst_amount=_money_decimal(effective.get("qst")),
        pre_tax_amount=_money_decimal(effective.get("pre_tax_amt")),
        billed_amount=_money_decimal(effective.get("billed")),
        retail_amount=_money_decimal(effective.get("retail")),
        total_amount=total,
        currency_raw=cur_raw,
        currency=cur_iso,
        classification=None,
        classification_status=CLASSIFICATION_STATUS_UNMAPPED,
        classification_source=None,
        provider_raw=_raw_provider_payload(raw, fuel_bvd_id=fuel_bvd_id, import_id=import_id),
        review_status="CONFIRMED",
        parsed_row_role="TRANSACTION",
        **ts,
    )


def _build_express_transaction(
    *,
    tenant_id: int,
    batch_id: int,
    effective: Mapping[str, Any],
    raw: Mapping[str, Any],
    fuel_bvd_id: int,
    import_id: uuid.UUID,
) -> FuelTransaction:
    ts = _provider_timestamp_fields(_row_get(effective, "transaction_date"))
    cur_raw, cur_iso = classify_currency(_row_get(effective, "cur"))
    if cur_iso is None and cur_raw and cur_raw.upper() == "US":
        cur_iso = "USD"
    principal = _money_decimal(effective.get("amount_cashed"))
    fee = _money_decimal(effective.get("express_fee"))
    total = _money_decimal(effective.get("final_amt"))
    if total is None:
        raise FuelBvdCanonicalProjectionError(
            "EXPRESS_TOTAL_MISSING",
            f"express row {fuel_bvd_id} missing final_amt",
        )
    return FuelTransaction(
        tenant_id=tenant_id,
        batch_id=batch_id,
        provider_transaction_identity=_row_get(effective, "auth_code"),
        source_row_order=int(raw.get("source_row_number") or 0),
        source_row_id=str(fuel_bvd_id),
        source_vendor=BVD_VENDOR,
        account_reference=None,
        provider_event_type_raw="OTHER",
        provider_event_type=PROVIDER_EVENT_OTHER,
        provider_section_raw=SECTION_EXPRESS,
        provider_reference_raw=_row_get(effective, "express_code"),
        provider_reason_raw=_row_get(effective, "payee_raw"),
        unit_number_snapshot=_row_get(effective, "express_tractor"),
        card_or_account_id=None,
        driver_name_snapshot=_row_get(effective, "driver_name"),
        principal_amount=principal,
        provider_fee_amount=fee,
        total_amount=total,
        currency_raw=cur_raw,
        currency=cur_iso,
        classification=None,
        classification_status=CLASSIFICATION_STATUS_UNMAPPED,
        classification_source=None,
        provider_raw=_raw_provider_payload(raw, fuel_bvd_id=fuel_bvd_id, import_id=import_id),
        review_status="CONFIRMED",
        parsed_row_role="TRANSACTION",
        **ts,
    )


def _build_control(
    *,
    tenant_id: int,
    batch_id: int,
    raw: Mapping[str, Any],
    fuel_bvd_id: int,
    import_id: uuid.UUID,
    control_type: str,
    control_scope: str,
    control_label: str,
    declared_amount: Decimal | None,
    scope_card: str | None = None,
    scope_product: str | None = None,
) -> FuelSourceControl:
    cur_raw, cur_iso = classify_currency(_row_get(raw, "cur"))
    return FuelSourceControl(
        tenant_id=tenant_id,
        batch_id=batch_id,
        source_vendor=BVD_VENDOR,
        account_reference=scope_card,
        provider_control_identity=f"{control_type}:{control_label}:{fuel_bvd_id}",
        control_label_raw=control_label,
        control_type_raw=control_label,
        control_type=control_type,
        control_scope_raw=control_scope,
        control_scope=control_scope,
        scope_card_or_account_id=scope_card,
        scope_product_raw=scope_product,
        invoice_number=_row_get(raw, "invoice_number"),
        source_row_order=int(raw.get("source_row_number") or 0),
        source_row_id=str(fuel_bvd_id),
        currency_raw=cur_raw,
        currency=cur_iso,
        declared_amount=declared_amount,
        provider_raw=_control_provider_payload(
            raw,
            fuel_bvd_id=fuel_bvd_id,
            import_id=import_id,
            control_type=control_type,
            control_scope=control_scope,
        ),
        review_status="CONFIRMED",
        parsed_row_role="CONTROL",
    )


def _control_from_bvd_row(
    raw: Mapping[str, Any],
    *,
    tenant_id: int,
    batch_id: int,
    fuel_bvd_id: int,
    import_id: uuid.UUID,
) -> FuelSourceControl | None:
    row_type = raw.get("row_type")
    label = (_row_get(raw, "row_label") or "").strip()
    product = (_row_get(raw, "product") or _row_get(raw, "prod") or "").strip()
    card = (_row_get(raw, "card_number") or "").strip() or None
    final = _money_decimal(raw.get("final_amt") or raw.get("final_amount"))

    if row_type == ROW_PAGE1_SUMMARY:
        if label == "Sub Total":
            return _build_control(
                tenant_id=tenant_id,
                batch_id=batch_id,
                raw=raw,
                fuel_bvd_id=fuel_bvd_id,
                import_id=import_id,
                control_type=CONTROL_TYPE_CARD_TOTAL,
                control_scope=CONTROL_SCOPE_CARD,
                control_label="Sub Total",
                declared_amount=final,
                scope_card=card,
            )
        if label == "Fuel Total":
            return _build_control(
                tenant_id=tenant_id,
                batch_id=batch_id,
                raw=raw,
                fuel_bvd_id=fuel_bvd_id,
                import_id=import_id,
                control_type=CONTROL_TYPE_GROUP_SUBTOTAL,
                control_scope=CONTROL_SCOPE_GROUP,
                control_label="Fuel Total",
                declared_amount=final,
                scope_card=card,
            )
        if label in {"DF", "S"} or product in {"DF", "S", "TA", "TF"}:
            return _build_control(
                tenant_id=tenant_id,
                batch_id=batch_id,
                raw=raw,
                fuel_bvd_id=fuel_bvd_id,
                import_id=import_id,
                control_type=CONTROL_TYPE_PRODUCT_SUBTOTAL,
                control_scope=CONTROL_SCOPE_PRODUCT,
                control_label=label or product,
                declared_amount=final,
                scope_card=card,
                scope_product=product or label,
            )
        return None

    if row_type == ROW_TRANSACTION_SUBTOTAL:
        if product:
            return _build_control(
                tenant_id=tenant_id,
                batch_id=batch_id,
                raw=raw,
                fuel_bvd_id=fuel_bvd_id,
                import_id=import_id,
                control_type=CONTROL_TYPE_PRODUCT_SUBTOTAL,
                control_scope=CONTROL_SCOPE_PRODUCT,
                control_label=f"SUBTOTAL {product}",
                declared_amount=final,
                scope_card=card,
                scope_product=product,
            )
        return _build_control(
            tenant_id=tenant_id,
            batch_id=batch_id,
            raw=raw,
            fuel_bvd_id=fuel_bvd_id,
            import_id=import_id,
            control_type=CONTROL_TYPE_GROUP_SUBTOTAL,
            control_scope=CONTROL_SCOPE_GROUP,
            control_label="SUBTOTAL",
            declared_amount=final,
            scope_card=card,
        )

    if row_type == ROW_EXPRESS_SUBTOTAL:
        return _build_control(
            tenant_id=tenant_id,
            batch_id=batch_id,
            raw=raw,
            fuel_bvd_id=fuel_bvd_id,
            import_id=import_id,
            control_type=CONTROL_TYPE_GROUP_SUBTOTAL,
            control_scope=CONTROL_SCOPE_GROUP,
            control_label="EXPRESS SUBTOTAL",
            declared_amount=final,
        )

    if row_type == ROW_GRAND_TOTAL:
        if label == "Grand Total":
            return _build_control(
                tenant_id=tenant_id,
                batch_id=batch_id,
                raw=raw,
                fuel_bvd_id=fuel_bvd_id,
                import_id=import_id,
                control_type=CONTROL_TYPE_INVOICE_TOTAL,
                control_scope=CONTROL_SCOPE_INVOICE,
                control_label="Grand Total",
                declared_amount=final,
            )
        if label in {"Express", "Manual"}:
            return _build_control(
                tenant_id=tenant_id,
                batch_id=batch_id,
                raw=raw,
                fuel_bvd_id=fuel_bvd_id,
                import_id=import_id,
                control_type=CONTROL_TYPE_GROUP_SUBTOTAL,
                control_scope=CONTROL_SCOPE_GROUP,
                control_label=label,
                declared_amount=final,
            )
        if label or product:
            return _build_control(
                tenant_id=tenant_id,
                batch_id=batch_id,
                raw=raw,
                fuel_bvd_id=fuel_bvd_id,
                import_id=import_id,
                control_type=CONTROL_TYPE_PRODUCT_SUBTOTAL,
                control_scope=CONTROL_SCOPE_PRODUCT,
                control_label=label or product,
                declared_amount=final,
                scope_product=product or label,
            )
    return None


def project_bvd_rows_to_canonical(
    *,
    tenant_id: int,
    batch: FuelSourceBatch,
    import_id: uuid.UUID,
    raw_rows: list[Mapping[str, Any]],
    effective_rows: list[Mapping[str, Any]],
    fuel_bvd_id_by_stage_row_id: dict[int, int],
) -> tuple[list[FuelTransaction], list[FuelSourceControl]]:
    """Build canonical ORM rows. Caller must flush fuel_bvd ids first."""
    if len(raw_rows) != len(effective_rows):
        raise FuelBvdCanonicalProjectionError("ROW_PAIR_MISMATCH", "raw/effective row count mismatch")

    by_stage_id_raw = {int(r["id"]): r for r in raw_rows if r.get("id") is not None}
    by_stage_id_eff = {int(r["id"]): r for r in effective_rows if r.get("id") is not None}

    transactions: list[FuelTransaction] = []
    controls: list[FuelSourceControl] = []

    for stage_id, fuel_bvd_id in fuel_bvd_id_by_stage_row_id.items():
        raw = by_stage_id_raw.get(stage_id)
        eff = by_stage_id_eff.get(stage_id)
        if raw is None or eff is None:
            raise FuelBvdCanonicalProjectionError(
                "STAGE_ROW_MISSING",
                f"missing raw/effective for stage row {stage_id}",
            )
        row_type = raw.get("row_type")
        if row_type == ROW_TRANSACTION:
            transactions.append(
                _build_purchase_transaction(
                    tenant_id=tenant_id,
                    batch_id=batch.id,
                    effective=eff,
                    raw=raw,
                    fuel_bvd_id=fuel_bvd_id,
                    import_id=import_id,
                )
            )
        elif row_type == ROW_EXPRESS_TRANSACTION:
            transactions.append(
                _build_express_transaction(
                    tenant_id=tenant_id,
                    batch_id=batch.id,
                    effective=eff,
                    raw=raw,
                    fuel_bvd_id=fuel_bvd_id,
                    import_id=import_id,
                )
            )
        elif row_type not in {ROW_HEADER, "LEGEND"}:
            ctrl = _control_from_bvd_row(
                raw,
                tenant_id=tenant_id,
                batch_id=batch.id,
                fuel_bvd_id=fuel_bvd_id,
                import_id=import_id,
            )
            if ctrl is not None:
                controls.append(ctrl)

    txn_orders = [t.source_row_order for t in transactions]
    ctl_orders = [c.source_row_order for c in controls if c.source_row_order is not None]
    assert_no_source_row_double_count(txn_orders, ctl_orders)

    return transactions, controls


def assert_canonical_money_gate(
    transactions: list[FuelTransaction],
    controls: list[FuelSourceControl],
    *,
    expected_transaction_count: int,
    expected_total: Decimal,
) -> None:
    if len(transactions) != expected_transaction_count:
        raise FuelBvdCanonicalProjectionError(
            "CANONICAL_TXN_COUNT",
            f"expected {expected_transaction_count} transactions, got {len(transactions)}",
        )
    total = sum((t.total_amount or Decimal("0") for t in transactions), Decimal("0"))
    total = quantize_money(total)
    expected_total = quantize_money(expected_total)
    if total != expected_total:
        raise FuelBvdCanonicalProjectionError(
            "CANONICAL_TXN_SUM",
            f"transaction sum {total} != expected {expected_total}",
        )
    invoice_controls = [
        c
        for c in controls
        if c.control_type == CONTROL_TYPE_INVOICE_TOTAL and c.control_scope == CONTROL_SCOPE_INVOICE
    ]
    if len(invoice_controls) != 1:
        raise FuelBvdCanonicalProjectionError(
            "INVOICE_CONTROL_MISSING",
            f"expected 1 INVOICE_TOTAL control, got {len(invoice_controls)}",
        )
    inv_amt = invoice_controls[0].declared_amount
    if inv_amt is None or quantize_money(inv_amt) != expected_total:
        raise FuelBvdCanonicalProjectionError(
            "INVOICE_CONTROL_MISMATCH",
            f"invoice control {inv_amt} != expected {expected_total}",
        )


def finalize_batch(batch: FuelSourceBatch, *, reviewed_by: str) -> None:
    now = datetime.now(timezone.utc)
    batch.status = BATCH_STATUS_FINALIZED
    batch.finalized_by = reviewed_by
    batch.finalized_at = now
    batch.updated_by = reviewed_by
