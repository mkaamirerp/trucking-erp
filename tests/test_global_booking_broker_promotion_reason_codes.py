"""Contract tests for global booking broker promotion reasons (no DB)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.constants import global_booking_broker_promotion_reason_codes as mod


def test_json_schema_version() -> None:
    path = Path(__file__).resolve().parents[1] / "shared" / "global_booking_broker_promotion_reason_codes.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["schema_version"] == mod.global_booking_broker_promotion_reason_schema_version()
    assert frozenset(raw["approve"]["write"]) == mod.APPROVE_PROMOTION_REASON_CODES_WRITE
    assert frozenset(raw["reject"]["write"]) == mod.REJECT_PROMOTION_REASON_CODES_WRITE
    assert frozenset(raw["reopen"]["write"]) == mod.REOPEN_PROMOTION_REASON_CODES_WRITE


@pytest.mark.parametrize(
    ("prev", "nxt", "code", "ok"),
    [
        ("pending", "approved", "approve_other", True),
        ("pending", "approved", "approve_bogus", False),
        ("rejected", "approved", "approve_reviewed_accepted", True),
        ("pending", "rejected", "reject_other", True),
        ("approved", "rejected", "reject_duplicate_global", True),
        ("approved", "pending", "reopen_operator", True),
        ("rejected", "pending", "reopen_needs_recheck", True),
        ("pending", "rejected", "approve_other", False),
        ("approved", "pending", "approve_other", False),
    ],
)
def test_normalize_promotion_reason(prev: str, nxt: str, code: str, ok: bool) -> None:
    if ok:
        out, _allowed = mod.normalize_and_validate_promotion_reason(
            prev_status=prev,
            next_status=nxt,
            promotion_reason_code=code,
        )
        assert out == code
    else:
        with pytest.raises(ValueError, match="global_broker_promotion_reason_not_allowed"):
            mod.normalize_and_validate_promotion_reason(
                prev_status=prev,
                next_status=nxt,
                promotion_reason_code=code,
            )


def test_promotion_reason_required() -> None:
    with pytest.raises(ValueError, match="global_broker_promotion_reason_required"):
        mod.normalize_and_validate_promotion_reason(
            prev_status="pending",
            next_status="approved",
            promotion_reason_code=None,
        )
    with pytest.raises(ValueError, match="global_broker_promotion_reason_required"):
        mod.normalize_and_validate_promotion_reason(
            prev_status="pending",
            next_status="approved",
            promotion_reason_code="   ",
        )


def test_invalid_transition() -> None:
    with pytest.raises(ValueError, match="global_broker_promotion_invalid_transition"):
        mod.normalize_and_validate_promotion_reason(
            prev_status="weird",
            next_status="approved",
            promotion_reason_code="approve_other",
        )


def test_operator_hint() -> None:
    assert mod.promotion_operator_hint("approve_other") == "Other approval"
    assert mod.promotion_operator_hint("nope") is None

