"""Slice 3A: Load/Rate-Con PDF acquisition classifier (no OCR, no semantics)."""

from __future__ import annotations

from pathlib import Path

from app.services.load_parser_pdf_acquisition import (
    MIN_ALPHANUMERIC_CHARS,
    MIN_WORD_LIKE_TOKENS,
    acquire_load_parser_pdf_pages,
    classify_pages_from_embedded_texts,
    page_has_usable_embedded_text,
)


def test_thresholds_are_named_constants() -> None:
    assert MIN_ALPHANUMERIC_CHARS == 40
    assert MIN_WORD_LIKE_TOKENS == 5


def test_all_usable_pages_digital_text() -> None:
    pages = [
        "Load confirmation page one with enough alphanumeric content here for usability.",
        "Second page also has enough readable embedded text for the classifier thresholds.",
    ]
    out = classify_pages_from_embedded_texts(pages)
    assert out["pdf_type"] == "digital_text"
    assert out["requires_ocr"] is False
    assert out["page_count"] == 2
    assert [p["page_number"] for p in out["pages"]] == [1, 2]
    assert all(p["source"] == "embedded_text" for p in out["pages"])
    assert out["pages"][0]["text"].startswith("Load confirmation")


def test_all_unusable_pages_scanned_image() -> None:
    pages = ["", "   ", "\x00\x01", "ab cd"]  # last fails token/alnum thresholds
    out = classify_pages_from_embedded_texts(pages)
    assert out["pdf_type"] == "scanned_image"
    assert out["requires_ocr"] is True
    assert all(p["source"] == "ocr_required" for p in out["pages"])
    assert all(p["text"] == "" for p in out["pages"])


def test_mixed_usable_and_unusable() -> None:
    pages = [
        "This page has plenty of embedded digital text for the usability gate to pass clearly.",
        "",
        "Another solid page of embedded text that should remain classified as digital evidence.",
    ]
    out = classify_pages_from_embedded_texts(pages)
    assert out["pdf_type"] == "mixed"
    assert out["requires_ocr"] is True
    assert [p["source"] for p in out["pages"]] == [
        "embedded_text",
        "ocr_required",
        "embedded_text",
    ]
    assert out["pages"][1]["text"] == ""
    assert out["pages"][0]["text"]


def test_tiny_junk_and_whitespace_control_only() -> None:
    usable, metrics = page_has_usable_embedded_text("!!@@##")
    assert usable is False
    assert metrics["alphanumeric_chars"] == 0

    usable2, _ = page_has_usable_embedded_text("   \n\t  \x00  ")
    assert usable2 is False

    # Single-letter tokens are not word-like ({2,}); still fails both thresholds.
    usable3, m3 = page_has_usable_embedded_text("a b c d e f g h")
    assert m3["word_like_tokens"] == 0
    assert m3["alphanumeric_chars"] == 8
    assert usable3 is False

    # Enough word-like tokens but still below alphanumeric floor.
    usable4, m4 = page_has_usable_embedded_text("ab cd ef gh ij")
    assert m4["word_like_tokens"] == 5
    assert m4["alphanumeric_chars"] == 10
    assert usable4 is False


def test_ocr_required_preserves_weak_text_separately() -> None:
    weak = "short"
    out = classify_pages_from_embedded_texts([weak])
    assert out["pages"][0]["source"] == "ocr_required"
    assert out["pages"][0]["text"] == ""
    assert out["pages"][0]["weak_embedded_text"] == weak


def test_page_numbering_starts_at_one_and_preserves_order() -> None:
    pages = [
        "Page alpha has enough alphanumeric tokens so the classifier marks it usable now.",
        "Page beta also clears the alphanumeric and word-like token thresholds for embedded.",
        "Page gamma likewise contains sufficient digital text for usability classification.",
    ]
    out = classify_pages_from_embedded_texts(pages)
    assert [p["page_number"] for p in out["pages"]] == [1, 2, 3]
    assert "alpha" in out["pages"][0]["text"]
    assert "gamma" in out["pages"][2]["text"]


def test_armstrong_classifies_digital_text() -> None:
    path = Path("/tmp/Armstrong.pdf")
    if not path.is_file():
        import pytest

        pytest.skip("Armstrong.pdf not present")
    out = acquire_load_parser_pdf_pages(path.read_bytes())
    assert out["pdf_type"] == "digital_text"
    assert out["requires_ocr"] is False
    assert out["page_count"] >= 1
    assert all(p["source"] == "embedded_text" for p in out["pages"])
    assert all(p["usable_embedded_text"] is True for p in out["pages"])


def test_agriculture_if_present_must_be_ocr_required() -> None:
    candidates = [
        Path("/tmp/Agriculture.pdf"),
        Path("/home/admin/Agriculture.pdf"),
        Path("/home/admin/trucking_erp/docs/fixtures/Agriculture.pdf"),
    ]
    path = next((p for p in candidates if p.is_file()), None)
    if path is None:
        import pytest

        pytest.skip("Agriculture.pdf not present on this host")
    out = acquire_load_parser_pdf_pages(path.read_bytes())
    # If this fails thresholds unexpectedly, Slice 3A must STOP and report metrics.
    assert out["requires_ocr"] is True
    assert out["pdf_type"] in ("scanned_image", "mixed")
