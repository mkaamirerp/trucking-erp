"""Promote workspace draft → ready load + optional planned trip (atomic, disposable DB only)."""

from __future__ import annotations

import os
import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("ALLOW_TENANT_RESOLUTION_SHORTCUTS", "true")
if not os.environ.get("DATABASE_URL"):
    os.environ["DATABASE_URL"] = "postgresql://test:test@db.example.invalid:5432/test"

from app.core.integration_db_guard import (
    IntegrationIsolationError,
    assert_tenant_database_url_allowed,
    database_name_from_url,
)
from app.schemas.load_workspace_draft import LoadWorkspaceDraftCreate, LoadWorkspaceDraftPromote
from app.services.load_workspace_draft import create_workspace_draft
from app.services.load_workspace_draft_promotion import promote_workspace_draft
from app.services.loads import get_load

REQUIRES_TENANT_DB = not (
    os.environ.get("TENANT_DATABASE_URL") or os.environ.get("ALEMBIC_TENANT_DATABASE_URL")
)

pytestmark = pytest.mark.skipif(REQUIRES_TENANT_DB, reason="TENANT_DATABASE_URL not configured")


def _tenant_async_url() -> str:
    from app.core.db_url import to_async_pg_url

    raw = os.environ.get("TENANT_DATABASE_URL") or os.environ.get("ALEMBIC_TENANT_DATABASE_URL")
    assert raw
    return to_async_pg_url(raw)


