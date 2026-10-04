"""Heuristic receipt text → structured manual-entry extraction payload."""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any

from app.services.fuel_manual_receipt_mask import is_masked_vehicle_id
from app.services.fuel_money import to_optional_decimal

_MONEY = re.compile(r"(?<!\d)(\d{1,3}(?:,\d{3})*|\d+)\.(\d{2})(?!\d)")
_AT_GAL_PRICE = re.compile(r"@\s*(\d+\.\d{2,4})\s*/\s*gal", re.I)
_UNIT_PRICE = re.compile(
    r"(?<!\d)(\d+\.\d{2,4})\s*(?:/|\s+per\s+)\s*(?:gal(?:lon)?s?|litre?s?|liters?|l)\b",
    re.I,
)
_PRICE_CANDIDATE = re.compile(
    r"(?<!\d)(\d+\.\d{3})\s*(?:/|\s+per\s+)\s*(?:litre?s?|liters?|l)\b",
    re.I,
)
_DATE_SLASH = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b")
_QTY_GAL = re.compile(
    r"(?<!\d)(\d{1,3}(?:,\d{3})*|\d+)\.(\d{1,4})\s*(?:GAL(?:LON)?S?|gal(?:lon)?s?)\b",
    re.I,
)
_QTY_L = re.compile(
    r"(?<!\d)(\d{1,3}(?:,\d{3})*|\d+)\.(\d{1,4})\s*(?:LITRE?S?|LITERS?|L)\b",
    re.I,
)


def _norm_lines(text: str) -> list[str]:
    lines = [re.sub(r"\s+", " ", ln).strip() for ln in text.replace("\r", "\n").split("\n")]
    return [ln for ln in lines if ln]


def _parse_money(raw: str) -> str | None:
    m = _MONEY.search(raw.replace("$", " "))
    if not m:
        return None
    whole, frac = m.group(1), m.group(2)
    return f"{whole.replace(',', '')}.{frac}"


def _all_money_values(raw: str) -> list[str]:
    out: list[str] = []
    for m in _MONEY.finditer(raw.replace("$", " ")):
        whole, frac = m.group(1), m.group(2)
        out.append(f"{whole.replace(',', '')}.{frac}")
    return out


def _iso_date(mm: str, dd: str, yyyy: str) -> str:
    return f"{yyyy}-{int(mm):02d}-{int(dd):02d}"


def _first_match(pattern: re.Pattern[str], text: str, group: int = 1) -> str | None:
    m = pattern.search(text)
    if not m:
        return None
    return m.group(group).strip()


def _label_value(lines: list[str], labels: tuple[str, ...]) -> str | None:
    lower_labels = tuple(l.lower() for l in labels)
    for i, line in enumerate(lines):
        low = line.lower()
        for lab in lower_labels:
            if low.startswith(lab):
                rest = line.split(":", 1)[-1].strip() if ":" in line else line[len(lab) :].strip()
                if rest:
                    return rest
                if i + 1 < len(lines):
                    return lines[i + 1]
    for line in lines:
        low = line.lower()
        for lab in lower_labels:
            if lab in low:
                parts = re.split(r"[:#]", line, maxsplit=1)
                if len(parts) == 2 and parts[1].strip():
                    return parts[1].strip()
    return None


