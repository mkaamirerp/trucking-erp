"""Load History panel v1 — audit read API actor_label and promotion audit actor."""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("ALLOW_TENANT_RESOLUTION_SHORTCUTS", "true")
if not os.environ.get("DATABASE_URL"):
    os.environ["DATABASE_URL"] = "postgresql://test:test@db.example.invalid:5432/test"

from app.authz.routes import _rows
from app.main import app
from app.schemas.audit_events import AuditEventOut
from app.schemas.load_workspace_draft import LoadWorkspaceDraftPromote
from app.services.load_workspace_draft_promotion import promote_workspace_draft
from app.services.loads import get_load
from tests.support.integration_auth import (
    clear_current_user_and_tenant_overrides,
    install_host_aligned_current_user_and_tenant,
)
from tests.support.demo_clone_integration import (
    clear_demo_clone_http_test_overrides,
    install_demo_clone_http_test_overrides,
)
from tests.support.integration_isolation import database_name_from_url, require_integration_tenant_database_url

REQUIRES_TENANT_DB = not (os.environ.get("TENANT_DATABASE_URL") or os.environ.get("ALEMBIC_TENANT_DATABASE_URL"))
_PLACEHOLDER_PLATFORM_DB = "db.example.invalid" in (os.environ.get("DATABASE_URL") or "")
_SKIP_WITHOUT_TENANT = _PLACEHOLDER_PLATFORM_DB and REQUIRES_TENANT_DB

pytestmark = [
    pytest.mark.skipif(_SKIP_WITHOUT_TENANT, reason="tenant DB not configured"),
    pytest.mark.skipif(REQUIRES_TENANT_DB, reason="TENANT_DATABASE_URL not configured"),
]

AUTH_HEADERS = {"host": "pytest.truckerp.me"}


def _tenant_async_url() -> str:
    from app.core.db_url import to_async_pg_url

    return to_async_pg_url(require_integration_tenant_database_url())


def test_audit_event_out_includes_actor_label_field() -> None:
    out = AuditEventOut(
        id=1,
        event_at=datetime.now(timezone.utc),
        actor_user_id=7,
        actor_label="Sam Dispatcher",
        module="loads",
        entity_type="load",
        entity_id="99",
        action="load_updated",
        source="ui",
        visibility="normal",
        changed_fields={"rate": {"before": "1", "after": "2"}},
    )
    dumped = out.model_dump()
    assert dumped["actor_label"] == "Sam Dispatcher"
    assert "context_json" not in dumped


def test_authz_route_inventory_binds_load_audit_by_entity() -> None:
    paths = {r.path for r in _rows() if r.method == "GET"}
    assert "/api/v1/audit-events/by-entity" in paths


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest.fixture
def override_auth_tenant():
    os.environ["TEST_BYPASS_AUTH"] = "1"
    install_host_aligned_current_user_and_tenant(app)
    install_demo_clone_http_test_overrides(app)
    yield
    clear_current_user_and_tenant_overrides(app)
    clear_demo_clone_http_test_overrides(app)


@pytest.mark.asyncio
async def test_by_entity_returns_actor_label(client, override_auth_tenant) -> None:
    if database_name_from_url(_tenant_async_url()) == "tenant_demo":
        pytest.skip("mutation tests must not run on tenant_demo")

    suffix = uuid.uuid4().hex[:8]
    create = await client.post(
        "/api/v1/loads",
        headers=AUTH_HEADERS,
        json={
            "status": "draft",
            "broker_name_snapshot": "History Audit Broker",
            "broker_load_reference": f"HIST-{suffix}",
            "stops": [
                {"stop_type": "PICKUP", "sequence": 0, "city": "Austin", "state_or_province": "TX"},
                {"stop_type": "DROP", "sequence": 1, "city": "Dallas", "state_or_province": "TX"},
            ],
        },
    )
    assert create.status_code == 201, create.text
    load_id = int(create.json()["id"])

    engine = create_async_engine(_tenant_async_url(), pool_pre_ping=True)
    Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    try:
        async with Session() as db:
            from app.services.audit_events import write_audit_event
            from tests.support.tenant_test_ids import platform_tenant_id_for_slug

            tenant_id = await platform_tenant_id_for_slug("pytest")
            await write_audit_event(
                db,
                tenant_id=tenant_id,
                module="loads",
                entity_type="load",
                entity_id=str(load_id),
                action="load_updated",
                source="ui",
                actor_user_id=42,
                actor_label="History Test Actor",
                changed_fields={"rate": {"before": "100", "after": "200"}},
            )
            await db.commit()
    finally:
        await engine.dispose()

    ar = await client.get(
        "/api/v1/audit-events/by-entity",
        headers=AUTH_HEADERS,
        params={"entity_type": "load", "entity_id": str(load_id), "limit": 50},
    )
    assert ar.status_code == 200, ar.text
    updated = next((row for row in ar.json() if row.get("action") == "load_updated"), None)
    assert updated is not None
    assert updated.get("actor_label") == "History Test Actor"
    assert "context_json" not in updated
    assert "storage_key" not in str(updated)


@pytest.mark.asyncio
async def test_promotion_load_created_audit_has_actor() -> None:
    if database_name_from_url(_tenant_async_url()) == "tenant_demo":
        pytest.skip("mutation tests must not run on tenant_demo")

    from tests.test_load_workspace_draft_api import (
        _create_draft,
        _delete_promoted_load_and_draft,
        _promotable_draft_json,
        _session,
    )

    engine, factory = _session()
    draft_id = None
    load_id = None
    actor_user_id = 4242
    actor_label = "Promo History Tester"
    try:
        tenant_id, draft_id = await _create_draft(
            factory,
            _promotable_draft_json(loadNumber=f"HIST-PROMO-{uuid.uuid4().hex[:8]}"),
        )
        async with factory() as db:
            result = await promote_workspace_draft(
                db,
                tenant_id,
                draft_id,
                LoadWorkspaceDraftPromote(
                    expected_concurrency_version=1,
                    promotion_idempotency_key=f"hist-promo-{uuid.uuid4().hex}",
                ),
                promoted_by_platform_user_id="platform-uuid-not-shown",
                audit_actor_user_id=actor_user_id,
                audit_actor_label=actor_label,
            )
            load_id = result.load_id

        async with factory() as db:
            row = await db.execute(
                text(
                    """
                    select actor_user_id, actor_label, action
                    from audit_events
                    where tenant_id = :tid and entity_type = 'load' and entity_id = :eid and action = 'load_created'
                    order by id desc limit 1
                    """
                ),
                {"tid": tenant_id, "eid": str(load_id)},
            )
            audit = row.mappings().first()
            assert audit is not None
            assert int(audit["actor_user_id"]) == actor_user_id
            assert audit["actor_label"] == actor_label
            load = await get_load(db, tenant_id, load_id)
            assert load is not None
    finally:
        await _delete_promoted_load_and_draft(factory, load_id, draft_id)
        await engine.dispose()
