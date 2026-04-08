"""Intake review ``reason_code`` values: loaded from ``shared/email_intake_review_reason_codes.json``.

* **write** sets — allowed on operator POST bodies (resolve / dismiss / reopen).
* **server_only** — emitted only by backend workflows; not accepted from clients on those paths.
* **operator_hint** — short UI labels (frontend imports the same JSON).

Legacy rows may still contain older or ad-hoc ``reason_code`` strings; APIs only accept the write sets above.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator

_JSON_PATH = Path(__file__).resolve().parents[2] / "shared" / "email_intake_review_reason_codes.json"

# Canonical duplicate / system codes (must match ``shared/email_intake_review_reason_codes.json``).
REASON_DUPLICATE_LINK_PRIOR = "duplicate_link_prior"
REASON_DUPLICATE_CONFIRMED = "duplicate_confirmed"
REASON_DUPLICATE_FALSE_POSITIVE = "duplicate_false_positive"
REASON_THREAD_LINKED_LOAD = "thread_linked_load"


@lru_cache
def _data() -> dict[str, Any]:
    raw = _JSON_PATH.read_text(encoding="utf-8")
    return json.loads(raw)


def _assert_json_matches_canonical() -> None:
    d = _data()
    if frozenset(d["duplicate"]["server_only"]) != frozenset(
        {REASON_DUPLICATE_LINK_PRIOR, REASON_DUPLICATE_CONFIRMED, REASON_DUPLICATE_FALSE_POSITIVE}
    ):
        raise RuntimeError("shared/email_intake_review_reason_codes.json duplicate.server_only drift")
    if frozenset(d["system"]["server_only"]) != frozenset({REASON_THREAD_LINKED_LOAD}):
        raise RuntimeError("shared/email_intake_review_reason_codes.json system.server_only drift")


_assert_json_matches_canonical()


def intake_review_reason_schema_version() -> int:
    return int(_data()["schema_version"])


def _write_codes(group: str) -> frozenset[str]:
    return frozenset(str(x) for x in _data()[group]["write"])


RESOLVE_REASON_CODES_WRITE = _write_codes("resolve")
DISMISS_REASON_CODES_WRITE = _write_codes("dismiss")
REOPEN_REASON_CODES_WRITE = _write_codes("reopen")

ALL_DOCUMENTED_REASON_CODES: frozenset[str] = frozenset(
    RESOLVE_REASON_CODES_WRITE
    | DISMISS_REASON_CODES_WRITE
    | REOPEN_REASON_CODES_WRITE
    | {
        REASON_DUPLICATE_LINK_PRIOR,
        REASON_DUPLICATE_CONFIRMED,
        REASON_DUPLICATE_FALSE_POSITIVE,
        REASON_THREAD_LINKED_LOAD,
    }
)


class IntakeReviewResolveReasonWrite(BaseModel):
    """POST /intake-review/resolve — ``reason_code`` must be in the resolve write set."""

    reason_code: str = Field(..., min_length=1, max_length=64)
    note: str | None = Field(default=None, max_length=8000)

    @field_validator("reason_code")
    @classmethod
    def _v_reason(cls, v: str) -> str:
        s = v.strip()
        if s not in RESOLVE_REASON_CODES_WRITE:
            raise ValueError("invalid_intake_review_resolve_reason_code")
        return s


class IntakeReviewDismissReasonWrite(BaseModel):
    """POST /intake-review/dismiss — ``reason_code`` must be in the dismiss write set."""

    reason_code: str = Field(..., min_length=1, max_length=64)
    note: str | None = Field(default=None, max_length=8000)

    @field_validator("reason_code")
    @classmethod
    def _must_be_allowed(cls, v: str) -> str:
        s = v.strip()
        if s not in DISMISS_REASON_CODES_WRITE:
            raise ValueError("invalid_intake_review_dismiss_reason_code")
        return s


class IntakeReviewReopenReasonWrite(BaseModel):
    """POST /intake-review/reopen — ``reason_code`` must be in the reopen write set."""

    reason_code: str = Field(..., min_length=1, max_length=64)
    note: str | None = Field(default=None, max_length=8000)

    @field_validator("reason_code")
    @classmethod
    def _must_be_allowed(cls, v: str) -> str:
        s = v.strip()
        if s not in REOPEN_REASON_CODES_WRITE:
            raise ValueError("invalid_intake_review_reopen_reason_code")
        return s


class IntakeReviewDuplicateDismissBody(BaseModel):
    """POST /intake-review/duplicate/dismiss-false-positive — server sets ``duplicate_false_positive``."""

    note: str | None = Field(default=None, max_length=8000)

    model_config = {"extra": "forbid"}
