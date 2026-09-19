"""Mechanical post-AI validation for Fuel Card statement extraction (Segment 5).

AI owns source-fact extraction only. This module validates shape, Decimal money
representation, provenance, row roles, exclusivity, and strips forbidden
business-resolution fields. It does not guess truck/payee/pricing/settlement.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, MutableMapping, Sequence

from app.services.fuel_ai_contract import (
    AI_FORBIDDEN_AUTHORITY_FIELDS,
    HANDOFF_VERSION,
    LAYOUT_UNRECOGNIZED,
    MONEY_DECIMAL_FIELDS,
    PROFILE,
    ROW_ROLE_CONTROL,
    ROW_ROLE_TRANSACTION,
    ROW_ROLE_UNKNOWN,
    contract_ai_forbidden_fields,
    load_fuel_ai_handoff_contract,
)
from app.services.fuel_canonical import (
    PROVIDER_EVENT_PURCHASE,
    PROVIDER_EVENT_TYPES,
    TZ_SOURCE_DATE_ONLY,
    TZ_SOURCE_PROVIDER_LOCAL_NO_ZONE,
    TZ_SOURCE_PROVIDER_SUPPLIED,
    TZ_SOURCE_UNKNOWN,
    classify_currency,
    classify_provider_event_type,
)
from app.services.fuel_controls import CONTROL_TYPES
from app.services.fuel_money import FuelFloatForbidden, to_decimal, to_optional_decimal

_TZ_SOURCES = frozenset(
    {
        TZ_SOURCE_PROVIDER_SUPPLIED,
        TZ_SOURCE_PROVIDER_LOCAL_NO_ZONE,
        TZ_SOURCE_DATE_ONLY,
        TZ_SOURCE_UNKNOWN,
    }
)

_SIGNED_EVENT_HINTS = frozenset({"CREDIT", "REFUND", "REVERSAL", "VOID"})


@dataclass
class FuelMechanicalValidationResult:
    ok: bool
    payload: dict[str, Any]
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    requires_review: bool = False
    review_reasons: list[str] = field(default_factory=list)

    @property
    def blocked(self) -> bool:
        return (not self.ok) or self.requires_review


def _as_dict(value: Any, *, path: str, errors: list[str]) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        errors.append(f"{path}: expected object")
        return None
    return value


def _reject_floats_in_tree(node: Any, *, path: str, errors: list[str]) -> None:
    if isinstance(node, float):
        errors.append(f"{path}: binary float forbidden")
        return
    if isinstance(node, dict):
        for k, v in node.items():
            _reject_floats_in_tree(v, path=f"{path}.{k}", errors=errors)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            _reject_floats_in_tree(v, path=f"{path}[{i}]", errors=errors)


def _check_decimal_fields(row: Mapping[str, Any], *, path: str, errors: list[str]) -> None:
    for key in MONEY_DECIMAL_FIELDS:
        if key not in row or row[key] is None:
            continue
        val = row[key]
        if isinstance(val, float):
            errors.append(f"{path}.{key}: binary float forbidden")
            continue
        if isinstance(val, bool):
            errors.append(f"{path}.{key}: bool is not a decimal")
            continue
        try:
            to_decimal(val)
        except (FuelFloatForbidden, TypeError, ValueError) as exc:
            errors.append(f"{path}.{key}: invalid decimal ({exc})")


def _strip_forbidden_fields(
    row: MutableMapping[str, Any],
    *,
    path: str,
    forbidden: frozenset[str],
    errors: list[str],
) -> None:
    present = sorted(forbidden.intersection(row.keys()))
    for key in present:
        errors.append(f"{path}.{key}: AI forbidden authority field")
        row.pop(key, None)


def _validate_timezone_provenance(
    row: Mapping[str, Any],
    *,
    path: str,
    errors: list[str],
    warnings: list[str],
) -> None:
    tz_source = row.get("transaction_timezone_source")
    if tz_source is None:
        errors.append(f"{path}.transaction_timezone_source: required")
        return
    if tz_source not in _TZ_SOURCES:
        errors.append(f"{path}.transaction_timezone_source: unknown value {tz_source!r}")
    # Aware datetime only when provider-supplied zone.
    if row.get("transaction_datetime") is not None and tz_source != TZ_SOURCE_PROVIDER_SUPPLIED:
        errors.append(
            f"{path}.transaction_datetime: must be null unless timezone_source is PROVIDER_SUPPLIED"
        )
    if tz_source == TZ_SOURCE_DATE_ONLY and not row.get("transaction_date"):
        warnings.append(f"{path}: DATE_ONLY without transaction_date")


def _validate_event(
    row: MutableMapping[str, Any],
    *,
    path: str,
    errors: list[str],
    warnings: list[str],
) -> None:
    raw = row.get("provider_event_type_raw")
    canonical = row.get("provider_event_type")
    preserved, mapped = classify_provider_event_type(raw if isinstance(raw, str) else None)
    if canonical is None:
        row["provider_event_type"] = mapped
        canonical = mapped
    if canonical not in PROVIDER_EVENT_TYPES:
        errors.append(f"{path}.provider_event_type: invalid {canonical!r}")
        row["provider_event_type"] = mapped
        canonical = mapped
    # Never coerce unknown raw into PURCHASE.
    if mapped == "UNKNOWN" and canonical == PROVIDER_EVENT_PURCHASE and raw:
        errors.append(
            f"{path}.provider_event_type: unknown raw {raw!r} must not be forced to PURCHASE"
        )
        row["provider_event_type"] = "UNKNOWN"
        row["requires_review"] = True
        row["review_reason"] = "PROVIDER_EVENT_UNKNOWN"
    # Sign preservation hint for credits/refunds/reversals/voids.
    total = row.get("total_amount")
    if total is not None and canonical in _SIGNED_EVENT_HINTS:
        try:
            amt = to_optional_decimal(total)
        except (FuelFloatForbidden, TypeError, ValueError):
            amt = None
        if amt is not None and amt > 0:
            warnings.append(
                f"{path}: {canonical} has positive total_amount; verify provider sign preserved"
            )


def _validate_currency(
    row: MutableMapping[str, Any],
    *,
    path: str,
    errors: list[str],
) -> None:
    raw = row.get("currency_raw")
    if raw is None and row.get("currency") is None:
        return
    preserved, canonical = classify_currency(raw if isinstance(raw, str) else None)
    if row.get("currency_raw") is None and preserved is not None:
        row["currency_raw"] = preserved
    declared = row.get("currency")
    if declared is not None and canonical is not None and declared != canonical:
        errors.append(
            f"{path}.currency: {declared!r} disagrees with evidenced map from "
            f"currency_raw={raw!r} -> {canonical!r}"
        )
    elif declared is None and canonical is not None:
        row["currency"] = canonical
    elif declared is not None and canonical is None and raw:
        # Unknown alias — keep raw, null canonical, review.
        row["currency"] = None
        row["requires_review"] = True
        row.setdefault("review_reason", "CURRENCY_UNMAPPED")


def validate_fuel_ai_extraction(
    payload: Mapping[str, Any],
    *,
    contract: Mapping[str, Any] | None = None,
) -> FuelMechanicalValidationResult:
    """Validate AI extraction payload. Returns cleaned payload + errors/warnings."""
    errors: list[str] = []
    warnings: list[str] = []
    review_reasons: list[str] = []
    doc = contract or load_fuel_ai_handoff_contract()
    forbidden = contract_ai_forbidden_fields(doc)

    _reject_floats_in_tree(payload, path="$", errors=errors)

    data = dict(payload)
    if data.get("handoff_version") not in {None, HANDOFF_VERSION, doc.get("handoff_version")}:
        warnings.append(
            f"handoff_version {data.get('handoff_version')!r} differs from contract "
            f"{HANDOFF_VERSION}"
        )
    if data.get("profile") not in {None, PROFILE}:
        errors.append(f"profile must be {PROFILE!r}")

    layout = data.get("layout_status")
    if layout == LAYOUT_UNRECOGNIZED:
        review_reasons.append(LAYOUT_UNRECOGNIZED)
    elif layout not in {None, "RECOGNIZED", "REVIEW", LAYOUT_UNRECOGNIZED}:
        errors.append(f"layout_status invalid: {layout!r}")

    header = _as_dict(data.get("header") or {}, path="header", errors=errors) or {}
    data["header"] = header

    txns_raw = data.get("transactions")
    ctl_raw = data.get("controls")
    if not isinstance(txns_raw, list):
        errors.append("transactions: expected array")
        txns_raw = []
    if not isinstance(ctl_raw, list):
        errors.append("controls: expected array")
        ctl_raw = []

    transactions: list[dict[str, Any]] = []
    controls: list[dict[str, Any]] = []
    seen_orders: dict[int, str] = {}

    for i, item in enumerate(txns_raw):
        path = f"transactions[{i}]"
        row = _as_dict(item, path=path, errors=errors)
        if row is None:
            continue
        row = dict(row)
        _strip_forbidden_fields(row, path=path, forbidden=forbidden, errors=errors)
        role = row.get("row_role") or ROW_ROLE_TRANSACTION
        if role == ROW_ROLE_CONTROL:
            errors.append(f"{path}: control row must not appear under transactions")
            continue
        if role == ROW_ROLE_UNKNOWN:
            row["requires_review"] = True
            row.setdefault("review_reason", "SOURCE_ROW_ROLE_UNKNOWN")
            review_reasons.append("SOURCE_ROW_ROLE_UNKNOWN")
        row["row_role"] = ROW_ROLE_TRANSACTION if role != ROW_ROLE_UNKNOWN else ROW_ROLE_UNKNOWN

        order = row.get("source_row_order")
        if not isinstance(order, int):
            errors.append(f"{path}.source_row_order: required int")
        else:
            if order in seen_orders:
                errors.append(
                    f"{path}.source_row_order={order}: conflicts with {seen_orders[order]} "
                    "(source-row exclusivity)"
                )
            else:
                seen_orders[order] = path

        if not row.get("transaction_datetime_source"):
            errors.append(f"{path}.transaction_datetime_source: required")
        if "provider_raw" not in row or not isinstance(row.get("provider_raw"), dict):
            errors.append(f"{path}.provider_raw: required object")
            row["provider_raw"] = {}

        # Controls must not silently become purchases merely because they carry an amount.
        if row.get("control_type") is not None or row.get("control_type_raw") is not None:
            errors.append(
                f"{path}: control markers (control_type/control_type_raw) are not allowed "
                "on transaction rows; place provider controls under controls[]"
            )

        _check_decimal_fields(row, path=path, errors=errors)
        _validate_timezone_provenance(row, path=path, errors=errors, warnings=warnings)
        _validate_event(row, path=path, errors=errors, warnings=warnings)
        _validate_currency(row, path=path, errors=errors)

        # Ambiguous/unknown stays reviewable; never force PURCHASE.
        if row.get("provider_event_type") == "UNKNOWN":
            row["requires_review"] = True
            row.setdefault("review_reason", "PROVIDER_EVENT_UNKNOWN")
            review_reasons.append("PROVIDER_EVENT_UNKNOWN")

        transactions.append(row)

    for i, item in enumerate(ctl_raw):
        path = f"controls[{i}]"
        row = _as_dict(item, path=path, errors=errors)
        if row is None:
            continue
        row = dict(row)
        _strip_forbidden_fields(row, path=path, forbidden=forbidden, errors=errors)
        role = row.get("row_role") or ROW_ROLE_CONTROL
        if role == ROW_ROLE_TRANSACTION:
            errors.append(f"{path}: transaction row must not appear under controls")
            continue
        row["row_role"] = ROW_ROLE_CONTROL

        order = row.get("source_row_order")
        if not isinstance(order, int):
            errors.append(f"{path}.source_row_order: required int")
        else:
            if order in seen_orders:
                errors.append(
                    f"{path}.source_row_order={order}: conflicts with {seen_orders[order]} "
                    "(source-row exclusivity)"
                )
            else:
                seen_orders[order] = path

        if "provider_raw" not in row or not isinstance(row.get("provider_raw"), dict):
            errors.append(f"{path}.provider_raw: required object")
            row["provider_raw"] = {}

        ctype = row.get("control_type")
        if ctype is None:
            row["control_type"] = "UNKNOWN"
            ctype = "UNKNOWN"
        if ctype not in CONTROL_TYPES:
            errors.append(f"{path}.control_type: invalid {ctype!r}")
            row["control_type"] = "UNKNOWN"
            ctype = "UNKNOWN"
        if ctype in {"UNKNOWN", "OTHER"}:
            row["requires_review"] = True
            row.setdefault("review_reason", "CONTROL_TYPE_UNKNOWN")
            review_reasons.append("CONTROL_TYPE_UNKNOWN")

        _check_decimal_fields(row, path=path, errors=errors)
        _validate_currency(row, path=path, errors=errors)
        controls.append(row)

    warn_list = list(data.get("warnings") or [])
    if not isinstance(data.get("warnings"), list):
        errors.append("warnings: expected array")
        warn_list = []
    warn_list.extend(warnings)

    cleaned = {
        "handoff_version": data.get("handoff_version") or HANDOFF_VERSION,
        "profile": PROFILE,
        "layout_status": layout or "RECOGNIZED",
        "header": header,
        "transactions": transactions,
        "controls": controls,
        "warnings": warn_list,
    }

    requires_review = bool(review_reasons) or cleaned["layout_status"] in {
        LAYOUT_UNRECOGNIZED,
        "REVIEW",
    }
    ok = len(errors) == 0
    return FuelMechanicalValidationResult(
        ok=ok,
        payload=cleaned,
        errors=errors,
        warnings=warn_list,
        requires_review=requires_review,
        review_reasons=sorted(set(review_reasons)),
    )


def assert_no_forbidden_authority_fields(row: Mapping[str, Any]) -> None:
    present = sorted(AI_FORBIDDEN_AUTHORITY_FIELDS.intersection(row.keys()))
    if present:
        raise ValueError(f"Forbidden AI authority fields present: {present}")
