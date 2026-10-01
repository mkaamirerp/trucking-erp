"""Nationwide provider — source field contract and import entry."""

from __future__ import annotations

import uuid
from typing import Any

NATIONWIDE_PROVIDER_CODE = "NATIONWIDE"

NW_REVIEW_IN_PROGRESS = "IN_REVIEW"
NW_REVIEW_SOURCE_COMPLETE = "SOURCE_REVIEWED"

ROW_HEADER = "HEADER"
ROW_TRANSACTION = "TRANSACTION"
ROW_CONTROL = "CONTROL"

NATIONWIDE_SOURCE_FIELD_NAMES: tuple[str, ...] = (
    "account_code",
    "invoice_number",
    "invoice_start_date",
    "invoice_end_date",
    "due_date",
    "customer_name",
    "card_number",
    "unit_number",
    "transaction_date",
    "city",
    "prov_st",
    "product",
    "volume",
    "ex_gst_per_unit",
    "total",
    "network",
    "currency",
    "usa_discount",
    "missed_disc",
    "oon_fees",
    "control_type",
    "row_label",
    "control_line_raw",
    "declared_amount",
    "gst",
    "pst",
    "qst",
    "control_volume",
)

_PROVIDER_KEY_TO_COLUMN: dict[str, str] = {
    "Account Code": "account_code",
    "Card Number": "card_number",
    "Unit #": "unit_number",
    "Date": "transaction_date",
    "City": "city",
    "Pr/St": "prov_st",
    "Product": "product",
    "Volume": "volume",
    "Ex-GST ($/U)": "ex_gst_per_unit",
    "Total": "total",
    "Network": "network",
    "Currency": "currency",
    "USA Discount": "usa_discount",
    "Missed Disc": "missed_disc",
    "OON Fees": "oon_fees",
    "GST": "gst",
    "PST": "pst",
    "QST": "qst",
    "declared_amount": "declared_amount",
    "row_label": "row_label",
    "control_line_raw": "control_line_raw",
}

_HEADER_KEY_TO_COLUMN: dict[str, str] = {
    "account_reference": "account_code",
    "Account Code": "account_code",
    "Invoice Number": "invoice_number",
    "Invoice Start Date:": "invoice_start_date",
    "Invoice End Date:": "invoice_end_date",
    "Due Date:": "due_date",
    "Customer Name": "customer_name",
    "statement_start": "invoice_start_date",
    "statement_end": "invoice_end_date",
    "due_date": "due_date",
    "customer_name_raw": "customer_name",
    "invoice_number": "invoice_number",
}


class FuelNationwideImportError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        http_status: int = 400,
        *,
        detail: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status
        self.detail = detail or {}


def map_provider_fields_to_columns(fields: dict[str, Any], *, is_header: bool = False) -> dict[str, str | None]:
    out: dict[str, str | None] = {}
    mapping = _HEADER_KEY_TO_COLUMN if is_header else _PROVIDER_KEY_TO_COLUMN
    for src, col in mapping.items():
        if src in fields and fields[src] is not None:
            out[col] = str(fields[src])
    if not is_header:
        for k, v in fields.items():
            if k in mapping and mapping[k] not in out and v is not None:
                out[mapping[k]] = str(v)
    return out


async def import_nationwide_digital_pdf(
    db: Any,
    *,
    tenant_id: int,
    tenant_slug: str,
    pdf_bytes: bytes,
    filename: str,
    uploaded_by: str | None,
) -> tuple[uuid.UUID, int, str]:
    from app.services.fuel_nationwide_stage import create_nationwide_import_stage_from_pdf

    stage_id, row_count, parse_status, _reused = await create_nationwide_import_stage_from_pdf(
        db,
        tenant_id=tenant_id,
        tenant_slug=tenant_slug,
        pdf_bytes=pdf_bytes,
        filename=filename,
        uploaded_by=uploaded_by,
    )
    return stage_id, row_count, parse_status
