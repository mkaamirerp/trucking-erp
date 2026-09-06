"""Tenant-safe read-only API tests for email threads/messages."""
from __future__ import annotations

import os

# Before Settings/app import: enable tenant bypass middleware (same as tests/test_dispatch_trip_numbers.py).
os.environ["ENVIRONMENT"] = "test"
os.environ["ALLOW_TENANT_RESOLUTION_SHORTCUTS"] = "true"

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select
from sqlalchemy.exc import ProgrammingError

from app.core.database import AsyncSessionLocal
from app.deps.tenant_db import open_tenant_session_by_id
from app.deps import entitlements as entitlements_deps
from app.main import app
from app.constants.email_intake_routing import DUPLICATE_PDF_SHA256, format_duplicate_pdf_sha256
from app.models.email_ingestion import EmailMessage, EmailThread
from app.models.load import Load
from app.models.platform import PlatformTenant
from app.services.email_intake_review_service import (
    sync_email_intake_review_for_thread,
    upsert_intake_review_from_intake_source,
)
from tests.support.integration_auth import (
    clear_current_user_and_tenant_overrides,
    install_host_aligned_current_user_and_tenant,
)
from tests.support.tenant_test_ids import platform_tenant_id_for_slug

REQUIRES_DB = not os.environ.get("DATABASE_URL")
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
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac


@pytest.fixture
def override_auth_tenant(test_bypass_env):
    install_host_aligned_current_user_and_tenant(app, role="ADMIN")

    async def _skip_email_inbox_entitlement() -> None:
        return None

    app.dependency_overrides[entitlements_deps.require_email_inbox_entitlement] = _skip_email_inbox_entitlement
    yield
    clear_current_user_and_tenant_overrides(app)
    app.dependency_overrides.pop(entitlements_deps.require_email_inbox_entitlement, None)


@pytest.fixture
async def demo_tid():
    return await platform_tenant_id_for_slug()


async def _cleanup_tenant_rows(tenant_id: int, external_suffix: str) -> None:
    async for tenant_db in open_tenant_session_by_id(tenant_id):
        await tenant_db.execute(
            delete(EmailMessage).where(
                EmailMessage.tenant_id == tenant_id,
                EmailMessage.external_message_id.like(f"%{external_suffix}%"),
            )
        )
        await tenant_db.execute(
            delete(EmailThread).where(
                EmailThread.tenant_id == tenant_id,
                EmailThread.external_thread_id.like(f"%{external_suffix}%"),
            )
        )
        await tenant_db.commit()
        break


