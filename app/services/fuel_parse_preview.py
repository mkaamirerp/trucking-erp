"""Non-persisted Fuel digital-PDF parse preview (source-fidelity review only).

No database session, no tenant DB, no writes to fuel_bvd / fuel_transactions / batches.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Mapping

from app.services.fuel_ai_contract import HANDOFF_VERSION, PROFILE
from app.services.fuel_ai_mechanical_validation import validate_fuel_ai_extraction
from app.services.fuel_canonical import TZ_SOURCE_DATE_ONLY
from app.services.fuel_digital_pdf_extract import (
    ROW_KIND_HEADER,
    extract_digital_pdf_source_rows,
)
from app.services.fuel_digital_pdf_nationwide_table import ROW_KIND_CONTROL, ROW_KIND_TRANSACTION
from app.services.fuel_digital_pdf_types import FuelDigitalPdfExtractError
from app.services.fuel_provider_profile import (
    apply_field_aliases,
    classify_source_row_role,
    load_provider_profile,
    match_provider_layout,
    suggest_control_type,
)
from app.services.pdf_text_extract import extract_text_and_pages_from_pdf_bytes

_PREVIEW_NORMALIZED_KEYS: frozenset[str] = frozenset(
    {
        "account_reference",
        "card_or_account_id",
        "unit_number_snapshot",
        "transaction_datetime_source",
        "transaction_date",
        "city",
        "province_state",
        "product",
        "quantity",
        "quantity_unit",
        "unit_price",
        "unit_price_basis",
        "total_amount",
        "currency_raw",
        "currency",
        "merchant_network",
        "provider_discount_amount",
        "missed_discount_amount",
        "out_of_network_fee",
        "driver_name_snapshot",
    }
)


def _preview_normalized(aliased: Mapping[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key in _PREVIEW_NORMALIZED_KEYS:
        if key in aliased and aliased[key] is not None:
            out[key] = aliased[key]
    if aliased.get("driver_name_snapshot") is None:
        out["driver_name_snapshot"] = None
    return out


def _map_header_fields(header_src: Mapping[str, Any], profile: Mapping[str, Any]) -> dict[str, Any]:
    aliases = profile.get("header_aliases") or {}
    out: dict[str, Any] = {}
    for src, target in aliases.items():
        if src in header_src and header_src[src]:
            out[str(target)] = header_src[src]
    for k, v in header_src.items():
        if k not in aliases and v:
            out[k] = v
    return out


def parse_fuel_pdf_preview(
    pdf_bytes: bytes,
    *,
    provider_code: str = "NATIONWIDE",
) -> dict[str, Any]:
    """Parse embedded-text digital PDF into a JSON-serializable preview. Never persists."""
    profile = load_provider_profile(provider_code)
    _full, page_texts, extract_warnings = extract_text_and_pages_from_pdf_bytes(pdf_bytes)
    pages = [{"page_number": i + 1, "text": t} for i, t in enumerate(page_texts)]
    layout = match_provider_layout(profile, page_texts=pages)

    warnings: list[str] = list(extract_warnings)
    if layout.status != "RECOGNIZED":
        return {
            "provider": provider_code,
            "profile_version": profile.get("profile_version"),
            "layout_status": layout.status,
            "layout": {
                "matched_anchors": list(layout.matched_anchors),
                "missing_required_anchors": list(layout.missing_required_anchors),
            },
            "header": {},
            "transactions": [],
            "controls": [],
            "warnings": warnings + [f"LAYOUT:{layout.status}"],
            "parser_rule_version": None,
        }

    try:
        source_rows, row_warnings, parser_rule_version = extract_digital_pdf_source_rows(
            provider_code=provider_code,
            pdf_bytes=pdf_bytes,
        )
    except FuelDigitalPdfExtractError as exc:
        return {
            "provider": provider_code,
            "profile_version": profile.get("profile_version"),
            "layout_status": layout.status,
            "header": {},
            "transactions": [],
            "controls": [],
            "warnings": warnings + [f"{exc.code}: {exc.message}"],
            "parser_rule_version": None,
        }

    warnings.extend(row_warnings)
    header_src: dict[str, Any] = {}
    transactions: list[dict[str, Any]] = []
    controls: list[dict[str, Any]] = []
    order = 0

    for row in source_rows:
        if row.row_kind == ROW_KIND_HEADER:
            header_src = dict(row.source_fields)
            continue
        order += 1
        provider_raw = {k: v for k, v in row.source_fields.items() if v is not None}
        line_text = provider_raw.pop("control_line_raw", None)

        if row.row_kind == ROW_KIND_TRANSACTION:
            role = classify_source_row_role(profile=profile, provider_raw=provider_raw)
            if role.role != "TRANSACTION":
                warnings.append(f"row {order}: expected TRANSACTION got {role.role} ({role.reason})")
                continue
            aliased = apply_field_aliases(provider_raw, profile=profile)
            if profile.get("field_semantics", {}).get("driver_absent_on_source"):
                aliased["driver_name_snapshot"] = None
            txn: dict[str, Any] = {
                "row_role": "TRANSACTION",
                "source_row_order": order,
                "provider_raw": dict(aliased.get("provider_raw") or provider_raw),
                "transaction_datetime_source": aliased.get("transaction_datetime_source"),
                "transaction_timezone_source": TZ_SOURCE_DATE_ONLY,
                "provider_event_type": "PURCHASE",
                "preview_normalized": _preview_normalized(aliased),
            }
            for key in (
                "unit_number_snapshot",
                "quantity",
                "quantity_unit",
                "unit_price",
                "unit_price_basis",
                "total_amount",
                "currency_raw",
                "currency",
                "merchant_network",
                "provider_discount_amount",
            ):
                if aliased.get(key) is not None:
                    txn[key] = aliased[key]
            dt_src = aliased.get("transaction_datetime_source")
            if dt_src and not txn.get("transaction_date"):
                txn["transaction_date"] = str(dt_src).split()[0]
            transactions.append(txn)
            continue

        if row.row_kind == ROW_KIND_CONTROL:
            role = classify_source_row_role(
                profile=profile, provider_raw=provider_raw, line_text=line_text
            )
            control_type = suggest_control_type(
                profile=profile, provider_raw=provider_raw, line_text=line_text
            )
            ctl: dict[str, Any] = {
                "row_role": "CONTROL",
                "source_row_order": order,
                "control_type": control_type,
                "control_type_raw": line_text or provider_raw.get("row_label"),
                "provider_raw": provider_raw,
            }
            if provider_raw.get("GST"):
                ctl["gst_amount"] = provider_raw["GST"]
                ctl["currency_raw"] = "CAD"
            if provider_raw.get("PST") is not None:
                ctl["pst_amount"] = provider_raw["PST"]
            if provider_raw.get("declared_amount"):
                ctl["declared_amount"] = provider_raw["declared_amount"]
            if provider_raw.get("Currency"):
                ctl["currency_raw"] = provider_raw["Currency"]
            controls.append(ctl)
            if role.role == "UNKNOWN":
                warnings.append(f"control row {order}: role UNKNOWN ({role.reason})")
            continue

    header = _map_header_fields(header_src, profile)
    mechanical_payload = {
        "handoff_version": HANDOFF_VERSION,
        "profile": PROFILE,
        "layout_status": layout.status,
        "header": header,
        "transactions": transactions,
        "controls": controls,
        "warnings": warnings,
    }
    validation = validate_fuel_ai_extraction(mechanical_payload)
    if validation.warnings:
        warnings.extend(validation.warnings)
    if validation.review_reasons:
        warnings.extend([f"REVIEW:{r}" for r in validation.review_reasons])
    if validation.errors:
        warnings.extend([f"MECHANICAL:{e}" for e in validation.errors])

    return {
        "provider": provider_code,
        "profile_version": profile.get("profile_version"),
        "layout_status": layout.status,
        "parser_rule_version": parser_rule_version,
        "header": header,
        "transactions": transactions,
        "controls": controls,
        "warnings": warnings,
        "mechanical_validation_ok": validation.ok and not validation.requires_review,
    }
