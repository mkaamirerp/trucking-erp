"""Global booking broker merge preview: classifications, blockers, hash (no DB)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.models.global_booking_broker import GlobalBookingBroker
from app.services import global_booking_broker_merge_preview as mp
from app.utils import global_booking_broker_merge as guard


def _broker(
    bid: int,
    *,
    name: str = "Acme",
    legal_name: str | None = "Acme LLC",
    display_name: str | None = None,
    mc: str | None = None,
    dot: str | None = None,
    cvor: str | None = None,
    merged_into: int | None = None,
    merged_at: datetime | None = None,
) -> GlobalBookingBroker:
    b = GlobalBookingBroker(
        name=name,
        legal_name=legal_name,
        display_name=display_name,
        mc_number=mc,
        dot_number=dot,
        cvor_number=cvor,
        canonical_status="approved",
    )
    b.id = bid
    b.merged_into_global_broker_id = merged_into
    b.merged_at = merged_at
    return b


def test_self_merge_blocker() -> None:
    b = _broker(1)
    out = mp.build_merge_preview(source=b, survivor=b, duplicate_candidate_id=None)
    assert any(x["code"] == "merge_self_not_allowed" for x in out.preview_body["blockers"])
    assert out.persist_eligible is False
    assert out.preview_body["summary"]["has_blockers"] is True


def test_source_already_merged_blocker_surfaces_link() -> None:
    when = datetime(2026, 3, 1, tzinfo=UTC)
    src = _broker(1, merged_into=99, merged_at=when)
    surv = _broker(2)
    out = mp.build_merge_preview(source=src, survivor=surv, duplicate_candidate_id=None)
    codes = [x["code"] for x in out.preview_body["blockers"]]
    assert guard.MERGE_SOURCE_BLOCKED_ALREADY_LOSER in codes
    blocker = next(x for x in out.preview_body["blockers"] if x["code"] == guard.MERGE_SOURCE_BLOCKED_ALREADY_LOSER)
    assert blocker["detail"]["merged_into_global_broker_id"] == 99
    assert blocker["detail"]["merged_at"] == when.isoformat()
    assert out.persist_eligible is False


def test_survivor_already_merged_blocker() -> None:
    when = datetime(2026, 3, 2, tzinfo=UTC)
    src = _broker(1)
    surv = _broker(2, merged_into=88, merged_at=when)
    out = mp.build_merge_preview(source=src, survivor=surv, duplicate_candidate_id=None)
    assert any(x["code"] == guard.MERGE_SURVIVOR_BLOCKED_ALREADY_LOSER for x in out.preview_body["blockers"])
    assert out.persist_eligible is False


def test_mc_dot_cvor_blocking_conflict_detection() -> None:
    src = _broker(1, mc="MC-123456", dot="DOT 1111111", cvor="123456789")
    surv = _broker(2, mc="MC-999999", dot="2222222", cvor="987654321")
    out = mp.build_merge_preview(source=src, survivor=surv, duplicate_candidate_id=None)
    by_field = {c["field"]: c for c in out.preview_body["field_comparisons"]}
    assert by_field["mc_number"]["classification"] == "blocking_conflict"
    assert by_field["dot_number"]["classification"] == "blocking_conflict"
    assert by_field["cvor_number"]["classification"] == "blocking_conflict"
    assert out.preview_body["summary"]["has_blocking_conflict"] is True
    assert out.persist_eligible is False


def test_regulator_safe_default_one_side_empty() -> None:
    src = _broker(1, mc="123456", dot=None, cvor=None)
    surv = _broker(2, mc=None, dot="33333333", cvor="111111111")
    out = mp.build_merge_preview(source=src, survivor=surv, duplicate_candidate_id=None)
    by_field = {c["field"]: c for c in out.preview_body["field_comparisons"]}
    assert by_field["mc_number"]["classification"] == "safe_default"
    assert by_field["dot_number"]["classification"] == "safe_default"
    assert by_field["cvor_number"]["classification"] == "safe_default"
    assert out.preview_body["summary"]["has_blocking_conflict"] is False


def test_name_operator_choice_required() -> None:
    src = _broker(1, name="Foo Inc", legal_name="Foo", display_name="FOO")
    surv = _broker(2, name="Bar Inc", legal_name="Bar", display_name="BAR")
    out = mp.build_merge_preview(source=src, survivor=surv, duplicate_candidate_id=None)
    by_field = {c["field"]: c for c in out.preview_body["field_comparisons"]}
    assert by_field["name"]["classification"] == "operator_choice_required"
    assert by_field["legal_name"]["classification"] == "operator_choice_required"
    assert by_field["display_name"]["classification"] == "operator_choice_required"
    assert "name" in out.preview_body["summary"]["operator_choice_required_fields"]


def test_preview_payload_shape_and_hash_stability() -> None:
    src = _broker(1, name="Same", mc="123456")
    surv = _broker(2, name="Same", mc="123456")
    a = mp.build_merge_preview(source=src, survivor=surv, duplicate_candidate_id=None)
    b = mp.build_merge_preview(source=src, survivor=surv, duplicate_candidate_id=None)
    assert a.preview_hash == b.preview_hash
    assert a.preview_hash == mp.compute_preview_hash(a.canonical)
    assert len(a.preview_hash) == 64
    for key in (
        "schema_version",
        "source_global_broker_id",
        "survivor_global_broker_id",
        "duplicate_candidate_id",
        "source_snapshot",
        "survivor_snapshot",
        "blockers",
        "field_comparisons",
        "summary",
    ):
        assert key in a.preview_body
    assert a.persist_eligible is True
    assert a.preview_body["summary"]["persist_eligible"] is True


def test_duplicate_candidate_id_affects_hash() -> None:
    src = _broker(1)
    surv = _broker(2)
    a = mp.build_merge_preview(source=src, survivor=surv, duplicate_candidate_id=None)
    b = mp.build_merge_preview(source=src, survivor=surv, duplicate_candidate_id=42)
    assert a.preview_hash != b.preview_hash


@pytest.mark.parametrize(
    ("s", "z", "exp"),
    [
        (None, None, "aligned"),
        ("123456", "123456", "aligned"),
        (None, "123456", "safe_default"),
        ("123456", "999999", "blocking_conflict"),
    ],
)
def test_classify_regulatory_pair(s: str | None, z: str | None, exp: str) -> None:
    assert mp.classify_regulatory_pair(s, z) == exp


@pytest.mark.parametrize(
    ("s", "z", "exp"),
    [
        (None, None, "aligned"),
        ("acme", "acme", "aligned"),
        (None, "x", "safe_default"),
        ("a", "b", "operator_choice_required"),
    ],
)
def test_classify_name_pair(s: str | None, z: str | None, exp: str) -> None:
    """``classify_name_pair`` expects *casefolded* normalized strings (see ``_norm_name_for_compare``)."""
    assert mp.classify_name_pair(s, z) == exp
