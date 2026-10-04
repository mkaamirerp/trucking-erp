"""Receipt file → plain text for manual fuel entry parsing."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from app.document_platform.capabilities.pdf.text_extract import extract_text_from_pdf_bytes
from app.services.load_parser_pdf_ocr import ocr_load_parser_pdf_pages

_MIN_DIGITAL_TEXT_CHARS = 40
_OCR_TIMEOUT_S = 120
_TESSERACT = "tesseract"


def receipt_text_from_upload(file_bytes: bytes, filename: str | None) -> tuple[str, list[str]]:
    """Extract searchable text from a receipt PDF or image."""
    warnings: list[str] = []
    if not file_bytes:
        return "", ["empty_file"]

    name = (filename or "").lower()
    if name.endswith(".txt"):
        return file_bytes.decode("utf-8", errors="replace"), warnings
    if name.endswith(".pdf") or (not name and file_bytes[:4] == b"%PDF"):
        text, pdf_warnings = extract_text_from_pdf_bytes(file_bytes)
        warnings.extend(pdf_warnings)
        if len(text.strip()) >= _MIN_DIGITAL_TEXT_CHARS:
            return text, warnings
        pages, ocr_warnings = ocr_load_parser_pdf_pages(file_bytes)
        warnings.extend(ocr_warnings)
        ocr_text = "\n".join(p.get("text") or "" for p in pages)
        if len(ocr_text.strip()) >= _MIN_DIGITAL_TEXT_CHARS:
            warnings.append("used_pdf_ocr")
            return ocr_text, warnings
        return text or ocr_text, warnings

    if name.endswith((".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff", ".bmp")):
        text, img_warnings = _ocr_image_bytes(file_bytes)
        warnings.extend(img_warnings)
        return text, warnings

    # Best-effort: try PDF then treat as image.
    if file_bytes[:4] == b"%PDF":
        return receipt_text_from_upload(file_bytes, "receipt.pdf")
    text, img_warnings = _ocr_image_bytes(file_bytes)
    warnings.extend(img_warnings)
    if not text.strip():
        warnings.append("unsupported_or_unreadable_file_type")
    return text, warnings


def _ocr_image_bytes(image_bytes: bytes) -> tuple[str, list[str]]:
    warnings: list[str] = []
    tesseract = shutil.which(_TESSERACT)
    if tesseract is None:
        return "", ["ocr_failed: tesseract not installed"]
    suffix = ".png"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(image_bytes)
        path = Path(tmp.name)
    try:
        proc = subprocess.run(
            [tesseract, str(path), "stdout", "-l", "eng"],
            check=True,
            capture_output=True,
            timeout=_OCR_TIMEOUT_S,
        )
        return proc.stdout.decode("utf-8", errors="replace"), warnings
    except subprocess.TimeoutExpired:
        return "", ["ocr_failed: tesseract timeout"]
    except subprocess.CalledProcessError as exc:
        err = (exc.stderr or b"").decode("utf-8", errors="replace")[:200]
        return "", [f"ocr_failed: tesseract exit {exc.returncode}: {err}".strip()]
    finally:
        path.unlink(missing_ok=True)