@pytest.mark.skipif(REQUIRES_DB, reason="DATABASE_URL required")
class TestEmailThreadsReadAPI:
    @pytest.mark.asyncio
    async def test_list_threads_filters_pagination_and_ordering(self, client, override_auth_tenant, demo_tid) -> None:
        suffix = uuid.uuid4().hex[:8]
        now = datetime.now(timezone.utc)
        await _cleanup_tenant_rows(demo_tid, suffix)
        async for tenant_db in open_tenant_session_by_id(demo_tid):
            t1 = EmailThread(
                tenant_id=demo_tid,
                provider="gmail",
                external_thread_id=f"thread-{suffix}-1",
                subject=f"Newest-{suffix}",
                participants_json=[{"email": "a@example.com"}],
                snippet="n1",
                last_message_at=now,
                message_count=2,
                unread_count=1,
                linked_load_id=None,
                status="active",
            )
            t2 = EmailThread(
                tenant_id=demo_tid,
                provider="gmail",
                external_thread_id=f"thread-{suffix}-2",
                subject=f"Older linked-{suffix}",
                participants_json=[{"email": "b@example.com"}],
                snippet="n2",
                last_message_at=now - timedelta(seconds=30),
                message_count=1,
                unread_count=0,
                linked_load_id=None,
                status="active",
            )
            t3 = EmailThread(
                tenant_id=demo_tid,
                provider="gmail",
                external_thread_id=f"thread-{suffix}-3",
                subject=f"No last message-{suffix}",
                participants_json=[],
                snippet=None,
                last_message_at=None,
                message_count=0,
                unread_count=0,
                status="archived",
            )
            tenant_db.add_all([t1, t2, t3])
            await tenant_db.commit()
            break

        try:
            resp = await client.get(
                "/api/v1/email-threads",
                headers=AUTH_HEADERS,
                params={"provider": "gmail", "status": "active", "page": 1, "size": 50},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["total"] >= 2
            filtered = [item for item in data["items"] if isinstance(item.get("subject"), str) and suffix in item["subject"]]
            assert [f["subject"] for f in filtered[:2]] == [f"Newest-{suffix}", f"Older linked-{suffix}"]

        finally:
            await _cleanup_tenant_rows(demo_tid, suffix)

    @pytest.mark.asyncio
    async def test_disregard_updates_status_and_hidden_from_default_list(self, client, override_auth_tenant, demo_tid) -> None:
        suffix = uuid.uuid4().hex[:8]
        await _cleanup_tenant_rows(demo_tid, suffix)
        thread_id: int
        async for tenant_db in open_tenant_session_by_id(demo_tid):
            thread = EmailThread(
                tenant_id=demo_tid,
                provider="gmail",
                external_thread_id=f"thread-{suffix}-disregard",
                subject=f"Disregard me {suffix}",
                participants_json=[],
                snippet="ignore",
                status="active",
            )
            tenant_db.add(thread)
            await tenant_db.commit()
            await tenant_db.refresh(thread)
            thread_id = thread.id
            break

        try:
            d = await client.post(f"/api/v1/email-threads/{thread_id}/disregard", headers=AUTH_HEADERS)
            assert d.status_code == 200
            assert d.json()["status"] == "disregarded"
            assert d.json().get("intake_bucket") == "disregarded"

            default_list = await client.get("/api/v1/email-threads", headers=AUTH_HEADERS)
            assert default_list.status_code == 200
            ids = [it["id"] for it in default_list.json().get("items", [])]
            assert thread_id not in ids

            explicit = await client.get(
                "/api/v1/email-threads",
                headers=AUTH_HEADERS,
                params={"status": "disregarded"},
            )
            assert explicit.status_code == 200
            ids_explicit = [it["id"] for it in explicit.json().get("items", [])]
            assert thread_id in ids_explicit
        finally:
            await _cleanup_tenant_rows(demo_tid, suffix)

    @pytest.mark.asyncio
    async def test_thread_detail_and_messages_ordering(self, client, override_auth_tenant, demo_tid) -> None:
        suffix = uuid.uuid4().hex[:8]
        now = datetime.now(timezone.utc)
        await _cleanup_tenant_rows(demo_tid, suffix)
        thread_id: int
        async for tenant_db in open_tenant_session_by_id(demo_tid):
            thread = EmailThread(
                tenant_id=demo_tid,
                provider="gmail",
                external_thread_id=f"thread-{suffix}-detail",
                subject="Detail thread",
                participants_json=[{"email": "c@example.com"}],
                snippet="detail",
                status="active",
            )
            tenant_db.add(thread)
            await tenant_db.flush()
            thread_id = thread.id
            tenant_db.add_all(
                [
                    EmailMessage(
                        tenant_id=demo_tid,
                        thread_id=thread_id,
                        provider="gmail",
                        external_message_id=f"msg-{suffix}-a",
                        external_thread_id=thread.external_thread_id,
                        direction="inbound",
                        from_email="from-a@example.com",
                        to_json=[{"email": "to@example.com"}],
                        received_at=now + timedelta(minutes=10),
                    ),
                    EmailMessage(
                        tenant_id=demo_tid,
                        thread_id=thread_id,
                        provider="gmail",
                        external_message_id=f"msg-{suffix}-b",
                        external_thread_id=thread.external_thread_id,
                        direction="inbound",
                        from_email="from-b@example.com",
                        to_json=[{"email": "to@example.com"}],
                        received_at=now,
                    ),
                ]
            )
            await tenant_db.commit()
            break

        try:
            detail = await client.get(f"/api/v1/email-threads/{thread_id}", headers=AUTH_HEADERS)
            assert detail.status_code == 200
            assert detail.json()["id"] == thread_id

            messages = await client.get(f"/api/v1/email-threads/{thread_id}/messages", headers=AUTH_HEADERS)
            assert messages.status_code == 200
            items = messages.json()
            assert len(items) == 2
            assert items[0]["external_message_id"].endswith("-b")
            assert items[1]["external_message_id"].endswith("-a")
        finally:
            await _cleanup_tenant_rows(demo_tid, suffix)

    @pytest.mark.asyncio
    async def test_cross_tenant_thread_access_returns_404(self, client, override_auth_tenant, demo_tid) -> None:
        async with AsyncSessionLocal() as platform_db:
            tenants = (
                await platform_db.execute(
                    select(PlatformTenant)
                    .where(PlatformTenant.status == "ACTIVE", PlatformTenant.db_status == "READY")
                    .order_by(PlatformTenant.id.asc())
                )
            ).scalars().all()
        tenant_ids = [int(t.id) for t in tenants]
        if len(tenant_ids) < 2 or demo_tid not in tenant_ids:
            pytest.skip("Requires at least two ACTIVE/READY tenants including slug=demo")
        other_tenant = next(tid for tid in tenant_ids if tid != demo_tid)

        suffix = uuid.uuid4().hex[:8]
        await _cleanup_tenant_rows(other_tenant, suffix)
        thread_id: int
        async for tenant_db in open_tenant_session_by_id(other_tenant):
            thread = EmailThread(
                tenant_id=other_tenant,
                provider="gmail",
                external_thread_id=f"thread-{suffix}-x",
                subject="Other tenant thread",
                participants_json=[],
                status="active",
            )
            tenant_db.add(thread)
            await tenant_db.commit()
            await tenant_db.refresh(thread)
            thread_id = thread.id
            break

        try:
            detail = await client.get(f"/api/v1/email-threads/{thread_id}", headers=AUTH_HEADERS)
            assert detail.status_code == 404
            messages = await client.get(f"/api/v1/email-threads/{thread_id}/messages", headers=AUTH_HEADERS)
            assert messages.status_code == 404
        finally:
            await _cleanup_tenant_rows(other_tenant, suffix)


@pytest.mark.skipif(REQUIRES_DB, reason="DATABASE_URL required")
class TestEmailThreadIntakeManualActions:
    @pytest.mark.asyncio
    async def test_create_draft_from_needs_review_moves_to_linked(self, client, override_auth_tenant, demo_tid) -> None:
        suffix = uuid.uuid4().hex[:8]
        await _cleanup_tenant_rows(demo_tid, suffix)
        thread_id: int
        load_id: int | None = None
        try:
            async for tenant_db in open_tenant_session_by_id(demo_tid):
                thread = EmailThread(
                    tenant_id=demo_tid,
                    provider="gmail",
                    external_thread_id=f"thread-{suffix}-draft",
                    subject=f"Draft from review {suffix}",
                    participants_json=[{"email": "a@example.com"}],
                    snippet="snip",
                    status="active",
                    intake_bucket="needs_review",
                    routing_reason="intake_fixture_review|fixture=draft_from_review",
                )
                tenant_db.add(thread)
                await tenant_db.commit()
                await tenant_db.refresh(thread)
                thread_id = thread.id
                await sync_email_intake_review_for_thread(tenant_db, demo_tid, thread_id)
                await tenant_db.commit()
                break

            r = await client.post(
                f"/api/v1/email-threads/{thread_id}/create-draft-load",
                headers=AUTH_HEADERS,
            )
            assert r.status_code == 200
            data = r.json()
            assert data["thread"]["intake_bucket"] == "linked"
            assert data["thread"]["routing_reason"] == "manual_create_draft_from_review"
            assert data["thread"]["linked_load_id"] == data["load"]["id"]
            assert data["load"]["load_number"].startswith("INT-")
            assert data["load"]["status"] == "draft"
            load_id = data["load"]["id"]

            ir = await client.get(f"/api/v1/email-threads/{thread_id}/intake-review", headers=AUTH_HEADERS)
            assert ir.status_code == 200
            bundle = ir.json()
            assert bundle["review"] is not None
            assert bundle["review"]["status"] == "resolved"
            ev_types = [e["event_type"] for e in bundle["events"]]
            assert "review_opened" in ev_types
            assert "auto_resolved_thread_linked_load" in ev_types
            auto_ev = next(e for e in bundle["events"] if e["event_type"] == "auto_resolved_thread_linked_load")
            assert auto_ev.get("reason_code") == "thread_linked_load"

            listed = await client.get(
                "/api/v1/email-threads",
                headers=AUTH_HEADERS,
                params={"status": "active", "intake_bucket": "linked"},
            )
            assert listed.status_code == 200
            linked_ids = [it["id"] for it in listed.json().get("items", [])]
            assert thread_id in linked_ids
        finally:
            async for tenant_db in open_tenant_session_by_id(demo_tid):
                if load_id:
                    await tenant_db.execute(delete(Load).where(Load.id == load_id, Load.tenant_id == demo_tid))
                await tenant_db.execute(
                    delete(EmailMessage).where(
                        EmailMessage.tenant_id == demo_tid,
                        EmailMessage.external_message_id.like(f"%{suffix}%"),
                    )
                )
                await tenant_db.execute(
                    delete(EmailThread).where(
                        EmailThread.tenant_id == demo_tid,
                        EmailThread.external_thread_id.like(f"%{suffix}%"),
                    )
                )
                await tenant_db.commit()
                break

    @pytest.mark.asyncio
    async def test_link_existing_load_moves_to_linked(self, client, override_auth_tenant, demo_tid) -> None:
        suffix = uuid.uuid4().hex[:8]
        await _cleanup_tenant_rows(demo_tid, suffix)
        thread_id: int | None = None
        load_id: int | None = None
        try:
            async for tenant_db in open_tenant_session_by_id(demo_tid):
                load = Load(
                    tenant_id=demo_tid,
                    load_number=f"MANLINK-{suffix}",
                    status="draft",
                    broker_name_snapshot="Test Broker",
                    broker_load_reference=f"REF-{suffix}",
                )
                tenant_db.add(load)
                await tenant_db.flush()
                load_id = load.id
                thread = EmailThread(
                    tenant_id=demo_tid,
                    provider="gmail",
                    external_thread_id=f"thread-{suffix}-link",
                    subject=f"Link me {suffix}",
                    participants_json=[],
                    snippet="x",
                    status="active",
                    intake_bucket="needs_review",
                    routing_reason="intake_fixture_review|fixture=link_existing",
                )
                tenant_db.add(thread)
                await tenant_db.commit()
                await tenant_db.refresh(thread)
                thread_id = thread.id
                await sync_email_intake_review_for_thread(tenant_db, demo_tid, thread_id)
                await tenant_db.commit()
                break

            r = await client.post(
                f"/api/v1/email-threads/{thread_id}/link-load",
                headers=AUTH_HEADERS,
                json={"load_id": load_id},
            )
            assert r.status_code == 200
            data = r.json()
            assert data["thread"]["intake_bucket"] == "linked"
            assert data["thread"]["linked_load_id"] == load_id
            assert data["thread"]["routing_reason"] == "manual_link_existing_load"
            assert data["load"]["id"] == load_id

            ir = await client.get(f"/api/v1/email-threads/{thread_id}/intake-review", headers=AUTH_HEADERS)
            assert ir.status_code == 200
            bundle = ir.json()
            assert bundle["review"] is not None
            assert bundle["review"]["status"] == "resolved"
            ev_types = [e["event_type"] for e in bundle["events"]]
            assert "review_opened" in ev_types
            assert "auto_resolved_thread_linked_load" in ev_types
            auto_ev = next(e for e in bundle["events"] if e["event_type"] == "auto_resolved_thread_linked_load")
            assert auto_ev.get("reason_code") == "thread_linked_load"
        finally:
            if thread_id is not None and load_id is not None:
                async for tenant_db in open_tenant_session_by_id(demo_tid):
                    await tenant_db.execute(
                        delete(EmailMessage).where(EmailMessage.tenant_id == demo_tid, EmailMessage.thread_id == thread_id)
                    )
                    await tenant_db.execute(delete(EmailThread).where(EmailThread.id == thread_id, EmailThread.tenant_id == demo_tid))
                    await tenant_db.execute(delete(Load).where(Load.id == load_id, Load.tenant_id == demo_tid))
                    await tenant_db.commit()
                    break

    @pytest.mark.asyncio
    async def test_intake_review_resolve_reopen_dismiss_reason_codes(self, client, override_auth_tenant, demo_tid) -> None:
        suffix = uuid.uuid4().hex[:8]
        await _cleanup_tenant_rows(demo_tid, suffix)
        thread_id: int | None = None
        try:
            async for tenant_db in open_tenant_session_by_id(demo_tid):
                thread = EmailThread(
                    tenant_id=demo_tid,
                    provider="gmail",
                    external_thread_id=f"thread-{suffix}-reasoncodes",
                    subject=f"Fixture {suffix}",
                    participants_json=[],
                    snippet="x",
                    status="active",
                    intake_bucket="needs_review",
                    routing_reason="intake_fixture_review|fixture=reason_validation",
                )
                tenant_db.add(thread)
                await tenant_db.commit()
                await tenant_db.refresh(thread)
                thread_id = thread.id
                await sync_email_intake_review_for_thread(tenant_db, demo_tid, thread_id)
                await tenant_db.commit()
                break

            bad = await client.post(
                f"/api/v1/email-threads/{thread_id}/intake-review/resolve",
                headers=AUTH_HEADERS,
                json={"reason_code": "custom_note_should_fail"},
            )
            assert bad.status_code == 422

            ok = await client.post(
                f"/api/v1/email-threads/{thread_id}/intake-review/resolve",
                headers=AUTH_HEADERS,
                json={"reason_code": "resolved_reviewed", "note": "ok"},
            )
            assert ok.status_code == 200
            assert ok.json()["status"] == "resolved"

            bad_reopen = await client.post(
                f"/api/v1/email-threads/{thread_id}/intake-review/reopen",
                headers=AUTH_HEADERS,
                json={"reason_code": "anything"},
            )
            assert bad_reopen.status_code == 422

            reopened = await client.post(
                f"/api/v1/email-threads/{thread_id}/intake-review/reopen",
                headers=AUTH_HEADERS,
                json={"reason_code": "reopened_operator"},
            )
            assert reopened.status_code == 200
            assert reopened.json()["status"] == "open"

            bad_dismiss = await client.post(
                f"/api/v1/email-threads/{thread_id}/intake-review/dismiss",
                headers=AUTH_HEADERS,
                json={"reason_code": "resolved_reviewed"},
            )
            assert bad_dismiss.status_code == 422

            dismissed = await client.post(
                f"/api/v1/email-threads/{thread_id}/intake-review/dismiss",
                headers=AUTH_HEADERS,
                json={"reason_code": "dismissed_not_intake"},
            )
            assert dismissed.status_code == 200
            assert dismissed.json()["status"] == "dismissed"
        finally:
            if thread_id is not None:
                async for tenant_db in open_tenant_session_by_id(demo_tid):
                    await tenant_db.execute(delete(EmailThread).where(EmailThread.id == thread_id, EmailThread.tenant_id == demo_tid))
                    await tenant_db.commit()
                    break

    @pytest.mark.asyncio
    async def test_duplicate_review_link_prior_confirm_and_mismatch(self, client, override_auth_tenant, demo_tid) -> None:
        suffix = uuid.uuid4().hex[:8]
        await _cleanup_tenant_rows(demo_tid, suffix)
        thread_id: int | None = None
        load_id: int | None = None
        try:
            async for tenant_db in open_tenant_session_by_id(demo_tid):
                load = Load(
                    tenant_id=demo_tid,
                    load_number=f"DUPDUP-{suffix}",
                    status="draft",
                )
                tenant_db.add(load)
                await tenant_db.flush()
                load_id = load.id
                dup_rr = format_duplicate_pdf_sha256(
                    prior_load_id=load_id,
                    content_sha256="a" * 64,
                    detection_source="pdf_sha256_match_same_tenant",
                )
                thread = EmailThread(
                    tenant_id=demo_tid,
                    provider="gmail",
                    external_thread_id=f"thread-{suffix}-dup",
                    subject=f"Dup {suffix}",
                    participants_json=[],
                    snippet="x",
                    status="active",
                    intake_bucket="needs_review",
                    routing_reason=dup_rr,
                )
                tenant_db.add(thread)
                await tenant_db.commit()
                await tenant_db.refresh(thread)
                thread_id = thread.id
                await upsert_intake_review_from_intake_source(
                    tenant_db,
                    demo_tid,
                    thread_id,
                    primary_code=DUPLICATE_PDF_SHA256,
                    detail_extensions={},
                    routing_reason_snapshot=thread.routing_reason,
                )
                await tenant_db.commit()
                break

            bad = await client.post(
                f"/api/v1/email-threads/{thread_id}/intake-review/duplicate/link-prior",
                headers=AUTH_HEADERS,
                json={"prior_load_id": 9_999_999},
            )
            assert bad.status_code == 409
            assert bad.json()["detail"] == "prior_load_id_mismatch"

            bad_dismiss = await client.post(
                f"/api/v1/email-threads/{thread_id}/intake-review/duplicate/dismiss-false-positive",
                headers=AUTH_HEADERS,
                json={"reason_code": "should_not_be_here"},
            )
            assert bad_dismiss.status_code == 422

            r = await client.post(
                f"/api/v1/email-threads/{thread_id}/intake-review/duplicate/link-prior",
                headers=AUTH_HEADERS,
                json={},
            )
            assert r.status_code == 200
            data = r.json()
            assert data["thread"]["linked_load_id"] == load_id

            ir = await client.get(f"/api/v1/email-threads/{thread_id}/intake-review", headers=AUTH_HEADERS)
            assert ir.status_code == 200
            ev_types = [e["event_type"] for e in ir.json().get("events", [])]
            assert "duplicate_link_prior" in ev_types
            assert "auto_resolved_thread_linked_load" in ev_types

            cr = await client.post(
                f"/api/v1/email-threads/{thread_id}/intake-review/duplicate/confirm",
                headers=AUTH_HEADERS,
                json={},
            )
            assert cr.status_code == 200

            ir2 = await client.get(f"/api/v1/email-threads/{thread_id}/intake-review", headers=AUTH_HEADERS)
            assert ir2.status_code == 200
            ev_types2 = [e["event_type"] for e in ir2.json().get("events", [])]
            assert "duplicate_confirmed" in ev_types2
        finally:
            if thread_id is not None and load_id is not None:
                async for tenant_db in open_tenant_session_by_id(demo_tid):
                    await tenant_db.execute(
                        delete(EmailMessage).where(EmailMessage.tenant_id == demo_tid, EmailMessage.thread_id == thread_id)
                    )
                    await tenant_db.execute(delete(EmailThread).where(EmailThread.id == thread_id, EmailThread.tenant_id == demo_tid))
                    await tenant_db.execute(delete(Load).where(Load.id == load_id, Load.tenant_id == demo_tid))
                    await tenant_db.commit()
                    break

    @pytest.mark.asyncio
    async def test_cannot_create_draft_if_already_linked(self, client, override_auth_tenant, demo_tid) -> None:
        suffix = uuid.uuid4().hex[:8]
        await _cleanup_tenant_rows(demo_tid, suffix)
        thread_id: int | None = None
        load_id: int | None = None
        try:
            async for tenant_db in open_tenant_session_by_id(demo_tid):
                load = Load(
                    tenant_id=demo_tid,
                    load_number=f"ALREADY-{suffix}",
                    status="draft",
                )
                tenant_db.add(load)
                await tenant_db.flush()
                load_id = load.id
                thread = EmailThread(
                    tenant_id=demo_tid,
                    provider="gmail",
                    external_thread_id=f"thread-{suffix}-al",
                    subject="x",
                    status="active",
                    intake_bucket="needs_review",
                    linked_load_id=load_id,
                )
                tenant_db.add(thread)
                await tenant_db.commit()
                await tenant_db.refresh(thread)
                thread_id = thread.id
                break

            r = await client.post(
                f"/api/v1/email-threads/{thread_id}/create-draft-load",
                headers=AUTH_HEADERS,
            )
            assert r.status_code == 400
        finally:
            if thread_id is not None and load_id is not None:
                async for tenant_db in open_tenant_session_by_id(demo_tid):
                    await tenant_db.execute(delete(EmailThread).where(EmailThread.id == thread_id, EmailThread.tenant_id == demo_tid))
                    await tenant_db.execute(delete(Load).where(Load.id == load_id, Load.tenant_id == demo_tid))
                    await tenant_db.commit()
                    break

    @pytest.mark.asyncio
    async def test_loads_search_tenant_scoped_for_link(self, client, override_auth_tenant, demo_tid) -> None:
        """
        A load_id that exists only in another tenant DB must not link on the demo workspace (404).

        Each tenant has its own Postgres DB, so SERIAL ids can collide across tenants. Using the other
        tenant's PK blindly can accidentally match a different load in the demo tenant DB. We allocate a load in
        the other DB until its id is absent from the demo loads table.
        """
        async with AsyncSessionLocal() as platform_db:
            tenants = (
                await platform_db.execute(
                    select(PlatformTenant)
                    .where(PlatformTenant.status == "ACTIVE", PlatformTenant.db_status == "READY")
                    .order_by(PlatformTenant.id.asc())
                )
            ).scalars().all()
        tenant_ids = [int(t.id) for t in tenants]
        if len(tenant_ids) < 2 or demo_tid not in tenant_ids:
            pytest.skip("Requires at least two ACTIVE/READY tenants including slug=demo")
        other_tenant = next(tid for tid in tenant_ids if tid != demo_tid)

        suffix = uuid.uuid4().hex[:8]
        await _cleanup_tenant_rows(demo_tid, suffix)
        await _cleanup_tenant_rows(other_tenant, suffix)
        thread_id_demo: int
        other_load_id: int | None = None
        try:
            async for tenant_db in open_tenant_session_by_id(demo_tid):
                res = await tenant_db.execute(select(Load.id).where(Load.tenant_id == demo_tid))
                ids_demo = {int(row[0]) for row in res.all()}
                break

            try:
                for attempt in range(80):
                    async for tenant_db in open_tenant_session_by_id(other_tenant):
                        load = Load(
                            tenant_id=other_tenant,
                            load_number=f"OTHER-{suffix}-{attempt}",
                            status="draft",
                        )
                        tenant_db.add(load)
                        await tenant_db.commit()
                        await tenant_db.refresh(load)
                        if load.id not in ids_demo:
                            other_load_id = int(load.id)
                        else:
                            await tenant_db.delete(load)
                            await tenant_db.commit()
                        break
                    if other_load_id is not None:
                        break
            except ProgrammingError as exc:
                if "active_dispatch_trip_id" in str(exc) or "trip_number" in str(exc):
                    pytest.skip(
                        "Environment hygiene: second workspace DB missing loads.dispatch columns "
                        "(e.g. active_dispatch_trip_id). Run tenant Alembic to head on that DB, or expect "
                        "this test to stay skipped until schemas align."
                    )
                raise

            if other_load_id is None:
                pytest.skip("Could not allocate a load PK in other tenant that is absent from the demo loads table")

            async for tenant_db in open_tenant_session_by_id(demo_tid):
                thread = EmailThread(
                    tenant_id=demo_tid,
                    provider="gmail",
                    external_thread_id=f"thread-{suffix}-scopedlink",
                    subject="t",
                    status="active",
                    intake_bucket="needs_review",
                )
                tenant_db.add(thread)
                await tenant_db.commit()
                await tenant_db.refresh(thread)
                thread_id_demo = thread.id
                break

            r = await client.post(
                f"/api/v1/email-threads/{thread_id_demo}/link-load",
                headers=AUTH_HEADERS,
                json={"load_id": other_load_id},
            )
            assert r.status_code == 404
        finally:
            async for tenant_db in open_tenant_session_by_id(demo_tid):
                await tenant_db.execute(delete(EmailThread).where(EmailThread.tenant_id == demo_tid, EmailThread.external_thread_id.like(f"%{suffix}%")))
                await tenant_db.commit()
                break
            if other_load_id is not None:
                async for tenant_db in open_tenant_session_by_id(other_tenant):
                    await tenant_db.execute(delete(Load).where(Load.id == other_load_id, Load.tenant_id == other_tenant))
                    await tenant_db.commit()
                    break
