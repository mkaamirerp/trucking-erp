"""Phase 1: workflow vs role gating for invite onboarding (no schema changes)."""

from __future__ import annotations

import os
from types import SimpleNamespace
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("ALLOW_TENANT_RESOLUTION_SHORTCUTS", "true")

from app.core.db_url import to_async_pg_url
from app.main import app
from app.routers.driver_onboarding import _is_driver_workflow_application, _sanitize_intake_for_workflow
from app.models.application_access_token import ApplicationAccessToken
from app.models.driver import Driver
from app.models.person_application import PersonApplication
from app.schemas.driver_onboarding import DriverOnboardingStatus
from tests.support.integration_auth import (
    clear_current_user_and_tenant_overrides,
    install_host_aligned_current_user_and_tenant,
)
from tests.support.tenant_test_ids import platform_tenant_id_for_slug

REQUIRES_DB = not os.environ.get("DATABASE_URL")


def test_sanitize_intake_non_driver_strips_driver_only_keys() -> None:
    app = SimpleNamespace(application_type="DISPATCHER")
    assert not _is_driver_workflow_application(app)
    out = _sanitize_intake_for_workflow(
        app,
        {
            "first_name": "A",
            "files": {"CDL_FRONT": {}},
            "driver_license_number": "X",
            "step": "common",
        },
    )
    assert out is not None
    assert out.get("first_name") == "A"
    assert "files" not in out
    assert "driver_license_number" not in out
    assert out.get("step") == "common"


def test_sanitize_intake_driver_keeps_files() -> None:
    app = SimpleNamespace(application_type="DRIVER")
    assert _is_driver_workflow_application(app)
    payload = {"files": {"CDL_FRONT": {"k": 1}}, "first_name": "B"}
    out = _sanitize_intake_for_workflow(app, payload)
    assert out == payload


def test_sanitize_empty_non_driver_adds_common_step() -> None:
    app = SimpleNamespace(application_type="OTHER")
    out = _sanitize_intake_for_workflow(app, {})
    assert out == {"step": "common"}


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


async def _make_tokenized_application(
    tenant_session: AsyncSession,
    *,
    demo_tenant_id: int,
    application_type: str,
    requested_role_code: str,
    email: str,
) -> tuple[int, str]:
    app_row = PersonApplication(
        tenant_id=demo_tenant_id,
        source="phase1_test",
        status=DriverOnboardingStatus.DRAFT.value,
        requested_role_code=requested_role_code,
        application_type=application_type,
        first_name=None,
        last_name=None,
        email=email,
        intake_payload={
            "step": "dl_upload" if application_type == "DRIVER" else "common",
            "form_country_default": "US",
            "form_region_default": "TX",
        },
    )
    tenant_session.add(app_row)
    await tenant_session.flush()
    raw_token = f"test_token_{uuid.uuid4().hex}"
    access = ApplicationAccessToken(
        tenant_id=demo_tenant_id,
        application_id=app_row.id,
        token=raw_token,
        token_hash=None,
        expires_at=datetime.now(timezone.utc) + timedelta(days=1),
        revoked_at=None,
    )
    tenant_session.add(access)
    await tenant_session.commit()
    return int(app_row.id), raw_token


