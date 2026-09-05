"""Domain event outbox + DL transition events + SSE applicant stream."""

from __future__ import annotations

import asyncio
import hashlib
import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from unittest.mock import AsyncMock

from app.core.db_url import to_async_pg_url
from app.main import app as fastapi_app
from app.models.application_access_token import ApplicationAccessToken
from app.models.domain_event_outbox import DomainEventOutbox
from app.models.person_application import PersonApplication
from app.schemas.driver_onboarding import DriverOnboardingStatus
from app.services.domain_event_delivery import DomainEventDispatcher, SubscriberRegistry, format_sse_application_changed
from app.services.domain_event_outbox import (
    EVENT_DRIVER_LICENCE_BACK_PROCESSED,
    EVENT_DRIVER_LICENCE_CAPTURE_COMPLETE,
    EVENT_DRIVER_LICENCE_FRONT_PROCESSED,
    EVENT_DRIVER_LICENCE_PROCESSING_FAILED,
    build_dl_licence_domain_events,
)
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


def test_front_processed_transition_event() -> None:
    events = build_dl_licence_domain_events(
        old_front="MISSING",
        old_back="MISSING",
        new_front="PROCESSED",
        new_back="MISSING",
        doc_type="CDL_FRONT",
        upload_failed=False,
    )
    types = [e[0] for e in events]
    assert EVENT_DRIVER_LICENCE_FRONT_PROCESSED in types
    assert EVENT_DRIVER_LICENCE_CAPTURE_COMPLETE not in types


def test_back_processed_transition_event() -> None:
    events = build_dl_licence_domain_events(
        old_front="PROCESSED",
        old_back="MISSING",
        new_front="PROCESSED",
        new_back="PROCESSED",
        doc_type="CDL_BACK",
        upload_failed=False,
    )
    types = [e[0] for e in events]
    assert EVENT_DRIVER_LICENCE_BACK_PROCESSED in types
    assert EVENT_DRIVER_LICENCE_CAPTURE_COMPLETE in types


def test_no_duplicate_capture_complete_when_already_complete() -> None:
    events = build_dl_licence_domain_events(
        old_front="PROCESSED",
        old_back="PROCESSED",
        new_front="PROCESSED",
        new_back="PROCESSED",
        doc_type="CDL_FRONT",
        upload_failed=False,
    )
    assert EVENT_DRIVER_LICENCE_CAPTURE_COMPLETE not in [e[0] for e in events]


def test_failed_upload_emits_processing_failed_only_side() -> None:
    events = build_dl_licence_domain_events(
        old_front="MISSING",
        old_back="MISSING",
        new_front="FAILED",
        new_back="MISSING",
        doc_type="CDL_FRONT",
        upload_failed=True,
    )
    failed = [e for e in events if e[0] == EVENT_DRIVER_LICENCE_PROCESSING_FAILED]
    assert len(failed) == 1
    assert failed[0][1] == {"side": "CDL_FRONT"}


def test_sse_event_contains_no_pii() -> None:
    body = format_sse_application_changed(
        "8c0d8100-6444-4a34-9279-5a41ad04010d",
        EVENT_DRIVER_LICENCE_FRONT_PROCESSED,
    )
    assert "event: application_changed" in body
    assert "driver_licence.front_processed" in body
    assert "first_name" not in body
    assert "email" not in body
    assert "phone" not in body


@pytest.mark.asyncio
async def test_subscriber_registry_isolates_application_ids() -> None:
    registry = SubscriberRegistry()
    queue_a: asyncio.Queue[dict[str, str]] = asyncio.Queue(maxsize=8)
    queue_b: asyncio.Queue[dict[str, str]] = asyncio.Queue(maxsize=8)
    tenant_id = 53
    await registry.subscribe(tenant_id, 100, queue_a)
    await registry.subscribe(tenant_id, 200, queue_b)

    message = {"event_id": "evt-a", "event_type": EVENT_DRIVER_LICENCE_FRONT_PROCESSED}
    await registry.publish(tenant_id, 100, message)

    received_a = queue_a.get_nowait()
    assert received_a == message
    with pytest.raises(asyncio.QueueEmpty):
        queue_b.get_nowait()


