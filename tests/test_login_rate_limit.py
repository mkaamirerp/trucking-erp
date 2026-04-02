"""POST /auth/login rate limits (per IP and per tenant+email fingerprint)."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.utils.rate_limit import (
    LOGIN_RATE_LIMIT_IP_DETAIL,
    LOGIN_RATE_LIMIT_TENANT_EMAIL_DETAIL,
    SlidingWindowLimiter,
    login_tenant_email_bucket_key,
    rate_limit_forgot_password_respects_login_tenant_bucket,
    rate_limit_login,
)


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
    d = exc.value.detail
    assert isinstance(d, dict)
    assert d["detail"] == LOGIN_RATE_LIMIT_IP_DETAIL
    assert isinstance(d.get("retry_after_seconds"), int) and d["retry_after_seconds"] >= 1
    assert isinstance(d.get("retry_at"), str) and len(d["retry_at"]) >= 10
    assert exc.value.headers and "Retry-After" in exc.value.headers


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
    d = exc.value.detail
    assert isinstance(d, dict)
    assert d["detail"] == LOGIN_RATE_LIMIT_TENANT_EMAIL_DETAIL
    assert isinstance(d.get("retry_after_seconds"), int) and d["retry_after_seconds"] >= 1
    assert isinstance(d.get("retry_at"), str)
    assert exc.value.headers and exc.value.headers.get("Retry-After") == str(d["retry_after_seconds"])

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


def test_sliding_window_is_at_or_over_limit_without_consuming():
    lim = SlidingWindowLimiter(max_requests=2, window_seconds=60.0)
    assert not lim.is_at_or_over_limit("a")
    assert lim.allow("a")
    assert not lim.is_at_or_over_limit("a")
    assert lim.allow("a")
    assert lim.is_at_or_over_limit("a")
    assert not lim.allow("a")


def test_sliding_window_seconds_until_slot_when_full():
    lim = SlidingWindowLimiter(max_requests=2, window_seconds=60.0)
    assert lim.allow("k")
    assert lim.allow("k")
    assert not lim.allow("k")
    wait = lim.seconds_until_slot_available("k")
    assert 0 < wait <= 60.0


@pytest.mark.asyncio
async def test_forgot_password_gate_blocks_when_login_tenant_bucket_full(monkeypatch):
    lim = SlidingWindowLimiter(max_requests=2, window_seconds=3600.0)
    monkeypatch.setattr("app.utils.rate_limit.login_per_tenant_email", lim)
    key = login_tenant_email_bucket_key(99, "u@example.com")
    assert lim.allow(key)
    assert lim.allow(key)
    with pytest.raises(HTTPException) as exc:
        await rate_limit_forgot_password_respects_login_tenant_bucket(99, "u@example.com")
    assert exc.value.status_code == 429
    assert exc.value.detail == LOGIN_RATE_LIMIT_TENANT_EMAIL_DETAIL


@pytest.mark.asyncio
async def test_forgot_password_gate_allows_when_login_tenant_bucket_not_full(monkeypatch):
    lim = SlidingWindowLimiter(max_requests=10, window_seconds=3600.0)
    monkeypatch.setattr("app.utils.rate_limit.login_per_tenant_email", lim)
    await rate_limit_forgot_password_respects_login_tenant_bucket(1, "a@example.com")


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