def parse_receipt_text(text: str) -> dict[str, Any]:
    """Parse OCR/digital receipt text into a structured extraction dict."""
    lines = _norm_lines(text)
    blob = "\n".join(lines)
    lower_blob = blob.lower()

    out: dict[str, Any] = {"source_text_lines": lines}

    if "love" in lower_blob and "s" in lower_blob.replace("love's", "loves"):
        out["vendor"] = "Love's"
    elif "pilot" in lower_blob:
        out["vendor"] = "Pilot"

    dm = _DATE_SLASH.search(blob)
    if dm:
        out["transaction_date"] = _iso_date(dm.group(1), dm.group(2), dm.group(3))

    store = _label_value(lines, ("Store #", "Store#", "Store No"))
    if store:
        out["store_number"] = re.sub(r"\D", "", store) or store

    for i, line in enumerate(lines):
        if re.search(r"\b(ON|BC|AB|SK|MB|QC|NB|NS|PE|NL|YT|NT|NU)\b", line) and re.search(r"\b[A-Z]\d[A-Z]", line):
            out.setdefault("province_state", re.search(r"\b(ON|BC|AB|SK|MB|QC|NB|NS|PE|NL|YT|NT|NU)\b", line).group(1))
            city_m = re.match(r"^([A-Za-z][A-Za-z\s.'-]+),", line)
            if city_m:
                out["city"] = city_m.group(1).strip()
        if re.search(r"\b(SC|AL|AK|AZ|AR|CA|CO|CT|DE|FL|GA|HI|ID|IL|IN|IA|KS|KY|LA|ME|MD|MA|MI|MN|MS|MO|MT|NE|NV|NH|NJ|NM|NY|NC|ND|OH|OK|OR|PA|RI|SD|TN|TX|UT|VT|VA|WA|WV|WI|WY)\b", line):
            st = re.search(
                r"\b(SC|AL|AK|AZ|AR|CA|CO|CT|DE|FL|GA|HI|ID|IL|IN|IA|KS|KY|LA|ME|MD|MA|MI|MN|MS|MO|MT|NE|NV|NH|NJ|NM|NY|NC|ND|OH|OK|OR|PA|RI|SD|TN|TX|UT|VT|VA|WA|WV|WI|WY)\b",
                line,
            )
            if st:
                out.setdefault("province_state", st.group(1))
            city_m = re.search(r",\s*([A-Za-z][A-Za-z\s.'-]+),", line)
            if city_m:
                out.setdefault("city", city_m.group(1).strip())

    product = _label_value(lines, ("Product", "PROD", "Item"))
    if product:
        out["product"] = product
    elif "trkds" in lower_blob:
        out["product"] = "TRKDS / diesel"
    elif "truck diesel" in lower_blob:
        out["product"] = "Truck Diesel"

    pump = _label_value(lines, ("Pump", "PUMP"))
    if pump:
        out["pump"] = re.sub(r"\D", "", pump) or pump

    qty_gal = _QTY_GAL.search(blob)
    qty_l = _QTY_L.search(blob)
    if qty_gal and (not qty_l or qty_gal.start() <= qty_l.start()):
        out["quantity"] = f"{qty_gal.group(1).replace(',', '')}.{qty_gal.group(2)}"
        out["quantity_unit"] = "gallons"
    elif qty_l:
        out["quantity"] = f"{qty_l.group(1).replace(',', '')}.{qty_l.group(2)}"
        out["quantity_unit"] = "litres"

    unit_prices = [m.group(1) for m in _AT_GAL_PRICE.finditer(blob)]
    unit_prices.extend(m.group(1) for m in _UNIT_PRICE.finditer(blob))
    litre_candidates = [m.group(1) for m in _PRICE_CANDIDATE.finditer(blob)]
    if litre_candidates:
        # Preserve order, unique; drop values that look like quantities not prices.
        qty_val = out.get("quantity")
        seen: set[str] = set()
        candidates: list[str] = []
        for c in litre_candidates:
            if c == qty_val:
                continue
            try:
                if Decimal(c) > Decimal("50"):
                    continue
            except InvalidOperation:
                pass
            if c not in seen:
                seen.add(c)
                candidates.append(c)
        if candidates:
            out["unit_price_candidates"] = candidates
    elif unit_prices:
        out["unit_price"] = unit_prices[0]

    sub = _label_value(lines, ("Subtotal", "SUBTOTAL", "Pre-Tax", "PRE-TAX"))
    if sub:
        out["pre_tax_amount"] = _parse_money(sub) or sub
    else:
        for line in lines:
            if "subtotal" in line.lower():
                val = _parse_money(line)
                if val:
                    out["pre_tax_amount"] = val
                    break

    tax_line = _label_value(lines, ("Sales Tax", "SALES TAX", "Tax"))
    if tax_line:
        out["printed_sales_tax"] = _parse_money(tax_line) or tax_line
    for line in lines:
        if "sales tax" in line.lower():
            val = _parse_money(line)
            if val is not None:
                out["printed_sales_tax"] = val
                break

    total = _label_value(lines, ("Total", "TOTAL", "Amount Due", "AMOUNT DUE", "Grand Total"))
    if total:
        out["total_amount"] = _parse_money(total) or total
    if not out.get("total_amount"):
        # Last resort: largest money on receipt often final total
        monies = _all_money_values(blob)
        if monies:
            try:
                out["total_amount"] = max(monies, key=lambda x: Decimal(x))
            except (InvalidOperation, ValueError):
                pass

    receipt_no = _label_value(lines, ("Receipt", "Receipt/Ticket", "Ticket #", "Ticket"))
    if receipt_no:
        out["receipt_ticket_number"] = re.sub(r"\D", "", receipt_no) or receipt_no

    auth = _label_value(lines, ("Authorization", "AUTH", "Auth #"))
    if auth:
        out["authorization_number"] = auth.replace(" ", "")

    card_m = re.search(r"(?:card|visa|mastercard|mc)\s*(?:#|ending)?\s*(\d{4})", lower_blob)
    if card_m:
        out["card"] = f"ending {card_m.group(1)}"

    vehicle = _label_value(lines, ("Unit/Vehicle ID", "Unit #", "Unit", "Vehicle ID", "Vehicle"))
    if vehicle:
        vehicle = vehicle.split()[0]
        if is_masked_vehicle_id(vehicle):
            out["vehicle_id"] = vehicle
        else:
            out["unit_number"] = vehicle

    trailer = _label_value(lines, ("Trailer", "TRAILER"))
    if trailer:
        out["trailer_number"] = trailer.split()[0]

    invoice = _label_value(lines, ("Invoice #", "Invoice", "INVOICE"))
    if invoice:
        out["invoice_reference"] = re.sub(r"\D", "", invoice) or invoice

    company = _label_value(lines, ("Company", "COMPANY", "Customer", "Fleet"))
    if company:
        out["company"] = company

    for line in lines:
        low = line.lower()
        if "hst" in low and "included" in low:
            out["tax_included_note"] = line
            break
        if "tax" in low and "included" in low and "price" in low:
            out["tax_included_note"] = line
            break

    cur_m = re.search(r"\b(USD|CAD|EUR)\b", blob)
    if cur_m:
        out["currency"] = cur_m.group(1)

    if to_optional_decimal(out.get("total_amount")) is None:
        out.setdefault("parse_warnings", []).append("total_amount_not_found")
    if not out.get("transaction_date"):
        out.setdefault("parse_warnings", []).append("transaction_date_not_found")

    return out
