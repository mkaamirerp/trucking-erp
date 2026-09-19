"""Segment 2 provider control totals: reconciliation evidence, never purchases.

Controls are associated with a source batch. They must not hydrate
`fuel_transactions` and must not increment purchase totals. The later
reconciliation engine reads these records; this module does not implement it.
"""

from __future__ import annotations

import re
from decimal import Decimal
from typing import Any, Final, Iterable, Mapping

from app.services.fuel_canonical import classify_currency
from app.services.fuel_money import FuelFloatForbidden, quantize_money, to_decimal

ROW_ROLE_TRANSACTION = "TRANSACTION"
ROW_ROLE_CONTROL = "CONTROL"

CONTROL_TYPE_CARD_TOTAL = "CARD_TOTAL"
CONTROL_TYPE_INVOICE_SUMMARY = "INVOICE_SUMMARY"
CONTROL_TYPE_INVOICE_TOTAL = "INVOICE_TOTAL"
CONTROL_TYPE_STATEMENT_TOTAL = "STATEMENT_TOTAL"
CONTROL_TYPE_CURRENCY_TOTAL = "CURRENCY_TOTAL"
CONTROL_TYPE_UNIT_SUBTOTAL = "UNIT_SUBTOTAL"
CONTROL_TYPE_GROUP_SUBTOTAL = "GROUP_SUBTOTAL"
CONTROL_TYPE_PRODUCT_SUBTOTAL = "PRODUCT_SUBTOTAL"
CONTROL_TYPE_TAX_CONTROL = "TAX_CONTROL"
CONTROL_TYPE_DISCOUNT_CONTROL = "DISCOUNT_CONTROL"
CONTROL_TYPE_PROVIDER_DECLARED_TOTAL = "PROVIDER_DECLARED_TOTAL"
CONTROL_TYPE_CALCULATED_DETAIL_TOTAL = "CALCULATED_DETAIL_TOTAL"
CONTROL_TYPE_VARIANCE = "VARIANCE"
CONTROL_TYPE_OTHER = "OTHER"
CONTROL_TYPE_UNKNOWN = "UNKNOWN"

CONTROL_TYPES: Final[frozenset[str]] = frozenset(
    {
        CONTROL_TYPE_CARD_TOTAL,
        CONTROL_TYPE_INVOICE_SUMMARY,
        CONTROL_TYPE_INVOICE_TOTAL,
        CONTROL_TYPE_STATEMENT_TOTAL,
        CONTROL_TYPE_CURRENCY_TOTAL,
        CONTROL_TYPE_UNIT_SUBTOTAL,
        CONTROL_TYPE_GROUP_SUBTOTAL,
        CONTROL_TYPE_PRODUCT_SUBTOTAL,
        CONTROL_TYPE_TAX_CONTROL,
        CONTROL_TYPE_DISCOUNT_CONTROL,
        CONTROL_TYPE_PROVIDER_DECLARED_TOTAL,
        CONTROL_TYPE_CALCULATED_DETAIL_TOTAL,
        CONTROL_TYPE_VARIANCE,
        CONTROL_TYPE_OTHER,
        CONTROL_TYPE_UNKNOWN,
    }
)

CONTROL_SCOPE_BATCH = "BATCH"
CONTROL_SCOPE_INVOICE = "INVOICE"
CONTROL_SCOPE_STATEMENT = "STATEMENT"
CONTROL_SCOPE_CARD = "CARD"
CONTROL_SCOPE_UNIT = "UNIT"
CONTROL_SCOPE_GROUP = "GROUP"
CONTROL_SCOPE_PRODUCT = "PRODUCT"
CONTROL_SCOPE_CURRENCY = "CURRENCY"
CONTROL_SCOPE_TAX = "TAX"
CONTROL_SCOPE_OTHER = "OTHER"
CONTROL_SCOPE_UNKNOWN = "UNKNOWN"

CONTROL_SCOPES: Final[frozenset[str]] = frozenset(
    {
        CONTROL_SCOPE_BATCH,
        CONTROL_SCOPE_INVOICE,
        CONTROL_SCOPE_STATEMENT,
        CONTROL_SCOPE_CARD,
        CONTROL_SCOPE_UNIT,
        CONTROL_SCOPE_GROUP,
        CONTROL_SCOPE_PRODUCT,
        CONTROL_SCOPE_CURRENCY,
        CONTROL_SCOPE_TAX,
        CONTROL_SCOPE_OTHER,
        CONTROL_SCOPE_UNKNOWN,
    }
)

