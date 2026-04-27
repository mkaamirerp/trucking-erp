"""Phase 1: trips + trip_loads + loads.active_trip_id mirror; requires tenant DB at head migration."""

from __future__ import annotations

import os

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("ALLOW_TENANT_RESOLUTION_SHORTCUTS", "true")

from app.core.db_url import to_async_pg_url
from app.models.trip import Trip, TripLoad


def _tenant_async_url() -> str | None:
    raw = os.environ.get("TENANT_DATABASE_URL") or os.environ.get("ALEMBIC_TENANT_DATABASE_URL")
    if not raw:
        return None
    return to_async_pg_url(raw)


REQUIRES_TENANT_DB = _tenant_async_url() is None


@pytest.fixture
async def tenant_session():
    url = _tenant_async_url()
    if not url:
        pytest.skip("TENANT_DATABASE_URL or ALEMBIC_TENANT_DATABASE_URL required")
    engine = create_async_engine(url, pool_pre_ping=True)
    Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    try:
        async with Session() as session:
            yield session
    finally:
        await engine.dispose()


def test_trip_models_import() -> None:
    assert Trip.__tablename__ == "trips"
    assert TripLoad.__tablename__ == "trip_loads"


@pytest.mark.skipif(REQUIRES_TENANT_DB, reason="TENANT_DATABASE_URL required")
class TestTripFoundationTables:
    async def test_backfill_one_trip_row_per_dispatch_row(self, tenant_session: AsyncSession) -> None:
        """Each dispatch_trips row must have exactly one trips row (legacy link). Count(trips) may be
        higher in dev if orphan rows (e.g. NULL legacy) were inserted for experiments."""
        n_dispatch = (await tenant_session.execute(text("SELECT count(*)::int FROM dispatch_trips"))).scalar()
        n_mirrored = (
            await tenant_session.execute(
                text(
                    """
                    SELECT count(*)::int
                    FROM dispatch_trips d
                    INNER JOIN trips t ON t.legacy_dispatch_trip_id = d.id
                    """
                )
            )
        ).scalar()
        assert n_mirrored == n_dispatch, (
            f"Every dispatch_trips row must be mirrored in trips: "
            f"dispatch={n_dispatch}, joined={n_mirrored}"
        )
        n_with_legacy = (
            await tenant_session.execute(
                text("SELECT count(*)::int FROM trips WHERE legacy_dispatch_trip_id IS NOT NULL")
            )
        ).scalar()
        assert n_with_legacy == n_dispatch, (
            f"One trips row with legacy per dispatch: trips_with_legacy={n_with_legacy}, "
            f"dispatch={n_dispatch}"
        )

    async def test_trip_number_preserved(
        self, tenant_session: AsyncSession
    ) -> None:
        rows = (
            await tenant_session.execute(
                text(
                    """
                    SELECT dt.trip_number, t.trip_number
                    FROM dispatch_trips dt
                    JOIN trips t ON t.legacy_dispatch_trip_id = dt.id
                    """
                )
            )
        ).all()
        for dt_num, t_num in rows:
            assert dt_num == t_num

    async def test_freight_dispatch_has_trip_loads_membership(self, tenant_session: AsyncSession) -> None:
        """Backfill inserts trip_loads only for freight at migration time. New freights may lack trip_loads
        until Phase 2 — so join only mirrored (legacy-linked) freights, not all current load_id rows."""
        n_freight_mirrored = (
            await tenant_session.execute(
                text(
                    """
                    SELECT count(*)::int
                    FROM dispatch_trips d
                    INNER JOIN trips t ON t.legacy_dispatch_trip_id = d.id
                    WHERE d.load_id IS NOT NULL
                    """
                )
            )
        ).scalar()
        tlc = (await tenant_session.execute(text("SELECT count(*)::int FROM trip_loads"))).scalar()
        assert tlc == n_freight_mirrored, (
            f"trip_loads rows must match freight dispatches that have a mirrored trips row: "
            f"trip_loads={tlc}, mirrored_freight={n_freight_mirrored}"
        )

    async def test_active_trip_id_join(
        self, tenant_session: AsyncSession
    ) -> None:
        """loads.active_trip_id should point at trips for rows with active_dispatch_trip_id."""
        rows = (
            await tenant_session.execute(
                text(
                    """
                    SELECT l.id, l.active_dispatch_trip_id, l.active_trip_id, t.id, t.legacy_dispatch_trip_id
                    FROM loads l
                    JOIN trips t ON t.id = l.active_trip_id
                    WHERE l.active_dispatch_trip_id IS NOT NULL
                    LIMIT 50
                    """
                )
            )
        ).all()
        for _lid, adtid, atid, tid, legacy in rows:
            assert adtid == legacy
            assert atid == tid

    async def test_partial_unique_rejects_second_active_membership(
        self, tenant_session: AsyncSession
    ) -> None:
        row = (
            await tenant_session.execute(
                text(
                    """
                    SELECT trip_id, load_id, tenant_id
                    FROM trip_loads
                    WHERE removed_at IS NULL
                    LIMIT 1
                    """
                )
            )
        ).first()
        if row is None:
            pytest.skip("No active trip_loads row in DB")
        trip_id, load_id, tenant_id = int(row[0]), int(row[1]), int(row[2])
        err: Exception | None = None
        try:
            await tenant_session.execute(
                text(
                    """
                    INSERT INTO trip_loads
                    (tenant_id, trip_id, load_id, status_within_trip, sequence_hint, added_at, removed_at, created_at, updated_at)
                    VALUES
                    (:tid, :trid, :lid, 'active', 0, now(), NULL, now(), now())
                    """
                ),
                {"tid": tenant_id, "trid": trip_id, "lid": load_id},
            )
            await tenant_session.commit()
        except Exception as e:  # noqa: BLE001 — accept SQLAlchemy/asyncpg IntegrityError
            err = e
        assert err is not None
        assert "uq_trip_loads_active_membership" in str(err) or "duplicate" in str(err).lower()
        await tenant_session.rollback()
