"""People workspace GET list: active_role_codes / primary_role_code (read-only, batch-loaded)."""

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
from app.models.person_application import PersonApplication
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
class TestPeopleWorkspaceListRoles:
    async def test_list_includes_active_role_codes_and_primary_excludes_inactive(
        self,
        client: AsyncClient,
        override_auth_tenant,
        tenant_session: AsyncSession,
        demo_tenant_id: int,
    ) -> None:
        suffix = uuid.uuid4().hex[:10]
        marker = f"lrw.{suffix}"
        base = datetime(2019, 6, 1, tzinfo=timezone.utc)

        p_multi = Person(
            tenant_id=demo_tenant_id,
            first_name="List",
            last_name=f"Roles{suffix}",
            email=f"{marker}@pws-test.invalid",
        )
        p_none = Person(
            tenant_id=demo_tenant_id,
            first_name="No",
            last_name=f"Roles{suffix}",
            email=f"noroles.{marker}@pws-test.invalid",
        )
        tenant_session.add_all([p_multi, p_none])
        await tenant_session.flush()

        # Inactive role must not appear in active_role_codes
        tenant_session.add(
            PersonRole(
                tenant_id=demo_tenant_id,
                person_id=p_multi.id,
                role_code="RETIRED",
                is_primary=False,
                is_active=False,
                created_at=base,
            )
        )
        # Active non-primary (older)
        tenant_session.add(
            PersonRole(
                tenant_id=demo_tenant_id,
                person_id=p_multi.id,
                role_code="DRIVER",
                is_primary=False,
                is_active=True,
                created_at=base + timedelta(days=1),
            )
        )
        # Active primary (newer) — should sort first in active_role_codes and set primary_role_code
        tenant_session.add(
            PersonRole(
                tenant_id=demo_tenant_id,
                person_id=p_multi.id,
                role_code="DISPATCHER",
                is_primary=True,
                is_active=True,
                created_at=base + timedelta(days=2),
            )
        )
        # Older application row — list must surface the latest by updated_at / id (same as detail).
        tenant_session.add(
            PersonApplication(
                tenant_id=demo_tenant_id,
                person_id=p_multi.id,
                status="DRAFT",
                current_workflow_lane="submitted",
                setup_status="pending",
                created_at=base,
                updated_at=base,
            )
        )
        tenant_session.add(
            PersonApplication(
                tenant_id=demo_tenant_id,
                person_id=p_multi.id,
                status="SUBMITTED",
                current_workflow_lane="processing",
                setup_status="pending_downstream",
                created_at=base + timedelta(days=1),
                updated_at=base + timedelta(days=2),
            )
        )
        await tenant_session.commit()
        await tenant_session.refresh(p_multi)
        await tenant_session.refresh(p_none)
        pid_multi = int(p_multi.id)
        pid_none = int(p_none.id)

        try:
            r = await client.get(
                "/api/v1/people",
                params={"q": marker, "limit": 50, "offset": 0},
                headers=AUTH_HEADERS,
            )
            assert r.status_code == 200, r.text
            rows = r.json()
            assert isinstance(rows, list)
            by_id = {int(x["id"]): x for x in rows}
            assert pid_multi in by_id
            assert pid_none in by_id

            m = by_id[pid_multi]
            assert m.get("active_role_codes") == ["DISPATCHER", "DRIVER"]
            assert m.get("primary_role_code") == "DISPATCHER"
            assert "RETIRED" not in (m.get("active_role_codes") or [])

            n = by_id[pid_none]
            assert n.get("active_role_codes") == []
            assert n.get("primary_role_code") is None

            la = m.get("latest_application")
            assert la is not None
            assert la.get("id") is not None
            assert la.get("status") == "SUBMITTED"
            assert la.get("setup_status") == "pending_downstream"
            assert la.get("current_workflow_lane") == "processing"
            assert n.get("latest_application") is None
        finally:
            await tenant_session.execute(
                delete(PersonApplication).where(
                    PersonApplication.person_id.in_([pid_multi, pid_none]), PersonApplication.tenant_id == demo_tenant_id
                )
            )
            await tenant_session.execute(
                delete(PersonRole).where(PersonRole.person_id.in_([pid_multi, pid_none]), PersonRole.tenant_id == demo_tenant_id)
            )
            await tenant_session.execute(
                delete(Person).where(Person.id.in_([pid_multi, pid_none]), Person.tenant_id == demo_tenant_id)
            )
            await tenant_session.commit()
