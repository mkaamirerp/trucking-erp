"""
Canonical login hardening smoke (backend). Guards the locked sign-in state machine from drift.

Protected behavior (runtime contracts this suite expects):
  - Public tenant client config always exposes `turnstile_site_key` (string or null).
  - Valid credentials succeed when no extra friction; wrong password yields generic 401 before thresholds.
  - After enough wrong passwords, Turnstile / “additional verification” arms when secret is configured;
    siteverify is mocked in tests.
  - Tenant+email sign-in bucket can return 429 with retry-style JSON + Retry-After (IP bucket often patched off).
  - Step-up (403) responses clear `trk_login_trust` so trust is not silently preserved.
  - After OTP step-up, `trust_this_device` only sets a trust cookie when explicitly true.

Naming: admin sign-in panel uses `sign_in_status` == `clear` | `locked` | `verification_on_next_sign_in`
(`clear` is the API value — not `no_lock`).

Requires DATABASE_URL (platform DB). Run with admin unlock smoke:
  python3 -m pytest tests/test_login_hardening_smoke.py tests/test_admin_sign_in_unlock_smoke.py -q

Turnstile verification is mocked; password streaks and some limiters are real unless patched.
"""
from __future__ import annotations

import logging
import os
import uuid
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.main import app
from app.models.platform import OTPPurpose, PlatformOTPToken, PlatformTenant
from app.utils.auth_identity import normalize_auth_email
from app.utils.otp import generate_otp, hash_otp
from tests.test_tenant_auth_matrix import _fake_provision_tenant_db, _host

SKIP_NO_DB = not os.environ.get("DATABASE_URL")


async def _signup_workspace(ac: AsyncClient, slug: str, email: str, password: str, otp: str) -> str:
    with (
        patch("app.routers.public_signup.send_signup_failure_alert", new_callable=AsyncMock),
        patch("app.routers.public_signup.send_signup_welcome_email", new_callable=AsyncMock),
        patch("app.routers.public_signup.send_otp_email", new_callable=AsyncMock),
        patch("app.routers.public_signup.generate_otp", return_value=otp),
    ):
        r = await ac.post(
            "/api/v1/public/signup",
            json={
                "workspace_slug": slug,
                "email": email,
                "password": password,
                "first_name": "L",
                "last_name": "SM",
                "phone": "+15551234567",
                "company_legal_name": "Smoke Inc",
                "address": {
                    "street": "1 St",
                    "city": "Toronto",
                    "region": "ON",
                    "postal": "M5V 1A1",
                    "country": "CA",
                },
            },
        )
    assert r.status_code == 201, r.text
    signup_id = r.json().get("signup_id")
    with patch("app.routers.public_signup.provision_tenant_db", AsyncMock(side_effect=_fake_provision_tenant_db)):
        vr = await ac.post(
            "/api/v1/public/verify-otp",
            json={"email": email, "otp": otp, "signup_id": signup_id},
        )
    assert vr.status_code == 200, vr.text
    return str(vr.json().get("slug"))


def _set_cookie_directives(response: httpx.Response) -> list[str]:
    h = response.headers
    gl = getattr(h, "get_list", None)
    if callable(gl):
        return list(gl("set-cookie"))
    raw = h.get("set-cookie")
    return [raw] if raw else []


def _any_trust_cookie_clear(directives: list[str]) -> bool:
    for d in directives:
        dl = d.lower()
        if "trk_login_trust" in dl and ("max-age=0" in dl or "max-age=0;" in dl or "expires=" in dl):
            return True
    return False


def _any_trust_cookie_set_non_empty(directives: list[str]) -> bool:
    for d in directives:
        if "trk_login_trust=" not in d.lower():
            continue
        dl = d.lower()
        if "max-age=0" in dl:
            continue
        # value after first = until first ;
        try:
            val = d.split("=", 1)[1].split(";", 1)[0].strip()
        except IndexError:
            continue
        if val:
            return True
    return False


@pytest.mark.asyncio
@pytest.mark.skipif(SKIP_NO_DB, reason="DATABASE_URL required")
async def test_smoke_public_tenant_includes_turnstile_site_key_field():
    """Runtime config: JSON always includes turnstile_site_key (null or string)."""
    slug = f"smoke_pub_{uuid.uuid4().hex[:8]}"
    email = f"{slug}@example.com"
    password = "password123456"
    otp = "612088"

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://truckerp.me") as ac:
        tenant_slug = await _signup_workspace(ac, slug, email, password, otp)
        r = await ac.get(f"/api/v1/public/tenant/{tenant_slug}")
    assert r.status_code == 200, r.text
    data = r.json()
    assert "turnstile_site_key" in data
    assert data.get("exists") is True
    assert data.get("slug") == tenant_slug


