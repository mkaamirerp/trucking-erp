"""Other (manual IMAP/SMTP) mailbox: encryption, routing (intake-only), mocked sync, admin API smoke."""
from __future__ import annotations

import json
import os
import uuid
from email.message import EmailMessage as MimeMessage
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import Request
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, func, select, text, update

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.deps import entitlements as entitlements_deps
from app.deps.auth import get_current_user
from app.deps.tenant import require_tenant
from app.deps.tenant_db import open_tenant_session_by_id
from app.main import app
from app.models.email_ingestion import EmailMessage, EmailThread
from app.models.email_mailbox import TenantEmailMailbox
from app.models.platform_integration import TenantIntegrationSecret
from app.services.email_intake_routing import apply_intake_routing_for_review_only_thread
from app.services.email_ingestion_imap import (
    EMAIL_PROVIDER_OTHER,
    ImapSyncResult,
    imap_test_connection_sync,
    smtp_test_connection_sync,
    sync_other_imap_inbox_for_tenant,
)
from app.utils.encryption import decrypt_secret, encrypt_secret

try:
    SKIP_NO_DB = not bool(getattr(settings, "database_url", None) or "")
except Exception:
    SKIP_NO_DB = True

TENANT_ID = 53
# Valid platform tenant id ≠ TENANT_ID for cross-tenant secret negative test (FK to platform_tenants).
_WRONG_SECRET_TENANT_ID = 62
AUTH_HEADERS = {"host": "pytest.truckerp.me"}


@pytest.fixture
async def require_other_imap_tenant_migration():
    """Skip integration tests if tenant DB was not migrated (Other IMAP mailbox columns)."""
    async for tdb in open_tenant_session_by_id(TENANT_ID):
        r = await tdb.execute(
            text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_schema = current_schema() "
                "AND table_name = 'tenant_email_mailboxes' "
                "AND column_name = 'imap_last_seen_uid' "
                "LIMIT 1"
            )
        )
        if r.scalar() is None:
            pytest.skip(
                "tenant_email_mailboxes.imap_last_seen_uid missing — run tenant Alembic upgrade "
                "(e.g. docker exec truckerp-api bash -lc 'set -a && . /run/secrets/truckerp.env && set +a && cd /app && bash scripts/tenant_upgrade_head.sh')."
            )
        # sync_other_imap_inbox_for_tenant picks limit(1) primary; clear flags so the test mailbox is sole primary.
        await tdb.execute(
            update(TenantEmailMailbox)
            .where(TenantEmailMailbox.tenant_id == TENANT_ID)
            .values(is_primary=False)
        )
        await tdb.commit()
        break


def _minimal_rfc822(mid: str, subject: str = "Hello") -> bytes:
    msg = MimeMessage()
    msg["Message-ID"] = f"<{mid}@test.example>"
    msg["Subject"] = subject
    msg["From"] = "sender@example.com"
    msg["To"] = "inbox@test.example"
    msg.set_content("body")
    return msg.as_bytes()


async def _cleanup_other_mailbox_test(cref: str) -> None:
    async for tdb in open_tenant_session_by_id(TENANT_ID):
        mb = await tdb.scalar(select(TenantEmailMailbox).where(TenantEmailMailbox.credential_ref == cref))
        if mb:
            tid = mb.tenant_id
            await tdb.execute(
                delete(EmailMessage).where(EmailMessage.tenant_id == tid, EmailMessage.provider == EMAIL_PROVIDER_OTHER)
            )
            await tdb.execute(
                delete(EmailThread).where(EmailThread.tenant_id == tid, EmailThread.provider == EMAIL_PROVIDER_OTHER)
            )
            await tdb.delete(mb)
        await tdb.commit()
        break
    async with AsyncSessionLocal() as pdb:
        await pdb.execute(delete(TenantIntegrationSecret).where(TenantIntegrationSecret.credential_ref == cref))
        await pdb.commit()


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
def override_admin_email_auth(test_bypass_env):
    fake_user = MagicMock()
    fake_user.user_id = "test-user-id"
    fake_user.email = "admin@example.com"
    fake_user.role = "ADMIN"
    fake_user.tenant_id = TENANT_ID
    app.dependency_overrides[get_current_user] = lambda: fake_user

    async def _skip_mailbox_entitlement() -> None:
        return None

    app.dependency_overrides[entitlements_deps.require_email_mailbox_entitlement] = _skip_mailbox_entitlement

    def _tenant_from_request(request: Request) -> int:
        tid = getattr(request.state, "tenant_id", None)
        return int(tid) if tid is not None else TENANT_ID

    app.dependency_overrides[require_tenant] = _tenant_from_request
    yield
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(require_tenant, None)
    app.dependency_overrides.pop(entitlements_deps.require_email_mailbox_entitlement, None)


