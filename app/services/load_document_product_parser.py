"""Canonical product entrypoint for load-related PDF parsing.

Import ``parse_pdf_bytes_to_load_document_response`` from here (or from
``load_document_parse_guarded``) so feature code converges on one implementation.
"""

from __future__ import annotations

from app.services.load_document_parse_guarded import parse_pdf_bytes_to_load_document_response

__all__ = ["parse_pdf_bytes_to_load_document_response"]