@pytest.mark.asyncio
@pytest.mark.skipif(SKIP_NO_DB, reason="DATABASE_URL required")
async def test_smoke_login_success_baseline():
    """Correct credentials → 200 when no step-up / Turnstile forced."""
    slug = f"smoke_ok_{uuid.uuid4().hex[:8]}"
    email = f"{slug}@example.com"
    password = "password123456"
    otp = "612088"

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://truckerp.me") as ac:
        tenant_slug = await _signup_workspace(ac, slug, email, password, otp)

    origin = f"http://{_host(tenant_slug)}"
    with (
        patch("app.routers.auth.rate_limit_login_tenant_email", AsyncMock()),
        patch.object(settings, "turnstile_secret_key", ""),
        patch.object(settings, "login_step_up_otp_required", False),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url=origin) as ac:
            lr = await ac.post(
                "/api/v1/auth/login",
                json={"email": email, "password": password, "trust_this_device": True},
            )
    assert lr.status_code == 200, lr.text
    body = lr.json()
    assert body.get("ok") is True
    assert body.get("workspace_url") or body.get("access_token")


@pytest.mark.asyncio
@pytest.mark.skipif(SKIP_NO_DB, reason="DATABASE_URL required")
async def test_smoke_wrong_password_not_turnstile_on_first_attempts():
    """Before threshold: 401 invalid credentials; Turnstile not required on attempts 1–3 if secret off."""
    slug = f"smoke_wp_{uuid.uuid4().hex[:8]}"
    email = f"{slug}@example.com"
    password = "password123456"
    otp = "612088"

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://truckerp.me") as ac:
        tenant_slug = await _signup_workspace(ac, slug, email, password, otp)

    origin = f"http://{_host(tenant_slug)}"
    with (
        patch("app.routers.auth.rate_limit_login_tenant_email", AsyncMock()),
        patch.object(settings, "turnstile_secret_key", ""),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url=origin) as ac:
            for _ in range(2):
                bad = await ac.post("/api/v1/auth/login", json={"email": email, "password": "nope"})
                assert bad.status_code == 401
                assert bad.json().get("detail") == "Invalid email or password"


@pytest.mark.asyncio
@pytest.mark.skipif(SKIP_NO_DB, reason="DATABASE_URL required")
async def test_smoke_turnstile_arms_after_three_failures_mocked_siteverify():
    """After 3 wrong passwords, next POST requires Turnstile (403) when secret is set; verify mocked."""
    slug = f"smoke_ts_{uuid.uuid4().hex[:8]}"
    email = f"{slug}@example.com"
    password = "password123456"
    otp = "612088"

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://truckerp.me") as ac:
        tenant_slug = await _signup_workspace(ac, slug, email, password, otp)

    origin = f"http://{_host(tenant_slug)}"
    with patch("app.routers.auth.rate_limit_login_tenant_email", AsyncMock()):
        async with AsyncClient(transport=ASGITransport(app=app), base_url=origin) as ac:
            for _ in range(3):
                bad = await ac.post("/api/v1/auth/login", json={"email": email, "password": "wrong"})
                assert bad.status_code == 401

            with patch.object(settings, "turnstile_secret_key", "unit-test-secret"):
                gated = await ac.post("/api/v1/auth/login", json={"email": email, "password": "wrong"})
            assert gated.status_code == 403
            assert gated.json().get("detail") == "Additional verification required."
            assert "login_challenge_id" not in gated.json() or gated.json().get("login_challenge_id") is None

            with (
                patch.object(settings, "turnstile_secret_key", "unit-test-secret"),
                patch(
                    "app.services.login_password_abuse.verify_turnstile_token",
                    new_callable=AsyncMock,
                    return_value=True,
                ),
            ):
                still = await ac.post(
                    "/api/v1/auth/login",
                    json={"email": email, "password": "wrong", "turnstile_token": "dummy-token"},
                )
            assert still.status_code == 401
            assert still.json().get("detail") == "Invalid email or password"


