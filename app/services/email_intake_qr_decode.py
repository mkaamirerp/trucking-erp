"""Decode PDF-embedded images and return QR payloads (rate con supplemental signal)."""

from __future__ import annotations

import io
import logging

from pypdf import PdfReader

logger = logging.getLogger(__name__)

try:
    import zxingcpp
except ImportError:  # pragma: no cover
    zxingcpp = None


def extract_qr_strings_from_pdf_bytes(pdf_bytes: bytes) -> list[tuple[int, str]]:
    """
    Scan each page's embedded images for QR / MicroQR codes.

    Returns list of ``(page_number_1based, raw_text)`` with duplicates (same page + text) collapsed.
    """
    if not pdf_bytes or zxingcpp is None:
        return []
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
    except Exception as exc:
        logger.debug("intake pdf qr: PdfReader failed: %s", exc)
        return []

    fmt = zxingcpp.BarcodeFormat.QRCode | zxingcpp.BarcodeFormat.MicroQRCode
    out: list[tuple[int, str]] = []
    seen: set[tuple[int, str]] = set()

    for page_num, page in enumerate(reader.pages, start=1):
        try:
            page_images = page.images
        except Exception:
            continue
        for imgfile in page_images:
            try:
                pil = getattr(imgfile, "image", None)
            except Exception:
                continue
            if pil is None:
                continue
            try:
                rgb = pil.convert("RGB")
            except Exception:
                continue
            try:
                codes = zxingcpp.read_barcodes(rgb, formats=fmt)
            except Exception as exc:
                logger.debug("intake pdf qr: zxing failed page=%s: %s", page_num, exc)
                continue
            for c in codes:
                text = (getattr(c, "text", None) or "").strip()
                if not text:
                    continue
                key = (page_num, text)
                if key in seen:
                    continue
                seen.add(key)
                out.append((page_num, text))
    return out
