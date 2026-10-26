"""Rate-confirmation duplicate detection by exact PDF hash and broker load reference.

Broker load reference (broker_load_reference) is the broker's tender id on the RC.
It is not interchangeable with PO, BOL, or stop reference numbers in operational_references.
"""

from __future__ import annotations

import re
from hashlib import sha256
from typing import Any, Literal

from fastapi import HTTPException, status
from sqlalchemy import and_, case, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.load import Load, LoadStop
from app.models.trip import Trip, TripLoad

LOAD_RATE_CONFIRMATION_DUPLICATE = "LOAD_RATE_CONFIRMATION_DUPLICATE"
LOAD_RATE_CONFIRMATION_DUPLICATE_SOFT = "LOAD_RATE_CONFIRMATION_DUPLICATE_SOFT"

DuplicateSeverity = Literal["hard", "soft"]

_WS_DASH_RE = re.compile(r"[\s\-]+")
_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")


def normalize_rate_confirmation_reference(value: str | None) -> str | None:
    """Trim, case-fold, remove spaces and dashes, strip other punctuation for compare."""
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    folded = raw.lower()
    folded = _WS_DASH_RE.sub("", folded)
    folded = _NON_ALNUM_RE.sub("", folded)
    return folded or None


def _place(stop: LoadStop | None) -> str | None:
    if stop is None:
        return None
    value = ", ".join(p for p in (stop.city, stop.state_or_province) if p)
    return value or None


async def _trip_snapshot_for_load(
    db: AsyncSession, tenant_id: int, load_id: int
) -> tuple[int | None, str | None, int | None, int | None, int | None]:
    trip = await db.scalar(
        select(Trip)
        .join(
            TripLoad,
            and_(TripLoad.tenant_id == Trip.tenant_id, TripLoad.trip_id == Trip.id),
        )
        .where(
            Trip.tenant_id == tenant_id,
            TripLoad.tenant_id == tenant_id,
            TripLoad.load_id == load_id,
        )
        .order_by(
            case(
                (Trip.status == "in_progress", 0),
                (Trip.status == "assigned", 1),
                (Trip.status == "planned", 2),
                else_=3,
            ),
            Trip.updated_at.desc(),
        )
        .limit(1)
    )
    if trip is None:
        return None, None, None, None, None
    return (
        int(trip.id),
        str(trip.status),
        int(trip.driver_id) if trip.driver_id is not None else None,
        int(trip.truck_id) if trip.truck_id is not None else None,
        int(trip.trailer_id) if trip.trailer_id is not None else None,
    )


async def snapshot_existing_load(
    db: AsyncSession, tenant_id: int, load: Load
) -> dict[str, Any]:
    stops = (
        await db.execute(
            select(LoadStop)
            .where(LoadStop.tenant_id == tenant_id, LoadStop.load_id == load.id)
            .order_by(LoadStop.sequence.asc(), LoadStop.id.asc())
        )
    ).scalars().all()
    pickup = next((s for s in stops if (s.stop_type or "").upper() == "PICKUP"), None)
    delivery = next(
        (s for s in reversed(stops) if (s.stop_type or "").upper() in {"DROP", "DELIVERY"}),
        None,
    )
    trip_id, trip_status, driver_id, truck_id, trailer_id = await _trip_snapshot_for_load(
        db, tenant_id, int(load.id)
    )
    broker_name = load.broker_name_snapshot
    if broker_name is None and load.broker_id is not None:
        from app.models.broker import Broker

        broker = await db.scalar(
            select(Broker).where(Broker.tenant_id == tenant_id, Broker.id == load.broker_id)
        )
        if broker is not None:
            broker_name = broker.display_name or broker.legal_name or broker.name
    return {
        "load_id": int(load.id),
        "load_number": str(load.load_number),
        "broker_id": int(load.broker_id) if load.broker_id is not None else None,
        "broker_name": broker_name,
        "broker_load_reference": load.broker_load_reference,
        "load_status": str(load.status),
        "pickup": _place(pickup),
        "delivery": _place(delivery),
        "trip_id": trip_id,
        "trip_status": trip_status,
        "driver_id": driver_id,
        "truck_id": truck_id,
        "trailer_id": trailer_id,
    }


async def find_loads_by_normalized_broker_reference(
    db: AsyncSession,
    *,
    tenant_id: int,
    broker_load_reference: str | None,
    exclude_load_id: int | None = None,
    limit: int = 10,
) -> list[Load]:
    norm = normalize_rate_confirmation_reference(broker_load_reference)
    if not norm:
        return []
    # Compare in SQL using the same normalization rules (active loads only).
    pattern = norm
    stmt = (
        select(Load)
        .where(
            Load.tenant_id == tenant_id,
            func.lower(
                func.regexp_replace(
                    func.regexp_replace(func.trim(Load.broker_load_reference), r"[\s\-]+", "", "g"),
                    r"[^a-z0-9]+",
                    "",
                    "g",
                )
            )
            == pattern,
            func.coalesce(func.trim(Load.broker_load_reference), "") != "",
            Load.status != "cancelled",
        )
        .order_by(Load.id.desc())
        .limit(max(1, min(limit, 20)))
    )
    if exclude_load_id is not None and int(exclude_load_id) > 0:
        stmt = stmt.where(Load.id != int(exclude_load_id))
    result = await db.execute(stmt)
    return list(result.scalars().all())


