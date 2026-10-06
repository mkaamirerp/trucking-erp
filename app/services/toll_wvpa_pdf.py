"""Explicit WVPA monthly statement PDF profile.

Uses the shared Document Platform PDF text extractor. Does not guess document type.
Does not post TollTransaction rows.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, Final

from app.document_platform.capabilities.pdf.text_extract import (
    extract_text_and_pages_from_pdf_bytes,
)
from app.models.toll import PDF_PROFILE_EZPASS_WVPA_MONTHLY

TOLL_WVPA_PARSER_NAME: Final[str] = "wvpa_monthly_statement_pdf"
TOLL_WVPA_PARSER_VERSION: Final[str] = "1"
MAX_TOLL_PDF_BYTES: Final[int] = 20 * 1024 * 1024
MAX_TOLL_PDF_REVIEW_ROWS: Final[int] = 50_000

_DATE_RE = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{2}|\d{4})$")
_TIME_RE = re.compile(r"^(\d{1,2}:\d{2})(?::\d{2})?$")
_AGENCY_RE = re.compile(r"^[A-Z]{2,8}$")
_CHARGE_RE = re.compile(r"^\(?\$?[\d,]+\.\d{2}\)?$")
_AMPM_RE = re.compile(r"^(AM|PM)$", re.IGNORECASE)
_PLATE_RE = re.compile(r"^[A-Z]{2}[A-Z0-9]{3,8}$")
_TRANSPONDER_RE = re.compile(r"^\d{8,}$")
_HEADER_FRAGMENTS = frozenset(
    {
        "post date",
        "agency",
        "entry time",
        "exit time",
        "entry",
        "location",
        "lane",
        "exit location",
        "exit lane",
        "transponder #",
        "plate #",
        "trip charge",
        "($)",
        "entry location",
        "entry lane",
        "summary",
        "payment details",
        "transaction details",
        "transaction date",
        "transaction type",
        "transaction description",
        "payment type",
        "amount ($)",
    }
)
_GROUP_RE = re.compile(
    r"Transactions for Transponder#\s*(\d+)(?:\s+and\s+Plate#\s*([A-Z0-9]+))?",
    re.IGNORECASE,
)
_ZERO_GROUP_RE = re.compile(
    r"no transactions|0 transactions|zero-transaction|zero transaction",
    re.IGNORECASE,
)
_LABEL_VALUE_RE = re.compile(r"^\s*([A-Za-z][A-Za-z0-9 #/.-]{1,40}):\s*(.+?)\s*$")


class TollPdfIntakeError(Exception):
    def __init__(self, code: str, message: str, http_status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status


@dataclass(frozen=True)
class TollPdfReviewParsedRow:
    source_row_order: int
    source_page_number: int
    post_date: date | None
    entry_date: date | None
    entry_time: str | None
    exit_date: date | None
    exit_time: str | None
    agency_raw: str | None
    entry_location: str | None
    entry_lane: str | None
    exit_location: str | None
    exit_lane: str | None
    transponder_number: str | None
    plate_number: str | None
    trip_charge: Decimal
    trip_charge_raw: str
    source_group_transponder: str | None
    source_group_plate: str | None
    provider_raw: dict[str, Any]


@dataclass(frozen=True)
class TollPdfParseResult:
    profile_code: str
    parser_name: str
    parser_version: str
    encoding_warnings: tuple[str, ...]
    source_page_count: int
    statement_date: date | None
    account_number: str | None
    period_start: date | None
    period_end: date | None
    start_balance: Decimal | None
    end_balance: Decimal | None
    total_payment_amount: Decimal | None
    total_payment_count: int | None
    source_total_trip_count: int | None
    source_total_trip_charge: Decimal | None
    rows: tuple[TollPdfReviewParsedRow, ...]
    parsed_trip_count: int
    parsed_total_trip_charge: Decimal
    trip_count_matches: bool
    trip_total_matches: bool
    reconciliation_ok: bool
    source_metadata: dict[str, Any] = field(default_factory=dict)
    source_hash: str = ""
    byte_size: int = 0


def parse_wvpa_trip_charge(raw: str) -> Decimal:
    """WVPA profile: parentheses are a printed charge, not a refund/negative."""
    text = (raw or "").strip()
    if not text:
        raise TollPdfIntakeError("TOLL_PDF_CHARGE", "Trip charge is missing")
    if text.startswith("(") and text.endswith(")"):
        text = text[1:-1].strip()
    text = text.replace("$", "").replace(",", "").strip()
    try:
        value = Decimal(text)
    except InvalidOperation as exc:
        raise TollPdfIntakeError("TOLL_PDF_CHARGE", f"Invalid trip charge {raw!r}") from exc
    if value < 0:
        raise TollPdfIntakeError(
            "TOLL_PDF_CHARGE",
            "WVPA trip charge parsed negative; profile treats parentheses as a charge",
        )
    return value


def _parse_date(token: str) -> date | None:
    match = _DATE_RE.match(token.strip())
    if match is None:
        return None
    month, day, year = (int(match.group(1)), int(match.group(2)), int(match.group(3)))
    if year < 100:
        year += 2000
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _parse_money_label(raw: str) -> Decimal | None:
    if not raw:
        return None
    text = raw.strip()
    if text.startswith("(") and text.endswith(")"):
        text = text[1:-1]
    text = text.replace("$", "").replace(",", "").strip()
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def _looks_like_header(line: str) -> bool:
    lowered = line.lower()
    if lowered in _HEADER_FRAGMENTS:
        return True
    return "post date" in lowered and "agency" in lowered and "trip charge" in lowered


def _is_footer(line: str) -> bool:
    lowered = line.lower()
    return (
        lowered.startswith("run date")
        or lowered.startswith("page ")
        or lowered.startswith("do not pay")
        or "customer service center" in lowered
        or "monthly summary statement" in lowered
        or lowered.startswith("p.o. box")
        or lowered.startswith(",")
        or bool(re.fullmatch(r"\d{5}(?:-\d{4})?", line))
    )


def _consume_datetime(tokens: list[str], index: int) -> tuple[date | None, str | None, int]:
    if index >= len(tokens):
        return None, None, index
    parsed_date = _parse_date(tokens[index])
    if parsed_date is None:
        return None, None, index
    index += 1
    if index < len(tokens) and _TIME_RE.match(tokens[index].split()[0]):
        return parsed_date, tokens[index], index + 1
    return parsed_date, None, index


def _merge_ampm(tokens: list[str]) -> list[str]:
    merged: list[str] = []
    for token in tokens:
        if merged and _AMPM_RE.match(token) and _TIME_RE.match(merged[-1].split()[0]):
            merged[-1] = f"{merged[-1]} {token.upper()}"
        else:
            merged.append(token)
    return merged


def _assign_middle(middle: list[str]) -> tuple[str | None, str | None, str | None, str | None]:
    entry_location = entry_lane = exit_location = exit_lane = None
    if len(middle) >= 4:
        entry_location, entry_lane, exit_location, exit_lane = middle[0], middle[1], middle[2], middle[3]
    elif len(middle) == 3:
        entry_location, entry_lane, exit_location = middle
    elif len(middle) == 2:
        if middle[0].isdigit() and middle[1].isdigit():
            entry_lane, exit_lane = middle
        else:
            entry_location, entry_lane = middle
    elif len(middle) == 1:
        if middle[0].isdigit():
            entry_lane = middle[0]
        else:
            entry_location = middle[0]
    return entry_location, entry_lane, exit_location, exit_lane


def _parse_transaction_tokens(
    tokens: list[str],
    *,
    page_number: int,
    group_transponder: str | None,
    group_plate: str | None,
    source_row_order: int,
    source_line: str,
) -> TollPdfReviewParsedRow | None:
    tokens = _merge_ampm([token for token in tokens if token])
    if len(tokens) < 3:
        return None
    charge_token = tokens[-1]
    if not _CHARGE_RE.match(charge_token):
        return None
    post_date = _parse_date(tokens[0])
    if post_date is None:
        return None
    agency = tokens[1] if _AGENCY_RE.match(tokens[1]) else None
    if agency is None:
        return None
    index = 2
    entry_date, entry_time, index = _consume_datetime(tokens, index)
    exit_date, exit_time, index = _consume_datetime(tokens, index)
    raw_middle = tokens[index:-1]
    transponder = group_transponder
    plate = group_plate
    rest: list[str] = []
    for token in raw_middle:
        if group_transponder and token == group_transponder:
            transponder = token
            continue
        if _TRANSPONDER_RE.match(token):
            transponder = token
            continue
        if group_plate and token == group_plate:
            plate = token
            continue
        if _PLATE_RE.match(token):
            plate = token
            continue
        rest.append(token)
    entry_location, entry_lane, exit_location, exit_lane = _assign_middle(rest)
    charge = parse_wvpa_trip_charge(charge_token)
    return TollPdfReviewParsedRow(
        source_row_order=source_row_order,
        source_page_number=page_number,
        post_date=post_date,
        entry_date=entry_date,
        entry_time=entry_time,
        exit_date=exit_date,
        exit_time=exit_time,
        agency_raw=agency,
        entry_location=entry_location,
        entry_lane=entry_lane,
        exit_location=exit_location,
        exit_lane=exit_lane,
        transponder_number=transponder,
        plate_number=plate,
        trip_charge=charge,
        trip_charge_raw=charge_token,
        source_group_transponder=group_transponder,
        source_group_plate=group_plate,
        provider_raw={
            "line": source_line,
            "profile_code": PDF_PROFILE_EZPASS_WVPA_MONTHLY,
            "trip_charge_raw": charge_token,
            "group_transponder": group_transponder,
            "group_plate": group_plate,
            "source_page_number": page_number,
            "layout": "columnar" if "\n" in source_line else "line",
        },
    )


def _parse_transaction_line(
    line: str,
    *,
    page_number: int,
    group_transponder: str | None,
    group_plate: str | None,
    source_row_order: int,
) -> TollPdfReviewParsedRow | None:
    return _parse_transaction_tokens(
        line.split(),
        page_number=page_number,
        group_transponder=group_transponder,
        group_plate=group_plate,
        source_row_order=source_row_order,
        source_line=line,
    )


def _extract_period(value: str) -> tuple[date | None, date | None]:
    parts = re.split(r"\s+to\s+", value, maxsplit=1, flags=re.IGNORECASE)
    if len(parts) != 2:
        return None, None
    return _parse_date(parts[0].strip()), _parse_date(parts[1].strip())


def _harvest_columnar_controls(meta: dict[str, Any], text: str) -> None:
    """Read WVPA monthly summary controls when labels and values are on separate lines."""
    if meta.get("_period_start") is None or meta.get("_period_end") is None:
        match = re.search(
            r"(\d{1,2}/\d{1,2}/\d{2,4})\s+TO\s+(\d{1,2}/\d{1,2}/\d{2,4})",
            text,
            re.IGNORECASE,
        )
        if match:
            meta["_period_start"] = _parse_date(match.group(1))
            meta["_period_end"] = _parse_date(match.group(2))
    lowered = text.lower()
    trip_at = lowered.find("total number of trips")
    if trip_at >= 0 and (
        meta.get("_source_total_trip_count") is None or meta.get("_source_total_trip_charge") is None
    ):
        ints: list[int] = []
        moneys: list[Decimal] = []
        for raw in text[trip_at:].splitlines():
            line = raw.strip()
            if not line:
                continue
            if line.lower().startswith("transactions for transponder"):
                break
            if _CHARGE_RE.match(line):
                money = _parse_money_label(line)
                if money is not None:
                    moneys.append(money)
                continue
            if re.fullmatch(r"\d+", line):
                ints.append(int(line))
        if meta.get("_source_total_trip_count") is None and ints:
            meta["_source_total_trip_count"] = ints[-1]
        if meta.get("_source_total_trip_charge") is None and moneys:
            meta["_source_total_trip_charge"] = moneys[-1]


def _apply_label(meta: dict[str, Any], label: str, value: str) -> None:
    key = re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")
    meta[key] = value
    if key == "statement_date":
        meta["_statement_date"] = _parse_date(value)
    elif key == "account_number":
        meta["_account_number"] = value.strip()
    elif key in {"statement_period", "period"}:
        start, end = _extract_period(value)
        meta["_period_start"] = start
        meta["_period_end"] = end
    elif key in {"start_balance", "beginning_balance"}:
        meta["_start_balance"] = _parse_money_label(value)
    elif key in {"end_balance", "ending_balance"}:
        meta["_end_balance"] = _parse_money_label(value)
    elif key in {"total_number_of_trips", "total_trips"}:
        digits = re.sub(r"[^\d]", "", value)
        meta["_source_total_trip_count"] = int(digits) if digits else None
    elif key in {"total_trip_charges", "total_trip_charge"}:
        meta["_source_total_trip_charge"] = _parse_money_label(value)
    elif key in {"total_payment_amount", "payments", "payment_amount"}:
        meta["_total_payment_amount"] = _parse_money_label(value)
    elif key in {"total_payment_count", "payment_count", "number_of_payments"}:
        digits = re.sub(r"[^\d]", "", value)
        meta["_total_payment_count"] = int(digits) if digits else None


def validate_toll_pdf_file(*, filename: str, body: bytes, content_type: str | None = None) -> None:
    if not body:
        raise TollPdfIntakeError("TOLL_PDF_EMPTY", "PDF file is empty")
    if len(body) > MAX_TOLL_PDF_BYTES:
        raise TollPdfIntakeError(
            "TOLL_PDF_TOO_LARGE",
            f"PDF file exceeds {MAX_TOLL_PDF_BYTES} bytes",
        )
    name = filename.rsplit("/", 1)[-1].rsplit("\\", 1)[-1].lower()
    if name.endswith((".csv", ".xlsx", ".xls", ".png", ".jpg", ".jpeg")):
        raise TollPdfIntakeError("TOLL_PDF_NOT_PDF", "Toll PDF intake accepts PDF FILE sources only")
    declared = (content_type or "").split(";", 1)[0].strip().lower()
    if declared and declared not in {"application/pdf", "application/octet-stream", ""}:
        if declared.startswith("text/") or declared.startswith("image/"):
            raise TollPdfIntakeError("TOLL_PDF_NOT_PDF", "Declared content type is not a PDF FILE")
    if not body.startswith(b"%PDF"):
        raise TollPdfIntakeError("TOLL_PDF_NOT_PDF", "File bytes are not PDF")


def parse_wvpa_monthly_statement_pdf(body: bytes) -> TollPdfParseResult:
    """Fail closed unless the PDF matches the explicit WVPA monthly statement profile."""
    full_text, page_texts, warnings = extract_text_and_pages_from_pdf_bytes(body)
    joined = "\n".join(page_texts) if page_texts else full_text
    lowered = joined.lower()
    if not any(page_texts) and not full_text.strip():
        raise TollPdfIntakeError(
            "TOLL_PDF_UNREADABLE",
            "Shared embedded-text extractor returned no text; OCR is out of scope for this slice",
        )
    is_ezpass = "e-zpass" in lowered or "ezpass" in lowered
    is_wvpa_issuer = "west virginia parkways" in lowered or "wvpa" in lowered
    if not (is_ezpass or is_wvpa_issuer):
        raise TollPdfIntakeError(
            "TOLL_PDF_PROFILE_MISMATCH",
            "PDF is not an E-ZPass/WVPA monthly statement",
        )
    if "statement period" not in lowered and "for period" not in lowered:
        raise TollPdfIntakeError(
            "TOLL_PDF_PROFILE_MISMATCH",
            "PDF is missing WVPA statement period",
        )
    if "transactions for transponder" not in lowered:
        raise TollPdfIntakeError(
            "TOLL_PDF_PROFILE_MISMATCH",
            "PDF is missing WVPA transponder transaction groups",
        )
    if "total number of trips" not in lowered and "total trips" not in lowered:
        raise TollPdfIntakeError(
            "TOLL_PDF_PROFILE_MISMATCH",
            "PDF is missing WVPA trip-count control",
        )
    if "total trip charge" not in lowered:
        raise TollPdfIntakeError(
            "TOLL_PDF_PROFILE_MISMATCH",
            "PDF is missing WVPA trip-charge control",
        )

    meta: dict[str, Any] = {}
    rows: list[TollPdfReviewParsedRow] = []
    zero_groups: list[dict[str, str | None]] = []
    group_transponder: str | None = None
    group_plate: str | None = None
    group_has_row = False
    pending_tokens: list[str] = []
    pending_page = 1

    def close_empty_group() -> None:
        nonlocal group_has_row
        if group_transponder and not group_has_row:
            zero_groups.append({"transponder": group_transponder, "plate": group_plate})

    def flush_pending() -> None:
        nonlocal pending_tokens, group_has_row
        if not pending_tokens:
            return
        parsed = _parse_transaction_tokens(
            pending_tokens,
            page_number=pending_page,
            group_transponder=group_transponder,
            group_plate=group_plate,
            source_row_order=len(rows) + 1,
            source_line="\n".join(pending_tokens),
        )
        pending_tokens = []
        if parsed is None:
            return
        if len(rows) >= MAX_TOLL_PDF_REVIEW_ROWS:
            raise TollPdfIntakeError(
                "TOLL_PDF_TOO_MANY_ROWS",
                f"PDF exceeds {MAX_TOLL_PDF_REVIEW_ROWS} review rows",
            )
        rows.append(parsed)
        group_has_row = True

    for page_index, page_text in enumerate(page_texts or [full_text], start=1):
        for raw_line in (page_text or "").splitlines():
            line = raw_line.strip()
            if not line:
                continue
            labeled = _LABEL_VALUE_RE.match(line)
            if labeled:
                _apply_label(meta, labeled.group(1), labeled.group(2))
                continue
            group = _GROUP_RE.search(line)
            if group:
                flush_pending()
                close_empty_group()
                group_transponder = group.group(1)
                group_plate = group.group(2)
                group_has_row = False
                continue
            if line.lower().startswith("total trip charges for transponder"):
                flush_pending()
                continue
            if _looks_like_header(line) or _is_footer(line):
                continue
            if _ZERO_GROUP_RE.search(line):
                continue
            if group_transponder is None:
                continue
            if len(rows) >= MAX_TOLL_PDF_REVIEW_ROWS:
                raise TollPdfIntakeError(
                    "TOLL_PDF_TOO_MANY_ROWS",
                    f"PDF exceeds {MAX_TOLL_PDF_REVIEW_ROWS} review rows",
                )
            parsed = _parse_transaction_line(
                line,
                page_number=page_index,
                group_transponder=group_transponder,
                group_plate=group_plate,
                source_row_order=len(rows) + 1,
            )
            if parsed is not None:
                flush_pending()
                rows.append(parsed)
                group_has_row = True
                continue
            if not pending_tokens and _parse_date(line) is None:
                continue
            pending_page = page_index
            pending_tokens.append(line)
            if _CHARGE_RE.match(line):
                flush_pending()
    flush_pending()
    close_empty_group()
    _harvest_columnar_controls(meta, "\n".join(page_texts or [full_text]))
    if not rows:
        raise TollPdfIntakeError(
            "TOLL_PDF_NO_DATA_ROWS",
            "WVPA statement has no parsable toll review rows",
        )

    parsed_total = sum((row.trip_charge for row in rows), Decimal("0.00"))
    source_count = meta.get("_source_total_trip_count")
    source_total = meta.get("_source_total_trip_charge")
    count_ok = source_count is not None and int(source_count) == len(rows)
    total_ok = source_total is not None and Decimal(source_total) == parsed_total
    public_meta = {
        "labels": {key: value for key, value in meta.items() if not key.startswith("_")},
        "zero_transaction_groups": zero_groups,
        "statement_issuer": "WVPA",
        "extraction_warnings": list(warnings),
    }
    return TollPdfParseResult(
        profile_code=PDF_PROFILE_EZPASS_WVPA_MONTHLY,
        parser_name=TOLL_WVPA_PARSER_NAME,
        parser_version=TOLL_WVPA_PARSER_VERSION,
        encoding_warnings=tuple(warnings),
        source_page_count=len(page_texts) if page_texts else 0,
        statement_date=meta.get("_statement_date"),
        account_number=meta.get("_account_number"),
        period_start=meta.get("_period_start"),
        period_end=meta.get("_period_end"),
        start_balance=meta.get("_start_balance"),
        end_balance=meta.get("_end_balance"),
        total_payment_amount=meta.get("_total_payment_amount"),
        total_payment_count=meta.get("_total_payment_count"),
        source_total_trip_count=source_count,
        source_total_trip_charge=source_total,
        rows=tuple(rows),
        parsed_trip_count=len(rows),
        parsed_total_trip_charge=parsed_total,
        trip_count_matches=bool(count_ok),
        trip_total_matches=bool(total_ok),
        reconciliation_ok=bool(count_ok and total_ok),
        source_metadata=public_meta,
        byte_size=len(body),
    )
