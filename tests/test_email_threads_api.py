"""Tenant-safe read-only API tests for email threads/messages."""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest
from fastapi import Request
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from app.core.database import AsyncSessionLocal
from app.deps.auth import get_current_user
from app.deps.tenant import require_tenant
from app.deps.tenant_db import open_tenant_session_by_id
from app.main import app
from app.models.email_ingestion import EmailMessage, EmailThread
from app.models.load import Load
from app.models.platform import PlatformTenant

REQUIRES_DB = not os.environ.get("DATABASE_URL")
AUTH_HEADERS = {"Host": "demo.truckerp.me", "X-Tenant-ID": "53"}


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
    fake_user = MagicMock()
    fake_user.user_id = "test-user-id"
    fake_user.email = "test@example.com"
    fake_user.role = "ADMIN"
    app.dependency_overrides[get_current_user] = lambda: fake_user

    def _tenant_from_request(request: Request) -> int:
        tid = getattr(request.state, "tenant_id", None)
        return int(tid) if tid is not None else 53

    app.dependency_overrides[require_tenant] = _tenant_from_request
    yield
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(require_tenant, None)


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
    async def test_list_threads_filters_pagination_and_ordering(self, client, override_auth_tenant) -> None:
        suffix = uuid.uuid4().hex[:8]
        now = datetime.now(timezone.utc)
        await _cleanup_tenant_rows(53, suffix)
        async for tenant_db in open_tenant_session_by_id(53):
            t1 = EmailThread(
                tenant_id=53,
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
                tenant_id=53,
                provider="gmail",
                external_thread_id=f"thread-{suffix}-2",
                subject=f"Older linked-{suffix}",
                participants_json=[{"email": "b@example.com"}],
                snippet="n2",
                last_message_at=now - timedelta(days=1),
                message_count=1,
                unread_count=0,
                linked_load_id=1,
                status="active",
            )
            t3 = EmailThread(
                tenant_id=53,
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
                params={"provider": "gmail", "status": "active", "page": 1, "size": 10},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["total"] >= 2
            filtered = [item for item in data["items"] if isinstance(item.get("subject"), str) and suffix in item["subject"]]
            assert [f["subject"] for f in filtered[:2]] == [f"Newest-{suffix}", f"Older linked-{suffix}"]

        finally:
            await _cleanup_tenant_rows(53, suffix)

    @pytest.mark.asyncio
    async def test_disregard_updates_status_and_hidden_from_default_list(self, client, override_auth_tenant) -> None:
        suffix = uuid.uuid4().hex[:8]
        await _cleanup_tenant_rows(53, suffix)
        thread_id: int
        async for tenant_db in open_tenant_session_by_id(53):
            thread = EmailThread(
                tenant_id=53,
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
            await _cleanup_tenant_rows(53, suffix)

    @pytest.mark.asyncio
    async def test_thread_detail_and_messages_ordering(self, client, override_auth_tenant) -> None:
        suffix = uuid.uuid4().hex[:8]
        now = datetime.now(timezone.utc)
        await _cleanup_tenant_rows(53, suffix)
        thread_id: int
        async for tenant_db in open_tenant_session_by_id(53):
            thread = EmailThread(
                tenant_id=53,
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
                        tenant_id=53,
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
                        tenant_id=53,
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
            await _cleanup_tenant_rows(53, suffix)

    @pytest.mark.asyncio
    async def test_cross_tenant_thread_access_returns_404(self, client, override_auth_tenant) -> None:
        async with AsyncSessionLocal() as platform_db:
            tenants = (
                await platform_db.execute(
                    select(PlatformTenant)
                    .where(PlatformTenant.status == "ACTIVE", PlatformTenant.db_status == "READY")
                    .order_by(PlatformTenant.id.asc())
                )
            ).scalars().all()
        tenant_ids = [int(t.id) for t in tenants]
        if len(tenant_ids) < 2 or 53 not in tenant_ids:
            pytest.skip("Requires at least two ACTIVE/READY tenants including tenant 53")
        other_tenant = next(tid for tid in tenant_ids if tid != 53)

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
    async def test_create_draft_from_needs_review_moves_to_linked(self, client, override_auth_tenant) -> None:
        suffix = uuid.uuid4().hex[:8]
        await _cleanup_tenant_rows(53, suffix)
        thread_id: int
        load_id: int | None = None
        try:
            async for tenant_db in open_tenant_session_by_id(53):
                thread = EmailThread(
                    tenant_id=53,
                    provider="gmail",
                    external_thread_id=f"thread-{suffix}-draft",
                    subject=f"Draft from review {suffix}",
                    participants_json=[{"email": "a@example.com"}],
                    snippet="snip",
                    status="active",
                    intake_bucket="needs_review",
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
            assert r.status_code == 200
            data = r.json()
            assert data["thread"]["intake_bucket"] == "linked"
            assert data["thread"]["routing_reason"] == "manual_create_draft_from_review"
            assert data["thread"]["linked_load_id"] == data["load"]["id"]
            assert data["load"]["load_number"].startswith("INT-")
            assert data["load"]["status"] == "draft"
            load_id = data["load"]["id"]

            listed = await client.get(
                "/api/v1/email-threads",
                headers=AUTH_HEADERS,
                params={"status": "active", "intake_bucket": "linked"},
            )
            assert listed.status_code == 200
            linked_ids = [it["id"] for it in listed.json().get("items", [])]
            assert thread_id in linked_ids
        finally:
            async for tenant_db in open_tenant_session_by_id(53):
                if load_id:
                    await tenant_db.execute(delete(Load).where(Load.id == load_id, Load.tenant_id == 53))
                await tenant_db.execute(
                    delete(EmailMessage).where(
                        EmailMessage.tenant_id == 53,
                        EmailMessage.external_message_id.like(f"%{suffix}%"),
                    )
                )
                await tenant_db.execute(
                    delete(EmailThread).where(
                        EmailThread.tenant_id == 53,
                        EmailThread.external_thread_id.like(f"%{suffix}%"),
                    )
                )
                await tenant_db.commit()
                break

    @pytest.mark.asyncio
    async def test_link_existing_load_moves_to_linked(self, client, override_auth_tenant) -> None:
        suffix = uuid.uuid4().hex[:8]
        await _cleanup_tenant_rows(53, suffix)
        thread_id: int | None = None
        load_id: int | None = None
        try:
            async for tenant_db in open_tenant_session_by_id(53):
                load = Load(
                    tenant_id=53,
                    load_number=f"MANLINK-{suffix}",
                    status="draft",
                    broker_name_snapshot="Test Broker",
                    broker_load_reference=f"REF-{suffix}",
                )
                tenant_db.add(load)
                await tenant_db.flush()
                load_id = load.id
                thread = EmailThread(
                    tenant_id=53,
                    provider="gmail",
                    external_thread_id=f"thread-{suffix}-link",
                    subject=f"Link me {suffix}",
                    participants_json=[],
                    snippet="x",
                    status="active",
                    intake_bucket="needs_review",
                )
                tenant_db.add(thread)
                await tenant_db.commit()
                await tenant_db.refresh(thread)
                thread_id = thread.id
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
        finally:
            if thread_id is not None and load_id is not None:
                async for tenant_db in open_tenant_session_by_id(53):
                    await tenant_db.execute(
                        delete(EmailMessage).where(EmailMessage.tenant_id == 53, EmailMessage.thread_id == thread_id)
                    )
                    await tenant_db.execute(delete(EmailThread).where(EmailThread.id == thread_id, EmailThread.tenant_id == 53))
                    await tenant_db.execute(delete(Load).where(Load.id == load_id, Load.tenant_id == 53))
                    await tenant_db.commit()
                    break

    @pytest.mark.asyncio
    async def test_cannot_create_draft_if_already_linked(self, client, override_auth_tenant) -> None:
        suffix = uuid.uuid4().hex[:8]
        await _cleanup_tenant_rows(53, suffix)
        thread_id: int | None = None
        load_id: int | None = None
        try:
            async for tenant_db in open_tenant_session_by_id(53):
                load = Load(
                    tenant_id=53,
                    load_number=f"ALREADY-{suffix}",
                    status="draft",
                )
                tenant_db.add(load)
                await tenant_db.flush()
                load_id = load.id
                thread = EmailThread(
                    tenant_id=53,
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
                async for tenant_db in open_tenant_session_by_id(53):
                    await tenant_db.execute(delete(EmailThread).where(EmailThread.id == thread_id, EmailThread.tenant_id == 53))
                    await tenant_db.execute(delete(Load).where(Load.id == load_id, Load.tenant_id == 53))
                    await tenant_db.commit()
                    break

    @pytest.mark.asyncio
    async def test_loads_search_tenant_scoped_for_link(self, client, override_auth_tenant) -> None:
        """Wrong-tenant load id cannot be linked (404)."""
        async with AsyncSessionLocal() as platform_db:
            tenants = (
                await platform_db.execute(
                    select(PlatformTenant)
                    .where(PlatformTenant.status == "ACTIVE", PlatformTenant.db_status == "READY")
                    .order_by(PlatformTenant.id.asc())
                )
            ).scalars().all()
        tenant_ids = [int(t.id) for t in tenants]
        if len(tenant_ids) < 2 or 53 not in tenant_ids:
            pytest.skip("Requires at least two ACTIVE/READY tenants including tenant 53")
        other_tenant = next(tid for tid in tenant_ids if tid != 53)

        suffix = uuid.uuid4().hex[:8]
        await _cleanup_tenant_rows(53, suffix)
        await _cleanup_tenant_rows(other_tenant, suffix)
        thread_id_53: int
        other_load_id: int
        try:
            async for tenant_db in open_tenant_session_by_id(other_tenant):
                load = Load(
                    tenant_id=other_tenant,
                    load_number=f"OTHER-{suffix}",
                    status="draft",
                )
                tenant_db.add(load)
                await tenant_db.commit()
                await tenant_db.refresh(load)
                other_load_id = load.id
                break

            async for tenant_db in open_tenant_session_by_id(53):
                thread = EmailThread(
                    tenant_id=53,
                    provider="gmail",
                    external_thread_id=f"thread-{suffix}-53",
                    subject="t",
                    status="active",
                    intake_bucket="needs_review",
                )
                tenant_db.add(thread)
                await tenant_db.commit()
                await tenant_db.refresh(thread)
                thread_id_53 = thread.id
                break

            r = await client.post(
                f"/api/v1/email-threads/{thread_id_53}/link-load",
                headers=AUTH_HEADERS,
                json={"load_id": other_load_id},
            )
            assert r.status_code == 404
        finally:
            async for tenant_db in open_tenant_session_by_id(53):
                await tenant_db.execute(delete(EmailThread).where(EmailThread.tenant_id == 53, EmailThread.external_thread_id.like(f"%{suffix}%")))
                await tenant_db.commit()
                break
            async for tenant_db in open_tenant_session_by_id(other_tenant):
                await tenant_db.execute(delete(Load).where(Load.id == other_load_id, Load.tenant_id == other_tenant))
                await tenant_db.commit()
                break
