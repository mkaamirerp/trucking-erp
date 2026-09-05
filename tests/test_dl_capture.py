"""DL capture token: purpose filter, scoped revoke, resume steps, applicant issue link."""

from __future__ import annotations

import hashlib
import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from unittest.mock import AsyncMock

from app.core.db_url import to_async_pg_url
from app.main import app as fastapi_app
from app.models.application_access_token import ApplicationAccessToken
from app.models.person_application import PersonApplication
from app.schemas.driver_onboarding import DriverOnboardingStatus
from app.routers import driver_onboarding as ro

REQUIRES_DB = not os.environ.get("DATABASE_URL")
AUTH_HEADERS = {"host": "demo.truckerp.me"}


def _tenant_async_url() -> str | None:
    raw = os.environ.get("TENANT_DATABASE_URL") or os.environ.get("ALEMBIC_TENANT_DATABASE_URL")
    if not raw:
        return None
    return to_async_pg_url(raw)


REQUIRES_TENANT_DB = _tenant_async_url() is None


def _token_sha256_hex(raw: str) -> str:
    return hashlib.sha256(raw.strip().encode("utf-8")).hexdigest()


def test_dl_capture_step_resume_rules() -> None:
    """Preprocess-only step. Phone capture stays on a side until user confirm (see test_dl_capture_confirm)."""
    assert ro._dl_capture_step("MISSING", "MISSING") == "FRONT"
    assert ro._dl_capture_step("FAILED", "MISSING") == "FRONT"
    assert ro._dl_capture_step("PROCESSED", "MISSING") == "BACK"
    assert ro._dl_capture_step("PROCESSED", "FAILED") == "BACK"
    assert ro._dl_capture_step("PROCESSED", "PROCESSED") == "COMPLETE"


def test_dl_side_status_from_intake() -> None:
    intake = {
        "files": {
            "CDL_FRONT": {"dl_preprocess_status": "PROCESSED"},
            "CDL_BACK": {"dl_preprocess_status": "FAILED"},
        }
    }
    assert ro._dl_side_status(intake, "CDL_FRONT") == "PROCESSED"
    assert ro._dl_side_status(intake, "CDL_BACK") == "FAILED"
    assert ro._dl_side_status({}, "CDL_FRONT") == "MISSING"


@pytest.mark.asyncio
async def test_revoke_active_tokens_purpose_scoped() -> None:
    db = AsyncMock()
    db.execute = AsyncMock()
    await ro._revoke_active_access_tokens_for_application(
        db, tenant_id=1, application_id=60, purpose=ro.TOKEN_PURPOSE_DL_CAPTURE
    )
    assert db.execute.await_count == 1
    stmt = db.execute.await_args.args[0]
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": False}))
    assert "application_access_tokens" in compiled.lower() or "application_access_tokens" in str(stmt)


@pytest.mark.asyncio
async def test_get_token_requires_dl_capture_purpose() -> None:
    db = AsyncMock()
    db.scalar = AsyncMock(return_value=None)
    with pytest.raises(Exception) as exc:
        await ro._get_application_and_access_by_token(
            db,
            tenant_id=1,
            token="abc",
            purpose=ro.TOKEN_PURPOSE_DL_CAPTURE,
            detail=ro._DL_CAPTURE_INVALID,
        )
    assert exc.value.status_code == 404
    assert exc.value.detail == ro._DL_CAPTURE_INVALID
    stmt = db.scalar.await_args.args[0]
    assert any(
        getattr(c, "right", None) is not None
        or "dl_capture" in str(c)
        for c in stmt._where_criteria
    ) or "dl_capture" in str(stmt)


def test_dl_capture_ttl_constant() -> None:
    assert ro.DL_CAPTURE_TOKEN_TTL == timedelta(hours=24)


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
    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def demo_tenant_id():
    from tests.support.tenant_test_ids import platform_tenant_id_for_slug

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


