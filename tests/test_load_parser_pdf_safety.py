"""Structural safety gate tests for Load / Rate Confirmation PDFs."""

from __future__ import annotations

import io

import pytest
from pypdf import PdfWriter

from app.services.load_parser_pdf_safety import (
    UnsafeLoadPdfError,
    validate_load_parser_pdf,
)


def _pdf_bytes(configure=None) -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    if configure is not None:
        configure(writer)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def test_accepts_plain_parseable_pdf() -> None:
    result = validate_load_parser_pdf(_pdf_bytes())
    assert result.page_count == 1
    assert result.objects_scanned > 0


def test_rejects_non_pdf_and_malformed_pdf() -> None:
    with pytest.raises(UnsafeLoadPdfError, match="Expected a PDF"):
        validate_load_parser_pdf(b"not a pdf")
    with pytest.raises(UnsafeLoadPdfError, match="Malformed or unsupported PDF"):
        validate_load_parser_pdf(b"%PDF-1.7\nnot a real object graph")


def test_rejects_encrypted_pdf() -> None:
    def encrypt(writer: PdfWriter) -> None:
        writer.encrypt("secret")

    with pytest.raises(UnsafeLoadPdfError, match="Encrypted"):
        validate_load_parser_pdf(_pdf_bytes(encrypt))


def test_rejects_javascript_action() -> None:
    def add_javascript(writer: PdfWriter) -> None:
        writer.add_js("app.alert('do not run')")

    with pytest.raises(UnsafeLoadPdfError, match="active content"):
        validate_load_parser_pdf(_pdf_bytes(add_javascript))


def test_rejects_embedded_file() -> None:
    def add_attachment(writer: PdfWriter) -> None:
        writer.add_attachment("payload.bin", b"arbitrary bytes")

    with pytest.raises(UnsafeLoadPdfError, match="active content|embedded file"):
        validate_load_parser_pdf(_pdf_bytes(add_attachment))