@pytest.mark.asyncio
@pytest.mark.skipif(REQUIRES_DB, reason="DATABASE_URL required")
@pytest.mark.skipif(REQUIRES_TENANT_DB, reason="tenant DB URL required")
class TestOnboardingPhase1ApplicantGating:
    async def test_non_driver_dl_upload_forbidden(
        self,
        client: AsyncClient,
        demo_tenant_id: int,
        tenant_session: AsyncSession,
    ) -> None:
        suffix = uuid.uuid4().hex[:10]
        _app_id, token = await _make_tokenized_application(
            tenant_session,
            demo_tenant_id=demo_tenant_id,
            application_type="DISPATCHER",
            requested_role_code="DISPATCHER",
            email=f"nd.{suffix}@phase1-test.invalid",
        )
        files = {"file": ("x.jpg", b"\xff\xd8\xff", "image/jpeg")}
        data = {"doc_type": "CDL_FRONT"}
        r = await client.post(
            f"/api/v1/driver-onboarding/applicant/application/dl-upload?token={token}",
            data=data,
            files=files,
            headers=AUTH_HEADERS,
        )
        assert r.status_code == 403, r.text

    async def test_non_driver_intake_strips_driver_only_keys(
        self,
        client: AsyncClient,
        demo_tenant_id: int,
        tenant_session: AsyncSession,
    ) -> None:
        suffix = uuid.uuid4().hex[:10]
        _app_id, token = await _make_tokenized_application(
            tenant_session,
            demo_tenant_id=demo_tenant_id,
            application_type="HR",
            requested_role_code="HR",
            email=f"hr.{suffix}@phase1-test.invalid",
        )
        r = await client.post(
            f"/api/v1/driver-onboarding/applicant/application/intake?token={token}",
            json={
                "intake_payload": {
                    "first_name": "Alex",
                    "files": {"CDL_FRONT": {"storage_key": "bogus"}},
                    "driver_license_number": "X",
                },
                "submit": False,
            },
            headers=AUTH_HEADERS,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        intake = body.get("intake_payload") or {}
        assert intake.get("first_name") == "Alex"
        assert "files" not in intake
        assert "driver_license_number" not in intake

    async def test_reset_non_driver_default_step_common(
        self,
        client: AsyncClient,
        demo_tenant_id: int,
        tenant_session: AsyncSession,
    ) -> None:
        suffix = uuid.uuid4().hex[:10]
        app_row = PersonApplication(
            tenant_id=demo_tenant_id,
            source="phase1_test",
            status=DriverOnboardingStatus.DRAFT.value,
            requested_role_code="OTHER",
            application_type="OTHER",
            email=f"rst.{suffix}@phase1-test.invalid",
            intake_payload={"step": "common", "first_name": "Temp"},
        )
        tenant_session.add(app_row)
        await tenant_session.flush()
        raw_token = f"test_token_{uuid.uuid4().hex}"
        tenant_session.add(
            ApplicationAccessToken(
                tenant_id=demo_tenant_id,
                application_id=app_row.id,
                token=raw_token,
                token_hash=None,
                expires_at=datetime.now(timezone.utc) + timedelta(days=1),
                revoked_at=None,
            )
        )
        await tenant_session.commit()
        # clear step so reset must infer default
        app_row.intake_payload = {"form_country_default": "US"}
        await tenant_session.commit()
        r = await client.post(
            f"/api/v1/driver-onboarding/applicant/application/reset?token={raw_token}",
            headers=AUTH_HEADERS,
        )
        assert r.status_code == 200, r.text
        assert (r.json().get("intake_payload") or {}).get("step") == "common"
        await tenant_session.execute(delete(ApplicationAccessToken).where(ApplicationAccessToken.token == raw_token))
        await tenant_session.execute(delete(PersonApplication).where(PersonApplication.id == app_row.id))
        await tenant_session.commit()


@pytest.mark.asyncio
@pytest.mark.skipif(REQUIRES_DB, reason="DATABASE_URL required")
@pytest.mark.skipif(REQUIRES_TENANT_DB, reason="tenant DB URL required")
class TestOnboardingPhase1ApprovalDriverEntities:
    async def test_dispatcher_workflow_with_driver_role_does_not_create_operational_driver(
        self,
        client: AsyncClient,
        override_auth_tenant,
        tenant_session: AsyncSession,
        demo_tenant_id: int,
    ) -> None:
        """MVP mismatch: workflow is not DRIVER — do not materialize DriverProfile/drivers."""
        suffix = uuid.uuid4().hex[:10]
        email = f"mismatch.{suffix}@phase1-test.invalid"
        app_row = PersonApplication(
            tenant_id=demo_tenant_id,
            source="phase1_test",
            status=DriverOnboardingStatus.SUBMITTED.value,
            requested_role_code="DRIVER",
            application_type="DISPATCHER",
            first_name="Sam",
            last_name=f"M{suffix}",
            email=email,
            phone="+15555550111",
            intake_payload={"first_name": "Sam"},
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

        person_id = int(
            (await tenant_session.scalar(select(PersonApplication.person_id).where(PersonApplication.id == app_id))) or 0
        )
        assert person_id > 0
        n_drivers = await tenant_session.scalar(
            select(func.count()).select_from(Driver).where(Driver.tenant_id == demo_tenant_id, Driver.person_id == person_id)
        )
        assert int(n_drivers or 0) == 0

        from app.models.person import Person, PersonRole

        person = await tenant_session.get(Person, person_id)
        assert person is not None
        await tenant_session.execute(
            delete(PersonRole).where(PersonRole.person_id == person.id, PersonRole.tenant_id == demo_tenant_id)
        )
        await tenant_session.execute(delete(Person).where(Person.id == person.id))
        await tenant_session.execute(delete(PersonApplication).where(PersonApplication.id == app_id))
        await tenant_session.commit()
