"""Trip number and trip driver on load GET are a read model.

Disposable tenant database only. Refuses tenant_demo even when the playground flag is set.
Does not copy trip driver/truck/trailer onto loads.
"""

from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("ALLOW_TENANT_RESOLUTION_SHORTCUTS", "true")
if not os.environ.get("DATABASE_URL"):
    os.environ["DATABASE_URL"] = "postgresql://test:test@db.example.invalid:5432/test"

from app.core.integration_db_guard import (
    FORBIDDEN_INTEGRATION_TENANT_DB_NAMES,
    IntegrationIsolationError,
    assert_tenant_database_url_allowed,
    database_name_from_url,
)
from app.models.driver import Driver
from app.models.trailer import Trailer
from app.models.truck import Truck
from app.schemas.load import LoadCreate, LoadResponse, LoadStopCreate
from app.schemas.trip_read import TripAssignmentBody
from app.services.loads import (
    _insert_commercial_load_uncommitted,
    enrich_load_responses,
    get_load,
)
from app.services.trips import (
    _activate_trip_load_membership_locked,
    _lock_load_for_membership,
    _lock_trip_for_mutation,
    create_planned_trip,
    update_trip_assignment,
)

REQUIRES_TENANT_DB = not (os.environ.get("TENANT_DATABASE_URL") or os.environ.get("ALEMBIC_TENANT_DATABASE_URL"))
pytestmark = pytest.mark.skipif(REQUIRES_TENANT_DB, reason="TENANT_DATABASE_URL not configured")


def _tenant_async_url() -> str:
    from app.core.db_url import to_async_pg_url

    raw = os.environ.get("TENANT_DATABASE_URL") or os.environ.get("ALEMBIC_TENANT_DATABASE_URL")
    assert raw
    return to_async_pg_url(raw)


def _refuse_tenant_demo_url() -> None:
    raw = os.environ.get("TENANT_DATABASE_URL") or os.environ.get("ALEMBIC_TENANT_DATABASE_URL") or ""
    name = database_name_from_url(str(raw).strip())
    if name in FORBIDDEN_INTEGRATION_TENANT_DB_NAMES:
        pytest.fail(
            f"trip visibility tests refuse tenant database {name!r}. "
            "Point TENANT_DATABASE_URL at a disposable database."
        )
    try:
        assert_tenant_database_url_allowed(str(raw).strip(), context="trip_visibility_read_model")
    except IntegrationIsolationError as exc:
        pytest.skip(f"disposable TENANT_DATABASE_URL required: {exc}")


