"""People workspace compensation-setup GET/PATCH (tenant DB + API when available)."""

from __future__ import annotations

import os
import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select
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

            # Effective-dated: the 2024 version keeps its rate and closes yesterday; a new version starts today.
            await tenant_session.refresh(prof)
            assert prof.hourly_rate == Decimal("20.0000")
            today = date.today()
            assert prof.effective_to == today - timedelta(days=1)
            versions = (
                await tenant_session.execute(
                    select(CompensationProfile)
                    .where(CompensationProfile.payee_id == payee_id)
                    .order_by(CompensationProfile.effective_from)
                    .execution_options(populate_existing=True)
                )
            ).scalars().all()
            assert [(v.effective_from, v.effective_to, v.hourly_rate) for v in versions] == [
                (date(2024, 1, 1), today - timedelta(days=1), Decimal("20.0000")),
                (today, None, Decimal("44.2500")),
            ]
            assert data["person"]["compensation"]["effective_from"] == today.isoformat()
        finally:
            await tenant_session.execute(delete(CompensationProfile).where(CompensationProfile.payee_id == payee_id))
            await tenant_session.execute(delete(Driver).where(Driver.id == drv_id))
            await tenant_session.execute(delete(Payee).where(Payee.id == payee_id))
            await tenant_session.execute(delete(Person).where(Person.id == pid, Person.tenant_id == demo_tenant_id))
            await tenant_session.commit()