# Explicit row-type / control-type tokens. Amount presence is never a signal.
_CONTROL_TYPE_ALIASES: Final[dict[str, str]] = {
    "CARD_TOTAL": CONTROL_TYPE_CARD_TOTAL,
    "CARD TOTAL": CONTROL_TYPE_CARD_TOTAL,
    "CARD_SUBTOTAL": CONTROL_TYPE_CARD_TOTAL,
    "CARD SUBTOTAL": CONTROL_TYPE_CARD_TOTAL,
    "INVOICE_SUMMARY": CONTROL_TYPE_INVOICE_SUMMARY,
    "INVOICE SUMMARY": CONTROL_TYPE_INVOICE_SUMMARY,
    "INVOICE_TOTAL": CONTROL_TYPE_INVOICE_TOTAL,
    "INVOICE TOTAL": CONTROL_TYPE_INVOICE_TOTAL,
    "GRAND_TOTAL": CONTROL_TYPE_INVOICE_TOTAL,
    "GRAND TOTAL": CONTROL_TYPE_INVOICE_TOTAL,
    "STATEMENT_TOTAL": CONTROL_TYPE_STATEMENT_TOTAL,
    "STATEMENT TOTAL": CONTROL_TYPE_STATEMENT_TOTAL,
    "CURRENCY_TOTAL": CONTROL_TYPE_CURRENCY_TOTAL,
    "CURRENCY SUBTOTAL": CONTROL_TYPE_CURRENCY_TOTAL,
    "UNIT_SUBTOTAL": CONTROL_TYPE_UNIT_SUBTOTAL,
    "UNIT SUBTOTAL": CONTROL_TYPE_UNIT_SUBTOTAL,
    "GROUP_SUBTOTAL": CONTROL_TYPE_GROUP_SUBTOTAL,
    "GROUP SUBTOTAL": CONTROL_TYPE_GROUP_SUBTOTAL,
    "PRODUCT_SUBTOTAL": CONTROL_TYPE_PRODUCT_SUBTOTAL,
    "PRODUCT SUBTOTAL": CONTROL_TYPE_PRODUCT_SUBTOTAL,
    "TAX_CONTROL": CONTROL_TYPE_TAX_CONTROL,
    "TAX TOTAL": CONTROL_TYPE_TAX_CONTROL,
    "GST": CONTROL_TYPE_TAX_CONTROL,
    "HST": CONTROL_TYPE_TAX_CONTROL,
    "PST": CONTROL_TYPE_TAX_CONTROL,
    "QST": CONTROL_TYPE_TAX_CONTROL,
    "DISCOUNT_CONTROL": CONTROL_TYPE_DISCOUNT_CONTROL,
    "DISCOUNT TOTAL": CONTROL_TYPE_DISCOUNT_CONTROL,
    "PROVIDER_DECLARED_TOTAL": CONTROL_TYPE_PROVIDER_DECLARED_TOTAL,
    "CALCULATED_DETAIL_TOTAL": CONTROL_TYPE_CALCULATED_DETAIL_TOTAL,
    "VARIANCE": CONTROL_TYPE_VARIANCE,
    "OTHER": CONTROL_TYPE_OTHER,
    "UNKNOWN": CONTROL_TYPE_UNKNOWN,
}

_SCOPE_ALIASES: Final[dict[str, str]] = {
    "BATCH": CONTROL_SCOPE_BATCH,
    "INVOICE": CONTROL_SCOPE_INVOICE,
    "STATEMENT": CONTROL_SCOPE_STATEMENT,
    "CARD": CONTROL_SCOPE_CARD,
    "UNIT": CONTROL_SCOPE_UNIT,
    "GROUP": CONTROL_SCOPE_GROUP,
    "PRODUCT": CONTROL_SCOPE_PRODUCT,
    "CURRENCY": CONTROL_SCOPE_CURRENCY,
    "TAX": CONTROL_SCOPE_TAX,
    "OTHER": CONTROL_SCOPE_OTHER,
    "UNKNOWN": CONTROL_SCOPE_UNKNOWN,
}

_TRANSACTION_ROW_ALIASES: Final[frozenset[str]] = frozenset(
    {"TRANSACTION", "PURCHASE", "CHARGE", "CREDIT", "REFUND", "REVERSAL", "VOID"}
)

