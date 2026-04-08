"""Duplicate detection SQL must exclude brokers that are already merge losers (no DB)."""

from __future__ import annotations

from sqlalchemy.sql.elements import TextClause

from app.services.global_broker_duplicate_candidates import (
    _ALIAS_SQL,
    _CVOR_MATCH_SQL,
    _DOMAIN_SQL,
    _DOT_MATCH_SQL,
    _KNOWN_SQL,
    _MC_MATCH_SQL,
)


def _snippet(t: TextClause) -> str:
    return getattr(t, "text", None) or str(t)


def test_all_overlap_sql_excludes_merged_into_brokers() -> None:
    needle = "merged_into_global_broker_id IS NULL"
    for stmt in (_MC_MATCH_SQL, _DOT_MATCH_SQL, _CVOR_MATCH_SQL, _DOMAIN_SQL, _KNOWN_SQL, _ALIAS_SQL):
        s = _snippet(stmt)
        assert needle in s, s[:200]
        assert s.count(needle) >= 2, "expect filters on both endpoints"
