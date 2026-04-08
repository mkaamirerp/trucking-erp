"""Pure helpers for global broker duplicate candidate edges (no DB)."""

from __future__ import annotations

from app.services.global_broker_duplicate_candidates import add_signal, ordered_pair, signals_to_json


def test_ordered_pair() -> None:
    assert ordered_pair(2, 5) == (2, 5)
    assert ordered_pair(9, 3) == (3, 9)


def test_add_signal_merges() -> None:
    pairs: dict[tuple[int, int], set[str]] = {}
    add_signal(pairs, 1, 2, "shared_mc_number")
    add_signal(pairs, 2, 1, "shared_domain:x.com")
    assert pairs[(1, 2)] == {"shared_mc_number", "shared_domain:x.com"}


def test_add_signal_merges_shared_cvor() -> None:
    pairs: dict[tuple[int, int], set[str]] = {}
    add_signal(pairs, 1, 2, "shared_cvor:123456789")
    add_signal(pairs, 1, 2, "shared_mc_number")
    assert pairs[(1, 2)] == {"shared_cvor:123456789", "shared_mc_number"}


def test_add_signal_ignores_self() -> None:
    pairs: dict[tuple[int, int], set[str]] = {}
    add_signal(pairs, 3, 3, "x")
    assert pairs == {}


def test_signals_to_json_sorted() -> None:
    assert signals_to_json({"b", "a"}) == '["a", "b"]'
