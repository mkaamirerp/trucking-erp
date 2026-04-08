"""Promotion ``reason_code`` values for global booking brokers — ``shared/global_booking_broker_promotion_reason_codes.json``.

* **approve / reject / reopen** ``write`` sets — allowed on ``PATCH`` when transitioning to that status.
* **operator_hint** — short UI labels (frontend imports the same JSON).

Legacy audit rows may still have older ``detail`` shapes (e.g. only ``note``); new changes always store
``promotion_reason_code`` plus ``promotion_reason_hint``.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

_JSON_PATH = Path(__file__).resolve().parents[2] / "shared" / "global_booking_broker_promotion_reason_codes.json"


@lru_cache
def _data() -> dict[str, Any]:
    raw = _JSON_PATH.read_text(encoding="utf-8")
    return json.loads(raw)


def global_booking_broker_promotion_reason_schema_version() -> int:
    return int(_data()["schema_version"])


def _write_codes(group: str) -> frozenset[str]:
    return frozenset(str(x) for x in _data()[group]["write"])


APPROVE_PROMOTION_REASON_CODES_WRITE = _write_codes("approve")
REJECT_PROMOTION_REASON_CODES_WRITE = _write_codes("reject")
REOPEN_PROMOTION_REASON_CODES_WRITE = _write_codes("reopen")

ALL_PROMOTION_REASON_CODES: frozenset[str] = frozenset(
    APPROVE_PROMOTION_REASON_CODES_WRITE
    | REJECT_PROMOTION_REASON_CODES_WRITE
    | REOPEN_PROMOTION_REASON_CODES_WRITE
)


def promotion_operator_hint(code: str) -> str | None:
    hints = _data().get("operator_hint") or {}
    v = hints.get(code.strip())
    return str(v) if v is not None else None


def allowed_promotion_reasons_for_transition(*, prev_status: str, next_status: str) -> frozenset[str] | None:
    """Return allowed reason codes for ``prev_status`` → ``next_status``, or ``None`` if disallowed or no-op."""
    prev = (prev_status or "").strip().lower()
    nxt = (next_status or "").strip().lower()
    if prev == nxt:
        return None
    if nxt == "approved" and prev in ("pending", "rejected"):
        return APPROVE_PROMOTION_REASON_CODES_WRITE
    if nxt == "rejected" and prev in ("pending", "approved"):
        return REJECT_PROMOTION_REASON_CODES_WRITE
    if nxt == "pending" and prev in ("approved", "rejected"):
        return REOPEN_PROMOTION_REASON_CODES_WRITE
    return None


def normalize_and_validate_promotion_reason(
    *,
    prev_status: str,
    next_status: str,
    promotion_reason_code: str | None,
) -> tuple[str, frozenset[str]]:
    """Return ``(normalized_code, allowed_set)``. Raises ``ValueError`` with a stable message if invalid."""
    allowed = allowed_promotion_reasons_for_transition(prev_status=prev_status, next_status=next_status)
    if allowed is None:
        prev = (prev_status or "").strip().lower()
        nxt = (next_status or "").strip().lower()
        if prev == nxt:
            raise ValueError("global_broker_promotion_no_status_change")
        raise ValueError("global_broker_promotion_invalid_transition")

    raw = (promotion_reason_code or "").strip()
    if not raw:
        raise ValueError("global_broker_promotion_reason_required")
    if raw not in allowed:
        raise ValueError("global_broker_promotion_reason_not_allowed_for_transition")
    return raw, allowed
