"""Operator review reasons for global booking broker **duplicate candidates** (not merges).

Loaded from ``shared/global_booking_broker_duplicate_review_reason_codes.json``.
``note`` on API bodies is supplemental only; primary dispositions use stable codes below.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

_JSON_PATH = Path(__file__).resolve().parents[2] / "shared" / "global_booking_broker_duplicate_review_reason_codes.json"


@lru_cache
def _data() -> dict[str, Any]:
    return json.loads(_JSON_PATH.read_text(encoding="utf-8"))


def duplicate_review_reason_schema_version() -> int:
    return int(_data()["schema_version"])


def _write_codes(group: str) -> frozenset[str]:
    return frozenset(str(x) for x in _data()[group]["write"])


DUPLICATE_REVIEW_DISMISS_REASONS_WRITE = _write_codes("dismiss")
DUPLICATE_REVIEW_ACKNOWLEDGE_REASONS_WRITE = _write_codes("acknowledge")


def duplicate_review_operator_hint(code: str) -> str | None:
    hints = _data().get("operator_hint") or {}
    v = hints.get((code or "").strip())
    return str(v) if v is not None else None


class GlobalBookingBrokerDuplicateCandidateReviewIn(BaseModel):
    """PATCH duplicate candidate — only ``open`` rows; disposition uses structured reason codes."""

    review_status: str = Field(..., min_length=1, max_length=32)
    duplicate_review_reason_code: str = Field(..., min_length=1, max_length=64)
    note: str | None = Field(default=None, max_length=2000)

    @field_validator("review_status")
    @classmethod
    def _status(cls, v: str) -> str:
        s = v.strip().lower()
        if s not in ("dismissed", "acknowledged"):
            raise ValueError("invalid_duplicate_candidate_review_status")
        return s

    @field_validator("duplicate_review_reason_code")
    @classmethod
    def _strip_code(cls, v: str) -> str:
        return (v or "").strip()

    @model_validator(mode="after")
    def _code_matches_status(self) -> GlobalBookingBrokerDuplicateCandidateReviewIn:
        if self.review_status == "dismissed":
            if self.duplicate_review_reason_code not in DUPLICATE_REVIEW_DISMISS_REASONS_WRITE:
                raise ValueError("invalid_duplicate_review_dismiss_reason_code")
        else:
            if self.duplicate_review_reason_code not in DUPLICATE_REVIEW_ACKNOWLEDGE_REASONS_WRITE:
                raise ValueError("invalid_duplicate_review_acknowledge_reason_code")
        return self
