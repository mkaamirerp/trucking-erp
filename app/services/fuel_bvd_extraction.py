"""BVD Implementation 1 — orchestration: generic digital PDF extract + fuel_bvd column map.

Does not implement provider parsing. Uses fuel_digital_pdf_extract (profile-driven)
and fuel_bvd_column_map (label → SQL column). No OCR. No canonical fuel pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Final

from app.services.fuel_bvd_column_map import map_bvd_source_fields_to_fuel_bvd_columns
from app.services.fuel_digital_pdf_extract import (
    FuelDigitalPdfExtractError,
    extract_digital_pdf_source_rows,
)
from app.services.fuel_provider_profile import load_provider_profile, match_provider_layout
from app.services.pdf_text_extract import extract_text_and_pages_from_pdf_bytes

BVD_PROVIDER_CODE: Final[str] = "BVD"

ROW_HEADER: Final[str] = "HEADER"
ROW_TRANSACTION: Final[str] = "TRANSACTION"
ROW_TRANSACTION_SUBTOTAL: Final[str] = "TRANSACTION_SUBTOTAL"
ROW_PAGE1_SUMMARY: Final[str] = "PAGE1_SUMMARY"
ROW_GRAND_TOTAL: Final[str] = "GRAND_TOTAL"
ROW_LEGEND: Final[str] = "LEGEND"


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


def extract_bvd_rows_from_digital_pdf(
    pdf_bytes: bytes,
) -> tuple[list[FuelBvdExtractedRow], list[str], str]:
    """Return fuel_bvd-shaped rows with exact source strings from digital PDF."""
    try:
        source_rows, warnings, parser_version = extract_digital_pdf_source_rows(
            provider_code=BVD_PROVIDER_CODE,
            pdf_bytes=pdf_bytes,
        )
    except FuelDigitalPdfExtractError as exc:
        raise FuelBvdExtractionError(exc.code, exc.message) from exc

    out: list[FuelBvdExtractedRow] = []
    for src in source_rows:
        mapped = map_bvd_source_fields_to_fuel_bvd_columns(src.source_fields)
        out.append(
            FuelBvdExtractedRow(
                row_type=src.row_kind,
                fields=mapped,
                source_page=src.source_page,
            )
        )
    return out, warnings, parser_version


def extracted_row_to_column_dict(row: FuelBvdExtractedRow) -> dict[str, Any]:
    return {"row_type": row.row_type, **row.fields}


def assert_bvd_extraction_uses_generic_digital_pdf_path() -> None:
    """Architecture guard: BVD layer must not embed independent PDF parsers."""
    import inspect

    src = inspect.getsource(extract_bvd_rows_from_digital_pdf)
    assert "extract_digital_pdf_source_rows" in src
    assert "fuel_digital_pdf_extract" not in src or "extract_digital_pdf_source_rows" in src
