"""Load History — actor_label on PATCH and empty stop diffs (disposable tenant DB only)."""

from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("ALLOW_TENANT_RESOLUTION_SHORTCUTS", "true")

from app.core.db_url import to_async_pg_url
from app.core.integration_db_guard import database_name_from_url
from app.schemas.load import LoadCreate, LoadUpdate
from app.services import loads as loads_service
from tests.support.integration_isolation import require_integration_tenant_database_url


def _tenant_async_url() -> str:
    return to_async_pg_url(require_integration_tenant_database_url(context="load_history_actor_stops"))


def _integration_ok() -> bool:
    try:
        require_integration_tenant_database_url(context="load_history_actor_stops")
        return True
    except Exception:
        return False


SKIP = "db.example.invalid" in (os.environ.get("DATABASE_URL") or "") or not _integration_ok()
SKIP_DEMO = database_name_from_url(_tenant_async_url()) == "tenant_demo" if _integration_ok() else True

pytestmark = [
    pytest.mark.skipif(SKIP, reason="disposable integration tenant DB not configured"),
    pytest.mark.skipif(SKIP_DEMO, reason="mutation tests must not run on tenant_demo"),
]


async def _audit_actions(db: AsyncSession, tenant_id: int, load_id: int) -> list[str]:
    rows = (
        await db.execute(
            text(
                """
                select action, actor_label
                from audit_events
                where tenant_id = :tid and entity_type = 'load' and entity_id = :eid
                order by id asc
                """
            ),
            {"tid": tenant_id, "eid": str(load_id)},
        )
    ).mappings().all()
    return [str(r["action"]) for r in rows]


async def _audit_row(
    db: AsyncSession, tenant_id: int, load_id: int, action: str
) -> dict | None:
    row = (
        await db.execute(
            text(
                """
                select action, actor_label
                from audit_events
                where tenant_id = :tid and entity_type = 'load' and entity_id = :eid and action = :action
                order by id desc limit 1
                """
            ),
            {"tid": tenant_id, "eid": str(load_id), "action": action},
        )
    ).mappings().first()
    return dict(row) if row else None


@pytest.mark.asyncio
async def test_patch_writes_actor_label_on_load_updated() -> None:
    from tests.support.tenant_test_ids import platform_tenant_id_for_slug

    engine = create_async_engine(_tenant_async_url(), pool_pre_ping=True)
    Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    tenant_id = await platform_tenant_id_for_slug("pytest")
    suffix = uuid.uuid4().hex[:8]
    load_id: int | None = None
    label = "History Actor Tester"
    try:
        async with Session() as db:
            created = await loads_service.create_load(
                db,
                tenant_id,
                LoadCreate(
                    status="draft",
                    broker_name_snapshot="Audit Actor Broker",
                    broker_load_reference=f"ACTOR-{suffix}",
                    stops=[
                        {"stop_type": "PICKUP", "sequence": 0, "city": "A", "state_or_province": "TX"},
                        {"stop_type": "DROP", "sequence": 1, "city": "B", "state_or_province": "TX"},
                    ],
                ),
                actor_user_id=None,
                actor_label=label,
                source="ui",
            )
            load_id = int(created.id)
            cv = int(created.concurrency_version)
            await loads_service.update_load(
                db,
                tenant_id,
                load_id,
                LoadUpdate(
                    expected_concurrency_version=cv,
                    internal_notes="audit label check",
                ),
                actor_user_id=None,
                actor_label=label,
                source="ui",
            )
            row = await _audit_row(db, tenant_id, load_id, "load_updated")
            assert row is not None
            assert row["actor_label"] == label
    finally:
        if load_id is not None:
            async with Session() as db:
                await db.execute(text("delete from audit_events where entity_id = :eid"), {"eid": str(load_id)})
                await db.execute(text("delete from load_stops where load_id = :lid"), {"lid": load_id})
                await db.execute(text("delete from loads where id = :lid and tenant_id = :tid"), {"lid": load_id, "tid": tenant_id})
                await db.commit()
        await engine.dispose()


