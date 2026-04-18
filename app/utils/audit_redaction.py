from __future__ import annotations

from dataclasses import dataclass
from typing import Any


DEFAULT_SENSITIVE_FIELD_SUBSTRINGS = (
    "password",
    "password_hash",
    "token",
    "secret",
    "api_key",
    "ssn",
    "routing_number",
    "bank_account",
)


@dataclass(frozen=True)
class RedactionResult:
    redacted: Any
    was_redacted: bool


def _is_sensitive_field(field_name: str) -> bool:
    f = field_name.strip().lower()
    return any(s in f for s in DEFAULT_SENSITIVE_FIELD_SUBSTRINGS)


def redact_changed_fields(changed_fields: dict[str, Any]) -> tuple[dict[str, Any], set[str]]:
    """Redact sensitive values in changed_fields payload.

    Contract shape:
      { field: { before: X, after: Y, redacted?: true } }
    """
    redacted_fields: set[str] = set()
    out: dict[str, Any] = {}
    for k, v in (changed_fields or {}).items():
        if _is_sensitive_field(k):
            redacted_fields.add(k)
            out[k] = {"before": None, "after": None, "redacted": True}
            continue

        # Best-effort normalize: accept either {before, after} or already-normalized.
        if isinstance(v, dict) and ("before" in v or "after" in v):
            before = v.get("before")
            after = v.get("after")
        else:
            before = None
            after = v

        out[k] = {"before": before, "after": after}
    return out, redacted_fields


def redact_snapshot(snapshot: dict[str, Any] | None) -> tuple[dict[str, Any] | None, set[str]]:
    """Redact sensitive keys at the top-level of a snapshot dict.

    We intentionally keep this conservative and shallow for Slice 1:
    - Top-level keys only (callers should avoid dumping nested secrets).
    - Future: recursive redaction and schema-specific redactors.
    """
    if snapshot is None:
        return None, set()
    out: dict[str, Any] = {}
    redacted_fields: set[str] = set()
    for k, v in snapshot.items():
        if _is_sensitive_field(k):
            redacted_fields.add(k)
            out[k] = None
        else:
            out[k] = v
    return out, redacted_fields


def classify_visibility(*, base_visibility: str, redacted_fields: set[str]) -> str:
    """Upgrade visibility when sensitive fields are involved.

    For Slice 1 we keep rules simple:
    - If sensitive fields were redacted, bump to at least `sensitive`.
    - Never downgrade a caller-specified visibility.
    """
    order = {
        "normal": 0,
        "sensitive": 1,
        "admin_sensitive": 2,
        "finance_sensitive": 2,
    }
    current = base_visibility or "normal"
    if redacted_fields and order.get(current, 0) < order["sensitive"]:
        return "sensitive"
    return current

