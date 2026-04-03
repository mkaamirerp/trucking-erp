"""
Canonical admin unlock + sign-in security panel smoke (backend).

Protected behavior:
  - `GET /api/v1/admin/users/{id}/sign-in-security` returns `sign_in_status` in
    `clear` | `locked` | `verification_on_next_sign_in` (API uses `clear` when no block — not `no_lock`).
  - Wrong passwords move the panel from `clear` → `locked` (workspace+email / streak signals).
  - `POST .../unlock-sign-in` clears streak + tenant-email throttle buckets; sets one-shot step-up pending
    only when there was workspace-level sign-in friction (otherwise no extra email code is mandated),
    returns `operator_message` and `state_after.post_unlock_step_up_pending`.
  - After unlock, correct password does not issue a session immediately: 403 step-up with
    `login_challenge_id`, `after_sign_in_unlock`, and trust cookie cleared for `trk_login_trust`.

Requires DATABASE_URL (platform DB). Run both canonical smoke files:
  python3 -m pytest tests/test_login_hardening_smoke.py tests/test_admin_sign_in_unlock_smoke.py -q
"""
from __future__ import annotations

import os
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.main import app
from app.models.platform import PlatformUser
from app.utils.auth_identity import normalize_auth_email
from tests.test_login_hardening_smoke import (
    _any_trust_cookie_clear,
    _set_cookie_directives,
    _signup_workspace,
)
from tests.test_tenant_auth_matrix import _host

SKIP_NO_DB = not os.environ.get("DATABASE_URL")


async def _platform_user_id(email: str) -> str:
    async with AsyncSessionLocal() as adb:
        pu = await adb.scalar(select(PlatformUser).where(PlatformUser.email == normalize_auth_email(email)))
    assert pu is not None
    return str(pu.id)


@pytest.mark.asyncio
@pytest.mark.skipif(SKIP_NO_DB, reason="DATABASE_URL required")
async def test_smoke_sign_in_security_panel_status_contract_locked_unlock_verification():
    """Panel contract: sign_in_status clear → locked → verification_on_next_sign_in (API: `clear`, never `no_lock`)."""
    slug = f"smoke_adm_{uuid.uuid4().hex[:8]}"
    email = f"{slug}@example.com"
    password = "password123456"
    otp = "612088"

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://truckerp.me") as ac:
        tenant_slug = await _signup_workspace(ac, slug, email, password, otp)

    user_id = await _platform_user_id(email)
    origin = f"http://{_host(tenant_slug)}"

    with (
        patch("app.routers.auth.rate_limit_login_tenant_email", AsyncMock()),
        patch("app.routers.auth.rate_limit_login_ip", AsyncMock()),
        patch.object(settings, "turnstile_secret_key", ""),
        patch.object(settings, "login_step_up_otp_required", False),
        patch.object(settings, "login_trust_cookie_secret", "pytest-admin-unlock-trust-secret"),
        patch.object(settings, "login_trust_cookie_dev_fallback_to_jwt", False),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url=origin) as admin_ac:
            login_ok = await admin_ac.post(
                "/api/v1/auth/login",
                json={"email": email, "password": password, "trust_this_device": False},
            )
            assert login_ok.status_code == 200, login_ok.text
            access_token = login_ok.json().get("access_token")
            assert access_token

            clear_panel = await admin_ac.get(f"/api/v1/admin/users/{user_id}/sign-in-security")
            assert clear_panel.status_code == 200, clear_panel.text
            clear_body = clear_panel.json()
            assert clear_body.get("sign_in_status") == "clear"
            assert clear_body.get("all_clear") is True
            rs0 = clear_body.get("restriction_summary") or {}
            assert rs0.get("post_unlock_step_up_pending") in (False, None)

        async with AsyncClient(transport=ASGITransport(app=app), base_url=origin) as brute:
            for _ in range(2):
                bad = await brute.post("/api/v1/auth/login", json={"email": email, "password": "wrong"})
                assert bad.status_code == 401

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url=origin,
            headers={"Authorization": f"Bearer {access_token}"},
        ) as admin_ac:
            locked_panel = await admin_ac.get(f"/api/v1/admin/users/{user_id}/sign-in-security")
            assert locked_panel.status_code == 200, locked_panel.text
            locked_body = locked_panel.json()
            assert locked_body.get("sign_in_status") == "locked"
            assert locked_body.get("all_clear") is False
            assert locked_body.get("reasons"), locked_body
            assert locked_body.get("restriction_summary")

            unlock = await admin_ac.post(f"/api/v1/admin/users/{user_id}/unlock-sign-in")
            assert unlock.status_code == 200, unlock.text
            uj = unlock.json()
            assert uj.get("ok") is True
            om = (uj.get("operator_message") or "").lower()
            assert "verification" in om or "sign-in" in om
            st = uj.get("state_after") or {}
            assert st.get("post_unlock_step_up_pending") is True

            ver_panel = await admin_ac.get(f"/api/v1/admin/users/{user_id}/sign-in-security")
            assert ver_panel.status_code == 200, ver_panel.text
            vb = ver_panel.json()
            assert vb.get("sign_in_status") == "verification_on_next_sign_in"
            assert vb.get("all_clear") is True
            rs = vb.get("restriction_summary") or {}
            assert rs.get("post_unlock_step_up_pending") is True
            reasons_blob = " ".join(vb.get("reasons") or []).lower()
            assert "unlock" in reasons_blob or "verification" in reasons_blob