def _session():
    engine = create_async_engine(_tenant_async_url(), pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    return engine, factory


def _skip_if_demo_or_not_disposable() -> None:
    if database_name_from_url(_tenant_async_url()) == "tenant_demo":
        pytest.skip("mutation tests must not run on tenant_demo")
    raw = os.environ.get("TENANT_DATABASE_URL") or os.environ.get("ALEMBIC_TENANT_DATABASE_URL")
    try:
        assert_tenant_database_url_allowed(str(raw).strip(), context="promote_movement_tests")
    except IntegrationIsolationError:
        pytest.skip("disposable TENANT_DATABASE_URL required")


def _promotable_draft_json(**overrides: object) -> dict:
    base = {
        "loadNumber": "",
        "brokerNameSnapshot": "Promote Movement Test",
        "brokerLoadReference": f"PROMO-MV-{uuid.uuid4().hex[:8]}",
        "draftStops": [
            {"stopType": "PICKUP", "city": "Austin", "stateOrProvince": "TX"},
            {"stopType": "DELIVERY", "city": "Dallas", "stateOrProvince": "TX"},
        ],
    }
    base.update(overrides)
    return base


async def _resolve_tenant_id(db: AsyncSession) -> int:
    tid = await db.scalar(text("SELECT MIN(tenant_id) FROM loads"))
    if tid is not None:
        return int(tid)
    tid = await db.scalar(text("SELECT MIN(tenant_id) FROM people"))
    if tid is None:
        pytest.skip("integration tenant has no tenant_id anchor")
    return int(tid)


async def _first_driver_id(db: AsyncSession, tenant_id: int) -> int:
    driver_id = await db.scalar(
        text("SELECT id FROM drivers WHERE tenant_id = :t ORDER BY id LIMIT 1"),
        {"t": tenant_id},
    )
    if driver_id is None:
        pytest.skip("integration tenant has no drivers")
    return int(driver_id)


async def _delete_promoted_artifacts(
    factory,
    *,
    tenant_id: int,
    load_id: int | None,
    draft_id,
    trip_id: int | None,
) -> None:
    async with factory() as db:
        if trip_id is not None:
            await db.execute(
                text("DELETE FROM trip_loads WHERE tenant_id = :t AND trip_id = :trip_id"),
                {"t": tenant_id, "trip_id": trip_id},
            )
            await db.execute(
                text("DELETE FROM trips WHERE tenant_id = :t AND id = :trip_id"),
                {"t": tenant_id, "trip_id": trip_id},
            )
        if load_id is not None:
            await db.execute(
                text("DELETE FROM trip_loads WHERE tenant_id = :t AND load_id = :load_id"),
                {"t": tenant_id, "load_id": load_id},
            )
            await db.execute(text("DELETE FROM load_stops WHERE load_id = :id"), {"id": load_id})
            await db.execute(text("DELETE FROM load_commercial_evidence WHERE load_id = :id"), {"id": load_id})
            await db.execute(
                text("UPDATE loads SET promotion_origin_workspace_draft_id = NULL WHERE id = :id"),
                {"id": load_id},
            )
        if draft_id is not None:
            await db.execute(text("DELETE FROM load_workspace_drafts WHERE id = :id"), {"id": draft_id})
        if load_id is not None:
            await db.execute(text("DELETE FROM loads WHERE id = :id"), {"id": load_id})
        await db.commit()


@pytest.mark.asyncio
async def test_promote_without_driver_creates_ready_load_only() -> None:
    _skip_if_demo_or_not_disposable()
    engine, factory = _session()
    draft_id = load_id = trip_id = None
    tenant_id = 0
    try:
        async with factory() as db:
            tenant_id = await _resolve_tenant_id(db)
            draft = await create_workspace_draft(
                db,
                tenant_id,
                LoadWorkspaceDraftCreate(source_channel="manual", draft_json=_promotable_draft_json()),
                created_by_platform_user_id="integration-test-user",
            )
            draft_id = draft.id
        async with factory() as db:
            result = await promote_workspace_draft(
                db,
                tenant_id,
                draft_id,
                LoadWorkspaceDraftPromote(
                    expected_concurrency_version=1,
                    promotion_idempotency_key=f"promo-no-driver-{uuid.uuid4().hex}",
                ),
                promoted_by_platform_user_id="integration-test-user",
            )
            load_id = result.load_id
            trip_id = result.trip_id
            assert trip_id is None
            load = await get_load(db, tenant_id, load_id)
            assert load is not None
            assert load.status == "ready"
            tl_count = await db.scalar(
                text("SELECT COUNT(*) FROM trip_loads WHERE tenant_id = :t AND load_id = :lid"),
                {"t": tenant_id, "lid": load_id},
            )
            assert int(tl_count or 0) == 0
    finally:
        await _delete_promoted_artifacts(
            factory, tenant_id=tenant_id, load_id=load_id, draft_id=draft_id, trip_id=trip_id
        )
        await engine.dispose()


@pytest.mark.asyncio
async def test_promote_with_driver_creates_load_and_planned_trip_atomically() -> None:
    _skip_if_demo_or_not_disposable()
    engine, factory = _session()
    draft_id = load_id = trip_id = None
    tenant_id = 0
    promo_key = f"promo-driver-{uuid.uuid4().hex}"
    try:
        async with factory() as db:
            tenant_id = await _resolve_tenant_id(db)
            driver_id = await _first_driver_id(db, tenant_id)
            draft = await create_workspace_draft(
                db,
                tenant_id,
                LoadWorkspaceDraftCreate(
                    source_channel="manual",
                    draft_json=_promotable_draft_json(driverId=driver_id),
                ),
                created_by_platform_user_id="integration-test-user",
            )
            draft_id = draft.id
        async with factory() as db:
            loads_before = int(await db.scalar(text("SELECT COUNT(*) FROM loads")))
            trips_before = int(await db.scalar(text("SELECT COUNT(*) FROM trips")))
            result = await promote_workspace_draft(
                db,
                tenant_id,
                draft_id,
                LoadWorkspaceDraftPromote(expected_concurrency_version=1, promotion_idempotency_key=promo_key),
                promoted_by_platform_user_id="integration-test-user",
            )
            load_id = result.load_id
            trip_id = result.trip_id
            assert trip_id is not None
            loads_after = int(await db.scalar(text("SELECT COUNT(*) FROM loads")))
            trips_after = int(await db.scalar(text("SELECT COUNT(*) FROM trips")))
            assert loads_after == loads_before + 1
            assert trips_after == trips_before + 1
            tl = await db.scalar(
                text(
                    "SELECT trip_id FROM trip_loads WHERE tenant_id = :t AND load_id = :lid LIMIT 1"
                ),
                {"t": tenant_id, "lid": load_id},
            )
            assert int(tl) == int(trip_id)
            replay = await promote_workspace_draft(
                db,
                tenant_id,
                draft_id,
                LoadWorkspaceDraftPromote(expected_concurrency_version=2, promotion_idempotency_key=promo_key),
                promoted_by_platform_user_id="integration-test-user",
            )
            assert replay.idempotent_replay is True
            assert replay.load_id == load_id
            assert replay.trip_id == trip_id
            loads_replay = int(await db.scalar(text("SELECT COUNT(*) FROM loads")))
            trips_replay = int(await db.scalar(text("SELECT COUNT(*) FROM trips")))
            assert loads_replay == loads_after
            assert trips_replay == trips_after
    finally:
        await _delete_promoted_artifacts(
            factory, tenant_id=tenant_id, load_id=load_id, draft_id=draft_id, trip_id=trip_id
        )
        await engine.dispose()


@pytest.mark.asyncio
async def test_promote_assignment_failure_rolls_back_load_and_keeps_draft() -> None:
    _skip_if_demo_or_not_disposable()
    engine, factory = _session()
    draft_id = None
    tenant_id = 0
    try:
        async with factory() as db:
            tenant_id = await _resolve_tenant_id(db)
            loads_before = int(await db.scalar(text("SELECT COUNT(*) FROM loads")))
            trips_before = int(await db.scalar(text("SELECT COUNT(*) FROM trips")))
            draft = await create_workspace_draft(
                db,
                tenant_id,
                LoadWorkspaceDraftCreate(
                    source_channel="manual",
                    draft_json=_promotable_draft_json(driverId=9_999_999),
                ),
                created_by_platform_user_id="integration-test-user",
            )
            draft_id = draft.id
        async with factory() as db:
            with pytest.raises(HTTPException):
                await promote_workspace_draft(
                    db,
                    tenant_id,
                    draft_id,
                    LoadWorkspaceDraftPromote(
                        expected_concurrency_version=1,
                        promotion_idempotency_key=f"promo-bad-driver-{uuid.uuid4().hex}",
                    ),
                    promoted_by_platform_user_id="integration-test-user",
                )
            await db.rollback()
        async with factory() as db:
            assert int(await db.scalar(text("SELECT COUNT(*) FROM loads"))) == loads_before
            assert int(await db.scalar(text("SELECT COUNT(*) FROM trips"))) == trips_before
            row = (
                await db.execute(
                    text(
                        "SELECT status, promoted_load_id FROM load_workspace_drafts "
                        "WHERE tenant_id = :t AND id = :id"
                    ),
                    {"t": tenant_id, "id": draft_id},
                )
            ).one()
            assert row.status == "draft"
            assert row.promoted_load_id is None
    finally:
        await _delete_promoted_artifacts(
            factory, tenant_id=tenant_id, load_id=None, draft_id=draft_id, trip_id=None
        )
        await engine.dispose()


@pytest.mark.asyncio
async def test_promote_rejects_malformed_driver_id_without_creating_load() -> None:
    _skip_if_demo_or_not_disposable()
    engine, factory = _session()
    draft_id = None
    tenant_id = 0
    try:
        async with factory() as db:
            tenant_id = await _resolve_tenant_id(db)
            loads_before = int(await db.scalar(text("SELECT COUNT(*) FROM loads")))
            draft = await create_workspace_draft(
                db,
                tenant_id,
                LoadWorkspaceDraftCreate(
                    source_channel="manual",
                    draft_json=_promotable_draft_json(driverId="not-a-driver"),
                ),
                created_by_platform_user_id="integration-test-user",
            )
            draft_id = draft.id
        async with factory() as db:
            with pytest.raises(HTTPException) as exc:
                await promote_workspace_draft(
                    db,
                    tenant_id,
                    draft_id,
                    LoadWorkspaceDraftPromote(
                        expected_concurrency_version=1,
                        promotion_idempotency_key=f"promo-bad-driver-str-{uuid.uuid4().hex}",
                    ),
                    promoted_by_platform_user_id="integration-test-user",
                )
            assert exc.value.status_code == 422
            await db.rollback()
        async with factory() as db:
            assert int(await db.scalar(text("SELECT COUNT(*) FROM loads"))) == loads_before
    finally:
        await _delete_promoted_artifacts(
            factory, tenant_id=tenant_id, load_id=None, draft_id=draft_id, trip_id=None
        )
        await engine.dispose()


@pytest.mark.asyncio
async def test_idempotent_replay_returns_trip_id_after_trip_progresses() -> None:
    _skip_if_demo_or_not_disposable()
    engine, factory = _session()
    draft_id = load_id = trip_id = None
    tenant_id = 0
    promo_key = f"promo-progressed-{uuid.uuid4().hex}"
    try:
        async with factory() as db:
            tenant_id = await _resolve_tenant_id(db)
            driver_id = await _first_driver_id(db, tenant_id)
            draft = await create_workspace_draft(
                db,
                tenant_id,
                LoadWorkspaceDraftCreate(
                    source_channel="manual",
                    draft_json=_promotable_draft_json(driverId=driver_id),
                ),
                created_by_platform_user_id="integration-test-user",
            )
            draft_id = draft.id
        async with factory() as db:
            result = await promote_workspace_draft(
                db,
                tenant_id,
                draft_id,
                LoadWorkspaceDraftPromote(expected_concurrency_version=1, promotion_idempotency_key=promo_key),
                promoted_by_platform_user_id="integration-test-user",
            )
            load_id = result.load_id
            trip_id = result.trip_id
            assert trip_id is not None
            await db.execute(
                text("UPDATE trips SET status = 'assigned' WHERE tenant_id = :t AND id = :id"),
                {"t": tenant_id, "id": trip_id},
            )
            await db.commit()
        async with factory() as db:
            replay = await promote_workspace_draft(
                db,
                tenant_id,
                draft_id,
                LoadWorkspaceDraftPromote(expected_concurrency_version=2, promotion_idempotency_key=promo_key),
                promoted_by_platform_user_id="integration-test-user",
            )
            assert replay.idempotent_replay is True
            assert replay.trip_id == trip_id
    finally:
        await _delete_promoted_artifacts(
            factory, tenant_id=tenant_id, load_id=load_id, draft_id=draft_id, trip_id=trip_id
        )
        await engine.dispose()
