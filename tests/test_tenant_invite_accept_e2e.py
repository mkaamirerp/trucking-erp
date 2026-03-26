"""
Invite + accept-invite E2E (platform and tenant auth mode).

Requires DATABASE_URL, a real tenant with subscription + admin credentials.

Run inside dev API image (pytest installed):
  docker exec truckerp-api bash -lc 'cd /app && python -m pytest tests/test_tenant_invite_accept_e2e.py -v'

Env:
  RUN_INVITE_E2E=1
  INVITE_E2E_TENANT_SLUG=demo
  INVITE_E2E_ADMIN_EMAIL=...
  INVITE_E2E_ADMIN_PASSWORD=...

Cleanup: synthetic users use emails invited_* / invited_t_*; finally block removes platform + tenant rows
so shared tenants (e.g. demo) are not permanently polluted.
"""
from __future__ import annotations

import logging
import os
import uuid
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, func, select

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.deps.tenant_db import open_tenant_session_by_id
from app.main import app
from app.models.platform import (
    PlatformTenant,
    PlatformTenantMember,
    PlatformTenantUserMap,
    PlatformUser,
    TenantMembership,
    UserInvite,
)
from app.models.tenant_auth import TenantUser, TenantUserInvite, TenantWorkspaceMember
from app.utils.auth_identity import normalize_auth_email

logger = logging.getLogger(__name__)

SKIP_NO_DB = not os.environ.get("DATABASE_URL")
RUN = os.environ.get("RUN_INVITE_E2E") == "1"
SLUG = os.environ.get("INVITE_E2E_TENANT_SLUG")
ADM_EMAIL = os.environ.get("INVITE_E2E_ADMIN_EMAIL")
ADM_PW = os.environ.get("INVITE_E2E_ADMIN_PASSWORD")


def _host(slug: str) -> str:
    base = (settings.base_domain or "truckerp.me").lower()
    return f"{slug}.{base}"


SKIP_INVITE = SKIP_NO_DB or not RUN or not SLUG or not ADM_EMAIL or not ADM_PW


async def cleanup_invite_e2e_artifacts(tenant_id: int, invited_email: str) -> None:
    """Best-effort removal of users created by this module's tests only."""
    raw = (invited_email or "").strip()
    if not raw.startswith(("invited_", "invited_t_")):
        logger.warning("cleanup_invite_e2e_skipped_unrecognized_pattern email=%s", invited_email)
        return
    email_norm = normalize_auth_email(raw)
    if not email_norm:
        return

    try:
        async with AsyncSessionLocal() as pdb:
            pu = await pdb.scalar(select(PlatformUser).where(PlatformUser.email == email_norm))
            if not pu:
                return
            uid = str(pu.id)
            await pdb.execute(
                delete(UserInvite).where(UserInvite.user_id == uid, UserInvite.tenant_id == int(tenant_id))
            )
            await pdb.execute(
                delete(PlatformTenantUserMap).where(
                    PlatformTenantUserMap.tenant_id == int(tenant_id),
                    PlatformTenantUserMap.platform_user_id == uid,
                )
            )
            await pdb.execute(
                delete(TenantMembership).where(
                    TenantMembership.user_id == uid,
                    TenantMembership.tenant_id == int(tenant_id),
                )
            )
            await pdb.execute(
                delete(PlatformTenantMember).where(
                    PlatformTenantMember.tenant_id == int(tenant_id),
                    PlatformTenantMember.platform_user_id == uid,
                )
            )
            other_ptm = int(
                (
                    await pdb.scalar(
                        select(func.count()).select_from(PlatformTenantMember).where(
                            PlatformTenantMember.platform_user_id == uid
                        )
                    )
                )
                or 0
            )
            if other_ptm == 0:
                await pdb.execute(delete(PlatformUser).where(PlatformUser.id == uid))
            await pdb.commit()
    except Exception as exc:
        logger.warning(
            "cleanup_invite_e2e platform phase failed tenant_id=%s email=%s err=%s",
            tenant_id,
            email_norm,
            exc,
        )

    try:
        async for tdb in open_tenant_session_by_id(int(tenant_id)):
            tu = await tdb.scalar(
                select(TenantUser).where(
                    TenantUser.tenant_id == int(tenant_id),
                    TenantUser.email_norm == email_norm,
                )
            )
            if tu:
                tuid = int(tu.id)
                await tdb.execute(
                    delete(TenantUserInvite).where(TenantUserInvite.tenant_user_id == tuid)
                )
                await tdb.execute(
                    delete(TenantWorkspaceMember).where(
                        TenantWorkspaceMember.tenant_id == int(tenant_id),
                        TenantWorkspaceMember.tenant_user_id == tuid,
                    )
                )
                await tdb.execute(delete(TenantUser).where(TenantUser.id == tuid))
            await tdb.commit()
            break
    except Exception as exc:
        logger.warning(
            "cleanup_invite_e2e tenant phase failed tenant_id=%s email=%s err=%s",
            tenant_id,
            email_norm,
            exc,
        )


