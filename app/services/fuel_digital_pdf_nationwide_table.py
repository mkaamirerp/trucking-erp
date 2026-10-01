"""Nationwide digital-PDF table extraction (profile mode ``nationwide_transaction_table``).

Not a standalone Nationwide parser engine — invoked only from
``fuel_digital_pdf_extract`` when the provider profile enables this mode.
"""

from __future__ import annotations

import re
from typing import Any, Mapping, Sequence

from app.services.fuel_digital_pdf_extract import DigitalPdfSourceRow, ROW_KIND_HEADER
from app.services.fuel_digital_pdf_types import FuelDigitalPdfExtractError
from app.services.fuel_nationwide_card_total import parse_nationwide_card_total_line

ROW_KIND_CONTROL: str = "CONTROL"
ROW_KIND_TRANSACTION: str = "TRANSACTION"

_PRODUCT_RE = re.compile(r"\b(DIESEL|REEFER|SCALE)\b")
_TXN_LINE_RE = re.compile(
    r"^(?P<account>\S+)\s+(?P<card>X+\d+)\s+(?P<unit>\d+)\s+(?P<date>\d{4}-\d{2}-\d{2})\s+"
    r"(?P<city_st>.+?)\s+(?P<product>DIESEL|REEFER|SCALE)\s+"
    r"(?P<volume>[\d.]+)\s+\$?(?P<ex_gst>[\d,]+\.?\d*)\s+\$?(?P<total>[\d,]+\.?\d*)\s+"
    r"(?P<network>\S+)\s+(?P<currency>CAD|USD)\s+\$?(?P<usa_disc>[\d,]+\.?\d*)\s+\$?(?P<missed>[\d,]+\.?\d*)\s+"
    r"(?P<oon>.+?)\s*$",
    re.IGNORECASE,
)
_CARD_TOTAL_RE = re.compile(r"^X+\d+\s+Total\b", re.IGNORECASE)
_INVOICE_NUMBER_RE = re.compile(r"\d{8}B-\d{8}")
_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
_GST_LINE_RE = re.compile(r"^GST\s+\$?([\d,]+\.?\d*)", re.IGNORECASE)
_PST_LINE_RE = re.compile(r"^PST\s+\$?([\d,]+\.?\d*)", re.IGNORECASE)
_MONEY_ONLY_LINE_RE = re.compile(r"^\$([\d,]+\.\d{2})$")


def _money_display(value: str) -> str:
    return value.replace("$", "").replace(",", "").strip()


def _split_city_prov(city_st: str) -> tuple[str, str]:
    text = city_st.strip()
    if " " in text:
        city, prov = text.rsplit(" ", 1)
        if len(prov) == 2 and prov.isalpha():
            return city.strip(), prov.upper()
    if len(text) > 2 and text[-2:].isalpha():
        return text[:-2].rstrip("- ").strip(), text[-2:].upper()
    return text, ""


def _parse_nationwide_header(page_texts: Sequence[str]) -> dict[str, str | None]:
    blob = "\n".join(page_texts)
    header: dict[str, str | None] = {}
    inv = _INVOICE_NUMBER_RE.search(blob)
    if inv:
        header["Invoice Number"] = inv.group(0)
        header["account_reference"] = inv.group(0).split("-")[0]
    acct = re.search(r"Account Code\s+(\S+)", blob, re.IGNORECASE)
    if acct:
        header["Account Code"] = acct.group(1)
    page1 = page_texts[0] if page_texts else ""
    if "Due Date:" in page1:
        tail = page1.split("Due Date:", 1)[1]
        inv_dates = _DATE_RE.findall(tail)
        if len(inv_dates) >= 3:
            header["Invoice Start Date:"] = inv_dates[0]
            header["Invoice End Date:"] = inv_dates[1]
            header["Due Date:"] = inv_dates[2]
    cust = re.search(r"Customer Name\s+(.+?)(?:\n|\d{8}B-)", blob, re.IGNORECASE)
    if cust:
        header["Customer Name"] = cust.group(1).strip()
    return header


def _parse_transaction_line(line: str) -> dict[str, str | None]:
    m = _TXN_LINE_RE.match(line.strip())
    if not m:
        raise FuelDigitalPdfExtractError("NATIONWIDE_TXN_PARSE", f"unrecognized transaction line: {line!r}")
    city, prov = _split_city_prov(m.group("city_st"))
    return {
        "Account Code": m.group("account"),
        "Card Number": m.group("card"),
        "Unit #": m.group("unit"),
        "Date": m.group("date"),
        "City": city,
        "Pr/St": prov,
        "Product": m.group("product").upper(),
        "Volume": m.group("volume"),
        "Ex-GST ($/U)": _money_display(m.group("ex_gst")),
        "Total": _money_display(m.group("total")),
        "Network": m.group("network"),
        "Currency": m.group("currency").upper(),
        "USA Discount": _money_display(m.group("usa_disc")),
        "Missed Disc": _money_display(m.group("missed")),
        "OON Fees": m.group("oon").strip(),
    }


