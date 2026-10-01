"""Nationwide digital PDF → structured source rows (generic parser path)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.services.fuel_digital_pdf_extract import (
    ROW_KIND_HEADER,
    extract_digital_pdf_source_rows,
)
from app.services.fuel_digital_pdf_nationwide_table import ROW_KIND_CONTROL, ROW_KIND_TRANSACTION
from app.services.fuel_digital_pdf_types import FuelDigitalPdfExtractError
from app.services.fuel_nationwide_import import (
    NATIONWIDE_PROVIDER_CODE,
    ROW_CONTROL,
    ROW_HEADER,
    ROW_TRANSACTION,
    map_provider_fields_to_columns,
)
from app.services.fuel_provider_profile import (
    load_provider_profile,
    match_provider_layout,
    suggest_control_type,
)
from app.services.pdf_text_extract import extract_text_and_pages_from_pdf_bytes


@dataclass(frozen=True)
class FuelNationwideExtractedRow:
    row_type: str
    fields: dict[str, str | None]
    source_page: int | None = None
    source_row_number: int | None = None
    control_type: str | None = None


class FuelNationwideExtractionError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def extract_nationwide_rows_from_digital_pdf(pdf_bytes: bytes) -> tuple[list[FuelNationwideExtractedRow], list[str], str]:
    profile = load_provider_profile(NATIONWIDE_PROVIDER_CODE)
    _full, page_texts, extract_warnings = extract_text_and_pages_from_pdf_bytes(pdf_bytes)
    pages = [{"page_number": i + 1, "text": t} for i, t in enumerate(page_texts)]
    layout = match_provider_layout(profile, page_texts=pages)
    if layout.status != "RECOGNIZED":
        raise FuelNationwideExtractionError(
            "LAYOUT_UNRECOGNIZED",
            f"Nationwide layout not recognized: {layout.status}",
        )

    try:
        source_rows, row_warnings, parser_version = extract_digital_pdf_source_rows(
            provider_code=NATIONWIDE_PROVIDER_CODE,
            pdf_bytes=pdf_bytes,
        )
    except FuelDigitalPdfExtractError as exc:
        raise FuelNationwideExtractionError(exc.code, exc.message) from exc

    warnings = list(extract_warnings) + list(row_warnings)
    out: list[FuelNationwideExtractedRow] = []
    row_num = 0
    for row in source_rows:
        if row.row_kind == ROW_KIND_HEADER:
            mapped = map_provider_fields_to_columns(dict(row.source_fields), is_header=True)
            out.append(
                FuelNationwideExtractedRow(
                    row_type=ROW_HEADER,
                    fields=mapped,
                    source_page=row.source_page,
                    source_row_number=1,
                )
            )
            continue
        row_num += 1
        if row.row_kind == ROW_KIND_TRANSACTION:
            mapped = map_provider_fields_to_columns(dict(row.source_fields))
            out.append(
                FuelNationwideExtractedRow(
                    row_type=ROW_TRANSACTION,
                    fields=mapped,
                    source_page=row.source_page,
                    source_row_number=row_num,
                )
            )
            continue
        if row.row_kind == ROW_KIND_CONTROL:
            raw = dict(row.source_fields)
            line = raw.get("control_line_raw") or ""
            control_type = suggest_control_type(profile=profile, provider_raw=raw, line_text=line)
            mapped = map_provider_fields_to_columns(raw)
            mapped["control_line_raw"] = line or None
            if raw.get("row_label"):
                mapped["row_label"] = str(raw["row_label"])
            if raw.get("declared_amount"):
                mapped["declared_amount"] = str(raw["declared_amount"])
            if raw.get("GST"):
                mapped["gst"] = str(raw["GST"])
            if raw.get("PST") is not None:
                mapped["pst"] = str(raw["PST"])
            mapped["control_type"] = control_type
            out.append(
                FuelNationwideExtractedRow(
                    row_type=ROW_CONTROL,
                    fields=mapped,
                    source_page=row.source_page,
                    source_row_number=row_num,
                    control_type=control_type,
                )
            )
            continue

    if not any(r.row_type == ROW_TRANSACTION for r in out):
        warnings.append("NO_TRANSACTION_ROWS_EXTRACTED")
    return out, warnings, parser_version
