"""PDF embedded-text extraction capability (Slice A).

Re-exports the existing implementation in ``app.services.pdf_text_extract``.
This package does not own the implementation yet.
"""

from app.document_platform.capabilities.pdf.text_extract import (
    extract_text_and_pages_from_pdf_bytes,
    extract_text_from_pdf_bytes,
)

__all__ = [
    "extract_text_and_pages_from_pdf_bytes",
    "extract_text_from_pdf_bytes",
]
