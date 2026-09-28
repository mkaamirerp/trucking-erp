"""BVD Express Codes section — provider source rows (not fuel card purchases)."""

from __future__ import annotations

import re
from typing import Any, Final, Mapping

from app.services.fuel_digital_pdf_types import FuelDigitalPdfExtractError

_DATETIME_RE: Final[re.Pattern[str]] = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$")
_EXPRESS_AUTH_RE: Final[re.Pattern[str]] = re.compile(r"^E\d+$")
_MONEY_RE: Final[re.Pattern[str]] = re.compile(r"^-?\d+(?:\.\d+)?$")
_CUR_RE: Final[re.Pattern[str]] = re.compile(r"^[A-Z]{2}$")


def parse_express_transaction_line(line: str) -> dict[str, str | None]:
    """Parse one Express Codes data line (embedded PDF text)."""
    text = line.strip()
    if not text or text.startswith("DATE ") or text.startswith("Page "):
        raise FuelDigitalPdfExtractError("EXPRESS_PARSE", f"not express data: {text!r}")

    parts = text.split()
    if len(parts) < 9:
        raise FuelDigitalPdfExtractError("EXPRESS_PARSE", f"too few tokens: {text!r}")

    if not _DATETIME_RE.match(f"{parts[0]} {parts[1]}"):
        raise FuelDigitalPdfExtractError("EXPRESS_PARSE", f"missing datetime: {text!r}")

    transaction_date = f"{parts[0]} {parts[1]}"
    express_code = parts[2]
    auth_code = parts[3]
    if not _EXPRESS_AUTH_RE.match(auth_code):
        raise FuelDigitalPdfExtractError("EXPRESS_PARSE", f"expected express auth: {auth_code!r}")

    cur_idx = next(
        (i for i in range(len(parts) - 1, 3, -1) if _CUR_RE.match(parts[i])),
        None,
    )
    if cur_idx is None or cur_idx < 6:
        raise FuelDigitalPdfExtractError("EXPRESS_PARSE", f"expected CUR token: {text!r}")
    cur = parts[cur_idx]
    payee_and_notes = " ".join(parts[cur_idx + 1 :]).strip() or None

    total = parts[cur_idx - 1]
    fee = parts[cur_idx - 2]
    amount_cashed = parts[cur_idx - 3]
    for label, val in (
        ("amount_cashed", amount_cashed),
        ("fee", fee),
        ("total", total),
    ):
        if not _MONEY_RE.match(val.replace(",", "")):
            raise FuelDigitalPdfExtractError("EXPRESS_PARSE", f"invalid {label}: {val!r}")

    middle = parts[4:cur_idx - 3]
    tractor: str | None = None
    trailer: str | None = None
    cdl: str | None = None
    trip_number: str | None = None
    driver_parts: list[str] = []

    idx = 0
    if middle and middle[0].isdigit():
        tractor = middle[0]
        idx = 1
    if idx < len(middle):
        driver_parts = middle[idx:]
    driver_name_or_id = " ".join(driver_parts).strip() or None

    return {
        "transaction_date": transaction_date,
        "express_code": express_code,
        "auth_code": auth_code,
        "express_tractor": tractor,
        "express_trailer": trailer,
        "driver_name": driver_name_or_id,
        "express_cdl": cdl,
        "express_trip_number": trip_number,
        "amount_cashed": amount_cashed,
        "express_fee": fee,
        "final_amt": total,
        "cur": cur,
        "payee_raw": payee_and_notes,
        "notes_raw": None,
    }


def parse_express_subtotal_line(line: str) -> dict[str, str | None]:
    """Express section SUBTOTAL amount_cashed fee total (no CUR)."""
    if not line.strip().startswith("SUBTOTAL"):
        raise FuelDigitalPdfExtractError("EXPRESS_SUBTOTAL", line)
    tokens = line.split()[1:]
    if len(tokens) != 3:
        raise FuelDigitalPdfExtractError("EXPRESS_SUBTOTAL", f"expected 3 money tokens: {line!r}")
    amount_cashed, fee, total = tokens
    return {
        "row_label": "EXPRESS SUBTOTAL",
        "amount_cashed": amount_cashed,
        "express_fee": fee,
        "final_amt": total,
    }


def is_express_data_line(line: str) -> bool:
    text = line.strip()
    if not text or text.startswith("DATE ") or text.startswith("Page "):
        return False
    parts = text.split()
    if len(parts) < 9:
        return False
    return _DATETIME_RE.match(f"{parts[0]} {parts[1]}") is not None and _EXPRESS_AUTH_RE.match(parts[3]) is not None
