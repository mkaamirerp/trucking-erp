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
_CARD_TOTAL_VOLUME_RE = re.compile(
    r"\bTotal\b"
    r"(?:\s+GST\s*\$?[\d,]+\.?\d*)?"
    r"(?:\s+QST\s*\$?[\d,]+\.?\d*)?"
    r"\s+([\d,]+\.\d{2})\b",
    re.IGNORECASE,
)


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

    # CARD_TOTAL layout after the provider labels is:
    #   Volume, Total, USA Discount, Missed Disc
    # OON Fees is not printed on these evidenced CARD_TOTAL lines, so do not
    # manufacture it.
    volume_m = _CARD_TOTAL_VOLUME_RE.search(stripped)
    if volume_m:
        out["control_volume"] = _normalize_money_text(volume_m.group(1))

    named_tax_values = {
        value
        for value in (out.get("GST"), out.get("QST"))
        if value
    }

    two_dec_amounts = [_normalize_money_text(m) for m in _MONEY_TWO_DEC_RE.findall(stripped)]
    two_dec_amounts = [a for a in two_dec_amounts if a]

    # Remove named tax amounts before positional Total/Discount interpretation.
    positional_money = [v for v in two_dec_amounts if v not in named_tax_values]

    if positional_money:
        out["declared_amount"] = positional_money[0]
    if len(positional_money) >= 2:
        out["USA Discount"] = positional_money[1]
    if len(positional_money) >= 3:
        out["Missed Disc"] = positional_money[2]

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

    volume = parsed.get("control_volume")
    if volume and not row.get("control_volume"):
        row["control_volume"] = volume

    usa_discount = parsed.get("USA Discount")
    if usa_discount and not row.get("usa_discount"):
        row["usa_discount"] = usa_discount

    missed_disc = parsed.get("Missed Disc")
    if missed_disc and not row.get("missed_disc"):
        row["missed_disc"] = missed_disc
