"""Nationwide CARD_TOTAL control — explicit provider facts from source lines."""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

from app.services.fuel_controls import CONTROL_TYPE_CARD_TOTAL

_CARD_TOTAL_LINE_RE = re.compile(r"^X+\d+\s+Total\b", re.IGNORECASE)
_MONEY_TWO_DEC_RE = re.compile(r"\$([\d,]+\.\d{2})")
_GST_IN_LINE_RE = re.compile(r"\bGST\s*\$?([\d,]+\.?\d*)", re.IGNORECASE)
_QST_IN_LINE_RE = re.compile(r"\bQST\s*\$?([\d,]+\.?\d*)", re.IGNORECASE)


def _normalize_money_text(raw: str) -> str:
    text = raw.replace("$", "").replace(",", "").strip()
    if not text:
        return ""
    try:
        value = Decimal(text)
    except (InvalidOperation, ValueError):
        return text
    return f"{value.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP):f}"


def parse_nationwide_card_total_line(line: str | None) -> dict[str, str | None]:
    """Parse provider-native CARD_TOTAL facts from a control line (parse-time authority)."""
    if not line or not _CARD_TOTAL_LINE_RE.match(line.strip()):
        return {}

    stripped = line.strip()
    card = stripped.split()[0]
    has_gst = bool(_GST_IN_LINE_RE.search(stripped))
    currency = "CAD" if has_gst else "USD"

    out: dict[str, str | None] = {
        "Card Number": card,
        "Currency": currency,
    }

    gst_m = _GST_IN_LINE_RE.search(stripped)
    if gst_m:
        out["GST"] = _normalize_money_text(gst_m.group(1))

    qst_m = _QST_IN_LINE_RE.search(stripped)
    if qst_m:
        qst = _normalize_money_text(qst_m.group(1))
        if qst and qst not in ("0", "0.00"):
            out["QST"] = qst

    two_dec_amounts = [_normalize_money_text(m) for m in _MONEY_TWO_DEC_RE.findall(stripped)]
    two_dec_amounts = [a for a in two_dec_amounts if a]
    if currency == "USD" and two_dec_amounts:
        out["declared_amount"] = two_dec_amounts[0]
    elif currency == "CAD" and two_dec_amounts:
        out["declared_amount"] = max(two_dec_amounts, key=lambda a: Decimal(a))

    return out


def apply_card_total_review_fields(row: dict[str, Any]) -> None:
    """Ensure review API rows expose explicit CARD_TOTAL facts (fill gaps on read/import)."""
    if row.get("control_type") != CONTROL_TYPE_CARD_TOTAL:
        return
    parsed = parse_nationwide_card_total_line(row.get("control_line_raw"))
    if not parsed:
        return

    card = parsed.get("Card Number")
    if card and not row.get("card_number"):
        row["card_number"] = card

    currency = parsed.get("Currency")
    if currency and not row.get("currency"):
        row["currency"] = currency

    declared = parsed.get("declared_amount")
    if declared and not row.get("declared_amount"):
        row["declared_amount"] = declared

    gst = parsed.get("GST")
    if gst and not row.get("gst"):
        row["gst"] = gst

    qst = parsed.get("QST")
    if qst and not row.get("qst"):
        row["qst"] = qst