@pytest.mark.asyncio
async def test_patch_unchanged_stops_writes_no_load_stops_changed() -> None:
    from tests.support.tenant_test_ids import platform_tenant_id_for_slug

    engine = create_async_engine(_tenant_async_url(), pool_pre_ping=True)
    Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    tenant_id = await platform_tenant_id_for_slug("pytest")
    suffix = uuid.uuid4().hex[:8]
    load_id: int | None = None
    try:
        async with Session() as db:
            created = await loads_service.create_load(
                db,
                tenant_id,
                LoadCreate(
                    status="draft",
                    broker_name_snapshot="Stop Guard Broker",
                    broker_load_reference=f"STOPS-{suffix}",
                    stops=[
                        {"stop_type": "PICKUP", "sequence": 0, "city": "A", "state_or_province": "TX"},
                        {"stop_type": "DROP", "sequence": 1, "city": "B", "state_or_province": "TX"},
                    ],
                ),
                source="ui",
            )
            load_id = int(created.id)
            hydrated = await loads_service.get_load(db, tenant_id, load_id)
            assert hydrated is not None
            stops = sorted(hydrated.stops or [], key=lambda s: s.sequence)
            cv = int(hydrated.concurrency_version)
            await db.execute(text("delete from audit_events where entity_id = :eid"), {"eid": str(load_id)})
            await db.commit()
            await loads_service.update_load(
                db,
                tenant_id,
                load_id,
                LoadUpdate(
                    expected_concurrency_version=cv,
                    commodity="Same stops",
                    stops=[
                        {
                            "id": stops[0].id,
                            "stop_type": "PICKUP",
                            "sequence": 0,
                            "city": "A",
                            "state_or_province": "TX",
                        },
                        {
                            "id": stops[1].id,
                            "stop_type": "DROP",
                            "sequence": 1,
                            "city": "B",
                            "state_or_province": "TX",
                        },
                    ],
                ),
                source="ui",
            )
            actions = await _audit_actions(db, tenant_id, load_id)
            assert "load_stops_changed" not in actions
    finally:
        if load_id is not None:
            async with Session() as db:
                await db.execute(text("delete from audit_events where entity_id = :eid"), {"eid": str(load_id)})
                await db.execute(text("delete from load_stops where load_id = :lid"), {"lid": load_id})
                await db.execute(text("delete from loads where id = :lid and tenant_id = :tid"), {"lid": load_id, "tid": tenant_id})
                await db.commit()
        await engine.dispose()


@pytest.mark.asyncio
async def test_real_stop_change_writes_one_load_stops_changed() -> None:
    from tests.support.tenant_test_ids import platform_tenant_id_for_slug

    engine = create_async_engine(_tenant_async_url(), pool_pre_ping=True)
    Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    tenant_id = await platform_tenant_id_for_slug("pytest")
    suffix = uuid.uuid4().hex[:8]
    load_id: int | None = None
    try:
        async with Session() as db:
            created = await loads_service.create_load(
                db,
                tenant_id,
                LoadCreate(
                    status="draft",
                    broker_name_snapshot="Stop Change Broker",
                    broker_load_reference=f"STOPCHG-{suffix}",
                    stops=[
                        {"stop_type": "PICKUP", "sequence": 0, "city": "A", "state_or_province": "TX"},
                        {"stop_type": "DROP", "sequence": 1, "city": "B", "state_or_province": "TX"},
                    ],
                ),
                source="ui",
            )
            load_id = int(created.id)
            hydrated = await loads_service.get_load(db, tenant_id, load_id)
            assert hydrated is not None
            stops = sorted(hydrated.stops or [], key=lambda s: s.sequence)
            cv = int(hydrated.concurrency_version)
            await db.execute(text("delete from audit_events where entity_id = :eid"), {"eid": str(load_id)})
            await db.commit()
            await loads_service.update_load(
                db,
                tenant_id,
                load_id,
                LoadUpdate(
                    expected_concurrency_version=cv,
                    stops=[
                        {
                            "id": stops[0].id,
                            "stop_type": "PICKUP",
                            "sequence": 0,
                            "city": "A",
                            "state_or_province": "TX",
                        },
                        {
                            "id": stops[1].id,
                            "stop_type": "DROP",
                            "sequence": 1,
                            "city": "C",
                            "state_or_province": "TX",
                        },
                    ],
                ),
                source="ui",
            )
            actions = await _audit_actions(db, tenant_id, load_id)
            assert actions.count("load_stops_changed") == 1
    finally:
        if load_id is not None:
            async with Session() as db:
                await db.execute(text("delete from audit_events where entity_id = :eid"), {"eid": str(load_id)})
                await db.execute(text("delete from load_stops where load_id = :lid"), {"lid": load_id})
                await db.execute(text("delete from loads where id = :lid and tenant_id = :tid"), {"lid": load_id, "tid": tenant_id})
                await db.commit()
        await engine.dispose()