@pytest.mark.asyncio
@pytest.mark.skipif(SKIP_INVITE, reason="RUN_INVITE_E2E=1 and INVITE_E2E_* env required")
async def test_invite_accept_platform_auth_mode_end_to_end():
    tid = None
    orig_mode = None
    async with AsyncSessionLocal() as pdb:
        t = await pdb.scalar(select(PlatformTenant).where(PlatformTenant.slug == SLUG.strip().lower()))
        if not t:
            pytest.skip("tenant slug not found")
        tid = int(t.id)
        orig_mode = getattr(t, "tenant_auth_mode", None) or "platform"
        t.tenant_auth_mode = "platform"
        await pdb.commit()

    assert tid is not None

    suffix = uuid.uuid4().hex[:8]
    invited_email = f"invited_{suffix}@example.com"
    fixed = f"invite_fixed_token_{suffix}________________"

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            host = _host(SLUG.strip().lower())
            lr = await ac.post(
                "/api/v1/auth/login",
                json={"email": ADM_EMAIL, "password": ADM_PW},
                headers={"host": host},
            )
            assert lr.status_code == 200, lr.text
            token = lr.json()["access_token"]

            with patch("app.routers.tenant_admin.secrets.token_urlsafe", return_value=fixed):
                inv = await ac.post(
                    "/api/v1/admin/users/invite",
                    json={
                        "username": invited_email.split("@")[0],
                        "email": invited_email,
                        "access_level": "FULL_ACCESS",
                    },
                    headers={"host": host, "Authorization": f"Bearer {token}"},
                )
            assert inv.status_code == 200, inv.text

            acc = await ac.post(
                "/api/v1/auth/accept-invite",
                json={"token": fixed, "new_password": "InviteAccept!234"},
                headers={"host": host},
            )
            assert acc.status_code == 200, acc.text

            li = await ac.post(
                "/api/v1/auth/login",
                json={"email": invited_email, "password": "InviteAccept!234"},
                headers={"host": host},
            )
            assert li.status_code == 200, li.text
            from app.utils.jwt_auth import TokenType, decode_token

            sub = decode_token(li.json()["access_token"], expected_type=TokenType.ACCESS).get("sub")
            assert sub and "-" in str(sub), "platform mode login should use platform user id (UUID) as sub"

        async with AsyncSessionLocal() as pdb:
            from app.models.platform import PlatformUser

            pu = await pdb.scalar(select(PlatformUser).where(PlatformUser.email == invited_email))
            assert pu is not None
            tm = await pdb.scalar(
                select(TenantMembership).where(
                    TenantMembership.user_id == pu.id,
                    TenantMembership.tenant_id == tid,
                )
            )
            assert tm and (tm.status or "").lower() == "active"
    finally:
        if tid is not None:
            await cleanup_invite_e2e_artifacts(tid, invited_email)
            async with AsyncSessionLocal() as pdb:
                t = await pdb.get(PlatformTenant, tid)
                if t:
                    t.tenant_auth_mode = orig_mode
                    await pdb.commit()


