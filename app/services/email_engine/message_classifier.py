"""
Shared classification heuristics (provider-agnostic signals). No DB side effects.

Booking-broker touchpoint patterns (e.g. known broker domains / keywords) are **hints only**.
Long-term they should come from tenant broker reference data, not hardcoded string lists here.
"""

from __future__ import annotations

import re
from typing import Literal

from app.models.email_ingestion import EmailThread

# TODO(data): move to tenant broker intake config (domains, aliases, known senders).
_BOOKING_BROKER_EMAIL_MARKERS = ("@tql.com", "@tqltrucks.com", "@tql.net")
_BOOKING_BROKER_SUBJECT_SNIPPET_RE = re.compile(
    r"\btql\b|total\s+quality\s+logistics", re.IGNORECASE
)

PostIngestIntakePath = Literal["email_pdf_intake", "review_only"]


def participants_indicate_booking_broker_touchpoints(participants_json: dict | list | None) -> bool:
    if not participants_json or not isinstance(participants_json, list):
        return False
    for p in participants_json:
        if not isinstance(p, dict):
            continue
        email = str(p.get("email") or "").strip().lower()
        if any(m in email for m in _BOOKING_BROKER_EMAIL_MARKERS):
            return True
    return False


def subject_or_snippet_indicates_booking_broker_touchpoints(subject: str | None, snippet: str | None) -> bool:
    blob = f"{subject or ''}\n{snippet or ''}"
    return bool(_BOOKING_BROKER_SUBJECT_SNIPPET_RE.search(blob))


def thread_indicates_booking_broker_touchpoints(thread: EmailThread) -> bool:
    return participants_indicate_booking_broker_touchpoints(
        thread.participants_json
    ) or subject_or_snippet_indicates_booking_broker_touchpoints(thread.subject, thread.snippet)


def post_ingest_intake_path(*, provider: str) -> PostIngestIntakePath:
    """Which shared intake pipeline applies after persistence (provider integration only)."""
    p = (provider or "").strip().lower()
    if p == "gmail":
        return "email_pdf_intake"
    return "review_only"
