"""People workspace GET detail: person_roles summary shape and stable ordering (read-only)."""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("ALLOW_TENANT_RESOLUTION_SHORTCUTS", "true")

from app.core.db_url import to_async_pg_url
from app.main import app
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
class TestPeopleWorkspaceRolesDetail:
    async def test_detail_roles_include_id_timestamps_and_ordering(
        self,
        client: AsyncClient,
        override_auth_tenant,
        tenant_session: AsyncSession,
        demo_tenant_id: int,
    ) -> None:
        suffix = uuid.uuid4().hex[:10]
        base = datetime(2020, 1, 10, 12, 0, 0, tzinfo=timezone.utc)
        p = Person(
            tenant_id=demo_tenant_id,
            first_name="Role",
            last_name=f"Ord{suffix}",
            email=f"roles.ord.{suffix}@pws-test.invalid",
        )
        tenant_session.add(p)
        await tenant_session.flush()

        # A: inactive, non-primary, oldest (last in list)
        role_a = PersonRole(
            tenant_id=demo_tenant_id,
            person_id=p.id,
            role_code="INACTIVE_OLD",
            is_primary=False,
            is_active=False,
            created_at=base,
        )
        # B: active, non-primary, middle timestamp
        role_b = PersonRole(
            tenant_id=demo_tenant_id,
            person_id=p.id,
            role_code="ACTIVE_MID",
            is_primary=False,
            is_active=True,
            created_at=base + timedelta(days=1),
        )
        # C: active, primary, middle-newer (should sort before B among actives: primary first)
        role_c = PersonRole(
            tenant_id=demo_tenant_id,
            person_id=p.id,
            role_code="ACTIVE_PRI",
            is_primary=True,
            is_active=True,
            created_at=base + timedelta(days=2),
        )
        # D: active, non-primary, newest (after C, before B: newer than B)
        role_d = PersonRole(
            tenant_id=demo_tenant_id,
            person_id=p.id,
            role_code="ACTIVE_NEW",
            is_primary=False,
            is_active=True,
            created_at=base + timedelta(days=3),
        )
        tenant_session.add_all([role_a, role_b, role_c, role_d])
        await tenant_session.commit()
        await tenant_session.refresh(p)
        pid = int(p.id)

        try:
            r = await client.get(f"/api/v1/people/{pid}", headers=AUTH_HEADERS)
            assert r.status_code == 200, r.text
            body = r.json()
            roles = body.get("roles") or []
            assert len(roles) == 4

            for row in roles:
                assert row["id"] is not None
                assert row["created_at"]
                assert row["role_code"]
                assert "is_primary" in row
                assert "is_active" in row

            codes = [x["role_code"] for x in roles]
            # Active first, primary first, then newest created_at, then id desc.
            assert codes == ["ACTIVE_PRI", "ACTIVE_NEW", "ACTIVE_MID", "INACTIVE_OLD"]

            assert roles[0]["is_active"] is True
            assert roles[0]["is_primary"] is True
            assert roles[-1]["is_active"] is False
        finally:
            await tenant_session.execute(delete(PersonRole).where(PersonRole.person_id == pid, PersonRole.tenant_id == demo_tenant_id))
            await tenant_session.execute(delete(Person).where(Person.id == pid, Person.tenant_id == demo_tenant_id))
            await tenant_session.commit()
