"""BVD transaction table parsing from PDF column geometry (pdfminer layout lines)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping

from app.document_platform.capabilities.pdf.layout_lines import (
    PdfLayoutLine,
    extract_layout_lines_from_pdf_bytes,
    group_layout_lines_into_rows,
)
from app.services.fuel_digital_pdf_types import FuelDigitalPdfExtractError

_DATETIME_RE = re.compile(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}")
_CUR_RE = re.compile(r"^[A-Z]{2}$")

# Printed header order on BVD digital invoices (21 data columns after header row).
_TXN_COLUMN_ORDER: tuple[str, ...] = (
    "Auth Code",
    "Driver Name",
    "Unit #",
    "Date",
    "Site #",
    "Site Name",
    "Site City",
    "Prov/ST",
    "Prod",
    "QTY",
    "Retail",
    "Billed",
    "Pre Tax AMT",
    "HST",
    "GST",
    "PST",
    "QST",
    "Disc Rate",
    "Disc AMT",
    "Final AMT",
    "CUR",
)

_HEADER_LABEL_ALIASES: dict[str, str] = {
    "Auth Code": "Auth Code",
    "Driver Name": "Driver Name",
    "Unit #": "Unit #",
    "Date": "Date",
    "Site #": "Site #",
    "Site Name": "Site Name",
    "Site City": "Site City",
    "Prov/ST": "Prov/ST",
    "Prod": "Prod",
    "QTY": "QTY",
    "Prod QTY": "Prod",  # combined header: second half handled separately
    "Retail": "Retail",
    "Billed": "Billed",
    "Pre Tax AMT": "Pre Tax AMT",
    "HST": "HST",
    "GST": "GST",
    "PST": "PST",
    "QST": "QST",
    "Disc Rate": "Disc Rate",
    "Disc AMT": "Disc AMT",
    "Final AMT": "Final AMT",
    "CUR": "CUR",
}


@dataclass
class _ColumnRegion:
    field: str
    x_min: float
    x_max: float


@dataclass
class _TransactionTableColumns:
    regions: list[_ColumnRegion]

    def assign(self, line: PdfLayoutLine) -> str | None:
        cx = line.x_center
        for region in self.regions:
            if region.x_min <= cx < region.x_max:
                return region.field
        return None


def _row_text_blob(row: list[PdfLayoutLine]) -> str:
    return " ".join(ln.text for ln in row)


def _row_label_texts(row: list[PdfLayoutLine]) -> set[str]:
    return {ln.text.strip() for ln in row}


def _is_transaction_header_row(row: list[PdfLayoutLine]) -> bool:
    texts = _row_label_texts(row)
    return "Auth Code" in texts and "Site Name" in texts and "Site City" in texts


def _merge_adjacent_header_rows(rows: list[list[PdfLayoutLine]], y_tolerance: float = 4.0) -> list[list[PdfLayoutLine]]:
    """Some BVD PDFs split one printed header across adjacent layout rows."""
    if not rows:
        return rows
    merged: list[list[PdfLayoutLine]] = []
    i = 0
    while i < len(rows):
        row = rows[i]
        if not _is_transaction_header_row(row) and "Auth Code" in _row_label_texts(row):
            if i + 1 < len(rows):
                nxt = rows[i + 1]
                if abs(nxt[0].y0 - row[0].y0) <= y_tolerance:
                    combined = sorted(row + nxt, key=lambda ln: ln.x0)
                    if _is_transaction_header_row(combined):
                        merged.append(combined)
                        i += 2
                        continue
        merged.append(row)
        i += 1
    return merged


def _header_segments(row: list[PdfLayoutLine]) -> list[tuple[str, float, float]]:
    """Map header row lines to canonical column fields with x extents."""
    segments: list[tuple[str, float, float]] = []
    for ln in sorted(row, key=lambda l: l.x0):
        label = ln.text.strip()
        if label == "Prod QTY":
            mid = (ln.x0 + ln.x1) / 2.0
            segments.append(("Prod", ln.x0, mid))
            segments.append(("QTY", mid, ln.x1))
            continue
        field = _HEADER_LABEL_ALIASES.get(label)
        if field is None:
            continue
        if field == "Prod" and any(s[0] == "Prod" for s in segments):
            continue
        segments.append((field, ln.x0, ln.x1))
    return segments


def _regions_from_header_segments(segments: list[tuple[str, float, float]]) -> list[_ColumnRegion]:
    if not segments:
        raise FuelDigitalPdfExtractError("TXN_GEOMETRY", "empty transaction header segments")
    ordered: list[tuple[str, float, float]] = []
    for field in _TXN_COLUMN_ORDER:
        match = next((s for s in segments if s[0] == field), None)
        if match is None:
            raise FuelDigitalPdfExtractError(
                "TXN_GEOMETRY",
                f"transaction header missing column: {field}",
            )
        ordered.append(match)
    centers = [(f, (a + b) / 2.0) for f, a, b in ordered]
    regions: list[_ColumnRegion] = []
    for i, (field, cx) in enumerate(centers):
        left_edge = ordered[i][1]
        right_edge = ordered[i][2]
        if i == 0:
            x_min = 0.0
        else:
            x_min = (centers[i - 1][1] + cx) / 2.0
        if i + 1 >= len(centers):
            x_max = right_edge + 500.0
        else:
            x_max = (cx + centers[i + 1][1]) / 2.0
        x_min = min(x_min, left_edge - 1.0)
        x_max = max(x_max, right_edge + 1.0)
        regions.append(_ColumnRegion(field=field, x_min=x_min, x_max=x_max))
    return regions


def _build_columns_from_header_row(row: list[PdfLayoutLine]) -> _TransactionTableColumns:
    segments = _header_segments(row)
    regions = _regions_from_header_segments(segments)
    return _TransactionTableColumns(regions=regions)


def _row_field_values(
    row: list[PdfLayoutLine],
    columns: _TransactionTableColumns,
) -> dict[str, list[str]]:
    buckets: dict[str, list[str]] = {f: [] for f in _TXN_COLUMN_ORDER}
    for ln in row:
        field = columns.assign(ln)
        if field is None:
            continue
        buckets[field].append(ln.text.strip())
    return buckets


def _join_field(parts: list[str]) -> str | None:
    if not parts:
        return None
    return " ".join(parts).strip() or None


def _parse_transaction_row_geometry(
    row: list[PdfLayoutLine],
    columns: _TransactionTableColumns,
    *,
    profile: Mapping[str, Any],
    auth_re: re.Pattern[str],
) -> dict[str, str | None]:
    buckets = _row_field_values(row, columns)
    auth = _join_field(buckets["Auth Code"])
    if not auth or not auth_re.search(auth):
        raise FuelDigitalPdfExtractError("TXN_PARSE", f"not a transaction row: {auth!r}")

    site_name = _join_field(buckets["Site Name"])
    site_city = _join_field(buckets["Site City"])
    if not site_name or not site_city:
        raise FuelDigitalPdfExtractError(
            "SITE_NAME_CITY_AMBIGUOUS",
            "cannot split Site Name / Site City without column boundaries",
        )

    prod = _join_field(buckets["Prod"])
    legend = profile.get("product_code_legend") or {}
    if prod and str(prod).strip() not in legend and str(prod).strip().upper() not in legend:
        raise FuelDigitalPdfExtractError("TXN_PARSE", f"unknown product code: {prod!r}")

    site_number = _join_field(buckets["Site #"])
    if not site_number or not site_number.isdigit():
        raise FuelDigitalPdfExtractError("TXN_PARSE", f"expected Site #, got {site_number!r}")

    txn_date = _join_field(buckets["Date"])
    if not txn_date or not _DATETIME_RE.fullmatch(txn_date):
        raise FuelDigitalPdfExtractError("TXN_PARSE", f"no Date on transaction row: {txn_date!r}")

    cur = _join_field(buckets["CUR"])
    if cur and not _CUR_RE.match(cur):
        raise FuelDigitalPdfExtractError("TXN_PARSE", f"expected CUR, got {cur!r}")

    return {
        "Auth Code": auth,
        "Driver Name": _join_field(buckets["Driver Name"]),
        "Unit #": _join_field(buckets["Unit #"]),
        "Date": txn_date,
        "Site #": site_number,
        "Site Name": site_name,
        "Site City": site_city,
        "Prov/ST": _join_field(buckets["Prov/ST"]),
        "Prod": prod,
        "QTY": _join_field(buckets["QTY"]),
        "Retail": _join_field(buckets["Retail"]),
        "Billed": _join_field(buckets["Billed"]),
        "Pre Tax AMT": _join_field(buckets["Pre Tax AMT"]),
        "HST": _join_field(buckets["HST"]),
        "GST": _join_field(buckets["GST"]),
        "PST": _join_field(buckets["PST"]),
        "QST": _join_field(buckets["QST"]),
        "Disc Rate": _join_field(buckets["Disc Rate"]),
        "Disc AMT": _join_field(buckets["Disc AMT"]),
        "Final AMT": _join_field(buckets["Final AMT"]),
        "CUR": cur,
    }


def extract_transaction_rows_from_pdf_geometry(
    pdf_bytes: bytes,
    *,
    profile: Mapping[str, Any],
    auth_line_pattern: str,
) -> list[tuple[dict[str, str | None], int]]:
    """Return (transaction fields, page_number) in document order."""
    layout_lines = extract_layout_lines_from_pdf_bytes(pdf_bytes)
    if not layout_lines:
        raise FuelDigitalPdfExtractError(
            "TXN_GEOMETRY",
            "pdf layout line extraction unavailable (pdfminer missing or PDF unreadable)",
        )

    auth_re = re.compile(auth_line_pattern)
    by_page: dict[int, list[PdfLayoutLine]] = {}
    for ln in layout_lines:
        by_page.setdefault(ln.page_number, []).append(ln)

    out: list[tuple[dict[str, str | None], int]] = []
    columns: _TransactionTableColumns | None = None

    for page_number in sorted(by_page):
        rows = _merge_adjacent_header_rows(group_layout_lines_into_rows(by_page[page_number]))
        for row in rows:
            if _is_transaction_header_row(row):
                try:
                    columns = _build_columns_from_header_row(row)
                except FuelDigitalPdfExtractError:
                    columns = None
                continue
            if columns is None:
                continue
            blob = _row_text_blob(row)
            if blob.startswith("SUBTOTAL") or blob.startswith("Grand Totals"):
                continue
            blob_auth = auth_re.search(_row_text_blob(row))
            if not blob_auth:
                continue
            fields = _parse_transaction_row_geometry(row, columns, profile=profile, auth_re=auth_re)
            out.append((fields, page_number))
    return out


def geometry_extraction_enabled(profile: Mapping[str, Any]) -> bool:
    spec = profile.get("digital_pdf_extraction") or {}
    split_spec = spec.get("site_name_city_split") or {}
    return str(split_spec.get("mode") or "") == "pdf_column_geometry"