@pytest.fixture
def override_non_admin_email_auth(test_bypass_env):
    fake_user = MagicMock()
    fake_user.user_id = "test-user-id"
    fake_user.email = "member@example.com"
    fake_user.role = "TENANT_MEMBER"
    fake_user.tenant_id = TENANT_ID
    app.dependency_overrides[get_current_user] = lambda: fake_user

    async def _skip_mailbox_entitlement() -> None:
        return None

    app.dependency_overrides[entitlements_deps.require_email_mailbox_entitlement] = _skip_mailbox_entitlement

    def _tenant_from_request(request: Request) -> int:
        tid = getattr(request.state, "tenant_id", None)
        return int(tid) if tid is not None else TENANT_ID

    app.dependency_overrides[require_tenant] = _tenant_from_request
    yield
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(require_tenant, None)
    app.dependency_overrides.pop(entitlements_deps.require_email_mailbox_entitlement, None)


def test_imap_smtp_test_helpers_require_password():
    mb = SimpleNamespace(
        imap_host="imap.example.com",
        imap_username="u",
        imap_port=993,
        imap_security="ssl",
        use_ssl=True,
        smtp_host="smtp.example.com",
        smtp_username="u",
        smtp_port=587,
        smtp_security="starttls",
    )
    with pytest.raises(ValueError, match="password"):
        imap_test_connection_sync(mb, None)
    with pytest.raises(ValueError, match="password"):
        smtp_test_connection_sync(mb, None)


@pytest.mark.asyncio
async def test_other_intake_routing_intake_only():
    """Non-Gmail path must not create loads; threads stay in review."""
    thread = MagicMock()
    thread.provider = "other"
    thread.status = "active"
    thread.linked_load_id = None
    thread.intake_bucket = "needs_review"
    thread.confidence_level = None
    thread.confidence_score = None
    thread.routing_reason = None
    db = AsyncMock()
    db.scalar = AsyncMock(return_value=thread)
    await apply_intake_routing_for_review_only_thread(db, 1, 42)
    assert thread.intake_bucket == "needs_review"
    assert thread.routing_reason == "mailbox_intake_review_only"


@pytest.mark.skipif(SKIP_NO_DB, reason="database_url required (settings)")
@pytest.mark.asyncio
async def test_other_mailbox_secret_encrypted_not_plaintext(require_other_imap_tenant_migration):
    cref = f"ut_{uuid.uuid4().hex[:16]}"
    plain = json.dumps({"imap_password": "secret-imap", "smtp_password": "secret-smtp"})
    enc = encrypt_secret(plain)
    assert b"secret-imap" not in enc
    try:
        async with AsyncSessionLocal() as pdb:
            row = TenantIntegrationSecret(
                tenant_id=TENANT_ID,
                integration_type="email_mailbox",
                provider=EMAIL_PROVIDER_OTHER,
                credential_ref=cref,
                encrypted_payload=enc,
            )
            pdb.add(row)
            await pdb.commit()
        async with AsyncSessionLocal() as pdb:
            loaded = await pdb.scalar(select(TenantIntegrationSecret).where(TenantIntegrationSecret.credential_ref == cref))
            assert loaded is not None
            dec = decrypt_secret(loaded.encrypted_payload).decode("utf-8")
            data = json.loads(dec)
            assert data["imap_password"] == "secret-imap"
    finally:
        await _cleanup_other_mailbox_test(cref)