@pytest.mark.asyncio
@pytest.mark.skipif(SKIP_NO_DB, reason="DATABASE_URL required")
async def test_smoke_turnstile_secret_without_site_key_logs_configuration(caplog):
    """If enforcement is on but TURNSTILE_SITE_KEY empty, logs must flag configuration (not vague)."""
    slug = f"smoke_cfg_{uuid.uuid4().hex[:8]}"
    email = f"{slug}@example.com"
    password = "password123456"
    otp = "612088"

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://truckerp.me") as ac:
        tenant_slug = await _signup_workspace(ac, slug, email, password, otp)

    origin = f"http://{_host(tenant_slug)}"
    with patch("app.routers.auth.rate_limit_login_tenant_email", AsyncMock()):
        async with AsyncClient(transport=ASGITransport(app=app), base_url=origin) as ac:
            for _ in range(3):
                await ac.post("/api/v1/auth/login", json={"email": email, "password": "wrong"})

            with (
                caplog.at_level(logging.ERROR, logger="app.services.login_password_abuse"),
                patch.object(settings, "turnstile_secret_key", "unit-test-secret"),
                patch.object(settings, "turnstile_site_key", ""),
            ):
                r = await ac.post("/api/v1/auth/login", json={"email": email, "password": "wrong"})
            assert r.status_code == 403
    joined = caplog.text
    assert "turnstile_configuration_error" in joined or "CONFIGURATION:" in joined


@pytest.mark.asyncio
@pytest.mark.skipif(SKIP_NO_DB, reason="DATABASE_URL required")
async def test_smoke_tenant_email_login_rate_limit_eventually_429():
    """Repeated workspace+email login posts hit tenant+email bucket (429) with retry-style body."""
    slug = f"smoke_rl_{uuid.uuid4().hex[:8]}"
    email = f"{slug}@example.com"
    password = "password123456"
    otp = "612088"

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://truckerp.me") as ac:
        tenant_slug = await _signup_workspace(ac, slug, email, password, otp)

    origin = f"http://{_host(tenant_slug)}"
    from app.utils.rate_limit import clear_login_unlock_throttles_for_tenant_email

    email_norm = normalize_auth_email(email)
    async with AsyncSessionLocal() as adb:
        t = await adb.scalar(select(PlatformTenant).where(PlatformTenant.slug == tenant_slug))
        tid = int(t.id)

    clear_login_unlock_throttles_for_tenant_email(tid, email_norm)

    with (
        patch("app.routers.auth.rate_limit_login_ip", AsyncMock()),
        patch.object(settings, "turnstile_secret_key", ""),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url=origin) as ac:
            last = None
            for i in range(8):
                last = await ac.post("/api/v1/auth/login", json={"email": email, "password": "bad"})
                if last.status_code == 429:
                    break
            assert last is not None
            assert last.status_code == 429, f"expected 429 after exhausting tenant email bucket, got {last.status_code}"
            payload = last.json()
            detail = payload.get("detail")
            assert isinstance(detail, dict), payload
            assert "retry_after_seconds" in detail or "detail" in detail


@pytest.mark.asyncio
@pytest.mark.skipif(SKIP_NO_DB, reason="DATABASE_URL required")
async def test_smoke_step_up_403_sends_trust_cookie_clearing_directive():
    """Step-up required: response should clear trk_login_trust so device is not silently trusted."""
    slug = f"smoke_clr_{uuid.uuid4().hex[:8]}"
    email = f"{slug}@example.com"
    password = "password123456"
    otp = "612088"

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://truckerp.me") as ac:
        tenant_slug = await _signup_workspace(ac, slug, email, password, otp)

    origin = f"http://{_host(tenant_slug)}"
    with (
        patch("app.routers.auth.rate_limit_login_tenant_email", AsyncMock()),
        patch.object(settings, "login_step_up_otp_required", True),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url=origin) as ac:
            lr = await ac.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert lr.status_code == 403
    cookies = _set_cookie_directives(lr)
    assert _any_trust_cookie_clear(cookies), cookies


