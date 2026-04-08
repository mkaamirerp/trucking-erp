"""Contract tests for shared intake review reason codes (no DB)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.constants import email_intake_review_reason_codes as mod


def test_json_matches_python_duplicate_and_system_constants() -> None:
    path = Path(__file__).resolve().parents[1] / "shared" / "email_intake_review_reason_codes.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert frozenset(raw["duplicate"]["server_only"]) == frozenset(
        {
            mod.REASON_DUPLICATE_LINK_PRIOR,
            mod.REASON_DUPLICATE_CONFIRMED,
            mod.REASON_DUPLICATE_FALSE_POSITIVE,
        }
    )
    assert raw["system"]["server_only"] == [mod.REASON_THREAD_LINKED_LOAD]


@pytest.mark.parametrize(
    ("model", "payload", "ok"),
    [
        (mod.IntakeReviewResolveReasonWrite, {"reason_code": "resolved_reviewed"}, True),
        (mod.IntakeReviewResolveReasonWrite, {"reason_code": "bogus"}, False),
        (mod.IntakeReviewDismissReasonWrite, {"reason_code": "dismissed_other"}, True),
        (mod.IntakeReviewDismissReasonWrite, {"reason_code": "duplicate_false_positive"}, False),
        (mod.IntakeReviewReopenReasonWrite, {"reason_code": "reopened_operator"}, True),
        (mod.IntakeReviewReopenReasonWrite, {"reason_code": "reopened_manual"}, False),
        (mod.IntakeReviewDuplicateDismissBody, {"note": "x"}, True),
        (mod.IntakeReviewDuplicateDismissBody, {"reason_code": "nope"}, False),
    ],
)
def test_pydantic_write_sets(model, payload: dict, ok: bool) -> None:
    if ok:
        model.model_validate(payload)
    else:
        with pytest.raises(ValidationError):
            model.model_validate(payload)
