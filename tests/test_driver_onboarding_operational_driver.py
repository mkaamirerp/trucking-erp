"""DRIVER PersonApplication approval materializes operational `Driver` rows for dispatch."""

from __future__ import annotations

import os
import uuid
from datetime import date

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Before importing Settings/app (matches tests/conftest.py + dispatch integration tests).
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("ALLOW_TENANT_RESOLUTION_SHORTCUTS", "true")

from app.core.db_url import to_async_pg_url
from app.main import app
from app.models.driver import Driver
from app.models.person import DriverProfile, Person, PersonRole
from app.models.person_application import PersonApplication
from app.schemas.driver_onboarding import DriverOnboardingStatus
from tests.support.integration_auth import (
    clear_current_user_and_tenant_overrides,
    install_host_aligned_current_user_and_tenant,
)
from tests.support.tenant_test_ids import platform_tenant_id_for_slug

REQUIRES_DB = not os.environ.get("DATABASE_URL")


def _tenant_async_url() -> str | None:
    raw = os.environ.get("TENANT_DATABASE_URL") or os.environ.get("ALEMBIC_TENANT_DATABASE_URL")
    if not raw:
        return None
    return to_async_pg_url(raw)


REQUIRES_TENANT_DB = _tenant_async_url() is None

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
@pytest.mark.skipif(REQUIRES_DB, reason="DATABASE_URL required")
@pytest.mark.skipif(REQUIRES_TENANT_DB, reason="tenant DB URL required")
class TestOperationalDriverOnApproval:
    async def test_approve_driver_creates_operational_driver(
        self,
        client: AsyncClient,
        override_auth_tenant,
        tenant_session: AsyncSession,
        demo_tenant_id: int,
    ) -> None:
        suffix = uuid.uuid4().hex[:10]
        email = f"opdrv.{suffix}@driver-onboarding-test.invalid"
        app_row = PersonApplication(
            tenant_id=demo_tenant_id,
            source="integration_test",
            status=DriverOnboardingStatus.SUBMITTED.value,
            requested_role_code="DRIVER",
            application_type="DRIVER",
            first_name="Jane",
            last_name=f"Test{suffix}",
            email=email,
            phone="+15555550201",
            intake_payload={
                "driver_license_number": f"DL-{suffix}",
                "license_region": "TX",
                "license_expiry": "2031-06-15",
            },
        )
        tenant_session.add(app_row)
        await tenant_session.commit()
        await tenant_session.refresh(app_row)
        app_id = int(app_row.id)

        r = await client.post(
            f"/api/v1/driver-onboarding/applications/{app_id}/approve",
            headers=AUTH_HEADERS,
        )
        assert r.status_code == 200, r.text

        person_id = (await tenant_session.scalar(select(PersonApplication.person_id).where(PersonApplication.id == app_id)))
        assert person_id is not None
        person = await tenant_session.get(Person, int(person_id))
        assert person is not None
        assert person.tenant_id == demo_tenant_id

        prof = await tenant_session.scalar(
            select(DriverProfile).where(
                DriverProfile.tenant_id == demo_tenant_id,
                DriverProfile.person_id == person.id,
            )
        )
        assert prof is not None

        drv = await tenant_session.scalar(
            select(Driver).where(Driver.tenant_id == demo_tenant_id, Driver.person_id == person.id)
        )
        assert drv is not None
        assert drv.is_active is True
        assert drv.person_id == person.id
        assert drv.first_name == person.first_name
        assert drv.license_number == f"DL-{suffix}"
        assert drv.issuing_region == "TX"
        assert drv.license_expiry_date == date(2031, 6, 15)

        listed = await client.get(
            "/api/v1/drivers",
            params={"q": email, "limit": 20},
            headers=AUTH_HEADERS,
        )
        assert listed.status_code == 200
        ids = {int(x["id"]) for x in listed.json()}
        assert drv.id in ids

        await tenant_session.execute(delete(Driver).where(Driver.id == drv.id))
        await tenant_session.execute(delete(DriverProfile).where(DriverProfile.id == prof.id))
        await tenant_session.execute(delete(PersonRole).where(PersonRole.person_id == person.id, PersonRole.tenant_id == demo_tenant_id))
        await tenant_session.execute(delete(Person).where(Person.id == person.id))
        await tenant_session.execute(delete(PersonApplication).where(PersonApplication.id == app_id))
        await tenant_session.commit()

    async def test_reapprove_idempotent_single_driver_row(
        self,
        client: AsyncClient,
        override_auth_tenant,
        tenant_session: AsyncSession,
        demo_tenant_id: int,
    ) -> None:
        suffix = uuid.uuid4().hex[:10]
        email = f"idemp.{suffix}@driver-onboarding-test.invalid"
        app_row = PersonApplication(
            tenant_id=demo_tenant_id,
            source="integration_test",
            status=DriverOnboardingStatus.SUBMITTED.value,
            requested_role_code="DRIVER",
            application_type="DRIVER",
            first_name="Idem",
            last_name=f"P{suffix}",
            email=email,
            intake_payload={"driver_license_number": f"I-{suffix}", "license_region": "OK"},
        )
        tenant_session.add(app_row)
        await tenant_session.commit()
        await tenant_session.refresh(app_row)
        app_id = int(app_row.id)

        r1 = await client.post(f"/api/v1/driver-onboarding/applications/{app_id}/approve", headers=AUTH_HEADERS)
        assert r1.status_code == 200, r1.text
        person_id = int((await tenant_session.scalar(select(PersonApplication.person_id).where(PersonApplication.id == app_id))) or 0)
        cnt1 = await tenant_session.scalar(
            select(func.count()).select_from(Driver).where(Driver.tenant_id == demo_tenant_id, Driver.person_id == person_id)
        )

        r2 = await client.post(f"/api/v1/driver-onboarding/applications/{app_id}/approve", headers=AUTH_HEADERS)
        assert r2.status_code == 200, r2.text
        cnt2 = await tenant_session.scalar(
            select(func.count()).select_from(Driver).where(Driver.tenant_id == demo_tenant_id, Driver.person_id == person_id)
        )
        assert int(cnt1) == 1 and int(cnt2) == 1

        drv = await tenant_session.scalar(select(Driver).where(Driver.tenant_id == demo_tenant_id, Driver.person_id == person_id))
        prof = await tenant_session.scalar(select(DriverProfile).where(DriverProfile.person_id == person_id, DriverProfile.tenant_id == demo_tenant_id))
        person = await tenant_session.get(Person, person_id)
        assert drv and prof and person
        await tenant_session.execute(delete(Driver).where(Driver.id == drv.id))
        await tenant_session.execute(delete(DriverProfile).where(DriverProfile.id == prof.id))
        await tenant_session.execute(delete(PersonRole).where(PersonRole.person_id == person.id, PersonRole.tenant_id == demo_tenant_id))
        await tenant_session.execute(delete(Person).where(Person.id == person.id))
        await tenant_session.execute(delete(PersonApplication).where(PersonApplication.id == app_id))
        await tenant_session.commit()

    async def test_non_driver_approval_no_driver_row(
        self,
        client: AsyncClient,
        override_auth_tenant,
        tenant_session: AsyncSession,
        demo_tenant_id: int,
    ) -> None:
        suffix = uuid.uuid4().hex[:10]
        email = f"hr.{suffix}@driver-onboarding-test.invalid"
        app_row = PersonApplication(
            tenant_id=demo_tenant_id,
            source="integration_test",
            status=DriverOnboardingStatus.SUBMITTED.value,
            requested_role_code="DISPATCHER",
            application_type="DRIVER",
            first_name="Pat",
            last_name=f"HR{suffix}",
            email=email,
            intake_payload={},
        )
        tenant_session.add(app_row)
        await tenant_session.commit()
        await tenant_session.refresh(app_row)
        app_id = int(app_row.id)

        r = await client.post(f"/api/v1/driver-onboarding/applications/{app_id}/approve", headers=AUTH_HEADERS)
        assert r.status_code == 200, r.text

        person_id = int((await tenant_session.scalar(select(PersonApplication.person_id).where(PersonApplication.id == app_id))) or 0)
        person = await tenant_session.get(Person, person_id)
        assert person is not None

        n_drivers = await tenant_session.scalar(
            select(func.count()).select_from(Driver).where(Driver.tenant_id == demo_tenant_id, Driver.person_id == person_id)
        )
        assert int(n_drivers or 0) == 0

        await tenant_session.execute(delete(PersonRole).where(PersonRole.person_id == person.id, PersonRole.tenant_id == demo_tenant_id))
        await tenant_session.execute(delete(Person).where(Person.id == person.id))
        await tenant_session.execute(delete(PersonApplication).where(PersonApplication.id == app_id))
        await tenant_session.commit()

    async def test_draft_application_not_in_drivers_list(
        self,
        client: AsyncClient,
        override_auth_tenant,
        tenant_session: AsyncSession,
        demo_tenant_id: int,
    ) -> None:
        suffix = uuid.uuid4().hex[:10]
        email = f"draft.{suffix}@driver-onboarding-test.invalid"
        app_row = PersonApplication(
            tenant_id=demo_tenant_id,
            source="integration_test",
            status=DriverOnboardingStatus.DRAFT.value,
            requested_role_code="DRIVER",
            application_type="DRIVER",
            first_name="Drafty",
            last_name=f"Mc{suffix}",
            email=email,
            intake_payload={"driver_license_number": f"D-{suffix}"},
        )
        tenant_session.add(app_row)
        await tenant_session.commit()
        await tenant_session.refresh(app_row)
        app_id = int(app_row.id)

        listed = await client.get("/api/v1/drivers", params={"q": email, "limit": 20}, headers=AUTH_HEADERS)
        assert listed.status_code == 200
        assert listed.json() == []

        await tenant_session.execute(delete(PersonApplication).where(PersonApplication.id == app_id))
        await tenant_session.commit()

    async def test_existing_driver_row_updated_in_place(
        self,
        client: AsyncClient,
        override_auth_tenant,
        tenant_session: AsyncSession,
        demo_tenant_id: int,
    ) -> None:
        suffix = uuid.uuid4().hex[:10]
        email = f"preop.{suffix}@driver-onboarding-test.invalid"

        person = Person(
            tenant_id=demo_tenant_id,
            first_name="OldFirst",
            last_name=f"LN{suffix}",
            email=email,
            phone="+15555550333",
        )
        tenant_session.add(person)
        await tenant_session.flush()

        existing = Driver(
            tenant_id=demo_tenant_id,
            person_id=person.id,
            first_name="OldFirst",
            last_name=f"LN{suffix}",
            email=email,
            phone="+19999999999",
            is_active=False,
            license_number="OLD-LIC",
            issuing_region="CA",
        )
        tenant_session.add(existing)
        await tenant_session.commit()
        await tenant_session.refresh(person)
        drv_id = int(existing.id)

        app_row = PersonApplication(
            tenant_id=demo_tenant_id,
            source="integration_test",
            person_id=person.id,
            status=DriverOnboardingStatus.SUBMITTED.value,
            requested_role_code="DRIVER",
            application_type="DRIVER",
            first_name="NewFirst",
            last_name=f"LN{suffix}",
            email=email,
            phone="+15555550333",
            intake_payload={
                "driver_license_number": f"NEW-{suffix}",
                "license_region": "NY",
                "license_expiry": "2032-03-20",
            },
        )
        tenant_session.add(app_row)
        await tenant_session.commit()
        await tenant_session.refresh(app_row)
        app_id = int(app_row.id)

        r = await client.post(f"/api/v1/driver-onboarding/applications/{app_id}/approve", headers=AUTH_HEADERS)
        assert r.status_code == 200, r.text

        # Approval used another DB session; reload the same ORM instance from the database.
        await tenant_session.refresh(existing)
        again = existing
        assert again is not None
        assert again.first_name == "NewFirst"
        assert again.is_active is True
        assert again.license_number == f"NEW-{suffix}"
        assert again.issuing_region == "NY"
        assert again.license_expiry_date == date(2032, 3, 20)

        cnt = await tenant_session.scalar(
            select(func.count()).select_from(Driver).where(Driver.tenant_id == demo_tenant_id, Driver.person_id == person.id)
        )
        assert int(cnt) == 1

        prof = await tenant_session.scalar(
            select(DriverProfile).where(DriverProfile.person_id == person.id, DriverProfile.tenant_id == demo_tenant_id)
        )
        await tenant_session.execute(delete(Driver).where(Driver.id == drv_id))
        if prof:
            await tenant_session.execute(delete(DriverProfile).where(DriverProfile.id == prof.id))
        await tenant_session.execute(delete(PersonRole).where(PersonRole.person_id == person.id, PersonRole.tenant_id == demo_tenant_id))
        await tenant_session.execute(delete(Person).where(Person.id == person.id))
        await tenant_session.execute(delete(PersonApplication).where(PersonApplication.id == app_id))
        await tenant_session.commit()

    async def test_duplicate_drivers_deactivated_survivor_lowest_id(
        self,
        client: AsyncClient,
        override_auth_tenant,
        tenant_session: AsyncSession,
        demo_tenant_id: int,
    ) -> None:
        suffix = uuid.uuid4().hex[:10]
        email = f"dup.{suffix}@driver-onboarding-test.invalid"

        person = Person(
            tenant_id=demo_tenant_id,
            first_name="Dup",
            last_name=f"P{suffix}",
            email=email,
            phone="+15555550444",
        )
        tenant_session.add(person)
        await tenant_session.flush()

        survivor = Driver(
            tenant_id=demo_tenant_id,
            person_id=person.id,
            first_name="Dup",
            last_name=f"P{suffix}",
            email=email,
            is_active=True,
            license_number="DUP-A",
            issuing_region="TX",
        )
        duplicate = Driver(
            tenant_id=demo_tenant_id,
            person_id=person.id,
            first_name="Dup",
            last_name=f"P{suffix}",
            email=email,
            is_active=True,
            license_number="DUP-B",
            issuing_region="TX",
        )
        tenant_session.add(survivor)
        tenant_session.add(duplicate)
        await tenant_session.commit()
        await tenant_session.refresh(survivor)
        await tenant_session.refresh(duplicate)
        assert survivor.id < duplicate.id

        app_row = PersonApplication(
            tenant_id=demo_tenant_id,
            source="integration_test",
            person_id=person.id,
            status=DriverOnboardingStatus.SUBMITTED.value,
            requested_role_code="DRIVER",
            application_type="DRIVER",
            first_name="Dup",
            last_name=f"P{suffix}",
            email=email,
            intake_payload={
                "driver_license_number": f"DUP-CANON-{suffix}",
                "license_region": "OK",
                "license_expiry": "2033-01-10",
            },
        )
        tenant_session.add(app_row)
        await tenant_session.commit()
        await tenant_session.refresh(app_row)
        app_id = int(app_row.id)

        r = await client.post(f"/api/v1/driver-onboarding/applications/{app_id}/approve", headers=AUTH_HEADERS)
        assert r.status_code == 200, r.text

        await tenant_session.refresh(survivor)
        await tenant_session.refresh(duplicate)

        active_for_person = (
            await tenant_session.execute(
                select(Driver).where(
                    Driver.tenant_id == demo_tenant_id,
                    Driver.person_id == person.id,
                    Driver.is_active.is_(True),
                )
            )
        ).scalars().all()
        assert len(active_for_person) == 1
        assert active_for_person[0].id == survivor.id
        assert survivor.is_active is True
        assert survivor.license_number == f"DUP-CANON-{suffix}"
        assert survivor.issuing_region == "OK"
        assert survivor.license_expiry_date == date(2033, 1, 10)
        assert duplicate.is_active is False

        listed = await client.get("/api/v1/drivers", params={"q": email, "limit": 20}, headers=AUTH_HEADERS)
        assert listed.status_code == 200
        body = listed.json()
        assert len(body) == 1
        assert int(body[0]["id"]) == survivor.id

        prof = await tenant_session.scalar(
            select(DriverProfile).where(DriverProfile.person_id == person.id, DriverProfile.tenant_id == demo_tenant_id)
        )
        await tenant_session.execute(delete(Driver).where(Driver.id.in_([survivor.id, duplicate.id])))
        if prof:
            await tenant_session.execute(delete(DriverProfile).where(DriverProfile.id == prof.id))
        await tenant_session.execute(delete(PersonRole).where(PersonRole.person_id == person.id, PersonRole.tenant_id == demo_tenant_id))
        await tenant_session.execute(delete(Person).where(Person.id == person.id))
        await tenant_session.execute(delete(PersonApplication).where(PersonApplication.id == app_id))
        await tenant_session.commit()
