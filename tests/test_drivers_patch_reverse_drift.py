"""PATCH /drivers/{id}: block master-data edits when person_id is set (People workspace is canonical)."""

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
from app.models.driver import Driver
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
class TestDriversPatchLinkedPerson:
    async def test_blocks_name_when_person_linked(
        self,
        client: AsyncClient,
        override_auth_tenant,
        tenant_session: AsyncSession,
        demo_tenant_id: int,
    ) -> None:
        suffix = uuid.uuid4().hex[:10]
        email = f"drift.{suffix}@test.invalid"
        p = Person(
            tenant_id=demo_tenant_id,
            first_name="A",
            last_name=f"B{suffix}",
            email=email,
        )
        tenant_session.add(p)
        await tenant_session.flush()
        drv = Driver(
            tenant_id=demo_tenant_id,
            person_id=p.id,
            first_name="A",
            last_name=f"B{suffix}",
            email=email,
            is_active=True,
        )
        tenant_session.add(drv)
        await tenant_session.commit()
        await tenant_session.refresh(drv)
        did = int(drv.id)
        pid = int(p.id)
        try:
            r = await client.patch(
                f"/api/v1/drivers/{did}",
                json={"first_name": "Changed"},
                headers=AUTH_HEADERS,
            )
            assert r.status_code == 409, r.text
            body = r.json()
            d = body.get("detail", {})
            assert d.get("code") == "use_people_workspace_for_driver_master_data"
            assert d.get("pattern") == "people_first_operational_projection"
            assert d.get("operational_table") == "drivers"
            assert "first_name" in d["blocked_fields"]
        finally:
            await tenant_session.execute(delete(Driver).where(Driver.id == did))
            await tenant_session.execute(delete(Person).where(Person.id == pid, Person.tenant_id == demo_tenant_id))
            await tenant_session.commit()

    async def test_allows_operational_fields_when_person_linked(
        self,
        client: AsyncClient,
        override_auth_tenant,
        tenant_session: AsyncSession,
        demo_tenant_id: int,
    ) -> None:
        suffix = uuid.uuid4().hex[:10]
        email = f"op.{suffix}@test.invalid"
        p = Person(
            tenant_id=demo_tenant_id,
            first_name="C",
            last_name=f"D{suffix}",
            email=email,
        )
        tenant_session.add(p)
        await tenant_session.flush()
        drv = Driver(
            tenant_id=demo_tenant_id,
            person_id=p.id,
            first_name="C",
            last_name=f"D{suffix}",
            email=email,
            is_active=True,
        )
        tenant_session.add(drv)
        await tenant_session.commit()
        await tenant_session.refresh(drv)
        did = int(drv.id)
        pid = int(p.id)
        try:
            r = await client.patch(
                f"/api/v1/drivers/{did}",
                json={"is_active": False},
                headers=AUTH_HEADERS,
            )
            assert r.status_code == 200, r.text
            assert r.json()["is_active"] is False
        finally:
            await tenant_session.execute(delete(Driver).where(Driver.id == did))
            await tenant_session.execute(delete(Person).where(Person.id == pid, Person.tenant_id == demo_tenant_id))
            await tenant_session.commit()

    async def test_allows_master_fields_when_person_unlinked_legacy(
        self,
        client: AsyncClient,
        override_auth_tenant,
        tenant_session: AsyncSession,
        demo_tenant_id: int,
    ) -> None:
        suffix = uuid.uuid4().hex[:10]
        email = f"leg.{suffix}@test.invalid"
        drv = Driver(
            tenant_id=demo_tenant_id,
            person_id=None,
            first_name="E",
            last_name=f"F{suffix}",
            email=email,
            is_active=True,
        )
        tenant_session.add(drv)
        await tenant_session.commit()
        await tenant_session.refresh(drv)
        did = int(drv.id)
        try:
            r = await client.patch(
                f"/api/v1/drivers/{did}",
                json={"first_name": "LegacyFirst"},
                headers=AUTH_HEADERS,
            )
            assert r.status_code == 200, r.text
            assert r.json()["first_name"] == "LegacyFirst"
        finally:
            await tenant_session.execute(delete(Driver).where(Driver.id == did))
            await tenant_session.commit()

    async def test_blocks_license_fields_when_person_linked(
        self,
        client: AsyncClient,
        override_auth_tenant,
        tenant_session: AsyncSession,
        demo_tenant_id: int,
    ) -> None:
        suffix = uuid.uuid4().hex[:10]
        email = f"lic.{suffix}@test.invalid"
        p = Person(
            tenant_id=demo_tenant_id,
            first_name="G",
            last_name=f"H{suffix}",
            email=email,
        )
        tenant_session.add(p)
        await tenant_session.flush()
        drv = Driver(
            tenant_id=demo_tenant_id,
            person_id=p.id,
            first_name="G",
            last_name=f"H{suffix}",
            email=email,
            is_active=True,
            license_number="OLD",
        )
        tenant_session.add(drv)
        await tenant_session.commit()
        await tenant_session.refresh(drv)
        did = int(drv.id)
        pid = int(p.id)
        try:
            r = await client.patch(
                f"/api/v1/drivers/{did}",
                json={"license_number": "NEW"},
                headers=AUTH_HEADERS,
            )
            assert r.status_code == 409, r.text
            detail = r.json()["detail"]
            assert "license_number" in detail["blocked_fields"]
        finally:
            await tenant_session.execute(delete(Driver).where(Driver.id == did))
            await tenant_session.execute(delete(Person).where(Person.id == pid, Person.tenant_id == demo_tenant_id))
            await tenant_session.commit()
