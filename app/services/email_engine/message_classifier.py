"""
Shared classification heuristics (provider-agnostic). No DB side effects.

Stage 1 (intake / filter): broker-neutral cues that an email thread may be load or PDF related.
Broker identity stays in ``resolve_booking_broker_for_email_intake`` / registry — not hardcoded domains here.
"""

from __future__ import annotations

import re
from typing import Literal

from app.models.email_ingestion import EmailThread

PostIngestIntakePath = Literal["email_pdf_intake", "review_only"]

# Generic document / ops language common to brokerage freight email (not carrier-specific).
_LOAD_INTAKE_TEXT_CUE_RE = re.compile(
    r"\b(?:"
    r"rate\s+confirmation|rate\s*con(?:firmation)?|ratecon|"
    r"bill\s+of\s+lading|\bbol\b|"
    r"load\s+(?:tender|assignment|confirmation|offer)|"
    r"freight\s+(?:tender|quote|confirmation)|"
    r"(?:carrier|line)\s*haul|"
    r"dispatch\s+(?:notice|confirmation)|"
    r"\bmc\s*[#:.-]?\s*\d{4,8}\b|\b(?:us\s*)?dot\s*[#:.-]?\s*\d{4,10}\b"
    r")\b",
    re.IGNORECASE,
)


def participants_indicate_booking_broker_touchpoints(participants_json: dict | list | None) -> bool:
    """No per-carrier participant heuristics without tenant broker registry data."""
    return False


def subject_or_snippet_indicates_booking_broker_touchpoints(subject: str | None, snippet: str | None) -> bool:
    """True when subject/snippet suggests rate con / load doc / MC-DOT style freight email (broker-neutral)."""
    blob = f"{subject or ''}\n{snippet or ''}"
    if not blob.strip():
        return False
    return bool(_LOAD_INTAKE_TEXT_CUE_RE.search(blob))


def thread_indicates_booking_broker_touchpoints(thread: EmailThread) -> bool:
    """Thread-level load-intake text cues (subject + snippet only at classify time)."""
    return subject_or_snippet_indicates_booking_broker_touchpoints(thread.subject, thread.snippet)


def post_ingest_intake_path(*, provider: str) -> PostIngestIntakePath:
    """Which shared intake pipeline applies after persistence (provider integration only)."""
    p = (provider or "").strip().lower()
    if p == "gmail":
        return "email_pdf_intake"
    return "review_only"
