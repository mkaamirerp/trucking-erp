"""Contract tests for duplicate candidate review reasons (no DB)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.constants import global_booking_broker_duplicate_review_reason_codes as mod


def test_json_aligns_with_sets() -> None:
    path = Path(__file__).resolve().parents[1] / "shared" / "global_booking_broker_duplicate_review_reason_codes.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["schema_version"] == mod.duplicate_review_reason_schema_version()
    assert frozenset(raw["dismiss"]["write"]) == mod.DUPLICATE_REVIEW_DISMISS_REASONS_WRITE
    assert frozenset(raw["acknowledge"]["write"]) == mod.DUPLICATE_REVIEW_ACKNOWLEDGE_REASONS_WRITE


@pytest.mark.parametrize(
    ("payload", "ok"),
    [
        ({"review_status": "dismissed", "duplicate_review_reason_code": "dup_dismiss_other"}, True),
        ({"review_status": "acknowledged", "duplicate_review_reason_code": "dup_ack_other"}, True),
        ({"review_status": "dismissed", "duplicate_review_reason_code": "dup_ack_other"}, False),
        ({"review_status": "open", "duplicate_review_reason_code": "dup_dismiss_other"}, False),
        ({"review_status": "dismissed", "duplicate_review_reason_code": "nope"}, False),
    ],
)
def test_review_body(payload: dict, ok: bool) -> None:
    if ok:
        mod.GlobalBookingBrokerDuplicateCandidateReviewIn.model_validate(payload)
    else:
        with pytest.raises(ValidationError):
            mod.GlobalBookingBrokerDuplicateCandidateReviewIn.model_validate(payload)