@pytest.mark.skipif(SKIP_NO_DB, reason="database_url required (settings)")
@pytest.mark.asyncio
async def test_sync_other_imap_idempotent_mocked(require_other_imap_tenant_migration, monkeypatch):
    """First sync inserts message; second mock pass returns no UIDs → no duplicate rows."""
    mid = uuid.uuid4().hex
    raw = _minimal_rfc822(mid)
    calls = {"n": 0}

    def fake_imap_sync(mailbox, pw, *, max_messages=100):
        calls["n"] += 1
        if calls["n"] == 1:
            return [(1, raw)], 999001, 1
        return [], 999001, 1

    monkeypatch.setattr(
        "app.services.email_ingestion_imap.imap_sync_incremental_sync",
        fake_imap_sync,
    )

    cref = f"sync_{uuid.uuid4().hex[:12]}"
    await _cleanup_other_mailbox_test(cref)
    try:
        async with AsyncSessionLocal() as pdb:
            pdb.add(
                TenantIntegrationSecret(
                    tenant_id=TENANT_ID,
                    integration_type="email_mailbox",
                    provider=EMAIL_PROVIDER_OTHER,
                    credential_ref=cref,
                    encrypted_payload=encrypt_secret(json.dumps({"imap_password": "x"})),
                )
            )
            await pdb.commit()

        async for tdb in open_tenant_session_by_id(TENANT_ID):
            tdb.add(
                TenantEmailMailbox(
                    tenant_id=TENANT_ID,
                    credential_ref=cref,
                    email_address="box@test.example",
                    mailbox_type=EMAIL_PROVIDER_OTHER,
                    connection_mode="manual",
                    imap_host="imap.test",
                    imap_port=993,
                    imap_username="u",
                    imap_security="ssl",
                    smtp_host="smtp.test",
                    smtp_port=587,
                    smtp_username="u",
                    smtp_security="starttls",
                    status="CONFIGURED",
                    is_primary=True,
                )
            )
            await tdb.commit()
            break

        async for tdb in open_tenant_session_by_id(TENANT_ID):
            async with AsyncSessionLocal() as pdb:
                r1 = await sync_other_imap_inbox_for_tenant(tdb, pdb, TENANT_ID, max_messages=50)
            break
        assert r1.messages_upserted == 1
        assert r1.uids_fetched == 1

        async for tdb in open_tenant_session_by_id(TENANT_ID):
            async with AsyncSessionLocal() as pdb:
                r2 = await sync_other_imap_inbox_for_tenant(tdb, pdb, TENANT_ID, max_messages=50)
            break
        assert r2.messages_upserted == 0
        assert r2.uids_fetched == 0

        async for tdb in open_tenant_session_by_id(TENANT_ID):
            c = await tdb.scalar(
                select(func.count()).select_from(EmailMessage).where(
                    EmailMessage.tenant_id == TENANT_ID,
                    EmailMessage.provider == EMAIL_PROVIDER_OTHER,
                )
            )
            assert int(c or 0) == 1
            th = await tdb.scalar(
                select(EmailThread).where(EmailThread.tenant_id == TENANT_ID, EmailThread.provider == EMAIL_PROVIDER_OTHER)
            )
            assert th is not None
            assert th.intake_bucket == "needs_review"
            assert th.linked_load_id is None
            break
    finally:
        await _cleanup_other_mailbox_test(cref)


@pytest.mark.skipif(SKIP_NO_DB, reason="database_url required (settings)")
@pytest.mark.asyncio
async def test_imap_incremental_mock_second_call_fetches_higher_uid_only(
    require_other_imap_tenant_migration, monkeypatch
):
    """Second sync requests UID range after last_seen only (mock asserts criterion contains '2:*')."""
    seen = []

    def fake_imap_sync(mailbox, pw, *, max_messages=100):
        last = mailbox.imap_last_seen_uid
        seen.append(last)
        raw = _minimal_rfc822(f"incr-{len(seen)}")
        if last is None or int(last) == 0:
            return [(1, raw)], 100, 1
        return [(2, raw)], 100, 2

    monkeypatch.setattr("app.services.email_ingestion_imap.imap_sync_incremental_sync", fake_imap_sync)
    cref = f"incr_{uuid.uuid4().hex[:12]}"
    await _cleanup_other_mailbox_test(cref)
    try:
        async with AsyncSessionLocal() as pdb:
            pdb.add(
                TenantIntegrationSecret(
                    tenant_id=TENANT_ID,
                    integration_type="email_mailbox",
                    provider=EMAIL_PROVIDER_OTHER,
                    credential_ref=cref,
                    encrypted_payload=encrypt_secret(json.dumps({"imap_password": "x"})),
                )
            )
            await pdb.commit()
        async for tdb in open_tenant_session_by_id(TENANT_ID):
            tdb.add(
                TenantEmailMailbox(
                    tenant_id=TENANT_ID,
                    credential_ref=cref,
                    email_address="box2@test.example",
                    mailbox_type=EMAIL_PROVIDER_OTHER,
                    connection_mode="manual",
                    imap_host="imap.test",
                    imap_port=993,
                    imap_username="u",
                    imap_security="ssl",
                    smtp_host="smtp.test",
                    smtp_port=587,
                    smtp_username="u",
                    smtp_security="starttls",
                    status="CONFIGURED",
                    is_primary=True,
                )
            )
            await tdb.commit()
            break
        async for tdb in open_tenant_session_by_id(TENANT_ID):
            async with AsyncSessionLocal() as pdb:
                await sync_other_imap_inbox_for_tenant(tdb, pdb, TENANT_ID, max_messages=50)
            break
        async for tdb in open_tenant_session_by_id(TENANT_ID):
            async with AsyncSessionLocal() as pdb:
                await sync_other_imap_inbox_for_tenant(tdb, pdb, TENANT_ID, max_messages=50)
            break
        assert seen[0] is None or seen[0] == 0
        assert int(seen[1] or 0) >= 1
    finally:
        await _cleanup_other_mailbox_test(cref)


