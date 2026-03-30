"""POST /auth/login rate limits (per IP and per tenant+email fingerprint)."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.utils.rate_limit import SlidingWindowLimiter, rate_limit_login


def _req(ip: str = "203.0.113.7") -> MagicMock:
    r = MagicMock()
    r.client = MagicMock()
    r.client.host = ip
    return r


@pytest.mark.asyncio
async def test_rate_limit_login_blocks_per_ip_after_threshold(monkeypatch):
    monkeypatch.setattr(
        "app.utils.rate_limit.login_per_ip",
        SlidingWindowLimiter(max_requests=2, window_seconds=900.0),
    )
    monkeypatch.setattr(
        "app.utils.rate_limit.login_per_tenant_email",
        SlidingWindowLimiter(max_requests=100, window_seconds=900.0),
    )
    req = _req()
    await rate_limit_login(req, 1, "user@example.com")
    await rate_limit_login(req, 1, "other@example.com")
    with pytest.raises(HTTPException) as exc:
        await rate_limit_login(req, 99, "third@example.com")
    assert exc.value.status_code == 429
    assert exc.value.detail == "Too many attempts. Try again later."


@pytest.mark.asyncio
async def test_rate_limit_login_blocks_per_tenant_email_after_threshold(monkeypatch):
    monkeypatch.setattr(
        "app.utils.rate_limit.login_per_ip",
        SlidingWindowLimiter(max_requests=100, window_seconds=900.0),
    )
    monkeypatch.setattr(
        "app.utils.rate_limit.login_per_tenant_email",
        SlidingWindowLimiter(max_requests=2, window_seconds=3600.0),
    )
    req = _req()
    await rate_limit_login(req, 42, "victim@example.com")
    await rate_limit_login(req, 42, "victim@example.com")
    with pytest.raises(HTTPException) as exc:
        await rate_limit_login(req, 42, "victim@example.com")
    assert exc.value.status_code == 429
    assert exc.value.detail == "Too many attempts. Try again later."

    # other tenant same email gets its own bucket
    await rate_limit_login(req, 99, "victim@example.com")


@pytest.mark.asyncio
async def test_rate_limit_login_same_ip_different_tenants_distinct_email_buckets(monkeypatch):
    monkeypatch.setattr(
        "app.utils.rate_limit.login_per_ip",
        SlidingWindowLimiter(max_requests=100, window_seconds=900.0),
    )
    monkeypatch.setattr(
        "app.utils.rate_limit.login_per_tenant_email",
        SlidingWindowLimiter(max_requests=2, window_seconds=3600.0),
    )
    req = _req()
    await rate_limit_login(req, 1, "a@x.com")
    await rate_limit_login(req, 2, "a@x.com")
    await rate_limit_login(req, 1, "a@x.com")


@pytest.mark.asyncio
async def test_rate_limit_login_different_ips_independent(monkeypatch):
    monkeypatch.setattr(
        "app.utils.rate_limit.login_per_ip",
        SlidingWindowLimiter(max_requests=2, window_seconds=900.0),
    )
    monkeypatch.setattr(
        "app.utils.rate_limit.login_per_tenant_email",
        SlidingWindowLimiter(max_requests=100, window_seconds=900.0),
    )
    await rate_limit_login(_req("198.51.100.1"), 5, "e@e.com")
    await rate_limit_login(_req("198.51.100.2"), 5, "e@e.com")
