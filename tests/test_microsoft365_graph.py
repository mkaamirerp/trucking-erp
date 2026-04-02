"""Microsoft 365 Graph: webhook validation, clientState, delta sync (mocked), classification path."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.services.email_engine.message_classifier import post_ingest_intake_path
from app.services.microsoft_graph_sync import sync_microsoft_delta_for_tenant
from app.services.microsoft_webhook_state import sign_ms_graph_client_state, verify_ms_graph_client_state


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_microsoft_graph_webhook_validation_returns_plain_token(client):
    token = "abc123validation"
    r = await client.get("/api/v1/webhooks/microsoft-graph", params={"validationToken": token})
    assert r.status_code == 200
    assert r.text == token
    assert (r.headers.get("content-type") or "").startswith("text/plain")


def test_ms_graph_client_state_roundtrip_tenant_53():
    cs = sign_ms_graph_client_state(53)
    assert verify_ms_graph_client_state(cs) == 53


def test_ms_graph_client_state_rejects_tamper():
    cs = sign_ms_graph_client_state(53)
    parts = cs.rsplit(":", 1)
    bad = parts[0] + ":00000000000000000000"
    assert verify_ms_graph_client_state(bad) is None


def test_post_ingest_path_microsoft_is_review_only():
    assert post_ingest_intake_path(provider="microsoft365") == "review_only"


def test_post_ingest_path_other_provider_review():
    assert post_ingest_intake_path(provider="other") == "review_only"


@pytest.mark.asyncio
async def test_microsoft_delta_sync_mocked_ingests_once(monkeypatch):
    """Idempotent shape: one message in delta page → one ingest_normalized_thread call."""
    calls = {"ingest": 0}

    async def fake_ingest(tenant_db, ctx, rollup, messages):
        calls["ingest"] += 1
        return (MagicMock(), 1, 0)

    monkeypatch.setattr(
        "app.services.microsoft_graph_sync.ingest_normalized_thread",
        fake_ingest,
    )

    acc = MagicMock()
    acc.refresh_token_encrypted = b"x"
    acc.tenant_id = 53
    acc.id = 1
    acc.ms_graph_delta_link = None
    acc.ms_graph_subscription_id = None
    acc.ms_graph_subscription_expiration_at = None
    acc.access_token_encrypted = b"x"
    acc.token_expiry_at = None
    acc.last_sync_at = None
    acc.last_error = None

    tenant_db = AsyncMock()
    tenant_db.scalar = AsyncMock(return_value=acc)
    tenant_db.commit = AsyncMock()

    async def fake_refresh(**_k):
        return {
            "access_token": "at",
            "refresh_token": None,
            "expires_in": 3600,
        }

    page = {
        "value": [
            {
                "id": "msg-a",
                "conversationId": "conv-1",
                "subject": "Hi",
                "body": {"contentType": "text", "content": "hello"},
                "from": {"emailAddress": {"address": "a@x.com"}},
                "toRecipients": [],
                "receivedDateTime": "2026-03-31T12:00:00Z",
                "isRead": False,
                "hasAttachments": False,
            }
        ],
        "@odata.deltaLink": "https://graph.microsoft.com/v1.0/me/messages/delta?$deltatoken=z",
    }

    async def fake_delta(_token, _url):
        return page

    async def fake_msg(_token, mid):
        return page["value"][0]

    monkeypatch.setattr("app.services.microsoft_graph_sync.refresh_ms_access_token", fake_refresh)
    monkeypatch.setattr("app.services.microsoft_graph_sync.decrypt_secret", lambda _b: b"refresh")
    monkeypatch.setattr("app.services.microsoft_graph_sync.encrypt_secret", lambda _s: b"enc")
    monkeypatch.setattr("app.services.microsoft_graph_sync.graph_delta_get", fake_delta)
    monkeypatch.setattr("app.services.microsoft_graph_sync.graph_get_message", fake_msg)
    async def _no_atts(*_a, **_k):
        return []

    monkeypatch.setattr("app.services.microsoft_graph_sync.graph_list_attachments", _no_atts)

    r = await sync_microsoft_delta_for_tenant(tenant_db, 53, max_pages=3)
    assert r.messages_processed == 1
    assert calls["ingest"] == 1
    assert "deltatoken" in (acc.ms_graph_delta_link or "")


@pytest.mark.asyncio
async def test_microsoft_webhook_bad_client_state_does_not_sync(client, monkeypatch):
    calls = {"sync": 0}

    async def _no_sync(*_a, **_k):
        calls["sync"] += 1

    monkeypatch.setattr(
        "app.routers.microsoft_graph_webhook.sync_microsoft_delta_for_tenant",
        _no_sync,
    )
    body = {"value": [{"subscriptionId": "sub-1", "clientState": "1:deadbeef"}]}
    r = await client.post("/api/v1/webhooks/microsoft-graph", json=body)
    assert r.status_code == 200
    assert calls["sync"] == 0


@pytest.mark.asyncio
async def test_microsoft_renew_subscription_force_mocked(monkeypatch):
    from app.services.microsoft_graph_sync import renew_microsoft_subscription_if_due

    acc = MagicMock()
    acc.ms_graph_subscription_id = "sub-x"
    acc.ms_graph_subscription_expiration_at = None
    tenant_db = AsyncMock()
    tenant_db.commit = AsyncMock()

    async def fake_access(_acc):
        return "tok"

    async def fake_renew(_token, sid):
        assert sid == "sub-x"
        return {"expirationDateTime": "2026-04-15T12:00:00.0000000Z"}

    monkeypatch.setattr("app.services.microsoft_graph_sync._access_token_for_account", fake_access)
    monkeypatch.setattr("app.services.microsoft_graph_sync.graph_renew_subscription", fake_renew)
    ok = await renew_microsoft_subscription_if_due(tenant_db, 53, acc, force=True)
    assert ok is True
    tenant_db.commit.assert_awaited()