@pytest.mark.asyncio
async def test_subscriber_registry_isolates_tenant_ids() -> None:
    registry = SubscriberRegistry()
    queue_tenant_a: asyncio.Queue[dict[str, str]] = asyncio.Queue(maxsize=8)
    queue_tenant_b: asyncio.Queue[dict[str, str]] = asyncio.Queue(maxsize=8)
    application_id = 100
    await registry.subscribe(53, application_id, queue_tenant_a)
    await registry.subscribe(54, application_id, queue_tenant_b)

    message = {"event_id": "evt-tenant-a", "event_type": EVENT_DRIVER_LICENCE_BACK_PROCESSED}
    await registry.publish(53, application_id, message)

    received = queue_tenant_a.get_nowait()
    assert received == message
    with pytest.raises(asyncio.QueueEmpty):
        queue_tenant_b.get_nowait()


@pytest.mark.asyncio
async def test_dispatcher_publish_does_not_cross_applications() -> None:
    registry = SubscriberRegistry()
    queue_app_a: asyncio.Queue[dict[str, str]] = asyncio.Queue(maxsize=8)
    queue_app_b: asyncio.Queue[dict[str, str]] = asyncio.Queue(maxsize=8)
    tenant_id = 53
    await registry.subscribe(tenant_id, 501, queue_app_a)
    await registry.subscribe(tenant_id, 502, queue_app_b)

    dispatcher = DomainEventDispatcher()
    dispatcher.registry = registry
    db = AsyncMock()
    row = DomainEventOutbox(
        id=3,
        event_id=uuid.uuid4(),
        event_type=EVENT_DRIVER_LICENCE_CAPTURE_COMPLETE,
        aggregate_type="person_application",
        aggregate_id="501",
        tenant_id=tenant_id,
        payload={},
        attempt_count=0,
    )
    db.commit = AsyncMock()

    await dispatcher._dispatch_row(db, row)

    received = queue_app_a.get_nowait()
    assert received["event_type"] == EVENT_DRIVER_LICENCE_CAPTURE_COMPLETE
    with pytest.raises(asyncio.QueueEmpty):
        queue_app_b.get_nowait()


@pytest.mark.asyncio
async def test_dispatcher_marks_published_on_success() -> None:
    dispatcher = DomainEventDispatcher()
    db = AsyncMock()
    row = DomainEventOutbox(
        id=1,
        event_id=uuid.uuid4(),
        event_type=EVENT_DRIVER_LICENCE_FRONT_PROCESSED,
        aggregate_type="person_application",
        aggregate_id="60",
        tenant_id=53,
        payload={},
        attempt_count=0,
    )
    db.commit = AsyncMock()

    await dispatcher._dispatch_row(db, row)
    assert row.published_at is not None
    assert row.attempt_count == 1
    assert row.last_error is None
    db.commit.assert_awaited()


