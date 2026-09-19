"""Segment 3 historical resolution for Fuel/Card.

Resolve truck, ownership/payee, and card/account assignment at the
transaction's documented time. Never fall back to current fleet assignment.

Ambiguous or missing matches are REVIEW. This module does not write settlement
or mutate finalized financial history.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from typing import Any, Iterable, Mapping, Sequence

STATUS_RESOLVED = "RESOLVED"
STATUS_REVIEW_ZERO_MATCH = "REVIEW_ZERO_MATCH"
STATUS_REVIEW_MULTIPLE_MATCH = "REVIEW_MULTIPLE_MATCH"
STATUS_REVIEW_MISSING_INPUT = "REVIEW_MISSING_INPUT"
STATUS_REVIEW_MISSING_POINT_IN_TIME = "REVIEW_MISSING_POINT_IN_TIME"

# Overlap write-path validation (service boundary; no btree_gist exclusion).
# Resolver never silently picks one of several covering rows.
HISTORY_KIND_UNIT = "unit_number"
HISTORY_KIND_OWNERSHIP = "ownership"
HISTORY_KIND_CARD = "card_account"


class FuelHistoryOverlapError(ValueError):
    """Raised when proposed effective-dated history would overlap an existing row."""


def _as_aware(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        raise ValueError("History effective_from/effective_to must be timezone-aware")
    return dt


def intervals_overlap(
    a_from: datetime,
    a_to: datetime | None,
    b_from: datetime,
    b_to: datetime | None,
) -> bool:
    """True if half-open intervals [a_from, a_to) and [b_from, b_to) intersect.

    Adjacent periods that meet at a boundary (a_to == b_from) do not overlap.
    """
    a_start, b_start = _as_aware(a_from), _as_aware(b_from)
    a_end = None if a_to is None else _as_aware(a_to)
    b_end = None if b_to is None else _as_aware(b_to)
    if a_end is not None and a_end <= a_start:
        raise ValueError("effective_to must be strictly after effective_from when set")
    if b_end is not None and b_end <= b_start:
        raise ValueError("effective_to must be strictly after effective_from when set")
    if a_end is not None and a_end <= b_start:
        return False
    if b_end is not None and b_end <= a_start:
        return False
    return True


def _business_key(kind: str, row: Mapping[str, Any]) -> tuple[Any, ...]:
    if kind == HISTORY_KIND_UNIT:
        # Uniqueness expected: one truck per unit at a time, and one unit per truck.
        # Callers validate both key spaces separately.
        raise ValueError("Use unit_number or truck_id key helpers for unit history")
    if kind == HISTORY_KIND_OWNERSHIP:
        return (int(row["truck_id"]),)
    if kind == HISTORY_KIND_CARD:
        account = row.get("account_reference")
        account = None if account is None else str(account).strip() or None
        return (
            str(row["provider_code"]).strip().upper(),
            str(row["card_or_account_id"]).strip(),
            account,
        )
    raise ValueError(f"Unknown history kind: {kind}")


def find_overlapping_history_rows(
    rows: Sequence[Mapping[str, Any]],
    *,
    key_fn,
) -> list[tuple[Mapping[str, Any], Mapping[str, Any]]]:
    """Return overlapping pairs that share the same business key."""
    by_key: dict[tuple[Any, ...], list[Mapping[str, Any]]] = {}
    for row in rows:
        by_key.setdefault(key_fn(row), []).append(row)
    overlaps: list[tuple[Mapping[str, Any], Mapping[str, Any]]] = []
    for group in by_key.values():
        for i, a in enumerate(group):
            for b in group[i + 1 :]:
                if intervals_overlap(
                    a["effective_from"],
                    a.get("effective_to"),
                    b["effective_from"],
                    b.get("effective_to"),
                ):
                    overlaps.append((a, b))
    return overlaps


def assert_history_rows_have_no_overlap(
    rows: Sequence[Mapping[str, Any]],
    *,
    kind: str,
) -> None:
    """Write-path / fixture validation. Overlaps are rejected, never auto-merged."""
    if kind == HISTORY_KIND_UNIT:
        unit_overlaps = find_overlapping_history_rows(
            rows, key_fn=lambda r: (str(r["unit_number"]).strip(),)
        )
        if unit_overlaps:
            raise FuelHistoryOverlapError(
                "Overlapping truck_unit_number_history for the same unit_number"
            )
        truck_overlaps = find_overlapping_history_rows(
            rows, key_fn=lambda r: (int(r["truck_id"]),)
        )
        if truck_overlaps:
            raise FuelHistoryOverlapError(
                "Overlapping truck_unit_number_history for the same truck_id"
            )
        return
    if kind == HISTORY_KIND_OWNERSHIP:
        overlaps = find_overlapping_history_rows(
            rows, key_fn=lambda r: _business_key(HISTORY_KIND_OWNERSHIP, r)
        )
        if overlaps:
            raise FuelHistoryOverlapError(
                "Overlapping truck_ownership_history for the same truck_id"
            )
        return
    if kind == HISTORY_KIND_CARD:
        overlaps = find_overlapping_history_rows(
            rows, key_fn=lambda r: _business_key(HISTORY_KIND_CARD, r)
        )
        if overlaps:
            raise FuelHistoryOverlapError(
                "Overlapping fuel_card_account_assignments for the same "
                "provider/card/(account) key"
            )
        return
    raise ValueError(f"Unknown history kind: {kind}")


def assert_proposed_history_row_no_overlap(
    *,
    kind: str,
    proposed: Mapping[str, Any],
    existing_rows: Sequence[Mapping[str, Any]],
) -> None:
    """Reject a proposed write that would overlap an existing same-key interval."""
    combined = [dict(r) for r in existing_rows] + [dict(proposed)]
    assert_history_rows_have_no_overlap(combined, kind=kind)


@dataclass(frozen=True)
class HistoricalResolution:
    status: str
    matched_ids: tuple[int, ...] = ()
    value: dict[str, Any] | None = None
    review_reason: str | None = None

    @property
    def requires_review(self) -> bool:
        return self.status != STATUS_RESOLVED


def resolution_point_in_time(
    *,
    transaction_datetime: datetime | None,
    transaction_date: date | None,
) -> datetime | None:
    """Point-in-time used for historical lookup.

    Prefer timezone-aware transaction_datetime. When only a provider/source-local
    date exists, use that calendar date at 00:00:00 UTC as a date-level probe —
    not a claim that the event occurred at UTC midnight, only a deterministic
    date-bounded lookup key. Never invent a zone for local-time-without-zone.
    """
    if transaction_datetime is not None:
        if transaction_datetime.tzinfo is None:
            raise ValueError(
                "transaction_datetime must be timezone-aware for historical resolution"
            )
        return transaction_datetime
    if transaction_date is not None:
        return datetime.combine(transaction_date, time.min, tzinfo=timezone.utc)
    return None


def interval_covers(row: Mapping[str, Any], at: datetime) -> bool:
    """Half-open [effective_from, effective_to)."""
    start = _as_aware(row["effective_from"])
    end = row.get("effective_to")
    if at < start:
        return False
    if end is None:
        return True
    return at < _as_aware(end)


def _filter_covering(rows: Iterable[Mapping[str, Any]], at: datetime) -> list[Mapping[str, Any]]:
    return [r for r in rows if interval_covers(r, at)]


def _outcome_from_matches(
    matches: Sequence[Mapping[str, Any]],
    *,
    id_key: str,
    value_builder,
) -> HistoricalResolution:
    if len(matches) == 0:
        return HistoricalResolution(
            status=STATUS_REVIEW_ZERO_MATCH,
            review_reason=STATUS_REVIEW_ZERO_MATCH,
        )
    if len(matches) > 1:
        ids = tuple(int(m[id_key]) for m in matches)
        return HistoricalResolution(
            status=STATUS_REVIEW_MULTIPLE_MATCH,
            matched_ids=ids,
            review_reason=STATUS_REVIEW_MULTIPLE_MATCH,
        )
    only = matches[0]
    return HistoricalResolution(
        status=STATUS_RESOLVED,
        matched_ids=(int(only[id_key]),),
        value=value_builder(only),
    )


def resolve_truck_from_unit_history(
    *,
    unit_number_snapshot: str | None,
    at: datetime | None,
    history_rows: Sequence[Mapping[str, Any]],
    current_trucks_by_unit: Mapping[str, int] | None = None,
) -> HistoricalResolution:
    """unit_number_snapshot + point-in-time -> exactly one truck_id.

    `current_trucks_by_unit` is accepted only to prove it is ignored. Never use
    today's trucks.unit_number as a fallback.
    """
    del current_trucks_by_unit  # explicit: no current-truck fallback
    if unit_number_snapshot is None or str(unit_number_snapshot).strip() == "":
        return HistoricalResolution(
            status=STATUS_REVIEW_MISSING_INPUT,
            review_reason="MISSING_UNIT_NUMBER_SNAPSHOT",
        )
    if at is None:
        return HistoricalResolution(
            status=STATUS_REVIEW_MISSING_POINT_IN_TIME,
            review_reason=STATUS_REVIEW_MISSING_POINT_IN_TIME,
        )
    needle = str(unit_number_snapshot).strip()
    covering = [
        r
        for r in _filter_covering(history_rows, at)
        if str(r.get("unit_number", "")).strip() == needle
    ]
    return _outcome_from_matches(
        covering,
        id_key="truck_id",
        value_builder=lambda r: {
            "truck_id": int(r["truck_id"]),
            "unit_number": str(r["unit_number"]),
            "history_id": int(r["id"]) if r.get("id") is not None else None,
        },
    )


def resolve_ownership_at(
    *,
    truck_id: int | None,
    at: datetime | None,
    history_rows: Sequence[Mapping[str, Any]],
    current_ownership: Mapping[str, Any] | None = None,
) -> HistoricalResolution:
    """truck_id + point-in-time -> ownership_type / owner_operator_payee_id.

    Current trucks.ownership_type is ignored (no fallback).
    """
    del current_ownership
    if truck_id is None:
        return HistoricalResolution(
            status=STATUS_REVIEW_MISSING_INPUT,
            review_reason="MISSING_TRUCK_ID",
        )
    if at is None:
        return HistoricalResolution(
            status=STATUS_REVIEW_MISSING_POINT_IN_TIME,
            review_reason=STATUS_REVIEW_MISSING_POINT_IN_TIME,
        )
    covering = [
        r for r in _filter_covering(history_rows, at) if int(r["truck_id"]) == int(truck_id)
    ]
    return _outcome_from_matches(
        covering,
        id_key="id",
        value_builder=lambda r: {
            "truck_id": int(r["truck_id"]),
            "ownership_type": str(r["ownership_type"]),
            "owner_operator_payee_id": (
                None
                if r.get("owner_operator_payee_id") is None
                else int(r["owner_operator_payee_id"])
            ),
            "history_id": int(r["id"]),
        },
    )


def resolve_card_account_assignment(
    *,
    provider_code: str | None,
    card_or_account_id: str | None,
    account_reference: str | None,
    at: datetime | None,
    assignment_rows: Sequence[Mapping[str, Any]],
    current_assignment: Mapping[str, Any] | None = None,
) -> HistoricalResolution:
    """Card/account snapshot + point-in-time -> historical truck/driver/payee links.

    Never falls back to the current assignment.
    """
    del current_assignment
    if provider_code is None or str(provider_code).strip() == "":
        return HistoricalResolution(
            status=STATUS_REVIEW_MISSING_INPUT,
            review_reason="MISSING_PROVIDER_CODE",
        )
    if card_or_account_id is None or str(card_or_account_id).strip() == "":
        return HistoricalResolution(
            status=STATUS_REVIEW_MISSING_INPUT,
            review_reason="MISSING_CARD_OR_ACCOUNT_ID",
        )
    if at is None:
        return HistoricalResolution(
            status=STATUS_REVIEW_MISSING_POINT_IN_TIME,
            review_reason=STATUS_REVIEW_MISSING_POINT_IN_TIME,
        )
    provider = str(provider_code).strip().upper()
    card = str(card_or_account_id).strip()
    account = None if account_reference is None else str(account_reference).strip() or None

    covering = []
    for r in _filter_covering(assignment_rows, at):
        if str(r.get("provider_code", "")).strip().upper() != provider:
            continue
        if str(r.get("card_or_account_id", "")).strip() != card:
            continue
        row_account = r.get("account_reference")
        row_account = None if row_account is None else str(row_account).strip() or None
        if account is not None and row_account is not None and account != row_account:
            continue
        covering.append(r)

    return _outcome_from_matches(
        covering,
        id_key="id",
        value_builder=lambda r: {
            "assignment_id": int(r["id"]),
            "truck_id": None if r.get("truck_id") is None else int(r["truck_id"]),
            "driver_id": None if r.get("driver_id") is None else int(r["driver_id"]),
            "owner_operator_payee_id": (
                None
                if r.get("owner_operator_payee_id") is None
                else int(r["owner_operator_payee_id"])
            ),
            "provider_code": str(r["provider_code"]),
            "card_or_account_id": str(r["card_or_account_id"]),
            "account_reference": r.get("account_reference"),
        },
    )


def resolve_fuel_transaction_historical_links(
    *,
    unit_number_snapshot: str | None,
    card_or_account_id: str | None,
    source_vendor: str | None,
    account_reference: str | None,
    transaction_datetime: datetime | None,
    transaction_date: date | None,
    unit_history_rows: Sequence[Mapping[str, Any]],
    ownership_history_rows: Sequence[Mapping[str, Any]],
    card_assignment_rows: Sequence[Mapping[str, Any]],
    current_trucks_by_unit: Mapping[str, int] | None = None,
    current_ownership: Mapping[str, Any] | None = None,
    current_card_assignment: Mapping[str, Any] | None = None,
) -> dict[str, HistoricalResolution]:
    """Resolve truck, ownership, and card assignment for one Fuel transaction."""
    at = resolution_point_in_time(
        transaction_datetime=transaction_datetime,
        transaction_date=transaction_date,
    )
    truck = resolve_truck_from_unit_history(
        unit_number_snapshot=unit_number_snapshot,
        at=at,
        history_rows=unit_history_rows,
        current_trucks_by_unit=current_trucks_by_unit,
    )
    truck_id = None if truck.value is None else truck.value.get("truck_id")
    ownership = resolve_ownership_at(
        truck_id=truck_id,
        at=at,
        history_rows=ownership_history_rows,
        current_ownership=current_ownership,
    )
    card = resolve_card_account_assignment(
        provider_code=source_vendor,
        card_or_account_id=card_or_account_id,
        account_reference=account_reference,
        at=at,
        assignment_rows=card_assignment_rows,
        current_assignment=current_card_assignment,
    )
    return {
        "point_in_time": HistoricalResolution(
            status=STATUS_RESOLVED if at is not None else STATUS_REVIEW_MISSING_POINT_IN_TIME,
            value={"at": at.isoformat() if at is not None else None},
            review_reason=None if at is not None else STATUS_REVIEW_MISSING_POINT_IN_TIME,
        ),
        "truck": truck,
        "ownership": ownership,
        "card_assignment": card,
    }
