"""BVD Implementation 1 — digital PDF extraction into fuel_bvd column shapes.

Uses generic Fuel BVD profile layout recognition + embedded PDF text (no OCR).
Does not write fuel_transactions, canonical aliases, or reconciliation inputs.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Final

from app.services.fuel_provider_profile import load_provider_profile, match_provider_layout
from app.services.pdf_text_extract import extract_text_and_pages_from_pdf_bytes

BVD_PROVIDER_CODE: Final[str] = "BVD"

ROW_HEADER: Final[str] = "HEADER"
ROW_TRANSACTION: Final[str] = "TRANSACTION"
ROW_TRANSACTION_SUBTOTAL: Final[str] = "TRANSACTION_SUBTOTAL"
ROW_PAGE1_SUMMARY: Final[str] = "PAGE1_SUMMARY"
ROW_GRAND_TOTAL: Final[str] = "GRAND_TOTAL"
ROW_LEGEND: Final[str] = "LEGEND"

_DATETIME_RE = re.compile(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}")
_TXN_AUTH_RE = re.compile(r"^A\d{6,}-[A-Z]{2}\b")
_MONEY_TOKEN_RE = re.compile(r"^-?[\d,]+\.\d+$|^-?[\d,]+$")
_CUR_RE = re.compile(r"^[A-Z]{2}$")


class FuelBvdExtractionError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class FuelBvdExtractedRow:
    row_type: str
    fields: dict[str, str | None] = field(default_factory=dict)
    source_page: int | None = None


def _is_money_token(tok: str) -> bool:
    return bool(_MONEY_TOKEN_RE.match(tok))


def _parse_transaction_tail(tokens: list[str]) -> dict[str, str | None]:
    """Parse site # through CUR from tokens after transaction datetime."""
    if len(tokens) < 14:
        raise FuelBvdExtractionError("BVD_TXN_PARSE", f"transaction tail too short: {tokens!r}")
    work = list(tokens)
    cur = work.pop()
    if not _CUR_RE.match(cur):
        raise FuelBvdExtractionError("BVD_TXN_PARSE", f"expected CUR, got {cur!r}")
    final_amt = work.pop()
    disc_amt = work.pop()
    disc_rate = work.pop()
    qst = work.pop()
    pst = work.pop()
    gst = work.pop()
    hst = work.pop()
    pre_tax_amt = work.pop()
    billed = work.pop()
    retail = work.pop()
    qty = work.pop()
    prod = work.pop()
    prov_st = work.pop()
    site_number = work.pop(0)
    if not site_number.isdigit():
        raise FuelBvdExtractionError("BVD_TXN_PARSE", f"expected site #, got {site_number!r}")
    if not work:
        raise FuelBvdExtractionError("BVD_TXN_PARSE", "missing site name/city")
    if len(work) >= 3:
        site_name = " ".join(work[:2])
        site_city = " ".join(work[2:])
    elif len(work) == 2:
        site_name, site_city = work[0], work[1]
    else:
        site_name = site_city = work[0]
    return {
        "site_number": site_number,
        "site_name": site_name,
        "site_city": site_city,
        "prov_st": prov_st,
        "prod": prod,
        "qty": qty,
        "retail": retail,
        "billed": billed,
        "pre_tax_amt": pre_tax_amt,
        "hst": hst,
        "gst": gst,
        "pst": pst,
        "qst": qst,
        "disc_rate": disc_rate,
        "disc_amt": disc_amt,
        "final_amt": final_amt,
        "cur": cur,
    }


def _parse_transaction_line(line: str) -> dict[str, str | None]:
    dt_match = _DATETIME_RE.search(line)
    if not dt_match:
        raise FuelBvdExtractionError("BVD_TXN_PARSE", f"no datetime in transaction line: {line!r}")
    txn_date = dt_match.group(0)
    before = line[: dt_match.start()].strip()
    after = line[dt_match.end() :].strip()
    before_tokens = before.split()
    auth_code = before_tokens[0]
    unit_number = before_tokens[-1]
    driver_name = " ".join(before_tokens[1:-1])
    tail = _parse_transaction_tail(after.split())
    return {
        "auth_code": auth_code,
        "driver_name": driver_name,
        "unit_number": unit_number,
        "transaction_date": txn_date,
        **tail,
    }