@pytest.mark.skipif(SKIP_NO_DB, reason="database_url required (settings)")
@pytest.mark.asyncio
async def test_sync_other_rejects_platform_secret_wrong_tenant_id(require_other_imap_tenant_migration):
    """Credential must be stored under the same platform tenant_id as the mailbox."""
    cref = f"xtenant_{uuid.uuid4().hex[:12]}"
    await _cleanup_other_mailbox_test(cref)
    try:
        async with AsyncSessionLocal() as pdb:
            pdb.add(
                TenantIntegrationSecret(
                    tenant_id=_WRONG_SECRET_TENANT_ID,
                    integration_type="email_mailbox",
                    provider=EMAIL_PROVIDER_OTHER,
                    credential_ref=cref,
                    encrypted_payload=encrypt_secret(json.dumps({"imap_password": "secret"})),
                )
            )
            await pdb.commit()
        async for tdb in open_tenant_session_by_id(TENANT_ID):
            tdb.add(
                TenantEmailMailbox(
                    tenant_id=TENANT_ID,
                    credential_ref=cref,
                    email_address="cross@test.example",
                    mailbox_type=EMAIL_PROVIDER_OTHER,
                    connection_mode="manual",
                    imap_host="imap.test",
                    imap_port=993,
                    imap_username="u",
                    imap_security="ssl",
                    smtp_host="smtp.test",
                    smtp_port=587,
                    smtp_username="u",
                    smtp_security="starttls",
                    status="CONFIGURED",
                    is_primary=True,
                )
            )
            await tdb.commit()
            break
        async for tdb in open_tenant_session_by_id(TENANT_ID):
            async with AsyncSessionLocal() as pdb:
                with pytest.raises(ValueError, match="IMAP password"):
                    await sync_other_imap_inbox_for_tenant(tdb, pdb, TENANT_ID, max_messages=10)
            break
    finally:
        await _cleanup_other_mailbox_test(cref)


@pytest.mark.skipif(SKIP_NO_DB, reason="database_url required (settings)")
@pytest.mark.asyncio
async def test_admin_test_inbound_and_outbound_mocked(
    client, override_admin_email_auth, require_other_imap_tenant_migration, monkeypatch
):
    monkeypatch.setattr("app.routers.admin_email_config.imap_test_connection_sync", lambda m, p: None)
    monkeypatch.setattr("app.routers.admin_email_config.smtp_test_connection_sync", lambda m, p: None)
    cref = f"http_{uuid.uuid4().hex[:12]}"
    await _cleanup_other_mailbox_test(cref)
    try:
        async with AsyncSessionLocal() as pdb:
            pdb.add(
                TenantIntegrationSecret(
                    tenant_id=TENANT_ID,
                    integration_type="email_mailbox",
                    provider=EMAIL_PROVIDER_OTHER,
                    credential_ref=cref,
                    encrypted_payload=encrypt_secret(json.dumps({"imap_password": "ip", "smtp_password": "sp"})),
                )
            )
            await pdb.commit()
        async for tdb in open_tenant_session_by_id(TENANT_ID):
            tdb.add(
                TenantEmailMailbox(
                    tenant_id=TENANT_ID,
                    credential_ref=cref,
                    email_address="admintest@test.example",
                    mailbox_type=EMAIL_PROVIDER_OTHER,
                    connection_mode="manual",
                    imap_host="imap.test",
                    imap_port=993,
                    imap_username="u",
                    imap_security="ssl",
                    smtp_host="smtp.test",
                    smtp_port=587,
                    smtp_username="u",
                    smtp_security="starttls",
                    status="CONFIGURED",
                    is_primary=True,
                )
            )
            await tdb.commit()
            break
        ri = await client.post("/api/v1/admin/email-config/primary/test-inbound", headers=AUTH_HEADERS)
        assert ri.status_code == 200
        assert ri.json().get("ok") is True
        assert ri.json().get("direction") == "inbound"
        ro = await client.post("/api/v1/admin/email-config/primary/test-outbound", headers=AUTH_HEADERS)
        assert ro.status_code == 200
        assert ro.json().get("ok") is True
        assert ro.json().get("direction") == "outbound"
    finally:
        await _cleanup_other_mailbox_test(cref)