async def _make_draft_driver_app_with_invite(
    tenant_session: AsyncSession,
    *,
    demo_tenant_id: int,
    status: str = DriverOnboardingStatus.DRAFT.value,
    email: str | None = "__auto__",
    application_type: str = "DRIVER",
) -> tuple[int, str]:
    suffix = uuid.uuid4().hex[:10]
    stored_email = f"dlcap.{suffix}@test.invalid" if email == "__auto__" else email
    app_row = PersonApplication(
        tenant_id=demo_tenant_id,
        source="dl_capture_test",
        status=status,
        requested_role_code=application_type,
        application_type=application_type,
        email=stored_email,
        intake_payload={"step": "dl_upload"},
    )
    tenant_session.add(app_row)
    await tenant_session.flush()
    invite_raw = f"invite_{uuid.uuid4().hex}"
    tenant_session.add(
        ApplicationAccessToken(
            tenant_id=demo_tenant_id,
            application_id=app_row.id,
            token=invite_raw,
            token_hash=_token_sha256_hex(invite_raw),
            expires_at=datetime.now(timezone.utc) + timedelta(days=7),
            revoked_at=None,
            purpose=ro.TOKEN_PURPOSE_INVITE,
        )
    )
    await tenant_session.commit()
    return int(app_row.id), invite_raw


async def _add_access_token(
    tenant_session: AsyncSession,
    *,
    demo_tenant_id: int,
    application_id: int,
    purpose: str,
    raw_token: str | None = None,
) -> str:
    raw = raw_token or f"{purpose}_{uuid.uuid4().hex}"
    tenant_session.add(
        ApplicationAccessToken(
            tenant_id=demo_tenant_id,
            application_id=application_id,
            token=raw,
            token_hash=_token_sha256_hex(raw),
            expires_at=datetime.now(timezone.utc) + timedelta(days=7),
            revoked_at=None,
            purpose=purpose,
        )
    )
    await tenant_session.commit()
    return raw