def _parse_subtotal_line(line: str, *, with_product: bool) -> dict[str, str | None]:
    tokens = line.split()
    if tokens[0] != "SUBTOTAL":
        raise FuelBvdExtractionError("BVD_SUBTOTAL_PARSE", line)
    tokens = tokens[1:]
    product: str | None = None
    if with_product and tokens and not _is_money_token(tokens[0]):
        product = tokens[0]
        tokens = tokens[1:]
    has_cur = bool(tokens) and _CUR_RE.match(tokens[-1])
    cur = tokens.pop() if has_cur else None
    if len(tokens) == 8:
        qty, pre_tax, hst, gst, pst, qst, disc_amt, final_amt = tokens
        disc_rate = None
    elif len(tokens) == 9:
        qty, pre_tax, hst, gst, pst, qst, disc_rate, disc_amt, final_amt = tokens
    else:
        raise FuelBvdExtractionError("BVD_SUBTOTAL_PARSE", f"unexpected token count: {line!r}")
    out: dict[str, str | None] = {
        "row_label": "SUBTOTAL",
        "product": product,
        "qty": qty,
        "pre_tax_amt": pre_tax,
        "hst": hst,
        "gst": gst,
        "pst": pst,
        "qst": qst,
        "disc_rate": disc_rate,
        "disc_amt": disc_amt,
        "final_amt": final_amt,
        "cur": cur,
    }
    return out


def _parse_money_row(
    label_parts: list[str],
    tokens: list[str],
    *,
    use_final_amount: bool = False,
) -> dict[str, str | None]:
    has_cur = bool(tokens) and _CUR_RE.match(tokens[-1])
    cur = tokens.pop() if has_cur else None
    final_key = "final_amount" if use_final_amount else "final_amt"
    if len(tokens) == 8:
        qty, pre_tax, hst, gst, pst, qst, disc_rate, disc_amt = tokens[:7]
        final_val = tokens[7]
        fields = {
            "qty": qty,
            "pre_tax_amt": pre_tax,
            "hst": hst,
            "gst": gst,
            "pst": pst,
            "qst": qst,
            "disc_rate": disc_rate,
            "disc_amt": disc_amt,
            final_key: final_val,
            "cur": cur,
        }
    elif len(tokens) == 9:
        qty, pre_tax, hst, gst, pst, qst, disc_rate, disc_amt, final_val = tokens
        fields = {
            "qty": qty,
            "pre_tax_amt": pre_tax,
            "hst": hst,
            "gst": gst,
            "pst": pst,
            "qst": qst,
            "disc_rate": disc_rate,
            "disc_amt": disc_amt,
            final_key: final_val,
            "cur": cur,
        }
    elif len(tokens) == 7:
        pre_tax, hst, gst, pst, qst, disc_amt, final_val = tokens
        fields = {
            "pre_tax_amt": pre_tax,
            "hst": hst,
            "gst": gst,
            "pst": pst,
            "qst": qst,
            "disc_amt": disc_amt,
            final_key: final_val,
            "cur": cur,
        }
    elif len(tokens) == 1 and use_final_amount:
        fields = {final_key: tokens[0], "cur": cur}
    else:
        raise FuelBvdExtractionError("BVD_MONEY_ROW_PARSE", f"{label_parts!r} {tokens!r}")
    row_label = " ".join(label_parts).strip()
    fields["row_label"] = row_label or None
    return fields


def _parse_page1_summary_line(line: str) -> dict[str, str | None]:
    if line.startswith("Card #"):
        tokens = line.split()
        product = tokens[2] if len(tokens) > 2 else None
        money = _parse_money_row(["Card #"], tokens[3:])
        money["product"] = product
        return money
    if "Fuel Total" in line:
        tokens = line.split()
        card_number = tokens[0]
        money = _parse_money_row(["Fuel Total"], tokens[3:])
        money["card_number"] = card_number
        return money
    if line.startswith("DF "):
        return _parse_money_row(["DF"], line.split()[1:])
    if line.startswith("Sub Total"):
        return _parse_money_row(["Sub Total"], line.split()[2:])
    raise FuelBvdExtractionError("BVD_SUMMARY_PARSE", line)


