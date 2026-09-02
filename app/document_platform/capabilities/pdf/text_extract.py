"""Slice A re-export of the existing low-level PDF text extractor.

Implementation remains in ``app.services.pdf_text_extract``.
This module must not import Load, DL, router, or profile code.
"""

from app.services.pdf_text_extract import (
    extract_text_and_pages_from_pdf_bytes,
    extract_text_from_pdf_bytes,
)

__all__ = [
    "extract_text_and_pages_from_pdf_bytes",
    "extract_text_from_pdf_bytes",
]
