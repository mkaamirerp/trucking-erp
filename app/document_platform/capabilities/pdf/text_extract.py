"""Shared PDF text extraction (pypdf). Used by product guardrails, Load Lab, and email intake hints."""

from __future__ import annotations

import io
try:
    from pypdf import PdfReader
except ImportError:  # pragma: no cover
    PdfReader = None  # type: ignore[assignment,misc]


def extract_text_and_pages_from_pdf_bytes(data: bytes) -> tuple[str, list[str], list[str]]:
    """Return (full_text, page_texts, warnings)."""
    warnings: list[str] = []
    if PdfReader is None:
        warnings.append("pypdf not installed — cannot extract text")
        return "", [], warnings
    try:
        reader = PdfReader(io.BytesIO(data))
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"PDF open error: {type(exc).__name__}")
        return "", [], warnings
    page_texts: list[str] = []
    for i, page in enumerate(reader.pages):
        try:
            page_texts.append(page.extract_text() or "")
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"Page {i} extract error: {type(exc).__name__}")
            page_texts.append("")
    return "\n".join(page_texts), page_texts, warnings


def extract_text_from_pdf_bytes(data: bytes) -> tuple[str, list[str]]:
    """Return (full_text, warnings)."""
    full, _pages, warnings = extract_text_and_pages_from_pdf_bytes(data)
    return full, warnings
