"""PDF embedded-text extraction capability.

Implementation is owned by ``app.document_platform.capabilities.pdf.text_extract``.
``app.services.pdf_text_extract`` remains a compatibility shim.
"""

from app.document_platform.capabilities.pdf.text_extract import (
    extract_text_and_pages_from_pdf_bytes,
    extract_text_from_pdf_bytes,
)

__all__ = [
    "extract_text_and_pages_from_pdf_bytes",
    "extract_text_from_pdf_bytes",
]
