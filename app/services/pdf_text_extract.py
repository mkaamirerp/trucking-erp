"""Compatibility re-export of the shared PDF text extractor.

Implementation: ``app.document_platform.capabilities.pdf.text_extract``.
"""

from app.document_platform.capabilities.pdf.text_extract import (
    extract_text_and_pages_from_pdf_bytes,
    extract_text_from_pdf_bytes,
)