@pytest.mark.asyncio
@pytest.mark.skipif(SKIP_INVITE, reason="RUN_INVITE_E2E=1 and INVITE_E2E_* env required")
async def test_invite_accept_tenant_auth_mode_end_to_end():
    tid = None
    orig_mode = None
    async with AsyncSessionLocal() as pdb:
        t = await pdb.scalar(select(PlatformTenant).where(PlatformTenant.slug == SLUG.strip().lower()))
        if not t:
            pytest.skip("tenant slug not found")
        tid = int(t.id)
        orig_mode = getattr(t, "tenant_auth_mode", None) or "platform"
        t.tenant_auth_mode = "tenant"
        await pdb.commit()

    assert tid is not None

    suffix = uuid.uuid4().hex[:8]
    invited_email = f"invited_t_{suffix}@example.com"
    fixed = f"invite_t_fixed_token_{suffix}______________"

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            host = _host(SLUG.strip().lower())
            lr = await ac.post(
                "/api/v1/auth/login",
                json={"email": ADM_EMAIL, "password": ADM_PW},
                headers={"host": host},
            )
            assert lr.status_code == 200, lr.text
            token = lr.json()["access_token"]

            with patch("app.routers.tenant_admin.secrets.token_urlsafe", return_value=fixed):
                inv = await ac.post(
                    "/api/v1/admin/users/invite",
                    json={
                        "username": invited_email.split("@")[0],
                        "email": invited_email,
                        "access_level": "READ_ONLY",
                    },
                    headers={"host": host, "Authorization": f"Bearer {token}"},
                )
            assert inv.status_code == 200, inv.text

            acc = await ac.post(
                "/api/v1/auth/accept-invite",
                json={"token": fixed, "new_password": "InviteAccept!234"},
                headers={"host": host},
            )
            assert acc.status_code == 200, acc.text

            li = await ac.post(
                "/api/v1/auth/login",
                json={"email": invited_email, "password": "InviteAccept!234"},
                headers={"host": host},
            )
            assert li.status_code == 200, li.text
            pl = li.json()
            assert pl.get("access_token")
            me = await ac.get(
                "/api/v1/auth/me",
                headers={"host": host, "Authorization": f"Bearer {pl['access_token']}"},
            )
            assert me.status_code == 200, me.text
            assert me.json().get("tenant_local_user_id") is not None

        async for tdb in open_tenant_session_by_id(tid):
            tu = await tdb.scalar(
                select(TenantUser).where(TenantUser.tenant_id == tid, TenantUser.email_norm == invited_email)
            )
            assert tu is not None
            twm = await tdb.scalar(
                select(TenantWorkspaceMember).where(
                    TenantWorkspaceMember.tenant_id == tid,
                    TenantWorkspaceMember.tenant_user_id == tu.id,
                )
            )
            assert twm and (twm.status or "").lower() == "active"
            tinv = await tdb.scalar(
                select(TenantUserInvite).where(TenantUserInvite.tenant_user_id == tu.id)
            )
            assert tinv and tinv.consumed_at is not None
            break

        async with AsyncSessionLocal() as pdb:
            from app.models.platform import PlatformUser

            pu = await pdb.scalar(select(PlatformUser).where(PlatformUser.email == invited_email))
            assert pu is not None
            pmap = await pdb.scalar(
                select(PlatformTenantUserMap).where(
                    PlatformTenantUserMap.tenant_id == tid,
                    PlatformTenantUserMap.platform_user_id == str(pu.id),
                )
            )
            assert pmap is not None
    finally:
        if tid is not None:
            await cleanup_invite_e2e_artifacts(tid, invited_email)
            async with AsyncSessionLocal() as pdb:
                t = await pdb.get(PlatformTenant, tid)
                if t:
                    t.tenant_auth_mode = orig_mode
                    await pdb.commit()