@pytest.mark.asyncio
@pytest.mark.skipif(SKIP_NO_DB, reason="DATABASE_URL required")
async def test_smoke_post_unlock_login_step_up_clears_trust_cookie():
    """After admin unlock, correct password returns step-up 403, clears trk_login_trust, flags after_sign_in_unlock."""
    slug = f"smoke_pu_{uuid.uuid4().hex[:8]}"
    email = f"{slug}@example.com"
    password = "password123456"
    otp = "612088"

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://truckerp.me") as ac:
        tenant_slug = await _signup_workspace(ac, slug, email, password, otp)

    user_id = await _platform_user_id(email)
    origin = f"http://{_host(tenant_slug)}"

    with (
        patch("app.routers.auth.rate_limit_login_tenant_email", AsyncMock()),
        patch("app.routers.auth.rate_limit_login_ip", AsyncMock()),
        patch.object(settings, "turnstile_secret_key", ""),
        patch.object(settings, "login_step_up_otp_required", False),
        patch.object(settings, "login_trust_cookie_secret", "pytest-admin-unlock-trust-secret"),
        patch.object(settings, "login_trust_cookie_dev_fallback_to_jwt", False),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url=origin) as ac:
            lr = await ac.post(
                "/api/v1/auth/login",
                json={"email": email, "password": password, "trust_this_device": True},
            )
            assert lr.status_code == 200, lr.text
            trust_val = ac.cookies.get("trk_login_trust")
            assert trust_val, "trust cookie should be set when login_trust_cookie_secret patched"

        async with AsyncClient(transport=ASGITransport(app=app), base_url=origin) as brute:
            for _ in range(2):
                await brute.post("/api/v1/auth/login", json={"email": email, "password": "bad"})

        async with AsyncClient(transport=ASGITransport(app=app), base_url=origin) as ac:
            lr2 = await ac.post("/api/v1/auth/login", json={"email": email, "password": password})
            assert lr2.status_code == 200, lr2.text
            token = lr2.json()["access_token"]

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url=origin,
            headers={"Authorization": f"Bearer {token}"},
        ) as admin_ac:
            un = await admin_ac.post(f"/api/v1/admin/users/{user_id}/unlock-sign-in")
            assert un.status_code == 200, un.text

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url=origin,
        cookies={"trk_login_trust": trust_val},
    ) as victim:
        step = await victim.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert step.status_code == 403, step.text
    body = step.json()
    assert body.get("detail") == "Additional verification required."
    assert body.get("login_challenge_id")
    assert body.get("after_sign_in_unlock") is True
            assert _any_trust_cookie_clear(_set_cookie_directives(step)), _set_cookie_directives(step)


@pytest.mark.asyncio
@pytest.mark.skipif(SKIP_NO_DB, reason="DATABASE_URL required")
async def test_smoke_unlock_when_already_clear_does_not_mandate_step_up():
    """Admin unlock with no streak/rates/friction does not set post_unlock mandate; login stays password-only."""
    slug = f"smoke_clr_{uuid.uuid4().hex[:8]}"
    email = f"{slug}@example.com"
    password = "password123456"
    otp = "612088"

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://truckerp.me") as ac:
        tenant_slug = await _signup_workspace(ac, slug, email, password, otp)

    user_id = await _platform_user_id(email)
    origin = f"http://{_host(tenant_slug)}"

    with (
        patch("app.routers.auth.rate_limit_login_tenant_email", AsyncMock()),
        patch("app.routers.auth.rate_limit_login_ip", AsyncMock()),
        patch.object(settings, "turnstile_secret_key", ""),
        patch.object(settings, "login_step_up_otp_required", False),
        patch.object(settings, "login_trust_cookie_secret", "pytest-admin-unlock-trust-secret"),
        patch.object(settings, "login_trust_cookie_dev_fallback_to_jwt", False),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url=origin) as admin_ac:
            login_ok = await admin_ac.post(
                "/api/v1/auth/login",
                json={"email": email, "password": password, "trust_this_device": False},
            )
            assert login_ok.status_code == 200, login_ok.text
            access_token = login_ok.json().get("access_token")
            assert access_token

            unlock = await admin_ac.post(
                "/api/v1/admin/users/{}/unlock-sign-in".format(user_id),
                headers={"Authorization": f"Bearer {access_token}"},
            )
            assert unlock.status_code == 200, unlock.text
            uj = unlock.json()
            assert uj.get("mandated_next_sign_in_verification") is False
            st = uj.get("state_after") or {}
            assert st.get("post_unlock_step_up_pending") in (False, None)

    async with AsyncClient(transport=ASGITransport(app=app), base_url=origin) as ac:
        lr = await ac.post(
            "/api/v1/auth/login",
            json={"email": email, "password": password, "trust_this_device": False},
        )
    assert lr.status_code == 200, lr.text
    assert lr.json().get("ok") is True
