"""B2: centralized driver eligibility on new trip assignment (onboarding/termination/inactive)."""

from __future__ import annotations

import os
import uuid
from datetime import date

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("ALLOW_TENANT_RESOLUTION_SHORTCUTS", "true")

from app.core.db_url import to_async_pg_url
from app.main import app
from app.models.driver import Driver
from app.models.person import Person
from app.models.person_application import PersonApplication
from app.schemas.driver_onboarding import DriverOnboardingStatus
from app.services.trips import DRIVER_NOT_ASSIGNABLE
from tests.support.integration_auth import (
    clear_current_user_and_tenant_overrides,
    install_host_aligned_current_user_and_tenant,
)
from tests.support.tenant_test_ids import platform_tenant_id_for_slug

AUTH_HEADERS = {"host": "pytest.truckerp.me"}


def _tenant_async_url() -> str | None:
    raw = os.environ.get("TENANT_DATABASE_URL") or os.environ.get("ALEMBIC_TENANT_DATABASE_URL")
    return to_async_pg_url(raw) if raw else None


REQUIRES_DB = not os.environ.get("DATABASE_URL") or _tenant_async_url() is None


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest.fixture
def override_auth_tenant():
    old = os.environ.get("TEST_BYPASS_AUTH")
    os.environ["TEST_BYPASS_AUTH"] = "1"
    install_host_aligned_current_user_and_tenant(app)
    yield
    clear_current_user_and_tenant_overrides(app)
    if old is None:
        os.environ.pop("TEST_BYPASS_AUTH", None)
    else:
        os.environ["TEST_BYPASS_AUTH"] = old


@pytest.fixture
async def tenant_session():
    engine = create_async_engine(_tenant_async_url(), pool_pre_ping=True)
    Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    try:
        async with Session() as session:
            yield session
    finally:
        await engine.dispose()


@pytest.fixture
async def tenant_id():
    return await platform_tenant_id_for_slug()


@pytest.fixture
async def locked_prefix(client, override_auth_tenant) -> None:
    r0 = await client.get("/api/v1/admin/dispatch-numbering", headers=AUTH_HEADERS)
    assert r0.status_code == 200, r0.text
    if r0.json().get("prefix_locked") and r0.json().get("trip_number_prefix"):
        return
    r1 = await client.put(
        "/api/v1/admin/dispatch-numbering",
        headers=AUTH_HEADERS,
        json={"trip_number_prefix": f"E{uuid.uuid4().hex[:7].upper()}"},
    )
    assert r1.status_code == 200, r1.text


class _Fixtures:
    def __init__(self, session: AsyncSession, tenant_id: int) -> None:
        self.s = session
        self.tenant_id = tenant_id
        self.person_ids: list[int] = []
        self.driver_ids: list[int] = []
        self.trip_ids: list[int] = []

    async def driver(
        self,
        *,
        app_status: str | None,
        is_active: bool = True,
        termination_date: date | None = None,
        person_active: bool = True,
    ) -> int:
        sfx = uuid.uuid4().hex[:8]
        person = Person(tenant_id=self.tenant_id, first_name="Elig", last_name=f"T{sfx}", is_active=person_active)
        self.s.add(person)
        await self.s.flush()
        self.person_ids.append(int(person.id))
        if app_status is not None:
            self.s.add(
                PersonApplication(
                    tenant_id=self.tenant_id,
                    source="integration_test",
                    person_id=person.id,
                    status=app_status,
                    requested_role_code="DRIVER",
                    application_type="DRIVER",
                    first_name="Elig",
                    last_name=f"T{sfx}",
                )
            )
        drv = Driver(
            tenant_id=self.tenant_id,
            person_id=person.id,
            first_name="Elig",
            last_name=f"T{sfx}",
            is_active=is_active,
            termination_date=termination_date,
        )
        self.s.add(drv)
        await self.s.commit()
        self.driver_ids.append(int(drv.id))
        return int(drv.id)

    async def cleanup(self) -> None:
        await self.s.rollback()
        if self.trip_ids:
            await self.s.execute(
                text("UPDATE trips SET driver_id = NULL WHERE tenant_id = :t AND id = ANY(:ids)"),
                {"t": self.tenant_id, "ids": self.trip_ids},
            )
        if self.driver_ids:
            await self.s.execute(delete(Driver).where(Driver.id.in_(self.driver_ids)))
        if self.person_ids:
            await self.s.execute(delete(PersonApplication).where(PersonApplication.person_id.in_(self.person_ids)))
            await self.s.execute(delete(Person).where(Person.id.in_(self.person_ids)))
        await self.s.commit()


