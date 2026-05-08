"""Digital PDF text access and plain-text heuristics for intake hints (no OCR).

Full load-document parsing uses ``parse_pdf_bytes_to_load_document_response``.
"""

from __future__ import annotations

import re

from app.services.pdf_text_extract import extract_text_and_pages_from_pdf_bytes


def extract_pdf_text_bytes(data: bytes) -> str:
    full, _pages, _warnings = extract_text_and_pages_from_pdf_bytes(data)
    return full.strip()


def guess_broker_load_reference(text: str) -> str | None:
    if not text:
        return None
    m = re.search(
        r"\b(?:load|ref|bol|pro)\s*#?\s*([A-Z0-9][A-Z0-9-]{4,24})\b",
        text,
        re.IGNORECASE,
    )
    return m.group(1).upper() if m else None


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


def extract_tql_rate_con_hints(text: str) -> dict[str, float | int | str]:
    """
    Best-effort rate/miles/commodity from plain text (fixtures / legacy tests only).
    Prefer ``LoadDocumentParseResponse.extracted`` in product code.
    """
    out: dict[str, float | int | str] = {}
    if not text or len(text.strip()) < 20:
        return out
    t = text
    rate_patterns = [
        r"(?:total\s+rate|line\s*haul|linehaul|carrier\s+pay|total\s+(?:carrier\s+)?pay|amount\s+due)[:\s]*\$?\s*([\d,]+(?:\.\d{2})?)\b",
        r"(?:\$|USD)\s*([\d,]+(?:\.\d{2})?)\b\s*(?:flat|total|per\s+load)?",
    ]
    for pat in rate_patterns:
        m = re.search(pat, t, re.IGNORECASE)
        if m:
            try:
                out["rate"] = float(m.group(1).replace(",", ""))
                break
            except ValueError:
                pass
    m_miles = re.search(r"(?:billable|total|loaded)?\s*miles[:\s]*(\d{1,5})\b", t, re.IGNORECASE)
    if not m_miles:
        m_miles = re.search(r"\b(\d{1,5})\s*(?:loaded\s+)?miles\b", t, re.IGNORECASE)
    if m_miles:
        try:
            out["miles"] = int(m_miles.group(1))
        except ValueError:
            pass
    m_com = re.search(
        r"(?:commodity|description\s+of\s+goods?|product)[:\s]+([^\n]{1,200}?)(?:\n|$)",
        t,
        re.IGNORECASE,
    )
    if m_com:
        line = " ".join(m_com.group(1).split())
        if line and len(line) > 2:
            out["commodity"] = line[:255]
    return out
