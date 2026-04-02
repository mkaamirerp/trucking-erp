"""
Shared classification heuristics (provider-agnostic signals). No DB side effects.

Gmail-specific TQL affinity lives here so providers never embed business rules.
"""

from __future__ import annotations

import re
from typing import Literal

from app.models.email_ingestion import EmailThread

_TQL_EMAIL_MARKERS = ("@tql.com", "@tqltrucks.com", "@tql.net")
_TQL_SUBJECT_SNIPPET_RE = re.compile(r"\btql\b|total\s+quality\s+logistics", re.IGNORECASE)

PostIngestIntakePath = Literal["gmail_tql_gate", "review_only"]


def participants_indicate_tql(participants_json: dict | list | None) -> bool:
    if not participants_json or not isinstance(participants_json, list):
        return False
    for p in participants_json:
        if not isinstance(p, dict):
            continue
        email = str(p.get("email") or "").strip().lower()
        if any(m in email for m in _TQL_EMAIL_MARKERS):
            return True
    return False


def subject_or_snippet_indicates_tql(subject: str | None, snippet: str | None) -> bool:
    blob = f"{subject or ''}\n{snippet or ''}"
    return bool(_TQL_SUBJECT_SNIPPET_RE.search(blob))


def thread_indicates_tql_affinity(thread: EmailThread) -> bool:
    return participants_indicate_tql(thread.participants_json) or subject_or_snippet_indicates_tql(
        thread.subject, thread.snippet
    )


def post_ingest_intake_path(*, provider: str) -> PostIngestIntakePath:
    """Which shared intake pipeline applies after persistence (not provider business logic)."""
    p = (provider or "").strip().lower()
    if p == "gmail":
        return "gmail_tql_gate"
    return "review_only"
