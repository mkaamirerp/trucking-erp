"""People workspace compensation-setup GET/PATCH (tenant DB + API when available)."""

from __future__ import annotations

import os
import uuid
from datetime import date
from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("ALLOW_TENANT_RESOLUTION_SHORTCUTS", "true")

from app.core.db_url import to_async_pg_url
from app.main import app
from app.models.driver import Driver
from app.models.enums import GrossCalcType, PayeeType, SettlementFrequency, WorkerType
from app.models.payee import CompensationProfile, Payee
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
AUTH_HEADERS = {"host": "pytest.truckerp.me"}

_COMP_PAYLOAD = {
    "gross_calc_type": "HOURLY",
    "hourly_rate": "33.5000",
    "percent_rate": None,
    "cpm_loaded": None,
    "cpm_empty": None,
    "salary_amount": None,
    "flat_amount": None,
    "settlement_frequency": "BIWEEKLY",
    "participates_in_fuel_discount_program": False,
    "dispatch_fee_enabled": False,
    "dispatch_fee_rate": "0",
    "dispatch_fee_basis": "GROSS",
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
class TestPeopleWorkspaceCompensation:
    async def test_patch_409_no_operational_driver(
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
            last_name=f"Drv{suffix}",
            email=f"nocmp.{suffix}@pws-test.invalid",
        )
        tenant_session.add(p)
        await tenant_session.commit()
        await tenant_session.refresh(p)
        pid = int(p.id)
        try:
            r = await client.patch(
                f"/api/v1/people/{pid}/compensation-setup",
                json=_COMP_PAYLOAD,
                headers=AUTH_HEADERS,
            )
            assert r.status_code == 409, r.text
        finally:
            await tenant_session.execute(delete(Person).where(Person.id == pid, Person.tenant_id == demo_tenant_id))
            await tenant_session.commit()

    async def test_patch_409_no_payee_requires_classification_to_bootstrap(
        self,
        client: AsyncClient,
        override_auth_tenant,
        tenant_session: AsyncSession,
        demo_tenant_id: int,
    ) -> None:
        suffix = uuid.uuid4().hex[:10]
        email = f"nopayee.{suffix}@pws-test.invalid"
        p = Person(
            tenant_id=demo_tenant_id,
            first_name="P",
            last_name=f"X{suffix}",
            email=email,
        )
        tenant_session.add(p)
        await tenant_session.flush()
        drv = Driver(
            tenant_id=demo_tenant_id,
            person_id=p.id,
            first_name="P",
            last_name=f"X{suffix}",
            email=email,
            is_active=True,
        )
        tenant_session.add(drv)
        await tenant_session.commit()
        await tenant_session.refresh(p)
        pid = int(p.id)
        drv_id = int(drv.id)
        try:
            r = await client.patch(
                f"/api/v1/people/{pid}/compensation-setup",
                json=_COMP_PAYLOAD,
                headers=AUTH_HEADERS,
            )
            assert r.status_code == 409, r.text
            assert "payee" in r.text.lower() or "classification" in r.text.lower()
        finally:
            await tenant_session.execute(delete(Driver).where(Driver.id == drv_id))
            await tenant_session.execute(delete(Person).where(Person.id == pid, Person.tenant_id == demo_tenant_id))
            await tenant_session.commit()

    async def test_patch_updates_open_compensation_profile(
        self,
        client: AsyncClient,
        override_auth_tenant,
        tenant_session: AsyncSession,
        demo_tenant_id: int,
    ) -> None:
        suffix = uuid.uuid4().hex[:10]
        email = f"cmp.{suffix}@pws-test.invalid"
        p = Person(
            tenant_id=demo_tenant_id,
            first_name="C",
            last_name=f"M{suffix}",
            email=email,
        )
        tenant_session.add(p)
        await tenant_session.flush()
        payee = Payee(
            tenant_id=demo_tenant_id,
            payee_type=PayeeType.DRIVER,
            worker_type=WorkerType.EMPLOYEE_DRIVER,
            display_name=f"C M{suffix}",
            is_active=True,
        )
        tenant_session.add(payee)
        await tenant_session.flush()
        drv = Driver(
            tenant_id=demo_tenant_id,
            person_id=p.id,
            payee_id=payee.id,
            first_name="C",
            last_name=f"M{suffix}",
            email=email,
            is_active=True,
        )
        tenant_session.add(drv)
        await tenant_session.flush()
        prof = CompensationProfile(
            tenant_id=demo_tenant_id,
            payee_id=payee.id,
            effective_from=date(2024, 1, 1),
            effective_to=None,
            worker_type_snapshot=WorkerType.EMPLOYEE_DRIVER,
            gross_calc_type=GrossCalcType.HOURLY,
            hourly_rate=Decimal("20.0000"),
            settlement_frequency=SettlementFrequency.BIWEEKLY,
            participates_in_fuel_discount_program=False,
            dispatch_fee_enabled=False,
            dispatch_fee_rate=Decimal("0"),
            dispatch_fee_basis="GROSS",
        )
        tenant_session.add(prof)
        await tenant_session.commit()
        await tenant_session.refresh(p)
        pid = int(p.id)
        drv_id = int(drv.id)
        payee_id = int(payee.id)
        prof_id = int(prof.id)
        try:
            body = {**_COMP_PAYLOAD, "hourly_rate": "44.2500"}
            r = await client.patch(
                f"/api/v1/people/{pid}/compensation-setup",
                json=body,
                headers=AUTH_HEADERS,
            )
            assert r.status_code == 200, r.text
            data = r.json()
            assert data["person"]["compensation"]["hourly_rate"] is not None
            assert float(data["person"]["compensation"]["hourly_rate"]) == pytest.approx(44.25)

            await tenant_session.refresh(prof)
            assert prof.hourly_rate == Decimal("44.2500")
        finally:
            await tenant_session.execute(delete(CompensationProfile).where(CompensationProfile.id == prof_id))
            await tenant_session.execute(delete(Driver).where(Driver.id == drv_id))
            await tenant_session.execute(delete(Payee).where(Payee.id == payee_id))
            await tenant_session.execute(delete(Person).where(Person.id == pid, Person.tenant_id == demo_tenant_id))
            await tenant_session.commit()
