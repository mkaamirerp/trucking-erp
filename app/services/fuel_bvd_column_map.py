"""Map BVD source labels (PDF column names) to locked fuel_bvd SQL columns.

Not a parser — label→column mapping for Implementation 1 persistence only.
"""

from __future__ import annotations

from typing import Any, Final, Mapping

# Source label → fuel_bvd column (docs/FUEL_BVD_IMPLEMENTATION_1.md).
BVD_SOURCE_LABEL_TO_COLUMN: Final[dict[str, str]] = {
    "Invoice Number": "invoice_number",
    "invoice_number": "invoice_number",
    "Invoice Date": "invoice_date",
    "invoice_date": "invoice_date",
    "Start Date": "start_date",
    "start_date": "start_date",
    "End Date": "end_date",
    "end_date": "end_date",
    "Due Date": "due_date",
    "due_date": "due_date",
    "client_name": "client_name",
    "client_address": "client_address",
    "client_phone": "client_phone",
    "client_email": "client_email",
    "card_number": "card_number",
    "Transactions for card": "card_number",
    "HST#": "hst_number",
    "hst_number": "hst_number",
    "QST#": "qst_number",
    "qst_number": "qst_number",
    "Auth Code": "auth_code",
    "Driver Name": "driver_name",
    "Unit #": "unit_number",
    "Date": "transaction_date",
    "Site #": "site_number",
    "Site Name": "site_name",
    "Site City": "site_city",
    "Prov/ST": "prov_st",
    "Prod": "prod",
    "QTY": "qty",
    "Retail": "retail",
    "Billed": "billed",
    "Pre Tax AMT": "pre_tax_amt",
    "HST": "hst",
    "GST": "gst",
    "PST": "pst",
    "QST": "qst",
    "Disc Rate": "disc_rate",
    "Disc AMT": "disc_amt",
    "Final AMT": "final_amt",
    "FINAL AMOUNT": "final_amount",
    "CUR": "cur",
    "row_label": "row_label",
    "PRODUCT": "product",
    "product": "product",
    "Code": "legend_code",
    "Product Name": "legend_product_name",
}


def map_bvd_source_fields_to_fuel_bvd_columns(source_fields: Mapping[str, str | None]) -> dict[str, str | None]:
    out: dict[str, str | None] = {}
    for label, value in source_fields.items():
        if value is None:
            continue
        col = BVD_SOURCE_LABEL_TO_COLUMN.get(label)
        if col is None:
            continue
        out[col] = value
    return out


def fuel_bvd_columns_from_digital_source_row(
    row_type: str,
    source_fields: Mapping[str, str | None],
) -> dict[str, Any]:
    mapped = map_bvd_source_fields_to_fuel_bvd_columns(source_fields)
    mapped["row_type"] = row_type
    return mapped
