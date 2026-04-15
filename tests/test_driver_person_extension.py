"""Phase 3A driver_person_extensions API and validation (tenant DB when available)."""

from __future__ import annotations

import os
import uuid

import pytest
from pydantic import ValidationError

from app.schemas.driver_person_extension import DriverPersonExtensionWrite
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("ALLOW_TENANT_RESOLUTION_SHORTCUTS", "true")

from app.core.db_url import to_async_pg_url
from app.main import app
from app.models.driver_person_extension import DriverPersonExtension
from app.models.person import Person
from tests.support.integration_auth import (
    clear_current_user_and_tenant_overrides,
    install_host_aligned_current_user_and_tenant,
    install_mutable_tenant_current_user_and_tenant,
)
from tests.support.tenant_test_ids import platform_tenant_id_for_slug


def _tenant_async_url() -> str | None:
    raw = os.environ.get("TENANT_DATABASE_URL") or os.environ.get("ALEMBIC_TENANT_DATABASE_URL")
    if not raw:
        return None
    return to_async_pg_url(raw)


REQUIRES_TENANT_DB = _tenant_async_url() is None
# Integration tests also resolve demo tenant via platform DB (DATABASE_URL).
REQUIRES_INTEGRATION_DB = REQUIRES_TENANT_DB or not (os.environ.get("DATABASE_URL") or "").strip()
AUTH_HEADERS = {"host": "demo.truckerp.me"}


def _valid_body(**overrides):
    base = {
        "employment_relationship_type": "company_driver",
        "driver_operating_subtype": "long_haul",
        "is_team_driver": False,
        "team_role_type": None,
        "provides_own_truck": False,
        "provides_own_trailer": False,
        "equipment_contribution_type": "company_equipment",
        "insurance_commercial_approved": False,
    }
    base.update(overrides)
    return base


