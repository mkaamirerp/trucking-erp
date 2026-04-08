"""Detect possible duplicate pairs among ``GlobalBookingBroker`` rows (platform DB).

No automatic merges — only **candidate** edges for operator review. Rules are conservative
identity overlaps: same MC, same DOT, same **canonical CVOR** (9-digit exact, see SQL),
same active domain, same active known-sender email,
same active alias (pairs ``min(id), max(id)``).

Pairs where **either** broker is already a merge loser
(``merged_into_global_broker_id IS NOT NULL``) are excluded from detection so refresh can drop
stale open rows and operators are not prompted to review obsolete edges.

CVOR overlap emits ``match_signals`` entries **shared_cvor:<canonical_value>** where
*canonical_value* is the trimmed 9-digit string from the row (same form as
``normalize_cvor_number_digits`` from API writes).
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.global_booking_broker import GlobalBookingBrokerDuplicateCandidate


def ordered_pair(a: int, b: int) -> tuple[int, int]:
    return (a, b) if a < b else (b, a)


def add_signal(pairs: dict[tuple[int, int], set[str]], a: int, b: int, signal: str) -> None:
    if a == b or not signal:
        return
    lo, hi = ordered_pair(a, b)
    pairs.setdefault((lo, hi), set()).add(signal)


_MC_MATCH_SQL = text(
    """
    SELECT b1.id AS id_a, b2.id AS id_b, :sig AS sig
    FROM global_booking_brokers b1
    INNER JOIN global_booking_brokers b2
      ON b1.id < b2.id
      AND b1.mc_number IS NOT NULL              AND b2.mc_number IS NOT NULL
      AND length(trim(b1.mc_number)) > 0       AND trim(b1.mc_number) = trim(b2.mc_number)
      AND b1.merged_into_global_broker_id IS NULL
      AND b2.merged_into_global_broker_id IS NULL
    """
)

_DOT_MATCH_SQL = text(
    """
    SELECT b1.id AS id_a, b2.id AS id_b, :sig AS sig
    FROM global_booking_brokers b1
    INNER JOIN global_booking_brokers b2
      ON b1.id < b2.id
      AND b1.dot_number IS NOT NULL            AND b2.dot_number IS NOT NULL
      AND length(trim(b1.dot_number)) > 0      AND trim(b1.dot_number) = trim(b2.dot_number)
      AND b1.merged_into_global_broker_id IS NULL
      AND b2.merged_into_global_broker_id IS NULL
    """
)

# Same canonical rule as API ``normalize_cvor_number_digits``: exactly nine digits (trimmed).
_CVOR_MATCH_SQL = text(
    """
    SELECT b1.id AS id_a, b2.id AS id_b, 'shared_cvor:' || trim(b1.cvor_number) AS sig
    FROM global_booking_brokers b1
    INNER JOIN global_booking_brokers b2
      ON b1.id < b2.id
      AND b1.cvor_number IS NOT NULL           AND b2.cvor_number IS NOT NULL
      AND trim(b1.cvor_number) ~ '^[0-9]{9}$'
      AND trim(b1.cvor_number) = trim(b2.cvor_number)
      AND b1.merged_into_global_broker_id IS NULL
      AND b2.merged_into_global_broker_id IS NULL
    """
)


_DOMAIN_SQL = text(
    """
    SELECT d1.global_broker_id AS id_a, d2.global_broker_id AS id_b, 'shared_domain:' || d1.domain AS sig
    FROM global_booking_broker_domains d1
    INNER JOIN global_booking_broker_domains d2
      ON d1.global_broker_id < d2.global_broker_id
      AND d1.domain = d2.domain
      AND d1.is_active IS TRUE
      AND d2.is_active IS TRUE
    INNER JOIN global_booking_brokers b1 ON b1.id = d1.global_broker_id
    INNER JOIN global_booking_brokers b2 ON b2.id = d2.global_broker_id
      AND b1.merged_into_global_broker_id IS NULL
      AND b2.merged_into_global_broker_id IS NULL
    """
)


_KNOWN_SQL = text(
    """
    SELECT k1.global_broker_id AS id_a, k2.global_broker_id AS id_b,
           'shared_known_sender:' || k1.email_normalized AS sig
    FROM global_booking_broker_known_senders k1
    INNER JOIN global_booking_broker_known_senders k2
      ON k1.global_broker_id < k2.global_broker_id
      AND k1.email_normalized = k2.email_normalized
      AND k1.is_active IS TRUE
      AND k2.is_active IS TRUE
    INNER JOIN global_booking_brokers b1 ON b1.id = k1.global_broker_id
    INNER JOIN global_booking_brokers b2 ON b2.id = k2.global_broker_id
      AND b1.merged_into_global_broker_id IS NULL
      AND b2.merged_into_global_broker_id IS NULL
    """
)


_ALIAS_SQL = text(
    """
    SELECT a1.global_broker_id AS id_a, a2.global_broker_id AS id_b,
           'shared_alias:' || a1.alias AS sig
    FROM global_booking_broker_aliases a1
    INNER JOIN global_booking_broker_aliases a2
      ON a1.global_broker_id < a2.global_broker_id
      AND a1.alias = a2.alias
      AND a1.is_active IS TRUE
      AND a2.is_active IS TRUE
    INNER JOIN global_booking_brokers b1 ON b1.id = a1.global_broker_id
    INNER JOIN global_booking_brokers b2 ON b2.id = a2.global_broker_id
      AND b1.merged_into_global_broker_id IS NULL
      AND b2.merged_into_global_broker_id IS NULL
    """
)


async def collect_duplicate_pairs(db: AsyncSession) -> dict[tuple[int, int], set[str]]:
    pairs: dict[tuple[int, int], set[str]] = {}
    res_mc = await db.execute(_MC_MATCH_SQL, {"sig": "shared_mc_number"})
    for id_a, id_b, sig in res_mc.all():
        add_signal(pairs, int(id_a), int(id_b), str(sig))
    res_dot = await db.execute(_DOT_MATCH_SQL, {"sig": "shared_dot_number"})
    for id_a, id_b, sig in res_dot.all():
        add_signal(pairs, int(id_a), int(id_b), str(sig))
    res_cvor = await db.execute(_CVOR_MATCH_SQL)
    for id_a, id_b, sig in res_cvor.all():
        add_signal(pairs, int(id_a), int(id_b), str(sig))

    for stmt in (_DOMAIN_SQL, _KNOWN_SQL, _ALIAS_SQL):
        res = await db.execute(stmt)
        for id_a, id_b, sig in res.all():
            add_signal(pairs, int(id_a), int(id_b), str(sig))
    return pairs


def signals_to_json(signals: set[str]) -> str:
    return json.dumps(sorted(signals))


def signals_from_json(raw: str | None) -> set[str]:
    if not raw or not str(raw).strip():
        return set()
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            return {str(x) for x in data}
    except json.JSONDecodeError:
        return set()
    return set()


@dataclass(frozen=True, slots=True)
class DuplicateRefreshResult:
    upserted_open: int
    updated_open_signals: int
    removed_stale_open: int
    touched_dismissed_or_ack: int


async def refresh_global_broker_duplicate_candidates(db: AsyncSession) -> DuplicateRefreshResult:
    """Recompute overlap pairs. Open rows not in the new set are removed. Reviews honor prior dispositions."""
    computed = await collect_duplicate_pairs(db)
    computed_set = frozenset(computed.keys())

    res = await db.execute(select(GlobalBookingBrokerDuplicateCandidate))
    existing_rows = list(res.scalars().all())
    existing_by_pair: dict[tuple[int, int], GlobalBookingBrokerDuplicateCandidate] = {
        (r.broker_id_low, r.broker_id_high): r for r in existing_rows
    }

    removed = 0
    upserted = 0
    updated_open = 0
    touched_closed = 0

    for row in existing_rows:
        if row.review_status != "open":
            continue
        key = (row.broker_id_low, row.broker_id_high)
        if key not in computed_set:
            await db.delete(row)
            removed += 1

    for pair, signals in computed.items():
        new_json = signals_to_json(signals)
        row = existing_by_pair.get(pair)
        if row is None:
            db.add(
                GlobalBookingBrokerDuplicateCandidate(
                    broker_id_low=pair[0],
                    broker_id_high=pair[1],
                    match_signals=new_json,
                    review_status="open",
                )
            )
            upserted += 1
            continue
        if row.review_status == "open":
            if row.match_signals != new_json:
                row.match_signals = new_json
                updated_open += 1
        else:
            if row.match_signals != new_json:
                row.match_signals = new_json
                touched_closed += 1

    await db.flush()
    return DuplicateRefreshResult(
        upserted_open=upserted,
        updated_open_signals=updated_open,
        removed_stale_open=removed,
        touched_dismissed_or_ack=touched_closed,
    )
