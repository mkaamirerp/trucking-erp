"""Gmail Pub/Sub push route (tenant resolution via platform index)."""
from __future__ import annotations

import base64
import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app

@pytest.mark.asyncio
async def test_pubsub_push_unknown_mailbox_returns_200_skip():
    inner = {"emailAddress": "nobody@example.com", "historyId": 1}
    data = base64.urlsafe_b64encode(json.dumps(inner).encode()).decode().rstrip("=")
    payload = {"message": {"data": data}}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        res = await ac.post("/api/v1/webhooks/gmail/pubsub", json=payload)
    assert res.status_code == 200
    body = res.json()
    assert body.get("skipped") == "unknown_mailbox"


@pytest.mark.asyncio
async def test_pubsub_push_invokes_delta_sync_when_tenant_mapped(monkeypatch):
    from app.routers import gmail_pubsub as gp

    monkeypatch.setattr(gp, "_require_push_auth", lambda _r: None)
    monkeypatch.setattr(gp, "resolve_tenant_id_for_gmail_address", AsyncMock(return_value=53))

    async def fake_open(_tid: int):
        sess = MagicMock()
        sess.scalar = AsyncMock(return_value=None)
        sess.commit = AsyncMock()
        yield sess

    monkeypatch.setattr(gp, "open_tenant_session_by_id", fake_open)
    sync_mock = AsyncMock()
    monkeypatch.setattr(gp, "sync_gmail_delta_for_tenant", sync_mock)

    inner = {"emailAddress": "ops@example.com", "historyId": 999}
    data = base64.urlsafe_b64encode(json.dumps(inner).encode()).decode().rstrip("=")
    payload = {"message": {"data": data}}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        res = await ac.post("/api/v1/webhooks/gmail/pubsub", json=payload)
    assert res.status_code == 200
    assert res.json().get("tenant_id") == 53
    sync_mock.assert_awaited_once()