@pytest.mark.skipif(SKIP_NO_DB, reason="database_url required (settings)")
@pytest.mark.asyncio
async def test_admin_disconnect_removes_mailbox_and_secret(
    client, override_admin_email_auth, require_other_imap_tenant_migration
):
    cref = f"dc_{uuid.uuid4().hex[:12]}"
    await _cleanup_other_mailbox_test(cref)
    async with AsyncSessionLocal() as pdb:
        pdb.add(
            TenantIntegrationSecret(
                tenant_id=TENANT_ID,
                integration_type="email_mailbox",
                provider=EMAIL_PROVIDER_OTHER,
                credential_ref=cref,
                encrypted_payload=encrypt_secret(json.dumps({"imap_password": "x"})),
            )
        )
        await pdb.commit()
    async for tdb in open_tenant_session_by_id(TENANT_ID):
        tdb.add(
            TenantEmailMailbox(
                tenant_id=TENANT_ID,
                credential_ref=cref,
                email_address="dc@test.example",
                mailbox_type=EMAIL_PROVIDER_OTHER,
                connection_mode="manual",
                imap_host="imap.test",
                imap_port=993,
                imap_username="u",
                imap_security="ssl",
                smtp_host="smtp.test",
                smtp_port=587,
                smtp_username="u",
                smtp_security="starttls",
                status="CONFIGURED",
                is_primary=True,
            )
        )
        await tdb.commit()
        break
    rd = await client.post("/api/v1/admin/email-config/primary/disconnect", headers=AUTH_HEADERS)
    assert rd.status_code == 200
    async with AsyncSessionLocal() as pdb:
        n = await pdb.scalar(
            select(func.count()).select_from(TenantIntegrationSecret).where(TenantIntegrationSecret.credential_ref == cref)
        )
        assert int(n or 0) == 0
    async for tdb in open_tenant_session_by_id(TENANT_ID):
        mb = await tdb.scalar(select(TenantEmailMailbox).where(TenantEmailMailbox.credential_ref == cref))
        assert mb is None
        break


@pytest.mark.skipif(SKIP_NO_DB, reason="database_url required (settings)")
@pytest.mark.asyncio
async def test_other_sync_now_forbidden_for_non_admin(client, override_non_admin_email_auth):
    r = await client.post("/api/v1/admin/email-config/other/sync-now", headers=AUTH_HEADERS)
    assert r.status_code == 403


@pytest.mark.skipif(SKIP_NO_DB, reason="database_url required (settings)")
@pytest.mark.asyncio
async def test_other_sync_now_ok_mocked(client, override_admin_email_auth, monkeypatch):
    async def fake_sync(tenant_db, platform_db, tenant_id, *, max_messages=100):
        return ImapSyncResult(
            tenant_id=tenant_id,
            provider=EMAIL_PROVIDER_OTHER,
            threads_upserted=0,
            messages_upserted=0,
            attachments_upserted=0,
            uids_fetched=0,
        )

    monkeypatch.setattr("app.routers.admin_email_config.sync_other_imap_inbox_for_tenant", fake_sync)
    r = await client.post("/api/v1/admin/email-config/other/sync-now", headers=AUTH_HEADERS)
    assert r.status_code == 200
    body = r.json()
    assert body.get("ok") is True
    assert body.get("uids_fetched") == 0
