"""Digital PDF text access and plain-text heuristics for intake hints (no OCR).

Full load-document parsing uses ``parse_pdf_bytes_to_load_document_response``.
"""

from __future__ import annotations

import re

from app.services.pdf_text_extract import extract_text_and_pages_from_pdf_bytes


def extract_pdf_text_bytes(data: bytes) -> str:
    full, _pages, _warnings = extract_text_and_pages_from_pdf_bytes(data)
    return full.strip()


def extract_broker_mc_dot_hints(text: str | None) -> tuple[str | None, str | None]:
    """
    Best-effort MC / USDOT from email subject, snippet, or PDF text (supplemental Tier D only).
    Returns raw digit groups; normalization happens in ``broker_identity`` helpers.
    """
    if not text or not str(text).strip():
        return None, None
    t = str(text)
    mc_m = re.search(r"\bMC(?:\s*[#:.-]*\s*)?(\d{4,8})\b", t, re.IGNORECASE)
    mc = mc_m.group(1) if mc_m else None
    dot_m = re.search(r"\b(?:US)?DOT(?:\s*[#:.-]*\s*)?(\d{4,10})\b", t, re.IGNORECASE)
    dot = dot_m.group(1) if dot_m else None
    return mc, dot
