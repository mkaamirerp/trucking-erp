"""PDF layout line extraction (positions) for table-style digital invoices."""

from __future__ import annotations

import io
from dataclasses import dataclass
from typing import Iterator

try:
    from pdfminer.high_level import extract_pages
    from pdfminer.layout import LTTextContainer, LTTextLine
except ImportError:  # pragma: no cover
    extract_pages = None  # type: ignore[assignment,misc]
    LTTextContainer = None  # type: ignore[assignment,misc]
    LTTextLine = None  # type: ignore[assignment,misc]


@dataclass(frozen=True)
class PdfLayoutLine:
    page_number: int
    x0: float
    x1: float
    y0: float
    y1: float
    text: str

    @property
    def x_center(self) -> float:
        return (self.x0 + self.x1) / 2.0


def extract_layout_lines_from_pdf_bytes(data: bytes) -> list[PdfLayoutLine]:
    """One entry per pdfminer LTTextLine (table cell fragment), with page and bbox."""
    if extract_pages is None or LTTextContainer is None or LTTextLine is None:
        return []
    lines: list[PdfLayoutLine] = []
    try:
        for page_number, page_layout in enumerate(extract_pages(io.BytesIO(data)), start=1):
            for element in page_layout:
                if not isinstance(element, LTTextContainer):
                    continue
                for line in element:
                    if not isinstance(line, LTTextLine):
                        continue
                    text = (line.get_text() or "").strip()
                    if not text:
                        continue
                    lines.append(
                        PdfLayoutLine(
                            page_number=page_number,
                            x0=float(line.x0),
                            x1=float(line.x1),
                            y0=float(line.y0),
                            y1=float(line.y1),
                            text=text,
                        )
                    )
    except Exception:
        return []
    return lines


def group_layout_lines_into_rows(
    lines: list[PdfLayoutLine],
    *,
    y_tolerance: float = 2.5,
) -> list[list[PdfLayoutLine]]:
    """Group lines on the same page with similar y0 into reading-order rows (top first)."""
    if not lines:
        return []
    sorted_lines = sorted(lines, key=lambda ln: (-ln.y0, ln.x0))
    rows: list[list[PdfLayoutLine]] = []
    current: list[PdfLayoutLine] = []
    current_y: float | None = None
    current_page: int | None = None
    for ln in sorted_lines:
        if current_page != ln.page_number or (
            current_y is not None and abs(ln.y0 - current_y) > y_tolerance
        ):
            if current:
                rows.append(current)
            current = [ln]
            current_y = ln.y0
            current_page = ln.page_number
        else:
            current.append(ln)
            if current_y is None:
                current_y = ln.y0
            current_page = ln.page_number
    if current:
        rows.append(current)
    for row in rows:
        row.sort(key=lambda ln: ln.x0)
    return rows