def classify_broker_reference_duplicates(
    *,
    incoming_broker_id: int | None,
    matches: list[Load],
) -> tuple[DuplicateSeverity | None, list[Load]]:
    if not matches:
        return None, []
    if incoming_broker_id is not None:
        hard = [m for m in matches if m.broker_id is not None and int(m.broker_id) == int(incoming_broker_id)]
        if hard:
            return "hard", hard
    return "soft", matches


async def evaluate_broker_reference_duplicate(
    db: AsyncSession,
    *,
    tenant_id: int,
    broker_load_reference: str | None,
    broker_id: int | None,
    exclude_load_id: int | None = None,
) -> tuple[DuplicateSeverity | None, list[dict[str, Any]]]:
    loads = await find_loads_by_normalized_broker_reference(
        db,
        tenant_id=tenant_id,
        broker_load_reference=broker_load_reference,
        exclude_load_id=exclude_load_id,
    )
    severity, matched = classify_broker_reference_duplicates(
        incoming_broker_id=broker_id, matches=loads
    )
    if severity is None:
        return None, []
    snapshots = [await snapshot_existing_load(db, tenant_id, row) for row in matched]
    return severity, snapshots


def http_exception_for_duplicate(
    *,
    severity: DuplicateSeverity,
    candidates: list[dict[str, Any]],
    acknowledge_soft_required: bool = False,
) -> HTTPException:
    primary = candidates[0] if candidates else {}
    code = (
        LOAD_RATE_CONFIRMATION_DUPLICATE
        if severity == "hard"
        else LOAD_RATE_CONFIRMATION_DUPLICATE_SOFT
    )
    detail: dict[str, Any] = {
        "code": code,
        "severity": severity,
        "message": (
            "This load already exists."
            if severity == "hard"
            else "Another load uses this broker reference number."
        ),
        "existing_load_id": primary.get("load_id"),
        "load_number": primary.get("load_number"),
        "load_status": primary.get("load_status"),
        "broker_name": primary.get("broker_name"),
        "broker_load_reference": primary.get("broker_load_reference"),
        "candidates": candidates,
        "match_basis": "broker_load_reference",
    }
    if acknowledge_soft_required:
        detail["acknowledge_soft_rate_confirmation_duplicate_required"] = True
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)


async def advisory_lock_broker_reference_promote(
    db: AsyncSession,
    *,
    tenant_id: int,
    broker_id: int | None,
    broker_load_reference: str | None,
) -> None:
    """Serialize concurrent promotes that would create the same hard duplicate."""
    norm = normalize_rate_confirmation_reference(broker_load_reference)
    if not norm or broker_id is None:
        return
    key = int(sha256(f"{tenant_id}:{broker_id}:{norm}".encode()).hexdigest()[:15], 16)
    await db.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": key})


async def assert_promote_rate_confirmation_not_duplicate(
    db: AsyncSession,
    *,
    tenant_id: int,
    broker_load_reference: str | None,
    broker_id: int | None,
    acknowledge_soft: bool,
) -> None:
    await advisory_lock_broker_reference_promote(
        db,
        tenant_id=tenant_id,
        broker_id=broker_id,
        broker_load_reference=broker_load_reference,
    )
    severity, candidates = await evaluate_broker_reference_duplicate(
        db,
        tenant_id=tenant_id,
        broker_load_reference=broker_load_reference,
        broker_id=broker_id,
        exclude_load_id=None,
    )
    if severity is None:
        return
    if severity == "hard":
        raise http_exception_for_duplicate(severity="hard", candidates=candidates)
    if not acknowledge_soft:
        raise http_exception_for_duplicate(
            severity="soft",
            candidates=candidates,
            acknowledge_soft_required=True,
        )


def apply_broker_reference_duplicate_to_parse_context(
    context: dict[str, Any],
    *,
    severity: DuplicateSeverity,
    candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    out = dict(context)
    out["duplicate_match_basis"] = "broker_load_reference"
    out["duplicate_severity"] = severity
    out["duplicate_candidates"] = candidates
    if severity == "hard":
        out["semantic_outcome"] = "blocked_duplicate_review"
        out["duplicate_code"] = LOAD_RATE_CONFIRMATION_DUPLICATE
    else:
        out["rate_confirmation_duplicate_warning"] = True
        out["duplicate_code"] = LOAD_RATE_CONFIRMATION_DUPLICATE_SOFT
    return out