@pytest.mark.asyncio
async def test_dispatcher_failure_leaves_pending() -> None:
    dispatcher = DomainEventDispatcher()

    async def boom(*args, **kwargs):
        raise RuntimeError("fan-out failed")

    dispatcher.registry.publish = boom  # type: ignore[method-assign]

    db = AsyncMock()
    row = DomainEventOutbox(
        id=2,
        event_id=uuid.uuid4(),
        event_type=EVENT_DRIVER_LICENCE_BACK_PROCESSED,
        aggregate_type="person_application",
        aggregate_id="60",
        tenant_id=53,
        payload={},
        attempt_count=0,
    )
    db.commit = AsyncMock()

    await dispatcher._dispatch_row(db, row)
    assert row.published_at is None
    assert row.attempt_count == 1
    assert row.last_error is not None


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
) -> tuple[int, str]:
    suffix = uuid.uuid4().hex[:10]
    app_row = PersonApplication(
        tenant_id=demo_tenant_id,
        source="domain_event_test",
        status=DriverOnboardingStatus.DRAFT.value,
        requested_role_code="DRIVER",
        application_type="DRIVER",
        email=f"evt.{suffix}@test.invalid",
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


@pytest.mark.asyncio
@pytest.mark.skipif(REQUIRES_DB, reason="DATABASE_URL required")
@pytest.mark.skipif(REQUIRES_TENANT_DB, reason="tenant DB URL required")
class TestDomainEventOutboxIntegration:
    async def test_outbox_row_persists_for_application(
        self,
        demo_tenant_id: int,
        tenant_session: AsyncSession,
    ) -> None:
        app_id, _invite = await _make_draft_driver_app_with_invite(
            tenant_session, demo_tenant_id=demo_tenant_id
        )
        row = DomainEventOutbox(
            event_id=uuid.uuid4(),
            event_type=EVENT_DRIVER_LICENCE_FRONT_PROCESSED,
            aggregate_type="person_application",
            aggregate_id=str(app_id),
            tenant_id=demo_tenant_id,
            payload={},
        )
        tenant_session.add(row)
        await tenant_session.commit()

        found = await tenant_session.scalar(
            select(DomainEventOutbox).where(DomainEventOutbox.event_id == row.event_id)
        )
        assert found is not None
        assert found.published_at is None

    async def test_outbox_rolls_back_with_application_transaction(
        self,
        demo_tenant_id: int,
        tenant_session: AsyncSession,
    ) -> None:
        from app.services.domain_event_outbox import AGGREGATE_TYPE_PERSON_APPLICATION, enqueue_domain_event

        app_id, _invite = await _make_draft_driver_app_with_invite(
            tenant_session, demo_tenant_id=demo_tenant_id
        )
        await enqueue_domain_event(
            tenant_session,
            tenant_id=demo_tenant_id,
            aggregate_type=AGGREGATE_TYPE_PERSON_APPLICATION,
            aggregate_id=str(app_id),
            event_type=EVENT_DRIVER_LICENCE_FRONT_PROCESSED,
            payload={},
        )
        await tenant_session.rollback()

        found = await tenant_session.scalar(
            select(DomainEventOutbox).where(
                DomainEventOutbox.tenant_id == demo_tenant_id,
                DomainEventOutbox.aggregate_id == str(app_id),
                DomainEventOutbox.event_type == EVENT_DRIVER_LICENCE_FRONT_PROCESSED,
            )
        )
        assert found is None

    async def test_sse_invite_authenticates(
        self,
        client: AsyncClient,
        demo_tenant_id: int,
        tenant_session: AsyncSession,
    ) -> None:
        """Stream open is verified live; ASGITransport hangs on infinite SSE bodies."""
        _app_id, invite = await _make_draft_driver_app_with_invite(
            tenant_session, demo_tenant_id=demo_tenant_id
        )
        app_resp = await client.get(
            f"/api/v1/driver-onboarding/applicant/application?token={invite}",
            headers=AUTH_HEADERS,
        )
        assert app_resp.status_code == 200
        assert app_resp.json()["id"] == _app_id

    async def test_sse_document_resume_forbidden(
        self,
        client: AsyncClient,
        demo_tenant_id: int,
        tenant_session: AsyncSession,
    ) -> None:
        app_id, _invite = await _make_draft_driver_app_with_invite(
            tenant_session, demo_tenant_id=demo_tenant_id
        )
        resume = f"resume_{uuid.uuid4().hex}"
        tenant_session.add(
            ApplicationAccessToken(
                tenant_id=demo_tenant_id,
                application_id=app_id,
                token=resume,
                token_hash=_token_sha256_hex(resume),
                expires_at=datetime.now(timezone.utc) + timedelta(days=7),
                revoked_at=None,
                purpose=ro.TOKEN_PURPOSE_DOCUMENT_RESUME,
            )
        )
        await tenant_session.commit()
        resp = await client.get(
            f"/api/v1/driver-onboarding/applicant/application/events?token={resume}",
            headers=AUTH_HEADERS,
        )
        assert resp.status_code == 403

    async def test_pending_row_recovered_by_dispatcher(
        self,
        demo_tenant_id: int,
        tenant_session: AsyncSession,
    ) -> None:
        app_id, _invite = await _make_draft_driver_app_with_invite(
            tenant_session, demo_tenant_id=demo_tenant_id
        )
        row = DomainEventOutbox(
            event_id=uuid.uuid4(),
            event_type=EVENT_DRIVER_LICENCE_FRONT_PROCESSED,
            aggregate_type="person_application",
            aggregate_id=str(app_id),
            tenant_id=demo_tenant_id,
            payload={},
        )
        tenant_session.add(row)
        await tenant_session.commit()

        dispatcher = DomainEventDispatcher()
        await dispatcher.process_pending_for_tenant(demo_tenant_id)

        verify_engine = create_async_engine(_tenant_async_url(), pool_pre_ping=True)
        VerifySession = async_sessionmaker(verify_engine, expire_on_commit=False, class_=AsyncSession)
        async with VerifySession() as verify_session:
            refreshed = await verify_session.scalar(
                select(DomainEventOutbox).where(DomainEventOutbox.event_id == row.event_id)
            )
        await verify_engine.dispose()
        assert refreshed is not None
        assert refreshed.published_at is not None
        assert refreshed.attempt_count == 1