def _parse_grand_total_line(line: str) -> dict[str, str | None]:
    tokens = line.split()
    if tokens[0] in {"Manual", "Express"}:
        label = tokens[0]
        if len(tokens) == 3 and _CUR_RE.match(tokens[-1]):
            return {"row_label": label, "final_amount": tokens[1], "cur": tokens[2]}
        if len(tokens) == 2:
            return {"row_label": label, "final_amount": tokens[1], "cur": None}
    if len(tokens) >= 2 and tokens[0] == "Grand" and tokens[1] == "Total":
        money = _parse_money_row(["Grand Total"], tokens[2:], use_final_amount=True)
        money["row_label"] = "Grand Total"
        return money
    product = tokens[0]
    money = _parse_money_row([product], tokens[1:], use_final_amount=True)
    money["product"] = product
    money["row_label"] = product
    return money


def _parse_header_from_page1(lines: list[str]) -> dict[str, str | None]:
    header: dict[str, str | None] = {}
    try:
        idx = next(i for i, ln in enumerate(lines) if ln.strip() == "Client info")
    except StopIteration:
        raise FuelBvdExtractionError("BVD_HEADER_PARSE", "Client info not found") from None
    for i, ln in enumerate(lines):
        if ln.startswith("972201") or (ln.split() and ln.split()[0].isdigit() and "Invoice" in lines[max(0, i - 2)]):
            parts = ln.split()
            if parts[0].isdigit():
                header["invoice_number"] = parts[0]
                if len(parts) > 1:
                    date_lines = []
                    j = i
                    while j < len(lines) and j < i + 10:
                        date_lines.append(lines[j])
                        j += 1
                break
    # Invoice block after header row
    inv_idx = next(i for i, ln in enumerate(lines) if "Invoice Date" in ln and "Number" in ln)
    block: list[str] = []
    for ln in lines[inv_idx + 1 : inv_idx + 12]:
        if ln.startswith("Client info"):
            break
        block.append(ln.strip())
    flat: list[str] = []
    for ln in block:
        flat.extend(ln.split())
    if flat and flat[0].isdigit():
        header["invoice_number"] = flat[0]
        flat = flat[1:]
    dates: list[str] = []
    i = 0
    while i < len(flat):
        if re.match(r"\d{4}-\d{2}-\d{2}", flat[i]):
            date_part = flat[i]
            time_part = flat[i + 1] if i + 1 < len(flat) and re.match(r"\d{2}:\d{2}:\d{2}", flat[i + 1]) else "00:00:00"
            if not re.match(r"\d{2}:\d{2}:\d{2}", time_part):
                time_part = "00:00:00"
                dates.append(f"{date_part} {time_part}")
                i += 1
            else:
                dates.append(f"{date_part} {time_part}")
                i += 2
        else:
            i += 1
    if len(dates) >= 4:
        header["invoice_date"], header["start_date"], header["end_date"], header["due_date"] = dates[:4]

    header["client_name"] = lines[idx + 1].strip()
    addr_lines: list[str] = []
    phone: str | None = None
    email: str | None = None
    for ln in lines[idx + 2 :]:
        if ln.startswith("Fuel Card Transactions"):
            break
        if ln.startswith("Address:"):
            addr_lines.append(ln.replace("Address:", "", 1).strip())
        elif ln.startswith("Phone:"):
            phone = ln.replace("Phone:", "", 1).strip()
        elif ln.startswith("Email:"):
            email = ln.replace("Email:", "", 1).strip() or None
        elif addr_lines and not ln.startswith("Transactions"):
            addr_lines.append(ln.strip())
    header["client_address"] = " ".join(addr_lines).strip() or None
    header["client_phone"] = phone
    header["client_email"] = email

    for ln in lines:
        if ln.startswith("Transactions for card"):
            header["card_number"] = ln.split()[-1]
            break
    return header


