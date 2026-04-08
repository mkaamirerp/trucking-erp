"""Normalization helpers for broker domain/alias identity (intake + API validation)."""

from __future__ import annotations

import re
from email.utils import parseaddr

# Conservative hostname: labels of [a-z0-9-], dots between, no leading/trailing hyphen per label.
_DOMAIN_LABEL = re.compile(r"^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)(?:\.(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?))*$")


def normalize_domain(raw: str) -> str:
    s = (raw or "").strip().lower()
    if not s or "@" in s or "/" in s or ":" in s or " " in s or "\t" in s or "\n" in s:
        raise ValueError("invalid_domain")
    s = s.strip(".")
    if not s or len(s) > 255:
        raise ValueError("invalid_domain")
    if not _DOMAIN_LABEL.match(s):
        raise ValueError("invalid_domain")
    return s


def normalize_alias(raw: str) -> str:
    s = (raw or "").strip()
    if not s:
        raise ValueError("invalid_alias")
    s = " ".join(s.split())
    s = s.casefold()
    if len(s) > 255:
        raise ValueError("invalid_alias")
    return s


def parsed_from_display_and_email(from_header: str) -> tuple[str, str]:
    """
    Parse a From header (or bare email). Returns (display_name, email) both possibly empty strings.
    """
    hdr = (from_header or "").strip()
    if not hdr:
        return "", ""
    display, addr = parseaddr(hdr)
    display = (display or "").strip()
    addr = (addr or "").strip().lower()
    return display, addr


def email_local_part(email: str) -> str:
    e = (email or "").strip().lower()
    if "@" not in e:
        return ""
    return e.split("@", 1)[0]


def normalize_known_sender_email(raw: str) -> str:
    """Lowercase full address for exact intake matching; raises ValueError if unusable."""
    s = (raw or "").strip().lower()
    if not s or "@" not in s or len(s) > 320:
        raise ValueError("invalid_known_sender_email")
    local, _, domain = s.partition("@")
    if not local or not domain:
        raise ValueError("invalid_known_sender_email")
    return s


def normalize_mc_number_digits(raw: str | None) -> str | None:
    """Digits-only MC for matching global/tenant reference (not a display formatter)."""
    if not raw:
        return None
    d = "".join(c for c in str(raw).strip() if c.isdigit())
    if len(d) < 4:
        return None
    return d


def normalize_dot_number_digits(raw: str | None) -> str | None:
    """Digits-only USDOT for matching global/tenant reference."""
    if not raw:
        return None
    d = "".join(c for c in str(raw).strip() if c.isdigit())
    if len(d) < 4:
        return None
    return d


def normalize_cvor_number_digits(raw: str | None) -> str | None:
    """9-digit CVOR (CA/ON) for global reference; ``None`` if empty.

    Raises ``ValueError`` with message ``invalid_cvor_number`` if input is non-empty
    but not exactly nine digits after digit extraction.
    """
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    d = "".join(c for c in s if c.isdigit())
    if len(d) != 9:
        raise ValueError("invalid_cvor_number")
    return d
