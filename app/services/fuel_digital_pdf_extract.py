"""Generic digital-PDF source-row extraction driven by Fuel provider profiles.

Profile section ``digital_pdf_extraction`` defines layout-bound parsing rules.
Provider-specific source labels live in the profile JSON — not hardcoded here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Final, Mapping, Sequence

from app.services.fuel_provider_profile import load_provider_profile, match_provider_layout
from app.services.pdf_text_extract import extract_text_and_pages_from_pdf_bytes

_DATETIME_RE = re.compile(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}")
_MONEY_TOKEN_RE = re.compile(r"^-?[\d,]+\.\d+$|^-?[\d,]+$")
_CUR_RE = re.compile(r"^[A-Z]{2}$")

ROW_KIND_HEADER: Final[str] = "HEADER"
ROW_KIND_TRANSACTION: Final[str] = "TRANSACTION"
ROW_KIND_TRANSACTION_SUBTOTAL: Final[str] = "TRANSACTION_SUBTOTAL"
ROW_KIND_PAGE1_SUMMARY: Final[str] = "PAGE1_SUMMARY"
ROW_KIND_GRAND_TOTAL: Final[str] = "GRAND_TOTAL"
ROW_KIND_LEGEND: Final[str] = "LEGEND"


class FuelDigitalPdfExtractError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class DigitalPdfSourceRow:
    row_kind: str
    source_fields: dict[str, str | None] = field(default_factory=dict)
    source_page: int | None = None


def _digital_spec(profile: Mapping[str, Any]) -> Mapping[str, Any]:
    spec = profile.get("digital_pdf_extraction")
    if not isinstance(spec, Mapping) or not spec.get("enabled"):
        raise FuelDigitalPdfExtractError(
            "DIGITAL_PDF_EXTRACTION_DISABLED",
            "Provider profile has no enabled digital_pdf_extraction section",
        )
    return spec


def _is_money_token(tok: str) -> bool:
    return bool(_MONEY_TOKEN_RE.match(tok))


def parse_money_tokens_from_right(
    tokens: list[str],
    *,
    use_final_amount_label: bool = False,
) -> dict[str, str | None]:
    """Parse trailing money columns using fixed token counts (profile table layout)."""
    work = list(tokens)
    has_cur = bool(work) and _CUR_RE.match(work[-1])
    cur = work.pop() if has_cur else None
    final_key = "FINAL AMOUNT" if use_final_amount_label else "Final AMT"
    fields: dict[str, str | None]
    if len(work) == 8:
        qty, pre_tax, hst, gst, pst, qst, disc_rate, final_val = work
        fields = {
            "QTY": qty,
            "Pre Tax AMT": pre_tax,
            "HST": hst,
            "GST": gst,
            "PST": pst,
            "QST": qst,
            "Disc Rate": disc_rate,
            "Disc AMT": None,
            final_key: final_val,
            "CUR": cur,
        }
    elif len(work) == 9:
        qty, pre_tax, hst, gst, pst, qst, disc_rate, disc_amt, final_val = work
        fields = {
            "QTY": qty,
            "Pre Tax AMT": pre_tax,
            "HST": hst,
            "GST": gst,
            "PST": pst,
            "QST": qst,
            "Disc Rate": disc_rate,
            "Disc AMT": disc_amt,
            final_key: final_val,
            "CUR": cur,
        }
    elif len(work) == 7:
        pre_tax, hst, gst, pst, qst, disc_amt, final_val = work
        fields = {
            "Pre Tax AMT": pre_tax,
            "HST": hst,
            "GST": gst,
            "PST": pst,
            "QST": qst,
            "Disc AMT": disc_amt,
            final_key: final_val,
            "CUR": cur,
        }
    elif len(work) == 1 and use_final_amount_label:
        fields = {final_key: work[0], "CUR": cur}
    else:
        raise FuelDigitalPdfExtractError("MONEY_ROW_PARSE", f"unexpected money token count: {work!r}")
    return fields


def _split_site_name_city(
    tokens: list[str],
    *,
    profile: Mapping[str, Any],
) -> tuple[str, str]:
    spec = _digital_spec(profile)
    split_spec = spec.get("site_name_city_split") or {}
    mode = str(split_spec.get("mode") or "")
    if mode != "uppercase_prefix_until_mixed_case_else_pair":
        raise FuelDigitalPdfExtractError(
            "SITE_SPLIT_UNSUPPORTED",
            f"Unsupported site_name_city_split mode: {mode!r}",
        )
    if not tokens:
        raise FuelDigitalPdfExtractError("SITE_SPLIT", "missing site name/city tokens")
    if len(tokens) == 1:
        return tokens[0], tokens[0]
    if len(tokens) == 2:
        return tokens[0], tokens[1]
    for i, tok in enumerate(tokens):
        if any(ch.islower() for ch in tok):
            if i == 0:
                raise FuelDigitalPdfExtractError(
                    "SITE_NAME_CITY_AMBIGUOUS",
                    "cannot split Site Name / Site City without column boundaries",
                )
            return " ".join(tokens[:i]), " ".join(tokens[i:])
    raise FuelDigitalPdfExtractError(
        "SITE_NAME_CITY_AMBIGUOUS",
        "cannot split Site Name / Site City without column boundaries",
    )


def _parse_transaction_tail(
    tokens: list[str],
    *,
    profile: Mapping[str, Any],
) -> dict[str, str | None]:
    if len(tokens) < 14:
        raise FuelDigitalPdfExtractError("TXN_PARSE", f"transaction tail too short: {tokens!r}")
    work = list(tokens)
    cur = work.pop()
    if not _CUR_RE.match(cur):
        raise FuelDigitalPdfExtractError("TXN_PARSE", f"expected CUR, got {cur!r}")
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
    legend = profile.get("product_code_legend") or {}
    if str(prod).strip() not in legend and str(prod).strip().upper() not in legend:
        raise FuelDigitalPdfExtractError("TXN_PARSE", f"unknown product code: {prod!r}")
    site_number = work.pop(0)
    if not site_number.isdigit():
        raise FuelDigitalPdfExtractError("TXN_PARSE", f"expected Site #, got {site_number!r}")
    site_name, site_city = _split_site_name_city(work, profile=profile)
    return {
        "Site #": site_number,
        "Site Name": site_name,
        "Site City": site_city,
        "Prov/ST": prov_st,
        "Prod": prod,
        "QTY": qty,
        "Retail": retail,
        "Billed": billed,
        "Pre Tax AMT": pre_tax_amt,
        "HST": hst,
        "GST": gst,
        "PST": pst,
        "QST": qst,
        "Disc Rate": disc_rate,
        "Disc AMT": disc_amt,
        "Final AMT": final_amt,
        "CUR": cur,
    }


def _parse_transaction_line(line: str, *, profile: Mapping[str, Any]) -> dict[str, str | None]:
    spec = _digital_spec(profile)
    auth_re = re.compile(str(spec.get("transaction_auth_line_pattern") or "^$"))
    if not auth_re.match(line):
        raise FuelDigitalPdfExtractError("TXN_PARSE", f"not a transaction line: {line!r}")
    dt_match = _DATETIME_RE.search(line)
    if not dt_match:
        raise FuelDigitalPdfExtractError("TXN_PARSE", f"no Date on transaction line: {line!r}")
    txn_date = dt_match.group(0)
    before = line[: dt_match.start()].strip()
    after = line[dt_match.end() :].strip()
    before_tokens = before.split()
    auth_code = before_tokens[0]
    unit_number = before_tokens[-1]
    driver_name = " ".join(before_tokens[1:-1])
    tail = _parse_transaction_tail(after.split(), profile=profile)
    return {
        "Auth Code": auth_code,
        "Driver Name": driver_name,
        "Unit #": unit_number,
        "Date": txn_date,
        **tail,
    }


def _parse_subtotal_line(line: str, *, with_product: bool) -> dict[str, str | None]:
    tokens = line.split()
    if tokens[0] != "SUBTOTAL":
        raise FuelDigitalPdfExtractError("SUBTOTAL_PARSE", line)
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
        raise FuelDigitalPdfExtractError("SUBTOTAL_PARSE", f"unexpected token count: {line!r}")
    return {
        "row_label": "SUBTOTAL",
        "PRODUCT": product,
        "QTY": qty,
        "Pre Tax AMT": pre_tax,
        "HST": hst,
        "GST": gst,
        "PST": pst,
        "QST": qst,
        "Disc Rate": disc_rate,
        "Disc AMT": disc_amt,
        "Final AMT": final_amt,
        "CUR": cur,
    }


def _parse_page1_summary_line(line: str) -> dict[str, str | None]:
    if line.startswith("Card #"):
        tokens = line.split()
        product = tokens[2] if len(tokens) > 2 else None
        money = parse_money_tokens_from_right(tokens[3:])
        money["row_label"] = "Card #"
        money["PRODUCT"] = product
        return money
    if "Fuel Total" in line:
        tokens = line.split()
        card_number = tokens[0]
        money = parse_money_tokens_from_right(tokens[3:])
        money["row_label"] = "Fuel Total"
        money["card_number"] = card_number
        return money
    if line.startswith("DF "):
        money = parse_money_tokens_from_right(line.split()[1:])
        money["row_label"] = "DF"
        return money
    if line.startswith("Sub Total"):
        money = parse_money_tokens_from_right(line.split()[2:])
        money["row_label"] = "Sub Total"
        return money
    raise FuelDigitalPdfExtractError("SUMMARY_PARSE", line)


def _parse_grand_total_line(line: str) -> dict[str, str | None]:
    tokens = line.split()
    if tokens[0] in {"Manual", "Express"}:
        label = tokens[0]
        if len(tokens) == 3 and _CUR_RE.match(tokens[-1]):
            return {"row_label": label, "FINAL AMOUNT": tokens[1], "CUR": tokens[2]}
        if len(tokens) == 2:
            return {"row_label": label, "FINAL AMOUNT": tokens[1], "CUR": None}
    if len(tokens) >= 2 and tokens[0] == "Grand" and tokens[1] == "Total":
        money = parse_money_tokens_from_right(tokens[2:], use_final_amount_label=True)
        money["row_label"] = "Grand Total"
        return money
    product = tokens[0]
    money = parse_money_tokens_from_right(tokens[1:], use_final_amount_label=True)
    money["PRODUCT"] = product
    money["row_label"] = product
    return money


def _parse_header_from_page1(lines: list[str]) -> dict[str, str | None]:
    header: dict[str, str | None] = {}
    try:
        idx = next(i for i, ln in enumerate(lines) if ln.strip() == "Client info")
    except StopIteration:
        raise FuelDigitalPdfExtractError("HEADER_PARSE", "Client info not found") from None

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
            if i + 1 < len(flat) and re.match(r"\d{2}:\d{2}:\d{2}", flat[i + 1]):
                dates.append(f"{date_part} {flat[i + 1]}")
                i += 2
            else:
                dates.append(date_part)
                i += 1
        else:
            i += 1
    if len(dates) >= 4:
        header["invoice_date"] = dates[0]
        header["start_date"] = dates[1]
        header["end_date"] = dates[2]
        header["due_date"] = dates[3]

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


def extract_digital_pdf_source_rows(
    *,
    provider_code: str,
    pdf_bytes: bytes,
) -> tuple[list[DigitalPdfSourceRow], list[str], str]:
    """Profile-driven digital PDF extraction (embedded text only, no OCR)."""
    _full, page_texts, extract_warnings = extract_text_and_pages_from_pdf_bytes(pdf_bytes)
    pages = [{"page_number": i + 1, "text": t} for i, t in enumerate(page_texts)]
    profile = load_provider_profile(provider_code)
    layout = match_provider_layout(profile, page_texts=pages)
    if layout.status != "RECOGNIZED":
        raise FuelDigitalPdfExtractError(
            "LAYOUT_UNRECOGNIZED",
            f"layout status={layout.status} missing={layout.missing_required_anchors}",
        )
    _digital_spec(profile)
    parser_version = f"{profile['provider_code']}:{profile['profile_version']}"

    spec = _digital_spec(profile)
    auth_re = re.compile(str(spec.get("transaction_auth_line_pattern") or "^$"))

    warnings = list(extract_warnings)
    rows: list[DigitalPdfSourceRow] = []

    page1_lines = [ln.strip() for ln in page_texts[0].splitlines() if ln.strip()]
    page2_lines = [ln.strip() for ln in page_texts[1].splitlines() if ln.strip()] if len(page_texts) > 1 else []

    header_fields = _parse_header_from_page1(page1_lines)
    header_fields.update(_parse_tax_ids_page2(page2_lines))
    rows.append(DigitalPdfSourceRow(ROW_KIND_HEADER, header_fields, source_page=1))

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
                        DigitalPdfSourceRow(
                            ROW_KIND_LEGEND,
                            {"Code": parts[0], "Product Name": parts[1]},
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
                    DigitalPdfSourceRow(
                        ROW_KIND_GRAND_TOTAL,
                        _parse_grand_total_line(line),
                        source_page=page_num,
                    )
                )
                continue
            if auth_re.match(line):
                rows.append(
                    DigitalPdfSourceRow(
                        ROW_KIND_TRANSACTION,
                        _parse_transaction_line(line, profile=profile),
                        source_page=page_num,
                    )
                )
                continue
            if line.startswith("SUBTOTAL"):
                with_product = line.startswith("SUBTOTAL ") and not _is_money_token(line.split()[1])
                rows.append(
                    DigitalPdfSourceRow(
                        ROW_KIND_TRANSACTION_SUBTOTAL,
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
                    DigitalPdfSourceRow(
                        ROW_KIND_PAGE1_SUMMARY,
                        _parse_page1_summary_line(line),
                        source_page=page_num,
                    )
                )
    return rows, warnings, parser_version


def parse_header_datetime_tokens(flat: Sequence[str]) -> list[str]:
    """Expose header date parsing for tests (no invented time components)."""
    dates: list[str] = []
    i = 0
    flat_list = list(flat)
    while i < len(flat_list):
        if re.match(r"\d{4}-\d{2}-\d{2}", flat_list[i]):
            date_part = flat_list[i]
            if i + 1 < len(flat_list) and re.match(r"\d{2}:\d{2}:\d{2}", flat_list[i + 1]):
                dates.append(f"{date_part} {flat_list[i + 1]}")
                i += 2
            else:
                dates.append(date_part)
                i += 1
        else:
            i += 1
    return dates