# Evidenced Nationwide CARD_TOTAL label, e.g. "XXXXX87115 Total"
_NATIONWIDE_CARD_TOTAL_LABEL = re.compile(r"^X{3,}\d+\s+Total$", re.IGNORECASE)

REVIEW_REASON_CONTROL_TYPE_UNKNOWN = "CONTROL_TYPE_UNKNOWN"
REVIEW_REASON_CONTROL_SCOPE_UNKNOWN = "CONTROL_SCOPE_UNKNOWN"
REVIEW_REASON_SOURCE_ROW_ROLE_UNKNOWN = "SOURCE_ROW_ROLE_UNKNOWN"


class FuelControlRowError(ValueError):
    """Control/unknown source rows must not be treated as purchases."""


def _norm_token(raw: str | None) -> str:
    return re.sub(r"\s+", " ", (raw or "").strip()).upper()


def classify_control_type(raw: str | None) -> tuple[str | None, str]:
    """Return (control_type_raw, canonical control_type).

    Unknown provider control terminology is never coerced to CARD_TOTAL or
    INVOICE_SUMMARY. Canonical UNKNOWN is REVIEW-eligible later.
    """
    if raw is None:
        return None, CONTROL_TYPE_UNKNOWN
    preserved = str(raw).strip()
    if preserved == "":
        return None, CONTROL_TYPE_UNKNOWN
    token = _norm_token(preserved)
    mapped = _CONTROL_TYPE_ALIASES.get(token)
    if mapped is not None:
        return preserved, mapped
    if token in CONTROL_TYPES:
        return preserved, token
    return preserved, CONTROL_TYPE_UNKNOWN


def classify_control_scope(raw: str | None) -> tuple[str | None, str]:
    """Return (control_scope_raw, canonical control_scope).

    Providers do not share one hierarchy. Unknown scope stays UNKNOWN rather
    than being forced into BATCH/CARD/INVOICE.
    """
    if raw is None:
        return None, CONTROL_SCOPE_UNKNOWN
    preserved = str(raw).strip()
    if preserved == "":
        return None, CONTROL_SCOPE_UNKNOWN
    token = _norm_token(preserved)
    mapped = _SCOPE_ALIASES.get(token)
    if mapped is not None:
        return preserved, mapped
    if token in CONTROL_SCOPES:
        return preserved, token
    return preserved, CONTROL_SCOPE_UNKNOWN


def looks_like_nationwide_card_total_label(label: str | None) -> bool:
    if not label:
        return False
    return _NATIONWIDE_CARD_TOTAL_LABEL.match(label.strip()) is not None


def classify_source_row_role(
    *,
    row_type_raw: str | None = None,
    source_label: str | None = None,
    amount: Any = None,
) -> str:
    """Classify a source row as TRANSACTION or CONTROL.

    `amount` is accepted and ignored. A monetary value never makes a purchase.
    """
    del amount
    token = _norm_token(row_type_raw)
    if token in _CONTROL_TYPE_ALIASES or token in CONTROL_TYPES - {CONTROL_TYPE_OTHER, CONTROL_TYPE_UNKNOWN}:
        return ROW_ROLE_CONTROL
    if looks_like_nationwide_card_total_label(source_label):
        return ROW_ROLE_CONTROL
    if token in _TRANSACTION_ROW_ALIASES:
        return ROW_ROLE_TRANSACTION
    # Unknown / missing row type: not a purchase merely because money is present.
    return ROW_ROLE_CONTROL


def control_requires_review(*, control_type: str, control_scope: str) -> bool:
    return control_type in {CONTROL_TYPE_UNKNOWN, CONTROL_TYPE_OTHER} or control_scope == CONTROL_SCOPE_UNKNOWN


def review_reason_for_control(
    *,
    control_type: str,
    control_scope: str,
    row_type_raw: str | None,
) -> str | None:
    token = _norm_token(row_type_raw)
    recognized = token in _CONTROL_TYPE_ALIASES or token in CONTROL_TYPES or token in _TRANSACTION_ROW_ALIASES
    if control_type == CONTROL_TYPE_UNKNOWN and not recognized:
        return REVIEW_REASON_SOURCE_ROW_ROLE_UNKNOWN
    if control_type == CONTROL_TYPE_UNKNOWN:
        return REVIEW_REASON_CONTROL_TYPE_UNKNOWN
    if control_type == CONTROL_TYPE_OTHER:
        return REVIEW_REASON_CONTROL_TYPE_UNKNOWN
    if control_scope == CONTROL_SCOPE_UNKNOWN:
        return REVIEW_REASON_CONTROL_SCOPE_UNKNOWN
    return None