def _parse_tax_ids_page2(lines: list[str]) -> dict[str, str | None]:
    out: dict[str, str | None] = {}
    for ln in lines:
        if ln.startswith("HST#"):
            out["hst_number"] = ln.replace("HST#", "", 1).strip()
        elif ln.startswith("QST#"):
            out["qst_number"] = ln.replace("QST#", "", 1).strip()
    return out


def extract_bvd_rows_from_digital_pdf(
    pdf_bytes: bytes,
) -> tuple[list[FuelBvdExtractedRow], list[str], str]:
    """Return extracted rows, warnings, and parser_version stamp."""
    _full, page_texts, extract_warnings = extract_text_and_pages_from_pdf_bytes(pdf_bytes)
    pages = [{"page_number": i + 1, "text": t} for i, t in enumerate(page_texts)]
    profile = load_provider_profile(BVD_PROVIDER_CODE)
    layout = match_provider_layout(profile, page_texts=pages)
    if layout.status != "RECOGNIZED":
        raise FuelBvdExtractionError(
            "BVD_LAYOUT_UNRECOGNIZED",
            f"layout status={layout.status} missing={layout.missing_required_anchors}",
        )
    parser_version = f"{profile['provider_code']}:{profile['profile_version']}"

    warnings = list(extract_warnings)
    rows: list[FuelBvdExtractedRow] = []

    page1_lines = [ln.strip() for ln in page_texts[0].splitlines() if ln.strip()]
    page2_lines = [ln.strip() for ln in page_texts[1].splitlines() if ln.strip()] if len(page_texts) > 1 else []

    header_fields = _parse_header_from_page1(page1_lines)
    header_fields.update(_parse_tax_ids_page2(page2_lines))
    rows.append(FuelBvdExtractedRow(ROW_HEADER, header_fields, source_page=1))

    in_grand = False
    in_legend = False
    for page_num, lines in ((1, page1_lines), (2, page2_lines)):
        for line in lines:
            if line.startswith("Auth Code"):
                continue
            if line.startswith("Grand Totals"):
                in_grand = True
                continue
            if line.startswith("Legend"):
                in_legend = True
                in_grand = False
                continue
            if line.startswith("Code Product"):
                continue
            if line.startswith("Page "):
                continue
            if in_legend:
                parts = line.split(None, 1)
                if len(parts) == 2:
                    rows.append(
                        FuelBvdExtractedRow(
                            ROW_LEGEND,
                            {"legend_code": parts[0], "legend_product_name": parts[1]},
                            source_page=page_num,
                        )
                    )
                continue
            if in_grand and page_num == 2:
                if line.startswith("HST#") or line.startswith("QST#"):
                    continue
                if line.startswith("PRODUCT "):
                    continue
                rows.append(
                    FuelBvdExtractedRow(
                        ROW_GRAND_TOTAL,
                        _parse_grand_total_line(line),
                        source_page=page_num,
                    )
                )
                continue
            if _TXN_AUTH_RE.match(line):
                rows.append(
                    FuelBvdExtractedRow(
                        ROW_TRANSACTION,
                        _parse_transaction_line(line),
                        source_page=page_num,
                    )
                )
                continue
            if line.startswith("SUBTOTAL"):
                with_product = line.startswith("SUBTOTAL ") and not line.startswith("SUBTOTAL ") is False
                with_product = "SUBTOTAL TA" in line or (
                    line.startswith("SUBTOTAL ") and not _is_money_token(line.split()[1])
                )
                rows.append(
                    FuelBvdExtractedRow(
                        ROW_TRANSACTION_SUBTOTAL,
                        _parse_subtotal_line(line, with_product=with_product),
                        source_page=page_num,
                    )
                )
                continue
            if page_num == 1 and (
                line.startswith("Card #")
                or "Fuel Total" in line
                or line.startswith("DF ")
                or line.startswith("Sub Total")
            ):
                rows.append(
                    FuelBvdExtractedRow(
                        ROW_PAGE1_SUMMARY,
                        _parse_page1_summary_line(line),
                        source_page=page_num,
                    )
                )
    return rows, warnings, parser_version


def extracted_row_to_column_dict(row: FuelBvdExtractedRow) -> dict[str, Any]:
    return {"row_type": row.row_type, **row.fields}
