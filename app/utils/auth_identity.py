"""Canonical email normalization for auth (login, reset, invite, sync)."""

from __future__ import annotations


def normalize_auth_email(email: str | None) -> str:
    """
    Trim whitespace, lowercase. Do NOT apply Gmail dot/plus normalization.
    """
    if email is None:
        return ""
    return str(email).strip().lower()
