"""People workspace GET audit-log (tenant_audit_logs subset)."""

from __future__ import annotations

import os
import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("ALLOW_TENANT_RESOLUTION_SHORTCUTS", "true")

from app.core.db_url import to_async_pg_url
from app.main import app
from app.models.person import Person
from tests.support.integration_auth import (
    clear_current_user_and_tenant_overrides,
    install_host_aligned_current_user_and_tenant,
)
from tests.support.tenant_test_ids import platform_tenant_id_for_slug


def _tenant_async_url() -> str | None:
    raw = os.environ.get("TENANT_DATABASE_URL") or os.environ.get("ALEMBIC_TENANT_DATABASE_URL")
    if not raw:
        return None
    return to_async_pg_url(raw)


REQUIRES_TENANT_DB = _tenant_async_url() is None
REQUIRES_INTEGRATION_DB = REQUIRES_TENANT_DB or not (os.environ.get("DATABASE_URL") or "").strip()
AUTH_HEADERS = {"host": "demo.truckerp.me"}


@pytest.fixture(autouse=True)
def test_bypass_env():
    old = os.environ.get("TEST_BYPASS_AUTH")
    os.environ["TEST_BYPASS_AUTH"] = "1"
    yield
    if old is None:
        os.environ.pop("TEST_BYPASS_AUTH", None)
    else:
        os.environ["TEST_BYPASS_AUTH"] = old


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest.fixture
def override_auth_tenant(test_bypass_env):
    install_host_aligned_current_user_and_tenant(app)
    yield
    clear_current_user_and_tenant_overrides(app)


@pytest.fixture
async def demo_tenant_id():
    return await platform_tenant_id_for_slug("demo")


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


@pytest.mark.asyncio
@pytest.mark.skipif(REQUIRES_INTEGRATION_DB, reason="DATABASE_URL + tenant DB URL required for integration")
class TestPeopleWorkspaceAuditLog:
    async def test_audit_log_lists_core_patch(
        self,
        client: AsyncClient,
        override_auth_tenant,
        tenant_session: AsyncSession,
        demo_tenant_id: int,
    ) -> None:
        suffix = uuid.uuid4().hex[:10]
        p = Person(
            tenant_id=demo_tenant_id,
            first_name="Aud",
            last_name=f"It{suffix}",
            email=f"audit.{suffix}@pws-test.invalid",
        )
        tenant_session.add(p)
        await tenant_session.commit()
        await tenant_session.refresh(p)
        pid = int(p.id)
        try:
            r0 = await client.get(f"/api/v1/people/{pid}/audit-log", headers=AUTH_HEADERS)
            assert r0.status_code == 200, r0.text
            assert r0.json() == []

            r1 = await client.patch(
                f"/api/v1/people/{pid}",
                json={"first_name": "Aud2"},
                headers=AUTH_HEADERS,
            )
            assert r1.status_code == 200, r1.text

            r2 = await client.get(f"/api/v1/people/{pid}/audit-log", headers=AUTH_HEADERS)
            assert r2.status_code == 200, r2.text
            rows = r2.json()
            assert len(rows) >= 1
            assert rows[0]["action"] == "people_core_patch"
            assert "first_name" in rows[0]["changed_keys"]
            assert rows[0]["snapshot"]["first_name"]["after"] == "Aud2"
        finally:
            await tenant_session.execute(delete(Person).where(Person.id == pid, Person.tenant_id == demo_tenant_id))
            await tenant_session.commit()
