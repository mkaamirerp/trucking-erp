"""Conservative provider reason normalization (Segment B)."""

from __future__ import annotations

import re
import unicodedata


def normalize_provider_reason_key(raw: str | None) -> str | None:
    """Unicode-normalize, trim, lowercase, collapse internal whitespace.

    Does not stem, drop punctuation, or rewrite semantics.
    """
    if raw is None:
        return None
    text = unicodedata.normalize("NFKC", str(raw)).strip()
    if not text:
        return None
    text = text.lower()
    text = re.sub(r"\s+", " ", text)
    return text
