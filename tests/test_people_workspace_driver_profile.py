"""People workspace PATCH driver-profile (tenant DB + API when available)."""

from __future__ import annotations

import os
import uuid
from datetime import date

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("ALLOW_TENANT_RESOLUTION_SHORTCUTS", "true")

from app.core.db_url import to_async_pg_url
from app.main import app
from app.models.driver import Driver
from app.models.person import DriverProfile, Person, PersonRole
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
class TestPeopleWorkspaceDriverProfilePatch:
    async def test_409_without_active_driver_role(
        self,
        client: AsyncClient,
        override_auth_tenant,
        tenant_session: AsyncSession,
        demo_tenant_id: int,
    ) -> None:
        suffix = uuid.uuid4().hex[:10]
        p = Person(
            tenant_id=demo_tenant_id,
            first_name="No",
            last_name=f"Drv{suffix}",
            email=f"nodrv.{suffix}@pws-test.invalid",
        )
        tenant_session.add(p)
        await tenant_session.commit()
        await tenant_session.refresh(p)
        pid = int(p.id)

        try:
            r = await client.patch(
                f"/api/v1/people/{pid}/driver-profile",
                json={"license_number": "X"},
                headers=AUTH_HEADERS,
            )
            assert r.status_code == 409, r.text
        finally:
            await tenant_session.execute(delete(Person).where(Person.id == pid, Person.tenant_id == demo_tenant_id))
            await tenant_session.commit()

    async def test_patch_creates_profile_and_syncs_active_driver(
        self,
        client: AsyncClient,
        override_auth_tenant,
        tenant_session: AsyncSession,
        demo_tenant_id: int,
    ) -> None:
        suffix = uuid.uuid4().hex[:10]
        email = f"pws.lic.{suffix}@pws-test.invalid"
        p = Person(
            tenant_id=demo_tenant_id,
            first_name="Lic",
            last_name=f"P{suffix}",
            email=email,
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
        drv = Driver(
            tenant_id=demo_tenant_id,
            person_id=p.id,
            first_name="Lic",
            last_name=f"P{suffix}",
            email=email,
            is_active=True,
            license_number="OLD",
            issuing_region="ZZ",
        )
        tenant_session.add(drv)
        await tenant_session.commit()
        await tenant_session.refresh(p)
        await tenant_session.refresh(drv)
        pid = int(p.id)
        drv_id = int(drv.id)

        try:
            r = await client.patch(
                f"/api/v1/people/{pid}/driver-profile",
                json={
                    "license_number": f"NEW-{suffix}",
                    "license_region": "CA",
                    "license_expiry": "2031-06-15",
                    "is_active": True,
                },
                headers=AUTH_HEADERS,
            )
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["person"]["driver_profile"] is not None
            assert body["person"]["driver_profile"]["license_number"] == f"NEW-{suffix}"
            assert body["person"]["driver_profile"]["license_region"] == "CA"
            assert body["person"]["driver_profile"]["license_expiry"] == "2031-06-15"
            assert drv_id in body.get("synced_operational_driver_ids", [])

            dp = await tenant_session.scalar(
                select(DriverProfile).where(
                    DriverProfile.tenant_id == demo_tenant_id,
                    DriverProfile.person_id == pid,
                )
            )
            assert dp is not None
            assert dp.license_number == f"NEW-{suffix}"
            assert dp.license_region == "CA"
            assert dp.license_expiry == date(2031, 6, 15)

            await tenant_session.refresh(drv)
            assert drv.license_number == f"NEW-{suffix}"
            assert drv.issuing_region == "CA"
            assert drv.license_expiry_date == date(2031, 6, 15)
        finally:
            await tenant_session.execute(delete(Driver).where(Driver.id == drv_id))
            await tenant_session.execute(
                delete(DriverProfile).where(DriverProfile.person_id == pid, DriverProfile.tenant_id == demo_tenant_id)
            )
            await tenant_session.execute(
                delete(PersonRole).where(PersonRole.person_id == pid, PersonRole.tenant_id == demo_tenant_id)
            )
            await tenant_session.execute(delete(Person).where(Person.id == pid, Person.tenant_id == demo_tenant_id))
            await tenant_session.commit()