@pytest.mark.asyncio
@pytest.mark.skipif(REQUIRES_TENANT_DB, reason="tenant DB URL required")
class TestCompensationEffectiveDating:
    """C2/C4: versions never overlap; unchanged saves are no-ops; past dates never rewritten."""

    async def _driver_with_extension(self, session: AsyncSession, tenant_id: int) -> tuple[int, int]:
        from app.models.driver_person_extension import DriverPersonExtension

        sfx = uuid.uuid4().hex[:8]
        p = Person(tenant_id=tenant_id, first_name="Ver", last_name=f"S{sfx}")
        session.add(p)
        await session.flush()
        session.add(
            DriverPersonExtension(
                tenant_id=tenant_id,
                person_id=p.id,
                employment_relationship_type="owner_operator",
                driver_operating_subtype="long_haul",
                is_team_driver=False,
                team_role_type=None,
                provides_own_truck=True,
                provides_own_trailer=False,
                equipment_contribution_type="company_equipment",
                insurance_commercial_approved=False,
            )
        )
        drv = Driver(tenant_id=tenant_id, person_id=p.id, first_name="Ver", last_name=f"S{sfx}", is_active=True)
        session.add(drv)
        await session.commit()
        return int(p.id), int(drv.id)

    async def _cleanup(self, session: AsyncSession, tenant_id: int, person_id: int, driver_id: int) -> None:
        from app.models.driver_person_extension import DriverPersonExtension

        await session.rollback()
        payee_id = await session.scalar(select(Driver.payee_id).where(Driver.id == driver_id))
        await session.execute(delete(Driver).where(Driver.id == driver_id))
        if payee_id:
            await session.execute(delete(CompensationProfile).where(CompensationProfile.payee_id == payee_id))
            await session.execute(delete(Payee).where(Payee.id == payee_id))
        await session.execute(
            delete(DriverPersonExtension).where(
                DriverPersonExtension.tenant_id == tenant_id, DriverPersonExtension.person_id == person_id
            )
        )
        await session.execute(delete(Person).where(Person.id == person_id))
        await session.commit()

    async def _versions(self, session: AsyncSession, payee_id: int):
        return (
            await session.execute(
                select(CompensationProfile)
                .where(CompensationProfile.payee_id == payee_id)
                .order_by(CompensationProfile.effective_from)
                .execution_options(populate_existing=True)
            )
        ).scalars().all()

    async def test_versioning_rules(self, tenant_session: AsyncSession, demo_tenant_id: int) -> None:
        from app.schemas.driver_compensation_setup import DriverCompensationSetupWrite
        from app.services.driver_compensation_setup import (
            get_driver_compensation_setup,
            select_compensation_profile_for_work_date,
            upsert_driver_compensation_setup,
        )

        person_id, driver_id = await self._driver_with_extension(tenant_session, demo_tenant_id)
        today = date.today()

        def body(rate: str, start: date | None = None) -> DriverCompensationSetupWrite:
            return DriverCompensationSetupWrite(
                gross_calc_type="PERCENT_REVENUE", percent_rate=rate, effective_from=start
            )

        async def save(rate: str, start: date | None = None):
            out = await upsert_driver_compensation_setup(
                tenant_session, tenant_id=demo_tenant_id, person_id=person_id, payload=body(rate, start)
            )
            await tenant_session.commit()
            return out

        try:
            out1 = await save("0.7000")
            payee_id = int(out1.payee_id)
            assert out1.worker_type == WorkerType.OWNER_OPERATOR_LEASED_ON.value
            v = await self._versions(tenant_session, payee_id)
            assert [(x.effective_from, x.effective_to) for x in v] == [(today, None)]
            first_id = v[0].id

            # Unchanged save: no new row, no update.
            await save("0.7000")
            v = await self._versions(tenant_session, payee_id)
            assert len(v) == 1 and v[0].id == first_id

            # Same-day correction: in place.
            await save("0.7200")
            v = await self._versions(tenant_session, payee_id)
            assert len(v) == 1 and v[0].id == first_id and v[0].percent_rate == Decimal("0.7200")

            # Future-effective change: current closes the day before; current read unchanged.
            future = today + timedelta(days=10)
            out_f = await save("0.8000", future)
            assert out_f.percent_rate == Decimal("0.7200")
            assert out_f.scheduled_change_effective_from == future
            v = await self._versions(tenant_session, payee_id)
            assert [(x.effective_from, x.effective_to, x.percent_rate) for x in v] == [
                (today, future - timedelta(days=1), Decimal("0.7200")),
                (future, None, Decimal("0.8000")),
            ]

            # Correcting the scheduled version on its own date: in place.
            await save("0.8100", future)
            v = await self._versions(tenant_session, payee_id)
            assert len(v) == 2 and v[1].percent_rate == Decimal("0.8100")

            # A change starting before an existing later version is rejected (no overlap / reorder).
            for start in (today, today + timedelta(days=5)):
                with pytest.raises(ValueError, match="compensation_future_version_exists"):
                    await save("0.9000", start)
                await tenant_session.rollback()

            # Past effective dates never rewrite history.
            with pytest.raises(ValueError, match="compensation_effective_from_in_past"):
                await save("0.9000", today - timedelta(days=1))
            await tenant_session.rollback()

            # Rate selection by work date.
            async def rate_on(d: date):
                row = await select_compensation_profile_for_work_date(
                    tenant_session, tenant_id=demo_tenant_id, payee_id=payee_id, work_date=d
                )
                return row.percent_rate if row else None

            assert await rate_on(today - timedelta(days=1)) is None
            assert await rate_on(today) == Decimal("0.7200")
            assert await rate_on(future - timedelta(days=1)) == Decimal("0.7200")
            assert await rate_on(future) == Decimal("0.8100")
            assert await rate_on(future + timedelta(days=400)) == Decimal("0.8100")

            current = await get_driver_compensation_setup(
                tenant_session, tenant_id=demo_tenant_id, person_id=person_id
            )
            assert current.percent_rate == Decimal("0.7200") and current.effective_from == today
        finally:
            await self._cleanup(tenant_session, demo_tenant_id, person_id, driver_id)

    async def test_people_patch_rejects_past_effective_from_409(
        self, client: AsyncClient, override_auth_tenant, tenant_session: AsyncSession, demo_tenant_id: int
    ) -> None:
        person_id, driver_id = await self._driver_with_extension(tenant_session, demo_tenant_id)
        try:
            r = await client.patch(
                f"/api/v1/people/{person_id}/compensation-setup",
                json={**_COMP_PAYLOAD, "effective_from": (date.today() - timedelta(days=3)).isoformat()},
                headers=AUTH_HEADERS,
            )
            assert r.status_code == 409, r.text
            for bad in ("75", "1.01", "0"):
                r_bad = await client.patch(
                    f"/api/v1/people/{person_id}/compensation-setup",
                    json={**_COMP_PAYLOAD, "gross_calc_type": "PERCENT_REVENUE", "hourly_rate": None, "percent_rate": bad},
                    headers=AUTH_HEADERS,
                )
                assert r_bad.status_code == 422, (bad, r_bad.text)
        finally:
            await self._cleanup(tenant_session, demo_tenant_id, person_id, driver_id)
