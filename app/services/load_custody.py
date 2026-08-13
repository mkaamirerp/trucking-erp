"""Load custody reads + bootstrap (Slice 1 foundation — no operational custody mutations)."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import and_, bindparam, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.custody import (
    CUSTODY_EVENT_BOOTSTRAP,
    CUSTODY_OWNER_TRIP,
    CUSTODY_PLACEMENT_ON_TRAILER,
    CUSTODY_PLACEMENT_UNKNOWN,
    CUSTODY_SOURCE_BOOTSTRAP,
)
from app.constants.trip_dispatch import TRIP_LOAD_STATUS_WITHIN_ACTIVE
from app.models.load import Load
from app.models.load_custody_event import LoadCustodyEvent
from app.models.terminal import Terminal
from app.models.trip import Trip, TripLoad
from app.schemas.custody import (
    LoadCustodyEventListResponse,
    LoadCustodyEventResponse,
    LoadCustodySnapshotResponse,
    TerminalCreate,
    TerminalListResponse,
    TerminalResponse,
    TerminalUpdate,
)

# Audited category-A pointer repairs for tenant_demo (tenant_id=53). load_id -> (from, to).
TENANT_DEMO_AUDITED_POINTER_REPAIRS: dict[int, tuple[int | None, int | None]] = {
    523: (79, None),
    528: (None, 77),
    529: (None, 77),
    563: (106, None),
    577: (116, None),
    578: (110, None),
}


def _trip_load_open_active_clause():
    return and_(
        TripLoad.status_within_trip == TRIP_LOAD_STATUS_WITHIN_ACTIVE,
        TripLoad.completed_at.is_(None),
        TripLoad.removed_at.is_(None),
    )


async def get_load_custody_snapshot(
    db: AsyncSession, tenant_id: int, load_id: int
) -> LoadCustodySnapshotResponse:
    load = await db.scalar(select(Load).where(Load.tenant_id == tenant_id, Load.id == load_id))
    if load is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Load not found")
    return LoadCustodySnapshotResponse(
        load_id=int(load.id),
        custody_owner=load.custody_owner,
        custody_trip_id=load.custody_trip_id,
        custody_terminal_id=load.custody_terminal_id,
        custody_placement=load.custody_placement,
        custody_trailer_id=load.custody_trailer_id,
        custody_since_at=load.custody_since_at,
        last_custody_event_id=load.last_custody_event_id,
    )


async def list_load_custody_events(
    db: AsyncSession,
    tenant_id: int,
    load_id: int,
    *,
    limit: int = 100,
    offset: int = 0,
) -> LoadCustodyEventListResponse:
    load = await db.scalar(select(Load).where(Load.tenant_id == tenant_id, Load.id == load_id))
    if load is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Load not found")

    total = int(
        await db.scalar(
            select(func.count())
            .select_from(LoadCustodyEvent)
            .where(
                LoadCustodyEvent.tenant_id == tenant_id,
                LoadCustodyEvent.load_id == load_id,
            )
        )
        or 0
    )
    rows = (
        await db.scalars(
            select(LoadCustodyEvent)
            .where(
                LoadCustodyEvent.tenant_id == tenant_id,
                LoadCustodyEvent.load_id == load_id,
            )
            .order_by(LoadCustodyEvent.occurred_at.asc(), LoadCustodyEvent.id.asc())
            .offset(offset)
            .limit(limit)
        )
    ).all()
    return LoadCustodyEventListResponse(
        items=[LoadCustodyEventResponse.model_validate(r) for r in rows],
        total=total,
    )


async def list_terminals(
    db: AsyncSession,
    tenant_id: int,
    *,
    active_only: bool = True,
) -> TerminalListResponse:
    stmt = select(Terminal).where(Terminal.tenant_id == tenant_id)
    if active_only:
        stmt = stmt.where(Terminal.is_active.is_(True))
    stmt = stmt.order_by(Terminal.name.asc())
    rows = (await db.scalars(stmt)).all()
    return TerminalListResponse(items=[TerminalResponse.model_validate(r) for r in rows])


async def get_terminal(db: AsyncSession, tenant_id: int, terminal_id: int) -> TerminalResponse:
    row = await db.scalar(
        select(Terminal).where(Terminal.tenant_id == tenant_id, Terminal.id == terminal_id)
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Terminal not found")
    return TerminalResponse.model_validate(row)


async def create_terminal(
    db: AsyncSession, tenant_id: int, body: TerminalCreate
) -> TerminalResponse:
    row = Terminal(
        tenant_id=tenant_id,
        name=body.name.strip(),
        street=body.street,
        city=body.city,
        state_or_province=body.state_or_province,
        postal_code=body.postal_code,
        country=body.country,
        is_active=body.is_active,
    )
    db.add(row)
    try:
        await db.flush()
    except IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"detail": "Terminal name already exists for this tenant", "code": "TERMINAL_NAME_CONFLICT"},
        ) from exc
    await db.refresh(row)
    return TerminalResponse.model_validate(row)


async def update_terminal(
    db: AsyncSession, tenant_id: int, terminal_id: int, body: TerminalUpdate
) -> TerminalResponse:
    row = await db.scalar(
        select(Terminal)
        .where(Terminal.tenant_id == tenant_id, Terminal.id == terminal_id)
        .with_for_update()
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Terminal not found")
    data = body.model_dump(exclude_unset=True)
    if "name" in data and data["name"] is not None:
        data["name"] = str(data["name"]).strip()
    for key, value in data.items():
        setattr(row, key, value)
    try:
        await db.flush()
    except IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"detail": "Terminal name already exists for this tenant", "code": "TERMINAL_NAME_CONFLICT"},
        ) from exc
    await db.refresh(row)
    return TerminalResponse.model_validate(row)


class CustodyBootstrapAnomaly(Exception):
    """Raised when bootstrap preflight finds data that must not be silently fixed."""

    def __init__(self, code: str, detail: str, samples: list[dict] | None = None):
        self.code = code
        self.detail = detail
        self.samples = samples or []
        super().__init__(detail)


async def preflight_custody_bootstrap_anomalies(
    db: AsyncSession,
    tenant_id: int | None = None,
    *,
    load_ids: list[int] | None = None,
    check_active_trip_id_mismatch: bool = True,
) -> None:
    """STOP on anomalous ACTIVE membership / pointer / trip-status rows. Does not mutate."""
    params: dict = {}
    tenant_filter_tl = ""
    tenant_filter_l = ""
    load_filter_tl = ""
    load_filter_l = ""
    if tenant_id is not None:
        params["tenant_id"] = tenant_id
        tenant_filter_tl = "AND tl.tenant_id = :tenant_id"
        tenant_filter_l = "AND l.tenant_id = :tenant_id"
    if load_ids is not None:
        if not load_ids:
            return
        params["load_ids"] = list(load_ids)
        load_filter_tl = "AND tl.load_id IN :load_ids"
        load_filter_l = "AND l.id IN :load_ids"

    def _exec(sql: str):
        stmt = text(sql)
        if load_ids is not None:
            stmt = stmt.bindparams(bindparam("load_ids", expanding=True))
        return db.execute(stmt, params)

    # >1 OPEN ACTIVE per load
    multi = (
        await _exec(
            f"""
                SELECT tl.tenant_id, tl.load_id, count(*)::int AS n
                FROM trip_loads tl
                WHERE tl.status_within_trip = 'active'
                  AND tl.completed_at IS NULL
                  AND tl.removed_at IS NULL
                  {tenant_filter_tl}
                  {load_filter_tl}
                GROUP BY tl.tenant_id, tl.load_id
                HAVING count(*) > 1
                ORDER BY tl.tenant_id, tl.load_id
                LIMIT 20
                """
        )
    ).mappings().all()
    if multi:
        raise CustodyBootstrapAnomaly(
            "MULTIPLE_OPEN_ACTIVE_MEMBERSHIPS",
            "Bootstrap stopped: more than one open ACTIVE TripLoad per Load",
            [dict(r) for r in multi],
        )

    if check_active_trip_id_mismatch:
        # active_trip_id mismatch vs unique OPEN ACTIVE
        mismatch = (
            await _exec(
                f"""
                WITH active_one AS (
                  SELECT tl.tenant_id, tl.load_id, tl.trip_id
                  FROM trip_loads tl
                  WHERE tl.status_within_trip = 'active'
                    AND tl.completed_at IS NULL
                    AND tl.removed_at IS NULL
                    {tenant_filter_tl}
                    {load_filter_tl}
                )
                SELECT l.tenant_id, l.id AS load_id, l.active_trip_id, a.trip_id AS open_active_trip_id
                FROM loads l
                LEFT JOIN active_one a
                  ON a.tenant_id = l.tenant_id AND a.load_id = l.id
                WHERE (
                  (a.trip_id IS NOT NULL AND (l.active_trip_id IS DISTINCT FROM a.trip_id))
                  OR (a.trip_id IS NULL AND l.active_trip_id IS NOT NULL)
                )
                {tenant_filter_l}
                {load_filter_l}
                ORDER BY l.tenant_id, l.id
                LIMIT 20
                """
            )
        ).mappings().all()
        if mismatch:
            raise CustodyBootstrapAnomaly(
                "ACTIVE_TRIP_ID_MISMATCH",
                "Bootstrap stopped: loads.active_trip_id does not match open ACTIVE TripLoad",
                [dict(r) for r in mismatch],
            )

    # OPEN ACTIVE on completed/cancelled trip
    bad_trip = (
        await _exec(
            f"""
                SELECT tl.tenant_id, tl.load_id, tl.trip_id, t.status AS trip_status
                FROM trip_loads tl
                JOIN trips t ON t.id = tl.trip_id
                WHERE tl.status_within_trip = 'active'
                  AND tl.completed_at IS NULL
                  AND tl.removed_at IS NULL
                  AND t.status IN ('completed', 'cancelled')
                  {tenant_filter_tl}
                  {load_filter_tl}
                ORDER BY tl.tenant_id, tl.load_id
                LIMIT 20
                """
        )
    ).mappings().all()
    if bad_trip:
        raise CustodyBootstrapAnomaly(
            "ACTIVE_MEMBERSHIP_ON_TERMINAL_TRIP",
            "Bootstrap stopped: open ACTIVE TripLoad on completed/cancelled Trip",
            [dict(r) for r in bad_trip],
        )


async def bootstrap_load_custody_for_tenant(
    db: AsyncSession,
    tenant_id: int,
    *,
    dry_run: bool = False,
    load_ids: list[int] | None = None,
) -> dict:
    """Create custody_bootstrap events for Loads with exactly one OPEN ACTIVE TripLoad.

    Idempotent: skips Loads that already have custody_owner=trip matching the ACTIVE trip
    and a prior custody_bootstrap event (or already-matching snapshot with last_custody_event_id).
    """
    await preflight_custody_bootstrap_anomalies(db, tenant_id=tenant_id, load_ids=load_ids)

    now = datetime.now(timezone.utc)
    stmt = (
        select(TripLoad, Trip)
        .join(Trip, Trip.id == TripLoad.trip_id)
        .where(
            TripLoad.tenant_id == tenant_id,
            _trip_load_open_active_clause(),
        )
        .order_by(TripLoad.load_id.asc())
    )
    if load_ids is not None:
        stmt = stmt.where(TripLoad.load_id.in_(load_ids))
    active_rows = (await db.execute(stmt)).all()

    created = 0
    skipped = 0
    for tl, trip in active_rows:
        load = await db.scalar(
            select(Load).where(Load.tenant_id == tenant_id, Load.id == int(tl.load_id))
        )
        if load is None:
            continue

        # Idempotent skip
        if (
            load.custody_owner == CUSTODY_OWNER_TRIP
            and load.custody_trip_id == int(trip.id)
            and load.last_custody_event_id is not None
        ):
            skipped += 1
            continue

        existing_bootstrap = await db.scalar(
            select(LoadCustodyEvent.id).where(
                LoadCustodyEvent.tenant_id == tenant_id,
                LoadCustodyEvent.load_id == int(tl.load_id),
                LoadCustodyEvent.event_type == CUSTODY_EVENT_BOOTSTRAP,
                LoadCustodyEvent.trip_id == int(trip.id),
            )
        )
        if existing_bootstrap is not None and load.custody_owner == CUSTODY_OWNER_TRIP:
            skipped += 1
            continue

        placement = (
            CUSTODY_PLACEMENT_ON_TRAILER
            if trip.trailer_id is not None
            else CUSTODY_PLACEMENT_UNKNOWN
        )
        trailer_id = int(trip.trailer_id) if trip.trailer_id is not None else None

        if dry_run:
            created += 1
            continue

        ev = LoadCustodyEvent(
            tenant_id=tenant_id,
            load_id=int(tl.load_id),
            event_type=CUSTODY_EVENT_BOOTSTRAP,
            occurred_at=now,
            recorded_at=now,
            custody_owner_after=CUSTODY_OWNER_TRIP,
            placement_after=placement,
            trip_id=int(trip.id),
            terminal_id=None,
            trailer_id=trailer_id,
            actor_user_id=None,
            source=CUSTODY_SOURCE_BOOTSTRAP,
            notes="Custody system initialized while this Trip was ACTIVE (not a historical pickup).",
            idempotency_key=f"bootstrap:trip:{int(trip.id)}:load:{int(tl.load_id)}",
        )
        db.add(ev)
        await db.flush()

        load.custody_owner = CUSTODY_OWNER_TRIP
        load.custody_trip_id = int(trip.id)
        load.custody_terminal_id = None
        load.custody_placement = placement
        load.custody_trailer_id = trailer_id
        load.custody_since_at = now
        load.last_custody_event_id = int(ev.id)
        created += 1

    if not dry_run:
        await db.flush()

    return {
        "tenant_id": tenant_id,
        "dry_run": dry_run,
        "bootstrapped": created,
        "skipped_idempotent": skipped,
        "active_memberships_seen": len(active_rows),
    }


async def _open_active_trip_ids_for_load(
    db: AsyncSession, tenant_id: int, load_id: int
) -> list[int]:
    rows = (
        await db.scalars(
            select(TripLoad.trip_id)
            .where(
                TripLoad.tenant_id == tenant_id,
                TripLoad.load_id == load_id,
                _trip_load_open_active_clause(),
            )
            .order_by(TripLoad.id.asc())
        )
    ).all()
    return [int(x) for x in rows]


async def list_active_trip_id_mismatches(db: AsyncSession, tenant_id: int) -> list[dict]:
    """Return pointer mismatches (same predicate as bootstrap preflight)."""
    rows = (
        await db.execute(
            text(
                """
                WITH active_one AS (
                  SELECT tl.tenant_id, tl.load_id, tl.trip_id,
                         count(*) OVER (PARTITION BY tl.tenant_id, tl.load_id) AS open_active_n
                  FROM trip_loads tl
                  WHERE tl.status_within_trip = 'active'
                    AND tl.completed_at IS NULL
                    AND tl.removed_at IS NULL
                    AND tl.tenant_id = :tenant_id
                )
                SELECT l.id AS load_id,
                       l.active_trip_id AS current_active_trip_id,
                       a.trip_id AS open_active_trip_id,
                       COALESCE(a.open_active_n, 0)::int AS open_active_n
                FROM loads l
                LEFT JOIN active_one a
                  ON a.tenant_id = l.tenant_id AND a.load_id = l.id
                WHERE l.tenant_id = :tenant_id
                  AND (
                    (a.trip_id IS NOT NULL AND (l.active_trip_id IS DISTINCT FROM a.trip_id))
                    OR (a.trip_id IS NULL AND l.active_trip_id IS NOT NULL)
                  )
                ORDER BY l.id
                """
            ),
            {"tenant_id": tenant_id},
        )
    ).mappings().all()
    return [dict(r) for r in rows]


async def repair_load_active_trip_pointers(
    db: AsyncSession,
    tenant_id: int,
    *,
    dry_run: bool = False,
    expected_repairs: dict[int, tuple[int | None, int | None]] | None = None,
) -> dict:
    """Recompute loads.active_trip_id from unique OPEN ACTIVE TripLoad only.

    Mutates only active_trip_id (ORM may bump updated_at). Does not touch TripLoad,
    Trip, Load.status, current_location, or legacy dispatch fields.
    """
    await preflight_custody_bootstrap_anomalies(
        db, tenant_id=tenant_id, check_active_trip_id_mismatch=False
    )

    mismatches = await list_active_trip_id_mismatches(db, tenant_id)
    plan: list[dict] = []
    for row in mismatches:
        load_id = int(row["load_id"])
        current = row["current_active_trip_id"]
        current_i = int(current) if current is not None else None
        open_n = int(row["open_active_n"] or 0)
        if open_n > 1:
            raise CustodyBootstrapAnomaly(
                "MULTIPLE_OPEN_ACTIVE_MEMBERSHIPS",
                "Repair stopped: more than one open ACTIVE TripLoad per Load",
                [row],
            )
        target = int(row["open_active_trip_id"]) if row["open_active_trip_id"] is not None else None
        # Defensive recompute under lock later; here build plan for audit gate
        plan.append(
            {
                "load_id": load_id,
                "from_active_trip_id": current_i,
                "to_active_trip_id": target,
            }
        )

    if expected_repairs is not None:
        expected_norm = {
            int(lid): (frm, to) for lid, (frm, to) in expected_repairs.items()
        }
        actual_norm = {
            p["load_id"]: (p["from_active_trip_id"], p["to_active_trip_id"]) for p in plan
        }
        if actual_norm != expected_norm:
            raise CustodyBootstrapAnomaly(
                "POINTER_REPAIR_PLAN_MISMATCH",
                "Repair stopped: computed plan does not match audited category-A set",
                [
                    {
                        "expected": {
                            str(k): {"from": v[0], "to": v[1]} for k, v in sorted(expected_norm.items())
                        },
                        "actual": {
                            str(k): {"from": v[0], "to": v[1]} for k, v in sorted(actual_norm.items())
                        },
                    }
                ],
            )

    applied: list[dict] = []
    if dry_run:
        return {
            "tenant_id": tenant_id,
            "dry_run": True,
            "repairs": plan,
            "repaired_count": len(plan),
        }

    for p in plan:
        load_id = int(p["load_id"])
        load = await db.scalar(
            select(Load)
            .where(Load.tenant_id == tenant_id, Load.id == load_id)
            .with_for_update()
        )
        if load is None:
            raise CustodyBootstrapAnomaly(
                "LOAD_NOT_FOUND",
                f"Repair stopped: load {load_id} missing",
                [{"load_id": load_id}],
            )
        before = int(load.active_trip_id) if load.active_trip_id is not None else None
        actives = await _open_active_trip_ids_for_load(db, tenant_id, load_id)
        if len(actives) > 1:
            raise CustodyBootstrapAnomaly(
                "MULTIPLE_OPEN_ACTIVE_MEMBERSHIPS",
                "Repair stopped under lock: more than one open ACTIVE TripLoad",
                [{"load_id": load_id, "trip_ids": actives}],
            )
        target = actives[0] if actives else None
        if before != p["from_active_trip_id"] or target != p["to_active_trip_id"]:
            raise CustodyBootstrapAnomaly(
                "POINTER_REPAIR_RACE",
                "Repair stopped: load state changed under lock vs planned repair",
                [
                    {
                        "load_id": load_id,
                        "planned": p,
                        "locked_before": before,
                        "locked_target": target,
                    }
                ],
            )
        load.active_trip_id = target
        applied.append(
            {
                "load_id": load_id,
                "from_active_trip_id": before,
                "to_active_trip_id": target,
            }
        )

    await db.flush()
    return {
        "tenant_id": tenant_id,
        "dry_run": False,
        "repairs": applied,
        "repaired_count": len(applied),
    }