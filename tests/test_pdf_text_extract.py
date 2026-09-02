from unittest.mock import MagicMock, patch

from app.services.pdf_text_extract import (
    extract_text_and_pages_from_pdf_bytes,
    extract_text_from_pdf_bytes,
)

_PDF_READER_PATCH = "app.services.pdf_text_extract.PdfReader"


def test_pdf_capability_namespace_reexports_same_callables() -> None:
    import app.document_platform.capabilities.pdf.text_extract as new
    import app.services.pdf_text_extract as old

    assert new.extract_text_and_pages_from_pdf_bytes is old.extract_text_and_pages_from_pdf_bytes
    assert new.extract_text_from_pdf_bytes is old.extract_text_from_pdf_bytes


def test_open_failure_returns_empty_and_exact_warning() -> None:
    with patch(_PDF_READER_PATCH, side_effect=ValueError("boom")):
        full_text, page_texts, warnings = extract_text_and_pages_from_pdf_bytes(b"%PDF-fake")

    assert full_text == ""
    assert page_texts == []
    assert warnings == ["PDF open error: ValueError"]


def test_page_order_join_and_empty_page_retention() -> None:
    pages = [
        MagicMock(extract_text=MagicMock(return_value="FIRST")),
        MagicMock(extract_text=MagicMock(return_value=None)),
        MagicMock(extract_text=MagicMock(return_value="THIRD")),
    ]
    reader = MagicMock(pages=pages)

    with patch(_PDF_READER_PATCH, return_value=reader):
        full_text, page_texts, warnings = extract_text_and_pages_from_pdf_bytes(b"%PDF-fake")

    assert page_texts == ["FIRST", "", "THIRD"]
    assert full_text == "FIRST\n\nTHIRD"
    assert warnings == []
    assert full_text == "\n".join(page_texts)


def test_per_page_extract_failure_uses_zero_based_warning_index() -> None:
    pages = [
        MagicMock(extract_text=MagicMock(return_value="FIRST")),
        MagicMock(extract_text=MagicMock(side_effect=RuntimeError("boom"))),
        MagicMock(extract_text=MagicMock(return_value="THIRD")),
    ]
    reader = MagicMock(pages=pages)

    with patch(_PDF_READER_PATCH, return_value=reader):
        full_text, page_texts, warnings = extract_text_and_pages_from_pdf_bytes(b"%PDF-fake")

    assert page_texts == ["FIRST", "", "THIRD"]
    assert full_text == "FIRST\n\nTHIRD"
    assert warnings == ["Page 1 extract error: RuntimeError"]


def test_extract_text_from_pdf_bytes_drops_page_texts() -> None:
    sentinel_full = "JOINED"
    sentinel_pages = ["a", "b"]
    sentinel_warnings = ["w"]

    with patch(
        "app.services.pdf_text_extract.extract_text_and_pages_from_pdf_bytes",
        return_value=(sentinel_full, sentinel_pages, sentinel_warnings),
    ) as mocked:
        out = extract_text_from_pdf_bytes(b"%PDF-fake")

    mocked.assert_called_once_with(b"%PDF-fake")
    assert out == (sentinel_full, sentinel_warnings)
    assert len(out) == 2


def test_missing_pypdf_returns_empty_and_exact_warning() -> None:
    with patch(_PDF_READER_PATCH, None):
        full_text, page_texts, warnings = extract_text_and_pages_from_pdf_bytes(b"%PDF-fake")

    assert full_text == ""
    assert page_texts == []
    assert warnings == ["pypdf not installed — cannot extract text"]