def assert_row_may_hydrate_as_transaction(
    *,
    row_type_raw: str | None = None,
    source_label: str | None = None,
    amount: Any = None,
) -> None:
    role = classify_source_row_role(
        row_type_raw=row_type_raw, source_label=source_label, amount=amount
    )
    if role != ROW_ROLE_TRANSACTION:
        raise FuelControlRowError(
            "Provider control/summary rows must not hydrate fuel_transactions; "
            f"row_type={row_type_raw!r} label={source_label!r}"
        )


def assert_no_source_row_double_count(
    transaction_source_row_orders: Iterable[int | None],
    control_source_row_orders: Iterable[int | None],
) -> None:
    """The same source row cannot be both a purchase transaction and a control."""
    txn = {o for o in transaction_source_row_orders if o is not None}
    ctl = {o for o in control_source_row_orders if o is not None}
    overlap = sorted(txn.intersection(ctl))
    if overlap:
        raise FuelControlRowError(
            "Source row cannot be both a fuel_transactions purchase and a "
            f"provider control: source_row_order={overlap}"
        )


def purchase_total_from_transactions(transaction_amounts: Iterable[Any]) -> Decimal:
    """Sum transaction money only. Callers must not pass control amounts."""
    total = Decimal("0.0000")
    for amount in transaction_amounts:
        if amount is None:
            continue
        total += quantize_money(amount)
    return quantize_money(total)


def route_provider_source_rows(rows: Iterable[Mapping[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Split source rows into transactions vs controls. Amount never decides role.

    Unknown/non-transaction row types become REVIEW-capable controls, never
    purchases. This is a mechanical safeguard, not a provider parser.
    """
    transactions: list[dict[str, Any]] = []
    controls: list[dict[str, Any]] = []
    for row in rows:
        raw_type = row.get("row_type") or row.get("row_type_raw")
        label = row.get("source_label") or row.get("control_label_raw")
        amount = row.get("amount") if "amount" in row else row.get("total_amount")
        role = classify_source_row_role(
            row_type_raw=None if raw_type is None else str(raw_type),
            source_label=None if label is None else str(label),
            amount=amount,
        )
        type_raw, control_type = classify_control_type(
            None if raw_type is None else str(raw_type)
        )
        if role == ROW_ROLE_TRANSACTION:
            transactions.append(dict(row))
            continue
        if looks_like_nationwide_card_total_label(
            None if label is None else str(label)
        ) and control_type == CONTROL_TYPE_UNKNOWN:
            type_raw = None if label is None else str(label)
            control_type = CONTROL_TYPE_CARD_TOTAL
        scope_raw, control_scope = classify_control_scope(
            None if row.get("control_scope") is None else str(row.get("control_scope"))
        )
        currency_raw, currency = classify_currency(
            None if row.get("currency_raw") is None and row.get("currency") is None
            else str(row.get("currency_raw") or row.get("currency"))
        )
        declared = row.get("declared_amount", amount)
        if isinstance(declared, float) and not isinstance(declared, bool):
            raise FuelFloatForbidden("Control declared_amount must not use float")
        requires = control_requires_review(
            control_type=control_type,
            control_scope=control_scope,
        )
        routed = dict(row)
        routed.update(
            {
                "row_role": ROW_ROLE_CONTROL,
                "control_type_raw": type_raw,
                "control_type": control_type,
                "control_scope_raw": scope_raw,
                "control_scope": control_scope,
                "currency_raw": currency_raw,
                "currency": currency,
                "requires_review": requires,
                "review_reason": review_reason_for_control(
                    control_type=control_type,
                    control_scope=control_scope,
                    row_type_raw=None if raw_type is None else str(raw_type),
                ),
                "declared_amount": None if declared is None else to_decimal(declared),
            }
        )
        if looks_like_nationwide_card_total_label(None if label is None else str(label)):
            routed["review_reason"] = None
            routed["requires_review"] = control_scope == CONTROL_SCOPE_UNKNOWN
        controls.append(routed)
    assert_no_source_row_double_count(
        (r.get("source_row_order") for r in transactions),
        (r.get("source_row_order") for r in controls),
    )
    return {"transactions": transactions, "controls": controls}
