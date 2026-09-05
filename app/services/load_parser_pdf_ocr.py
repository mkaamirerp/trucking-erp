"""OCR fallback for image-only load-parser PDFs.

Uses poppler ``pdftoppm`` + Tesseract CLI. No semantic parsing, no OpenAI,
no field rules. Digital PDFs must not call this module.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

_PDFTOPPM = "pdftoppm"
_TESSERACT = "tesseract"
_RENDER_DPI = "300"
_OCR_TIMEOUT_S = 120


def ocr_load_parser_pdf_pages(pdf_bytes: bytes) -> tuple[list[dict[str, Any]], list[str]]:
    """Rasterize each PDF page and OCR it.

    Returns ``([{page_number, text}, ...], warnings)``.
    On engine/install failure, pages is empty and warnings explain why.
    """
    warnings: list[str] = []
    if not pdf_bytes:
        return [], ["ocr_failed: empty pdf"]

    pdftoppm = shutil.which(_PDFTOPPM)
    tesseract = shutil.which(_TESSERACT)
    if pdftoppm is None:
        return [], ["ocr_failed: pdftoppm not installed"]
    if tesseract is None:
        return [], ["ocr_failed: tesseract not installed"]

    with tempfile.TemporaryDirectory(prefix="load_parser_ocr_") as td:
        work = Path(td)
        pdf_path = work / "input.pdf"
        pdf_path.write_bytes(pdf_bytes)
        prefix = work / "page"
        try:
            subprocess.run(
                [pdftoppm, "-png", "-r", _RENDER_DPI, str(pdf_path), str(prefix)],
                check=True,
                capture_output=True,
                timeout=_OCR_TIMEOUT_S,
            )
        except subprocess.TimeoutExpired:
            return [], ["ocr_failed: pdftoppm timeout"]
        except subprocess.CalledProcessError as exc:
            err = (exc.stderr or b"").decode("utf-8", errors="replace")[:300]
            return [], [f"ocr_failed: pdftoppm exit {exc.returncode}: {err}".strip()]

        images = sorted(work.glob("page*.png"))
        if not images:
            return [], ["ocr_failed: pdftoppm produced no pages"]

        pages: list[dict[str, Any]] = []
        for idx, image in enumerate(images, start=1):
            try:
                proc = subprocess.run(
                    [tesseract, str(image), "stdout", "-l", "eng"],
                    check=True,
                    capture_output=True,
                    timeout=_OCR_TIMEOUT_S,
                )
                text = proc.stdout.decode("utf-8", errors="replace")
            except subprocess.TimeoutExpired:
                warnings.append(f"ocr_page_{idx}_failed: tesseract timeout")
                text = ""
            except subprocess.CalledProcessError as exc:
                err = (exc.stderr or b"").decode("utf-8", errors="replace")[:200]
                warnings.append(f"ocr_page_{idx}_failed: tesseract exit {exc.returncode}: {err}".strip())
                text = ""
            pages.append({"page_number": idx, "text": text})
        return pages, warnings