@pytest.mark.asyncio
@pytest.mark.skipif(SKIP_NO_DB, reason="DATABASE_URL required")
async def test_smoke_trust_this_device_opt_in_after_step_up():
    """After OTP verify, trust cookie set only when trust_this_device true (API / Set-Cookie level)."""
    slug = f"smoke_tr_{uuid.uuid4().hex[:8]}"
    email = f"{slug}@example.com"
    password = "password123456"
    otp = "612088"

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://truckerp.me") as ac:
        tenant_slug = await _signup_workspace(ac, slug, email, password, otp)

    origin = f"http://{_host(tenant_slug)}"

    with (
        patch("app.routers.auth.rate_limit_login_tenant_email", AsyncMock()),
        patch("app.routers.auth.rate_limit_login_ip", AsyncMock()),
        patch.object(settings, "login_step_up_otp_required", True),
        patch.object(settings, "login_trust_cookie_secret", "pytest-hardening-trust-secret"),
        patch.object(settings, "login_trust_cookie_dev_fallback_to_jwt", False),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url=origin) as ac:
            lr = await ac.post("/api/v1/auth/login", json={"email": email, "password": password})
            assert lr.status_code == 403
            cid = lr.json()["login_challenge_id"]

        otp_plain = generate_otp()
        with patch("app.services.login_step_up_otp.send_otp_email_for_purpose", new_callable=AsyncMock):
            async with AsyncClient(transport=ASGITransport(app=app), base_url=origin) as ac:
                await ac.post("/api/v1/auth/login-step-up/issue", json={"login_challenge_id": cid})

        async with AsyncSessionLocal() as adb:
            row = await adb.scalar(
                select(PlatformOTPToken).where(
                    PlatformOTPToken.login_challenge_id == cid,
                    PlatformOTPToken.purpose == OTPPurpose.LOGIN_STEP_UP.value,
                    PlatformOTPToken.consumed_at.is_(None),
                )
            )
            assert row is not None
            row.otp_hash = hash_otp(otp_plain)
            await adb.commit()

        async with AsyncClient(transport=ASGITransport(app=app), base_url=origin) as ac:
            await ac.post("/api/v1/auth/login-step-up/verify", json={"login_challenge_id": cid, "otp": otp_plain})

        with patch.object(settings, "login_step_up_otp_required", True):
            async with AsyncClient(transport=ASGITransport(app=app), base_url=origin) as ac:
                no_trust = await ac.post(
                    "/api/v1/auth/login",
                    json={
                        "email": email,
                        "password": password,
                        "login_challenge_id": cid,
                        "trust_this_device": False,
                    },
                )
        assert no_trust.status_code == 200
        assert not _any_trust_cookie_set_non_empty(_set_cookie_directives(no_trust))

        with patch.object(settings, "login_step_up_otp_required", True):
            async with AsyncClient(transport=ASGITransport(app=app), base_url=origin) as ac:
                lr2 = await ac.post("/api/v1/auth/login", json={"email": email, "password": password})
            assert lr2.status_code == 403
            cid2 = lr2.json()["login_challenge_id"]

        otp_plain2 = generate_otp()
        with patch("app.services.login_step_up_otp.send_otp_email_for_purpose", new_callable=AsyncMock):
            async with AsyncClient(transport=ASGITransport(app=app), base_url=origin) as ac:
                await ac.post("/api/v1/auth/login-step-up/issue", json={"login_challenge_id": cid2})

        async with AsyncSessionLocal() as adb:
            row2 = await adb.scalar(
                select(PlatformOTPToken).where(
                    PlatformOTPToken.login_challenge_id == cid2,
                    PlatformOTPToken.purpose == OTPPurpose.LOGIN_STEP_UP.value,
                    PlatformOTPToken.consumed_at.is_(None),
                )
            )
            assert row2 is not None
            row2.otp_hash = hash_otp(otp_plain2)
            await adb.commit()

        async with AsyncClient(transport=ASGITransport(app=app), base_url=origin) as ac:
            await ac.post(
                "/api/v1/auth/login-step-up/verify",
                json={"login_challenge_id": cid2, "otp": otp_plain2},
            )

        with patch.object(settings, "login_step_up_otp_required", True):
            async with AsyncClient(transport=ASGITransport(app=app), base_url=origin) as ac:
                with_trust = await ac.post(
                    "/api/v1/auth/login",
                    json={
                        "email": email,
                        "password": password,
                        "login_challenge_id": cid2,
                        "trust_this_device": True,
                    },
                )
        assert with_trust.status_code == 200
        assert _any_trust_cookie_set_non_empty(_set_cookie_directives(with_trust))
