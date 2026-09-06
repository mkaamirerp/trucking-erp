"""People workspace driver-role-configuration GET/PATCH (`driver_person_extensions`)."""

from __future__ import annotations

import os
import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("ALLOW_TENANT_RESOLUTION_SHORTCUTS", "true")

from app.core.db_url import to_async_pg_url
from app.main import app
from app.models.driver_person_extension import DriverPersonExtension
from app.models.person import Person, PersonRole
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
AUTH_HEADERS = {"host": "pytest.truckerp.me"}

_VALID_BODY = {
    "employment_relationship_type": "company_driver",
    "driver_operating_subtype": "long_haul",
    "is_team_driver": False,
    "team_role_type": None,
    "provides_own_truck": False,
    "provides_own_trailer": False,
    "equipment_contribution_type": "company_equipment",
    "insurance_commercial_approved": False,
}


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
    return await platform_tenant_id_for_slug()


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
class TestPeopleWorkspaceDriverRoleConfiguration:
    async def test_get_null_when_no_row(
        self,
        client: AsyncClient,
        override_auth_tenant,
        tenant_session: AsyncSession,
        demo_tenant_id: int,
    ) -> None:
        suffix = uuid.uuid4().hex[:10]
        p = Person(
            tenant_id=demo_tenant_id,
            first_name="G",
            last_name=f"E{suffix}",
            email=f"getnull.{suffix}@pws-dpe.invalid",
        )
        tenant_session.add(p)
        await tenant_session.flush()
        tenant_session.add(
            PersonRole(
                tenant_id=demo_tenant_id,
                person_id=p.id,
                role_code="DRIVER",
                is_primary=True,
                is_active=True,
            )
        )
        await tenant_session.commit()
        await tenant_session.refresh(p)
        pid = int(p.id)
        try:
            r = await client.get(
                f"/api/v1/people/{pid}/driver-role-configuration",
                headers=AUTH_HEADERS,
            )
            assert r.status_code == 200, r.text
            assert r.json() is None
        finally:
            await tenant_session.execute(
                delete(PersonRole).where(PersonRole.person_id == pid, PersonRole.tenant_id == demo_tenant_id)
            )
            await tenant_session.execute(delete(Person).where(Person.id == pid, Person.tenant_id == demo_tenant_id))
            await tenant_session.commit()

    async def test_patch_409_without_driver_role(
        self,
        client: AsyncClient,
        override_auth_tenant,
        tenant_session: AsyncSession,
        demo_tenant_id: int,
    ) -> None:
        suffix = uuid.uuid4().hex[:10]
        p = Person(
            tenant_id=demo_tenant_id,
            first_name="N",
            last_name=f"R{suffix}",
            email=f"norole.{suffix}@pws-dpe.invalid",
        )
        tenant_session.add(p)
        await tenant_session.commit()
        await tenant_session.refresh(p)
        pid = int(p.id)
        try:
            r = await client.patch(
                f"/api/v1/people/{pid}/driver-role-configuration",
                json=_VALID_BODY,
                headers=AUTH_HEADERS,
            )
            assert r.status_code == 409, r.text
        finally:
            await tenant_session.execute(delete(Person).where(Person.id == pid, Person.tenant_id == demo_tenant_id))
            await tenant_session.commit()

    async def test_patch_creates_row(
        self,
        client: AsyncClient,
        override_auth_tenant,
        tenant_session: AsyncSession,
        demo_tenant_id: int,
    ) -> None:
        suffix = uuid.uuid4().hex[:10]
        p = Person(
            tenant_id=demo_tenant_id,
            first_name="C",
            last_name=f"R{suffix}",
            email=f"create.{suffix}@pws-dpe.invalid",
        )
        tenant_session.add(p)
        await tenant_session.flush()
        tenant_session.add(
            PersonRole(
                tenant_id=demo_tenant_id,
                person_id=p.id,
                role_code="DRIVER",
                is_primary=True,
                is_active=True,
            )
        )
        await tenant_session.commit()
        await tenant_session.refresh(p)
        pid = int(p.id)
        try:
            r = await client.patch(
                f"/api/v1/people/{pid}/driver-role-configuration",
                json=_VALID_BODY,
                headers=AUTH_HEADERS,
            )
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["person"]["driver_person_extension"] is not None
            assert body["person"]["driver_person_extension"]["employment_relationship_type"] == "company_driver"

            ext = await tenant_session.scalar(
                select(DriverPersonExtension).where(
                    DriverPersonExtension.tenant_id == demo_tenant_id,
                    DriverPersonExtension.person_id == pid,
                )
            )
            assert ext is not None
            assert ext.driver_operating_subtype == "long_haul"
        finally:
            await tenant_session.execute(
                delete(DriverPersonExtension).where(
                    DriverPersonExtension.person_id == pid, DriverPersonExtension.tenant_id == demo_tenant_id
                )
            )
            await tenant_session.execute(
                delete(PersonRole).where(PersonRole.person_id == pid, PersonRole.tenant_id == demo_tenant_id)
            )
            await tenant_session.execute(delete(Person).where(Person.id == pid, Person.tenant_id == demo_tenant_id))
            await tenant_session.commit()