async def _new_no_load_trip(client: AsyncClient, fx: _Fixtures) -> int:
    r = await client.post(
        "/api/v1/trips",
        headers=AUTH_HEADERS,
        json={"status": "planned", "job_type": "freight_load", "load_ids": []},
    )
    assert r.status_code == 201, r.text
    trip_id = int(r.json()["id"])
    fx.trip_ids.append(trip_id)
    return trip_id


async def _assign(client: AsyncClient, trip_id: int, driver_id: int | None, truck_id: int | None = None):
    return await client.put(
        f"/api/v1/trips/{trip_id}/assignment",
        headers=AUTH_HEADERS,
        json={"driver_id": driver_id, "truck_id": truck_id, "trailer_id": None},
    )


@pytest.mark.skipif(REQUIRES_DB, reason="integration DB required")
@pytest.mark.asyncio
class TestDriverAssignmentEligibility:
    @pytest.mark.parametrize(
        "kwargs, reason_fragment",
        [
            ({"app_status": DriverOnboardingStatus.SUBMITTED.value}, "not approved"),
            ({"app_status": DriverOnboardingStatus.REJECTED.value}, "not approved"),
            ({"app_status": DriverOnboardingStatus.DRAFT.value}, "not approved"),
            ({"app_status": None, "termination_date": date(2026, 1, 1), "is_active": True}, "terminated"),
            ({"app_status": None, "is_active": False}, "inactive"),
            ({"app_status": DriverOnboardingStatus.APPROVED.value, "person_active": False}, "person record"),
        ],
    )
    async def test_ineligible_driver_rejected_on_new_assignment(
        self, client, override_auth_tenant, locked_prefix, tenant_session, tenant_id, kwargs, reason_fragment
    ):
        fx = _Fixtures(tenant_session, tenant_id)
        try:
            d_id = await fx.driver(**kwargs)
            trip_id = await _new_no_load_trip(client, fx)
            r = await _assign(client, trip_id, d_id)
            assert r.status_code == 409, r.text
            detail = r.json()["detail"]
            assert detail["code"] == DRIVER_NOT_ASSIGNABLE
            assert reason_fragment in detail["detail"].lower()
        finally:
            await fx.cleanup()

    @pytest.mark.parametrize(
        "app_status",
        [DriverOnboardingStatus.APPROVED.value, None],
        ids=["approved_application", "grandfathered_no_application"],
    )
    async def test_eligible_driver_assigned_to_no_load_trip(
        self, client, override_auth_tenant, locked_prefix, tenant_session, tenant_id, app_status
    ):
        fx = _Fixtures(tenant_session, tenant_id)
        try:
            d_id = await fx.driver(app_status=app_status)
            trip_id = await _new_no_load_trip(client, fx)
            r = await _assign(client, trip_id, d_id)
            assert r.status_code == 200, r.text
            assert r.json()["driver_id"] == d_id
        finally:
            await fx.cleanup()

    async def test_existing_assignment_editable_after_driver_terminated(
        self, client, override_auth_tenant, locked_prefix, tenant_session, tenant_id
    ):
        fx = _Fixtures(tenant_session, tenant_id)
        try:
            d_id = await fx.driver(app_status=DriverOnboardingStatus.APPROVED.value)
            trip_id = await _new_no_load_trip(client, fx)
            assert (await _assign(client, trip_id, d_id)).status_code == 200
            await tenant_session.execute(
                text("UPDATE drivers SET is_active = false, termination_date = CURRENT_DATE WHERE id = :id"),
                {"id": d_id},
            )
            await tenant_session.commit()
            # Same driver kept (historical assignment): not re-checked.
            r_same = await _assign(client, trip_id, d_id)
            assert r_same.status_code == 200, r_same.text
            # Unassign is always allowed; re-assigning the terminated driver is a new assignment.
            assert (await _assign(client, trip_id, None)).status_code == 200
            r_again = await _assign(client, trip_id, d_id)
            assert r_again.status_code == 409, r_again.text
        finally:
            await fx.cleanup()