def _is_skipped_line(line: str) -> bool:
    s = line.strip()
    if not s:
        return True
    if s.startswith("*") or s.startswith("**"):
        return True
    if s.startswith("Account Code Card Number"):
        return True
    if s.startswith("RED highlighted"):
        return True
    if "See attached CSV" in s:
        return True
    if s == "TRANSACTION BREAKDOWN BY CARD":
        return True
    return False


def _is_control_line(line: str) -> bool:
    s = line.strip()
    if _CARD_TOTAL_RE.match(s):
        return True
    lower = s.casefold()
    if lower.startswith("gst $") or lower.startswith("qst $") or lower.startswith("pst $"):
        return True
    if lower.startswith("total ex-gst"):
        return True
    if lower.startswith("subtotal"):
        return True
    if lower.startswith("this weeks invoice"):
        return True
    if lower.startswith("total outstanding balance"):
        return True
    if lower.startswith("total volume"):
        return True
    if lower.startswith("billing summary"):
        return True
    return False


def _control_fields_from_line(line: str) -> dict[str, str | None]:
    out: dict[str, str | None] = {"control_line_raw": line.strip()}
    gst = _GST_LINE_RE.match(line.strip())
    if gst:
        out["GST"] = _money_display(gst.group(1))
    pst = _PST_LINE_RE.match(line.strip())
    if pst:
        out["PST"] = _money_display(pst.group(1))
    if _CARD_TOTAL_RE.match(line.strip()):
        out["row_label"] = "CARD_TOTAL"
        out.update({k: v for k, v in parse_nationwide_card_total_line(line).items() if v is not None})
    return out


def _page1_billing_control_rows(page_text: str) -> list[DigitalPdfSourceRow]:
    """Billing-summary controls on page 1 (USD declared total after Gallons label)."""
    rows: list[DigitalPdfSourceRow] = []
    lines = [ln.strip() for ln in page_text.splitlines() if ln.strip()]
    for index, line in enumerate(lines):
        if line.casefold() != "gallons":
            continue
        if index + 1 >= len(lines):
            continue
        money_line = lines[index + 1]
        money_match = _MONEY_ONLY_LINE_RE.match(money_line)
        if not money_match:
            continue
        amount = _money_display(money_match.group(1))
        rows.append(
            DigitalPdfSourceRow(
                ROW_KIND_CONTROL,
                {
                    "control_line_raw": f"USD billing total {money_line}",
                    "row_label": "USD_BILLING_TOTAL",
                    "declared_amount": amount,
                    "Currency": "USD",
                },
                source_page=1,
            )
        )
        break
    return rows


def extract_nationwide_digital_pdf_rows(
    *,
    page_texts: Sequence[str],
    profile: Mapping[str, Any],
) -> tuple[list[DigitalPdfSourceRow], list[str]]:
    """Extract header, purchases, and control lines from Nationwide embedded PDF text."""
    warnings: list[str] = []
    rows: list[DigitalPdfSourceRow] = []
    header_fields = _parse_nationwide_header(page_texts)
    rows.append(DigitalPdfSourceRow(ROW_KIND_HEADER, header_fields, source_page=1))
    if page_texts:
        rows.extend(_page1_billing_control_rows(page_texts[0]))

    for page_index, page_text in enumerate(page_texts):
        page_num = page_index + 1
        for line in page_text.splitlines():
            stripped = line.strip()
            if _is_skipped_line(stripped):
                continue
            if _TXN_LINE_RE.match(stripped):
                try:
                    fields = _parse_transaction_line(stripped)
                except FuelDigitalPdfExtractError as exc:
                    warnings.append(str(exc))
                    continue
                rows.append(DigitalPdfSourceRow(ROW_KIND_TRANSACTION, fields, source_page=page_num))
                continue
            if _is_control_line(stripped):
                rows.append(
                    DigitalPdfSourceRow(
                        ROW_KIND_CONTROL,
                        _control_fields_from_line(stripped),
                        source_page=page_num,
                    )
                )
                continue
            if _PRODUCT_RE.search(stripped):
                warnings.append(f"UNPARSED_POSSIBLE_TRANSACTION: {stripped[:120]}")

    if not any(r.row_kind == ROW_KIND_TRANSACTION for r in rows):
        warnings.append("NO_TRANSACTION_ROWS_EXTRACTED")
    return rows, warnings
