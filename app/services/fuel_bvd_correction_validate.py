"""Validate human-reviewed BVD field values before append-only correction write."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from app.services.fuel_bvd_effective import EFFECTIVE_BVD_FIELD_NAMES
from app.services.fuel_bvd_source_reconciliation import parse_bvd_decimal

_MONEY_FIELDS: frozenset[str] = frozenset(
    {
        "qty",
        "retail",
        "billed",
        "pre_tax_amt",
        "hst",
        "gst",
        "pst",
        "qst",
        "disc_rate",
        "disc_amt",
        "final_amt",
        "final_amount",
        "amount_cashed",
        "express_fee",
    }
)

_DATE_FIELDS: frozenset[str] = frozenset(
    {
        "invoice_date",
        "start_date",
        "end_date",
        "due_date",
        "transaction_date",
    }
)

_DATE_FORMATS = (
    "%Y-%m-%d",
    "%Y-%m-%d %H:%M:%S",
    "%m/%d/%Y",
    "%m/%d/%Y %H:%M:%S",
)

_CUR_RE = re.compile(r"^[A-Za-z]{2,4}$")


class BvdCorrectionValidationError(ValueError):
    def __init__(self, field_name: str, message: str) -> None:
        self.field_name = field_name
        super().__init__(message)


def validate_reviewed_bvd_field(
    field_name: str,
    reviewed_value: str,
    *,
    row_type: str | None = None,
) -> None:
    """Raise BvdCorrectionValidationError if reviewed_value is invalid for field_name."""
    if field_name not in EFFECTIVE_BVD_FIELD_NAMES:
        raise BvdCorrectionValidationError(field_name, f"Field not editable: {field_name}")

    text = reviewed_value if reviewed_value is not None else ""
    stripped = str(text).strip()

    if field_name in _MONEY_FIELDS:
        if not stripped:
            raise BvdCorrectionValidationError(field_name, "Money field cannot be blank")
        _, err = parse_bvd_decimal(stripped)
        if err:
            raise BvdCorrectionValidationError(field_name, f"Invalid money value: {stripped}")
        return

    if field_name in _DATE_FIELDS:
        if not stripped:
            raise BvdCorrectionValidationError(field_name, "Date field cannot be blank")
        for fmt in _DATE_FORMATS:
            try:
                datetime.strptime(stripped, fmt)
                return
            except ValueError:
                continue
        raise BvdCorrectionValidationError(field_name, f"Invalid date: {stripped}")

    if field_name == "cur":
        if not stripped:
            raise BvdCorrectionValidationError(field_name, "Currency cannot be blank")
        if not _CUR_RE.match(stripped):
            raise BvdCorrectionValidationError(field_name, f"Invalid currency code: {stripped}")
        return

    if field_name == "unit_number" and row_type == "TRANSACTION":
        if not stripped:
            raise BvdCorrectionValidationError(field_name, "Unit # cannot be blank on a transaction")
        return

    if field_name == "prod" and row_type == "TRANSACTION":
        if not stripped:
            raise BvdCorrectionValidationError(field_name, "Product cannot be blank on a transaction")
        return

    # Other text fields: allow any non-None string (including empty where not forbidden above).
