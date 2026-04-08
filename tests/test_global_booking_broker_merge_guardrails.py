"""Merge source guardrails for global booking brokers (no DB)."""

from __future__ import annotations

import pytest

from app.models.global_booking_broker import GlobalBookingBroker
from app.schemas.platform_global_booking_broker import GlobalBookingBrokerOut
from app.utils import global_booking_broker_merge as guard


def _broker(**kw) -> GlobalBookingBroker:
    merged_into = kw.pop("merged_into_global_broker_id", None)
    b = GlobalBookingBroker(name="B", canonical_status="pending", **kw)
    if merged_into is not None:
        b.merged_into_global_broker_id = merged_into
    return b


def test_is_merge_loser_false_when_no_link() -> None:
    b = _broker()
    assert guard.global_booking_broker_is_merge_loser(b) is False
    assert guard.global_booking_broker_merge_source_violation(b) is None


def test_is_merge_loser_true_when_merged_into_set() -> None:
    b = _broker(merged_into_global_broker_id=99)
    assert guard.global_booking_broker_is_merge_loser(b) is True
    assert guard.global_booking_broker_merge_source_violation(b) == guard.MERGE_SOURCE_BLOCKED_ALREADY_LOSER


def test_assert_eligible_merge_source_raises() -> None:
    b = _broker(merged_into_global_broker_id=1)
    with pytest.raises(ValueError, match=guard.MERGE_SOURCE_BLOCKED_ALREADY_LOSER):
        guard.assert_global_booking_broker_eligible_merge_source(b)


def test_assert_eligible_merge_source_ok() -> None:
    guard.assert_global_booking_broker_eligible_merge_source(_broker())


def test_survivor_violation_when_loser() -> None:
    b = _broker(merged_into_global_broker_id=3)
    assert guard.global_booking_broker_merge_survivor_violation(b) == guard.MERGE_SURVIVOR_BLOCKED_ALREADY_LOSER


def test_assert_eligible_merge_survivor_ok() -> None:
    guard.assert_global_booking_broker_eligible_merge_survivor(_broker())


def test_assert_eligible_merge_survivor_raises() -> None:
    b = _broker(merged_into_global_broker_id=1)
    with pytest.raises(ValueError, match=guard.MERGE_SURVIVOR_BLOCKED_ALREADY_LOSER):
        guard.assert_global_booking_broker_eligible_merge_survivor(b)


def test_global_booking_broker_out_includes_merge_fields() -> None:
    from datetime import UTC, datetime

    b = _broker()
    b.id = 1
    b.merged_into_global_broker_id = 7
    b.merged_at = datetime(2026, 1, 2, tzinfo=UTC)
    b.created_at = datetime(2026, 1, 1, tzinfo=UTC)
    b.updated_at = datetime(2026, 1, 1, tzinfo=UTC)
    out = GlobalBookingBrokerOut.model_validate(b)
    assert out.merged_into_global_broker_id == 7
    assert out.merged_at == b.merged_at
