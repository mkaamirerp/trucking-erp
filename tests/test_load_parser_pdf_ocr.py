"""OCR helper for image-only load-parser PDFs (no OpenAI, no semantics)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from app.services.load_parser_pdf_ocr import ocr_load_parser_pdf_pages

_AGRICULTURE = Path("/tmp/Agriculture.pdf")


def test_ocr_returns_warning_when_pdftoppm_missing() -> None:
    with patch("app.services.load_parser_pdf_ocr.shutil.which", side_effect=lambda name: None):
        pages, warnings = ocr_load_parser_pdf_pages(b"%PDF-1.4 fake")
    assert pages == []
    assert any("pdftoppm not installed" in w for w in warnings)


def test_ocr_runs_pdftoppm_then_tesseract_per_page() -> None:
    def fake_which(name: str) -> str | None:
        return f"/usr/bin/{name}"

    def fake_run(cmd, **_kwargs):
        if str(cmd[0]).endswith("pdftoppm"):
            prefix = Path(cmd[-1])
            (prefix.parent / "page-1.png").write_bytes(b"fake")
            (prefix.parent / "page-2.png").write_bytes(b"fake")
            return MagicMock(returncode=0, stdout=b"", stderr=b"")
        if str(cmd[0]).endswith("tesseract"):
            img = Path(cmd[1]).name
            text = "OCR PAGE ONE" if "page-1" in img else "OCR PAGE TWO"
            return MagicMock(returncode=0, stdout=text.encode("utf-8"), stderr=b"")
        raise AssertionError(cmd)

    with (
        patch("app.services.load_parser_pdf_ocr.shutil.which", side_effect=fake_which),
        patch("app.services.load_parser_pdf_ocr.subprocess.run", side_effect=fake_run),
    ):
        pages, warnings = ocr_load_parser_pdf_pages(b"%PDF-1.4 scanned")

    assert warnings == []
    assert [p["page_number"] for p in pages] == [1, 2]
    assert pages[0]["text"] == "OCR PAGE ONE"
    assert pages[1]["text"] == "OCR PAGE TWO"


def test_agriculture_ocr_if_engine_present() -> None:
    """Real OCR of Agriculture.pdf — no OpenAI. Skips if file or engine missing."""
    import shutil

    import pytest

    if not _AGRICULTURE.is_file():
        pytest.skip("Agriculture.pdf not present")
    if shutil.which("pdftoppm") is None or shutil.which("tesseract") is None:
        pytest.skip("pdftoppm/tesseract not installed in this environment")

    pages, warnings = ocr_load_parser_pdf_pages(_AGRICULTURE.read_bytes())
    assert not any(w.startswith("ocr_failed:") for w in warnings)
    assert len(pages) == 4
    joined = "\n".join(p["text"] for p in pages)
    assert len(joined.strip()) > 40
