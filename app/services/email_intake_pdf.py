"""Digital PDF text extraction and narrow TQL rate-confirmation heuristics (no OCR)."""

from __future__ import annotations

import io
import re

from pypdf import PdfReader


def extract_pdf_text_bytes(data: bytes) -> str:
    reader = PdfReader(io.BytesIO(data))
    parts: list[str] = []
    for page in reader.pages:
        parts.append(page.extract_text() or "")
    return "\n".join(parts).strip()


def guess_broker_load_reference(text: str) -> str | None:
    if not text:
        return None
    m = re.search(
        r"\b(?:load|ref|bol|pro)\s*#?\s*([A-Z0-9][A-Z0-9-]{4,24})\b",
        text,
        re.IGNORECASE,
    )
    return m.group(1).upper() if m else None


def tql_digital_pdf_high_confidence(text: str) -> tuple[bool, str]:
    """
    Hardcoded high-confidence gate for TQL digital PDFs only:
    sufficient extracted text + TQL / rate confirmation markers + pickup/delivery cues.
    """
    t = (text or "").strip()
    if len(t) < 200:
        return False, "extracted_text_too_short"
    u = t.upper()
    marker_rc = "RATE CONFIRMATION" in u
    marker_tql = "TQL" in u or "TOTAL QUALITY LOGISTICS" in u
    loc_pick = bool(re.search(r"\b(PICKUP|ORIGIN|SHIPPER)\b", u))
    loc_del = bool(re.search(r"\b(DELIVERY|DESTINATION|CONSIGNEE|DROP|RECEIVER)\b", u))
    if marker_tql and marker_rc and loc_pick and loc_del:
        return True, "tql_digital_pdf_rate_confirmation"
    return False, "tql_pdf_keyword_gate_failed"