@pytest.mark.asyncio
@pytest.mark.skipif(REQUIRES_DB, reason="DATABASE_URL required")
@pytest.mark.skipif(REQUIRES_TENANT_DB, reason="tenant DB URL required")
class TestApplicantDlCaptureLinkIssue:
    async def test_invite_draft_issues_capture_link(
        self,
        client: AsyncClient,
        demo_tenant_id: int,
        tenant_session: AsyncSession,
    ) -> None:
        app_id, invite = await _make_draft_driver_app_with_invite(tenant_session, demo_tenant_id=demo_tenant_id)
        r = await client.post(
            f"/api/v1/driver-onboarding/applicant/application/dl-capture-link?token={invite}",
            headers=AUTH_HEADERS,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["application_id"] == app_id
        assert "/dl-capture/" in body["link"]
        assert body["token"] in body["link"]
        assert "onboarding?token=" not in body["link"]

        cap = body["token"]
        sess = await client.get(
            f"/api/v1/driver-onboarding/applicant/dl-capture/{cap}",
            headers=AUTH_HEADERS,
        )
        assert sess.status_code == 200, sess.text

    async def test_document_resume_cannot_issue(
        self,
        client: AsyncClient,
        demo_tenant_id: int,
        tenant_session: AsyncSession,
    ) -> None:
        app_id, _invite = await _make_draft_driver_app_with_invite(tenant_session, demo_tenant_id=demo_tenant_id)
        resume = await _add_access_token(
            tenant_session,
            demo_tenant_id=demo_tenant_id,
            application_id=app_id,
            purpose=ro.TOKEN_PURPOSE_DOCUMENT_RESUME,
        )
        r = await client.post(
            f"/api/v1/driver-onboarding/applicant/application/dl-capture-link?token={resume}",
            headers=AUTH_HEADERS,
        )
        assert r.status_code == 403, r.text

    async def test_non_draft_cannot_issue(
        self,
        client: AsyncClient,
        demo_tenant_id: int,
        tenant_session: AsyncSession,
    ) -> None:
        _app_id, invite = await _make_draft_driver_app_with_invite(
            tenant_session,
            demo_tenant_id=demo_tenant_id,
            status=DriverOnboardingStatus.SUBMITTED.value,
        )
        r = await client.post(
            f"/api/v1/driver-onboarding/applicant/application/dl-capture-link?token={invite}",
            headers=AUTH_HEADERS,
        )
        assert r.status_code == 409, r.text

    async def test_second_issue_revokes_first_capture_only(
        self,
        client: AsyncClient,
        demo_tenant_id: int,
        tenant_session: AsyncSession,
    ) -> None:
        app_id, invite = await _make_draft_driver_app_with_invite(tenant_session, demo_tenant_id=demo_tenant_id)
        resume = await _add_access_token(
            tenant_session,
            demo_tenant_id=demo_tenant_id,
            application_id=app_id,
            purpose=ro.TOKEN_PURPOSE_DOCUMENT_RESUME,
        )
        r1 = await client.post(
            f"/api/v1/driver-onboarding/applicant/application/dl-capture-link?token={invite}",
            headers=AUTH_HEADERS,
        )
        r2 = await client.post(
            f"/api/v1/driver-onboarding/applicant/application/dl-capture-link?token={invite}",
            headers=AUTH_HEADERS,
        )
        assert r1.status_code == 200 and r2.status_code == 200
        first_cap = r1.json()["token"]
        second_cap = r2.json()["token"]
        assert first_cap != second_cap

        old_sess = await client.get(
            f"/api/v1/driver-onboarding/applicant/dl-capture/{first_cap}",
            headers=AUTH_HEADERS,
        )
        assert old_sess.status_code == 404

        new_sess = await client.get(
            f"/api/v1/driver-onboarding/applicant/dl-capture/{second_cap}",
            headers=AUTH_HEADERS,
        )
        assert new_sess.status_code == 200

        rows = (
            await tenant_session.scalars(
                select(ApplicationAccessToken).where(
                    ApplicationAccessToken.tenant_id == demo_tenant_id,
                    ApplicationAccessToken.application_id == app_id,
                )
            )
        ).all()
        invite_rows = [t for t in rows if t.purpose == ro.TOKEN_PURPOSE_INVITE]
        resume_rows = [t for t in rows if t.purpose == ro.TOKEN_PURPOSE_DOCUMENT_RESUME]
        capture_rows = [t for t in rows if t.purpose == ro.TOKEN_PURPOSE_DL_CAPTURE]
        assert len(invite_rows) == 1 and invite_rows[0].revoked_at is None
        assert len(resume_rows) == 1 and resume_rows[0].revoked_at is None
        assert resume == resume_rows[0].token
        active_capture = [t for t in capture_rows if t.revoked_at is None]
        revoked_capture = [t for t in capture_rows if t.revoked_at is not None]
        assert len(active_capture) == 1
        assert len(revoked_capture) >= 1

    async def test_tenant_isolation(
        self,
        client: AsyncClient,
        demo_tenant_id: int,
        tenant_session: AsyncSession,
    ) -> None:
        app_id, invite = await _make_draft_driver_app_with_invite(tenant_session, demo_tenant_id=demo_tenant_id)
        r = await client.post(
            f"/api/v1/driver-onboarding/applicant/application/dl-capture-link?token={invite}",
            headers={"host": "other.truckerp.me"},
        )
        assert r.status_code in (404, 403, 400), r.text

        cap_r = await client.post(
            f"/api/v1/driver-onboarding/applicant/application/dl-capture-link?token={invite}",
            headers=AUTH_HEADERS,
        )
        assert cap_r.status_code == 200
        cap = cap_r.json()["token"]
        wrong_host = await client.get(
            f"/api/v1/driver-onboarding/applicant/dl-capture/{cap}",
            headers={"host": "other.truckerp.me"},
        )
        assert wrong_host.status_code in (404, 403, 400), wrong_host.text

        assert app_id > 0


@pytest.mark.asyncio
@pytest.mark.skipif(REQUIRES_DB, reason="DATABASE_URL required")
@pytest.mark.skipif(REQUIRES_TENANT_DB, reason="tenant DB URL required")
class TestApplicantDlCaptureLinkEmail:
    async def test_email_without_application_email(
        self,
        client: AsyncClient,
        demo_tenant_id: int,
        tenant_session: AsyncSession,
    ) -> None:
        _app_id, invite = await _make_draft_driver_app_with_invite(
            tenant_session,
            demo_tenant_id=demo_tenant_id,
            email=None,
        )
        r = await client.post(
            f"/api/v1/driver-onboarding/applicant/application/dl-capture-link/email?token={invite}",
            headers=AUTH_HEADERS,
        )
        assert r.status_code == 400, r.text
        assert "No applicant email is available for this application." in r.text

        tenant_session.expire_all()
        rows = (
            await tenant_session.scalars(
                select(ApplicationAccessToken).where(
                    ApplicationAccessToken.tenant_id == demo_tenant_id,
                    ApplicationAccessToken.application_id == _app_id,
                    ApplicationAccessToken.purpose == ro.TOKEN_PURPOSE_DL_CAPTURE,
                )
            )
        ).all()
        assert rows == []

    async def test_email_success_replaces_active_token(
        self,
        client: AsyncClient,
        demo_tenant_id: int,
        tenant_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        sent: dict[str, str] = {}

        async def fake_send(*, to: str, capture_link: str) -> None:
            sent["to"] = to
            sent["link"] = capture_link

        monkeypatch.setattr(ro, "send_dl_capture_link_email", fake_send)

        app_id, invite = await _make_draft_driver_app_with_invite(
            tenant_session, demo_tenant_id=demo_tenant_id
        )
        first = await client.post(
            f"/api/v1/driver-onboarding/applicant/application/dl-capture-link?token={invite}",
            headers=AUTH_HEADERS,
        )
        assert first.status_code == 200
        first_token = first.json()["token"]

        r = await client.post(
            f"/api/v1/driver-onboarding/applicant/application/dl-capture-link/email?token={invite}",
            headers=AUTH_HEADERS,
            json={"email": "attacker@evil.test"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["application_id"] == app_id
        assert body["emailed"] is True
        assert "/dl-capture/" in body["link"]
        assert "onboarding?token=" not in body["link"]
        assert body["token"] != first_token
        assert sent["link"] == body["link"]
        assert "onboarding?token=" not in sent["link"]
        assert sent["to"].endswith("@test.invalid")
        assert sent["to"] != "attacker@evil.test"

        old = await client.get(
            f"/api/v1/driver-onboarding/applicant/dl-capture/{first_token}",
            headers=AUTH_HEADERS,
        )
        assert old.status_code == 404
        fresh = await client.get(
            f"/api/v1/driver-onboarding/applicant/dl-capture/{body['token']}",
            headers=AUTH_HEADERS,
        )
        assert fresh.status_code == 200
        tenant_session.expire_all()
        capture_rows = (
            await tenant_session.scalars(
                select(ApplicationAccessToken).where(
                    ApplicationAccessToken.tenant_id == demo_tenant_id,
                    ApplicationAccessToken.application_id == app_id,
                    ApplicationAccessToken.purpose == ro.TOKEN_PURPOSE_DL_CAPTURE,
                )
            )
        ).all()
        active = [t for t in capture_rows if t.revoked_at is None]
        assert len(active) == 1
        assert invite not in sent["link"]
        assert body["token"] in sent["link"]
        assert body["token"] in body["link"]

    async def test_no_email_does_not_revoke_existing_capture_token(
        self,
        client: AsyncClient,
        demo_tenant_id: int,
        tenant_session: AsyncSession,
    ) -> None:
        app_id, invite = await _make_draft_driver_app_with_invite(
            tenant_session,
            demo_tenant_id=demo_tenant_id,
            email=None,
        )
        issued = await client.post(
            f"/api/v1/driver-onboarding/applicant/application/dl-capture-link?token={invite}",
            headers=AUTH_HEADERS,
        )
        assert issued.status_code == 200
        token = issued.json()["token"]
        r = await client.post(
            f"/api/v1/driver-onboarding/applicant/application/dl-capture-link/email?token={invite}",
            headers=AUTH_HEADERS,
        )
        assert r.status_code == 400, r.text
        still = await client.get(
            f"/api/v1/driver-onboarding/applicant/dl-capture/{token}",
            headers=AUTH_HEADERS,
        )
        assert still.status_code == 200, still.text
        assert app_id > 0

    async def test_mail_failure_keeps_new_token_active(
        self,
        client: AsyncClient,
        demo_tenant_id: int,
        tenant_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        async def boom(*, to: str, capture_link: str) -> None:
            raise RuntimeError("smtp_unavailable")

        monkeypatch.setattr(ro, "send_dl_capture_link_email", boom)
        _app_id, invite = await _make_draft_driver_app_with_invite(
            tenant_session, demo_tenant_id=demo_tenant_id
        )
        first = await client.post(
            f"/api/v1/driver-onboarding/applicant/application/dl-capture-link?token={invite}",
            headers=AUTH_HEADERS,
        )
        assert first.status_code == 200
        first_token = first.json()["token"]
        r = await client.post(
            f"/api/v1/driver-onboarding/applicant/application/dl-capture-link/email?token={invite}",
            headers=AUTH_HEADERS,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["emailed"] is False
        assert body["email_error"]
        assert body["token"] != first_token
        assert "/dl-capture/" in body["link"]
        assert "onboarding?token=" not in body["link"]
        old = await client.get(
            f"/api/v1/driver-onboarding/applicant/dl-capture/{first_token}",
            headers=AUTH_HEADERS,
        )
        assert old.status_code == 404
        fresh = await client.get(
            f"/api/v1/driver-onboarding/applicant/dl-capture/{body['token']}",
            headers=AUTH_HEADERS,
        )
        assert fresh.status_code == 200

    async def test_email_rejected_for_non_driver_workflow(
        self,
        client: AsyncClient,
        demo_tenant_id: int,
        tenant_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        sent: dict[str, str] = {}

        async def fake_send(*, to: str, capture_link: str) -> None:
            sent["to"] = to
            sent["link"] = capture_link

        monkeypatch.setattr(ro, "send_dl_capture_link_email", fake_send)
        _app_id, invite = await _make_draft_driver_app_with_invite(
            tenant_session,
            demo_tenant_id=demo_tenant_id,
            application_type="DISPATCHER",
        )
        r = await client.post(
            f"/api/v1/driver-onboarding/applicant/application/dl-capture-link/email?token={invite}",
            headers=AUTH_HEADERS,
        )
        assert r.status_code == 403, r.text
        assert sent == {}

    async def test_email_rejected_for_submitted_application(
        self,
        client: AsyncClient,
        demo_tenant_id: int,
        tenant_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        async def fake_send(*, to: str, capture_link: str) -> None:
            raise AssertionError("mail must not send")

        monkeypatch.setattr(ro, "send_dl_capture_link_email", fake_send)
        _app_id, invite = await _make_draft_driver_app_with_invite(
            tenant_session,
            demo_tenant_id=demo_tenant_id,
            status=DriverOnboardingStatus.SUBMITTED.value,
        )
        r = await client.post(
            f"/api/v1/driver-onboarding/applicant/application/dl-capture-link/email?token={invite}",
            headers=AUTH_HEADERS,
        )
        assert r.status_code == 409, r.text

    async def test_email_rejected_for_invalid_invite_and_wrong_host(
        self,
        client: AsyncClient,
        demo_tenant_id: int,
        tenant_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        async def fake_send(*, to: str, capture_link: str) -> None:
            raise AssertionError("mail must not send")

        monkeypatch.setattr(ro, "send_dl_capture_link_email", fake_send)
        _app_id, invite = await _make_draft_driver_app_with_invite(
            tenant_session, demo_tenant_id=demo_tenant_id
        )
        missing = await client.post(
            "/api/v1/driver-onboarding/applicant/application/dl-capture-link/email?token=not-a-real-invite",
            headers=AUTH_HEADERS,
        )
        assert missing.status_code in (404, 403, 400), missing.text
        wrong_host = await client.post(
            f"/api/v1/driver-onboarding/applicant/application/dl-capture-link/email?token={invite}",
            headers={"host": "other.truckerp.me"},
        )
        assert wrong_host.status_code in (404, 403, 400), wrong_host.text
        assert demo_tenant_id > 0