class TestDriverPersonExtensionWriteValidation:
    """No DB — Pydantic rules only."""

    def test_owner_operator_forbidden_as_subtype(self) -> None:
        with pytest.raises(ValidationError) as ei:
            DriverPersonExtensionWrite(
                **_valid_body(driver_operating_subtype="owner_operator"),
            )
        assert "owner_operator" in str(ei.value).lower()

    def test_contractor_rejected(self) -> None:
        with pytest.raises(ValidationError):
            DriverPersonExtensionWrite(
                **_valid_body(employment_relationship_type="contractor"),
            )

    def test_team_role_required_when_team(self) -> None:
        with pytest.raises(ValidationError):
            DriverPersonExtensionWrite(
                **_valid_body(is_team_driver=True, team_role_type=None),
            )

    def test_team_role_forbidden_when_not_team(self) -> None:
        with pytest.raises(ValidationError):
            DriverPersonExtensionWrite(
                **_valid_body(is_team_driver=False, team_role_type="primary"),
            )

    def test_equipment_contradiction_company_equipment(self) -> None:
        with pytest.raises(ValidationError):
            DriverPersonExtensionWrite(
                **_valid_body(
                    equipment_contribution_type="company_equipment",
                    provides_own_truck=True,
                    provides_own_trailer=False,
                ),
            )

    def test_valid_team_payload(self) -> None:
        m = DriverPersonExtensionWrite(
            **_valid_body(
                is_team_driver=True,
                team_role_type="primary",
            ),
        )
        assert m.team_role_type == "primary"


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
class TestDriverPersonExtensionAPI:
    async def test_put_get_round_trip(
        self,
        client: AsyncClient,
        override_auth_tenant,
        tenant_session: AsyncSession,
        demo_tenant_id: int,
    ) -> None:
        suffix = uuid.uuid4().hex[:10]
        p = Person(
            tenant_id=demo_tenant_id,
            first_name="Ext",
            last_name=f"T{suffix}",
            email=f"ext.{suffix}@dpe-test.invalid",
        )
        tenant_session.add(p)
        await tenant_session.commit()
        await tenant_session.refresh(p)
        pid = int(p.id)

        r = await client.put(
            f"/api/v1/driver-person-extensions/{pid}",
            json=_valid_body(),
            headers=AUTH_HEADERS,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["person_id"] == pid
        assert data["employment_relationship_type"] == "company_driver"

        g = await client.get(f"/api/v1/driver-person-extensions/{pid}", headers=AUTH_HEADERS)
        assert g.status_code == 200
        assert g.json()["id"] == data["id"]

        ext = await tenant_session.get(DriverPersonExtension, data["id"])
        assert ext is not None
        await tenant_session.delete(ext)
        await tenant_session.delete(p)
        await tenant_session.commit()

    async def test_get_404_when_missing_extension(
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
            last_name=f"Ext{suffix}",
            email=f"noext.{suffix}@dpe-test.invalid",
        )
        tenant_session.add(p)
        await tenant_session.commit()
        await tenant_session.refresh(p)
        pid = int(p.id)

        r = await client.get(f"/api/v1/driver-person-extensions/{pid}", headers=AUTH_HEADERS)
        assert r.status_code == 404

        await tenant_session.delete(p)
        await tenant_session.commit()

    async def test_owner_operator_subtype_rejected(
        self,
        client: AsyncClient,
        override_auth_tenant,
        tenant_session: AsyncSession,
        demo_tenant_id: int,
    ) -> None:
        p = Person(
            tenant_id=demo_tenant_id,
            first_name="Bad",
            last_name="Subtype",
            email=f"badst.{uuid.uuid4().hex[:8]}@dpe-test.invalid",
        )
        tenant_session.add(p)
        await tenant_session.commit()
        await tenant_session.refresh(p)
        pid = int(p.id)

        body = _valid_body(driver_operating_subtype="owner_operator")
        r = await client.put(
            f"/api/v1/driver-person-extensions/{pid}",
            json=body,
            headers=AUTH_HEADERS,
        )
        assert r.status_code == 422, r.text

        await tenant_session.delete(p)
        await tenant_session.commit()

    async def test_contractor_rejected(
        self,
        client: AsyncClient,
        override_auth_tenant,
        tenant_session: AsyncSession,
        demo_tenant_id: int,
    ) -> None:
        p = Person(
            tenant_id=demo_tenant_id,
            first_name="Bad",
            last_name="Contractor",
            email=f"badct.{uuid.uuid4().hex[:8]}@dpe-test.invalid",
        )
        tenant_session.add(p)
        await tenant_session.commit()
        await tenant_session.refresh(p)
        pid = int(p.id)

        body = _valid_body(employment_relationship_type="contractor")
        r = await client.put(
            f"/api/v1/driver-person-extensions/{pid}",
            json=body,
            headers=AUTH_HEADERS,
        )
        assert r.status_code == 422, r.text

        await tenant_session.delete(p)
        await tenant_session.commit()

    async def test_team_role_required_when_team(
        self,
        client: AsyncClient,
        override_auth_tenant,
        tenant_session: AsyncSession,
        demo_tenant_id: int,
    ) -> None:
        p = Person(
            tenant_id=demo_tenant_id,
            first_name="Team",
            last_name="X",
            email=f"team.{uuid.uuid4().hex[:8]}@dpe-test.invalid",
        )
        tenant_session.add(p)
        await tenant_session.commit()
        await tenant_session.refresh(p)
        pid = int(p.id)

        body = _valid_body(is_team_driver=True, team_role_type=None)
        r = await client.put(
            f"/api/v1/driver-person-extensions/{pid}",
            json=body,
            headers=AUTH_HEADERS,
        )
        assert r.status_code == 422, r.text

        await tenant_session.delete(p)
        await tenant_session.commit()

    async def test_equipment_contradiction(
        self,
        client: AsyncClient,
        override_auth_tenant,
        tenant_session: AsyncSession,
        demo_tenant_id: int,
    ) -> None:
        p = Person(
            tenant_id=demo_tenant_id,
            first_name="Eq",
            last_name="Bad",
            email=f"eq.{uuid.uuid4().hex[:8]}@dpe-test.invalid",
        )
        tenant_session.add(p)
        await tenant_session.commit()
        await tenant_session.refresh(p)
        pid = int(p.id)

        body = _valid_body(
            equipment_contribution_type="company_equipment",
            provides_own_truck=True,
            provides_own_trailer=False,
        )
        r = await client.put(
            f"/api/v1/driver-person-extensions/{pid}",
            json=body,
            headers=AUTH_HEADERS,
        )
        assert r.status_code == 422, r.text

        await tenant_session.delete(p)
        await tenant_session.commit()

    async def test_tenant_safe_wrong_tenant_returns_404(
        self,
        client: AsyncClient,
        test_bypass_env,
        tenant_session: AsyncSession,
        demo_tenant_id: int,
    ) -> None:
        """Simulated tenant_id mismatch: person exists only under demo; override claims wrong tenant."""
        holder = {"tenant_id": demo_tenant_id}
        install_mutable_tenant_current_user_and_tenant(app, holder)
        p = Person(
            tenant_id=demo_tenant_id,
            first_name="Iso",
            last_name="Test",
            email=f"iso.{uuid.uuid4().hex[:8]}@dpe-test.invalid",
        )
        tenant_session.add(p)
        await tenant_session.commit()
        await tenant_session.refresh(p)
        pid = int(p.id)

        try:
            holder["tenant_id"] = demo_tenant_id + 999_999
            r = await client.get(f"/api/v1/driver-person-extensions/{pid}", headers=AUTH_HEADERS)
            assert r.status_code == 404
        finally:
            clear_current_user_and_tenant_overrides(app)
            install_host_aligned_current_user_and_tenant(app)

        ext = await tenant_session.scalar(
            select(DriverPersonExtension).where(DriverPersonExtension.person_id == pid)
        )
        if ext:
            await tenant_session.delete(ext)
        await tenant_session.delete(p)
        await tenant_session.commit()


@pytest.mark.asyncio
@pytest.mark.skipif(REQUIRES_INTEGRATION_DB, reason="DATABASE_URL + tenant DB URL required for integration")
class TestDriverPersonExtensionUniqueness:
    async def test_duplicate_tenant_person_raises(
        self,
        tenant_session: AsyncSession,
        demo_tenant_id: int,
    ) -> None:
        suffix = uuid.uuid4().hex[:10]
        p = Person(
            tenant_id=demo_tenant_id,
            first_name="Uq",
            last_name=f"T{suffix}",
            email=f"uq.{suffix}@dpe-test.invalid",
        )
        tenant_session.add(p)
        await tenant_session.flush()

        a = DriverPersonExtension(
            tenant_id=demo_tenant_id,
            person_id=p.id,
            employment_relationship_type="company_driver",
            driver_operating_subtype="long_haul",
            is_team_driver=False,
            team_role_type=None,
            provides_own_truck=False,
            provides_own_trailer=False,
            equipment_contribution_type="company_equipment",
            insurance_commercial_approved=False,
        )
        b = DriverPersonExtension(
            tenant_id=demo_tenant_id,
            person_id=p.id,
            employment_relationship_type="company_driver",
            driver_operating_subtype="city_local",
            is_team_driver=False,
            team_role_type=None,
            provides_own_truck=False,
            provides_own_trailer=False,
            equipment_contribution_type="company_equipment",
            insurance_commercial_approved=False,
        )
        tenant_session.add(a)
        await tenant_session.flush()
        tenant_session.add(b)
        with pytest.raises(IntegrityError):
            await tenant_session.flush()

        await tenant_session.rollback()
        ex = await tenant_session.scalar(
            select(DriverPersonExtension).where(
                DriverPersonExtension.tenant_id == demo_tenant_id,
                DriverPersonExtension.person_id == p.id,
            )
        )
        if ex:
            await tenant_session.delete(ex)
        pr = await tenant_session.get(Person, p.id)
        if pr:
            await tenant_session.delete(pr)
        await tenant_session.commit()