def _session():
    _refuse_tenant_demo_url()
    engine = create_async_engine(_tenant_async_url(), pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    return engine, factory


async def _assert_disposable(db: AsyncSession) -> None:
    current = await db.scalar(text("SELECT current_database()"))
    name = (current or "").strip().lower()
    if name in FORBIDDEN_INTEGRATION_TENANT_DB_NAMES:
        pytest.fail(f"trip visibility tests connected to {name!r}; refusing all writes.")


def _ready_load(tag: str) -> LoadCreate:
    return LoadCreate(
        status="draft",
        broker_load_reference=tag,
        stops=[
            LoadStopCreate(stop_type="PICKUP", sequence=0, city="Toronto", state_or_province="ON"),
            LoadStopCreate(stop_type="DELIVERY", sequence=1, city="Montreal", state_or_province="QC"),
        ],
    )


@pytest.mark.asyncio
async def test_load_get_trip_read_model_planned_assigned_and_none() -> None:
    engine, factory = _session()
    load_ids: list[int] = []
    trip_ids: list[int] = []
    driver_id = truck_id = trailer_id = None
    tenant_id = None
    try:
        async with factory() as db:
            await _assert_disposable(db)
            tenant_id = await db.scalar(
                text(
                    """
                    SELECT n.tenant_id
                    FROM tenant_dispatch_numbering n
                    JOIN tenant_load_number_periods p ON p.tenant_id = n.tenant_id
                    WHERE n.prefix_locked_at IS NOT NULL
                    ORDER BY n.tenant_id
                    LIMIT 1
                    """
                )
            )
            if tenant_id is None:
                pytest.fail(
                    "disposable database has no locked trip prefix and load-number period; "
                    "refusing to migrate or create numbering config"
                )
            tenant_id = int(tenant_id)
            suffix = uuid.uuid4().hex[:8]
            driver = Driver(
                tenant_id=tenant_id,
                first_name="Vis",
                last_name=f"Driver{suffix[:4]}",
                is_active=True,
            )
            truck = Truck(
                tenant_id=tenant_id,
                unit_number=f"UT-{suffix}",
                vin=f"1{suffix.upper()}VIN000000"[:17],
                status="active",
            )
            trailer = Trailer(
                tenant_id=tenant_id,
                unit_number=f"TR-{suffix}",
                status="active",
            )
            db.add_all([driver, truck, trailer])
            await db.flush()
            driver_id, truck_id, trailer_id = int(driver.id), int(truck.id), int(trailer.id)

            planned_load, _ = await _insert_commercial_load_uncommitted(
                db, tenant_id, _ready_load(f"TV-P-{suffix}"), insert_as_ready=True
            )
            assigned_load, _ = await _insert_commercial_load_uncommitted(
                db, tenant_id, _ready_load(f"TV-A-{suffix}"), insert_as_ready=True
            )
            bare_load, _ = await _insert_commercial_load_uncommitted(
                db, tenant_id, _ready_load(f"TV-N-{suffix}"), insert_as_ready=True
            )
            await db.flush()
            load_ids.extend([int(planned_load.id), int(assigned_load.id), int(bare_load.id)])

            planned = await create_planned_trip(
                db,
                tenant_id,
                driver_id=driver_id,
                load_ids=[int(planned_load.id)],
            )
            trip_ids.append(int(planned.id))

            active_trip = await create_planned_trip(
                db,
                tenant_id,
                load_ids=[int(assigned_load.id)],
            )
            trip_ids.append(int(active_trip.id))
            await update_trip_assignment(
                db,
                tenant_id,
                int(active_trip.id),
                TripAssignmentBody(
                    driver_id=driver_id,
                    truck_id=truck_id,
                    trailer_id=trailer_id,
                ),
                actor_user_id=None,
                actor_label="trip-visibility-test",
            )
            locked_trip = await _lock_trip_for_mutation(db, tenant_id, int(active_trip.id))
            locked_load = await _lock_load_for_membership(db, tenant_id, int(assigned_load.id))
            await _activate_trip_load_membership_locked(db, tenant_id, locked_trip, locked_load)
            await db.commit()

        async with factory() as db:
            await _assert_disposable(db)
            rows = []
            for load_id in load_ids:
                load = await get_load(db, tenant_id, load_id)
                assert load is not None
                assert load.driver_id is None
                assert load.truck_id is None
                assert load.trailer_id is None
                rows.append(LoadResponse.model_validate(load))
            enriched = await enrich_load_responses(db, tenant_id, rows)
            by_ref = {item.broker_load_reference: item for item in enriched}

            planned_out = by_ref[f"TV-P-{suffix}"]
            assert planned_out.open_planned_trip_number
            assert planned_out.open_planned_trip_driver_name == f"Vis Driver{suffix[:4]}"
            assert planned_out.active_membership_trip_number is None
            assert (planned_out.trip_number or "") == ""

            active_out = by_ref[f"TV-A-{suffix}"]
            assert active_out.active_membership_trip_number
            assert active_out.active_membership_driver_name == f"Vis Driver{suffix[:4]}"
            assert active_out.open_planned_trip_number is None

            bare_out = by_ref[f"TV-N-{suffix}"]
            assert bare_out.open_planned_trip_number is None
            assert bare_out.active_membership_trip_number is None
            assert bare_out.open_planned_trip_driver_name is None
            assert bare_out.active_membership_driver_name is None
    finally:
        async with factory() as db:
            if load_ids:
                await db.execute(
                    text("UPDATE loads SET active_trip_id = NULL, promotion_origin_workspace_draft_id = NULL WHERE id = ANY(:ids)"),
                    {"ids": load_ids},
                )
                await db.execute(text("DELETE FROM trip_loads WHERE load_id = ANY(:ids)"), {"ids": load_ids})
                await db.execute(text("DELETE FROM load_stops WHERE load_id = ANY(:ids)"), {"ids": load_ids})
                await db.execute(text("DELETE FROM loads WHERE id = ANY(:ids)"), {"ids": load_ids})
            if trip_ids:
                await db.execute(text("DELETE FROM trips WHERE id = ANY(:ids)"), {"ids": trip_ids})
            if trailer_id is not None:
                await db.execute(text("DELETE FROM trailers WHERE id = :id"), {"id": trailer_id})
            if truck_id is not None:
                await db.execute(text("DELETE FROM trucks WHERE id = :id"), {"id": truck_id})
            if driver_id is not None:
                await db.execute(text("DELETE FROM drivers WHERE id = :id"), {"id": driver_id})
            await db.commit()
        await engine.dispose()
