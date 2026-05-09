"""Unit tests for email intake PDF text and heuristics (not product parse)."""
from __future__ import annotations

import re

from app.services.email_intake_pdf import extract_broker_mc_dot_hints, extract_pdf_text_bytes
from app.services.email_engine.message_classifier import (
    participants_indicate_load_intake_text_cues,
    subject_or_snippet_indicates_load_intake_text_cues,
)


def _heuristic_load_reference_from_text(text: str) -> str | None:
    if not text:
        return None
    m = re.search(
        r"\b(?:load|ref|bol|pro)\s*#?\s*([A-Z0-9][A-Z0-9-]{4,24})\b",
        text,
        re.IGNORECASE,
    )
    return m.group(1).upper() if m else None


def _rate_con_hints_from_plain_text(text: str) -> dict[str, float | int | str]:
    """Test-only plain-text rate/miles/commodity hints (not used in product intake)."""
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


def test_heuristic_load_reference_from_text() -> None:
    assert _heuristic_load_reference_from_text("Please see Load # ABC12X for details") == "ABC12X"
    assert _heuristic_load_reference_from_text("no ref here") is None


def test_extract_rate_con_hints_from_plain_text() -> None:
    blob = """
    Example Brokerage
    RATE CONFIRMATION
    Total Rate: $2,500.50
    Billable Miles: 1245
    Commodity: Paper rolls
    PICKUP Chicago IL
    DELIVERY Dallas TX
    """
    h = _rate_con_hints_from_plain_text(blob)
    assert h["rate"] == 2500.50
    assert h["miles"] == 1245
    assert "Paper" in str(h.get("commodity", ""))


def test_participants_indicate_load_intake_text_cues() -> None:
    assert participants_indicate_load_intake_text_cues([{"email": "ops@example-broker.com"}]) is False
    assert participants_indicate_load_intake_text_cues(None) is False


def test_subject_snippet_generic_load_intake_cues() -> None:
    assert subject_or_snippet_indicates_load_intake_text_cues("RE: Rate confirmation — ORD456", None) is True
    assert subject_or_snippet_indicates_load_intake_text_cues(None, "See BOL attached MC 123456") is True
    assert subject_or_snippet_indicates_load_intake_text_cues("Weekend plans", None) is False


def test_extract_broker_mc_dot_hints() -> None:
    mc, dot = extract_broker_mc_dot_hints("MC 123456 USDOT 9876543")
    assert mc == "123456"
    assert dot == "9876543"


def test_extract_pdf_text_bytes_empty() -> None:
    assert extract_pdf_text_bytes(b"") == ""
