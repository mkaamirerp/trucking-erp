"""Phase 4C: real FastAPI, authentication, and tenant middleware for the Loads pilot.

These tests do not override get_current_user. They require the isolated phase4c
Postgres role and databases (platform_phase4c and tenant_pytest). They skip when
that database is not the process database. They do not connect to production.
"""

from __future__ import annotations

import os
import uuid
from urllib.parse import urlparse

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.authz.loader import PolicyLoadError
from app.core.config import settings
from app.deps.auth import get_current_user
from app.utils.jwt_auth import create_access_token

_PRODUCTION_HOSTS = frozenset({"172.29.0.4", "truckerp-postgres", "localhost", "127.0.0.1", "::1"})
_HOME_SLUG = "pytest"
_OTHER_SLUG = "phase4c-other"


def _db_name(url: str) -> str:
    return (urlparse(url).path or "").lstrip("/").split("?", 1)[0]


def _isolated_process() -> bool:
    platform = os.environ.get("DATABASE_URL") or ""
    tenant = os.environ.get("TENANT_DATABASE_URL") or os.environ.get("ALEMBIC_TENANT_DATABASE_URL") or ""
    parsed = urlparse(platform)
    host = (parsed.hostname or "").lower()
    if parsed.username != "phase4c" or host in _PRODUCTION_HOSTS or not host:
        return False
    if _db_name(platform) != "platform_phase4c" or "tenant_demo" in platform:
        return False
    tenant_parsed = urlparse(tenant)
    return (
        (tenant_parsed.hostname or "").lower() == host
        and _db_name(tenant) == "tenant_pytest"
        and "tenant_demo" not in tenant
    )


pytestmark = pytest.mark.skipif(
    not _isolated_process(),
    reason="isolated phase4c platform_phase4c/tenant_pytest database is not configured",
)


@pytest.fixture(scope="module")
def phase4c_world():
    if os.environ.get("TEST_BYPASS_AUTH") == "1":
        pytest.fail("Phase 4C must not use TEST_BYPASS_AUTH")
    if _db_name(settings.database_url) != "platform_phase4c":
        pytest.skip("process database is not platform_phase4c")
    from app.deps.auth import get_current_user as live_user
    from app.main import app
    from app.models.platform import PlatformTenant, PlatformTenantMember, PlatformUser, TenantMembership
    from app.core.database import AsyncSessionLocal

    if app.dependency_overrides.get(live_user) is not None or app.dependency_overrides.get(get_current_user) is not None:
        pytest.fail("get_current_user is overridden; Phase 4C requires the real dependency")

    import asyncio

    async def _seed() -> dict[str, int | str]:
        async with AsyncSessionLocal() as db:
            current = await db.scalar(text("SELECT current_database()"))
            if current != "platform_phase4c":
                raise RuntimeError(f"refusing database {current}")
            await db.execute(
                text(
                    "ALTER TABLE platform_users "
                    "ADD COLUMN IF NOT EXISTS session_version integer NOT NULL DEFAULT 1"
                )
            )
            await db.commit()

        # loads live in the tenant database, not the platform database.
        from sqlalchemy.ext.asyncio import create_async_engine

        from app.core.db_url import to_async_pg_url

        tenant_url = to_async_pg_url(os.environ["TENANT_DATABASE_URL"])
        if _db_name(tenant_url) != "tenant_pytest":
            raise RuntimeError("refusing non-isolated tenant database")
        engine = create_async_engine(tenant_url)
        try:
            async with engine.begin() as conn:
                which = await conn.scalar(text("SELECT current_database()"))
                if which != "tenant_pytest":
                    raise RuntimeError(f"refusing tenant database {which}")
                await conn.execute(text("UPDATE trips SET legacy_dispatch_trip_id = NULL"))
                await conn.execute(text("DELETE FROM load_commercial_evidence"))
                await conn.execute(text("DELETE FROM dispatch_trips"))
                await conn.execute(text("DELETE FROM load_stops"))
                await conn.execute(text("DELETE FROM load_notes"))
                await conn.execute(text("DELETE FROM loads"))
        finally:
            await engine.dispose()

        async with AsyncSessionLocal() as db:
            if await db.scalar(text("SELECT to_regclass('public.platform_subscriptions')")):
                await db.execute(
                    text(
                        "DELETE FROM platform_subscriptions WHERE tenant_id IN "
                        "(SELECT id FROM platform_tenants WHERE slug IN ('pytest', 'phase4c-other'))"
                    )
                )
            await db.execute(
                text("DELETE FROM platform_tenants WHERE slug IN ('pytest', 'phase4c-other')")
            )
            await db.execute(
                text(
                    "DELETE FROM platform_users WHERE email IN "
                    "('phase4c-admin@example.test', 'phase4c-member@example.test')"
                )
            )
            await db.commit()
            admin = PlatformUser(
                id=str(uuid.uuid4()),
                email="phase4c-admin@example.test",
                first_name="Phase",
                last_name="Admin",
                status="ACTIVE",
                session_version=1,
            )
            member = PlatformUser(
                id=str(uuid.uuid4()),
                email="phase4c-member@example.test",
                first_name="Phase",
                last_name="Member",
                status="ACTIVE",
                session_version=1,
            )
            home = PlatformTenant(
                name="phase4c home",
                slug=_HOME_SLUG,
                status="ACTIVE",
                db_name="tenant_pytest",
                db_status="READY",
                tenant_auth_mode="platform",
            )
            other = PlatformTenant(
                name="phase4c other",
                slug=_OTHER_SLUG,
                status="ACTIVE",
                db_name="tenant_pytest",
                db_status="READY",
                tenant_auth_mode="platform",
            )
            db.add_all([admin, member, home, other])
            await db.flush()
            for user, role in ((admin, "TENANT_ADMIN"), (member, "TENANT_MEMBER")):
                db.add(
                    PlatformTenantMember(
                        tenant_id=home.id,
                        platform_user_id=user.id,
                        role=role,
                    )
                )
                db.add(TenantMembership(user_id=user.id, tenant_id=home.id, status="active"))
            await db.commit()
            return {
                "admin_id": admin.id,
                "member_id": member.id,
                "home_id": int(home.id),
                "other_id": int(other.id),
            }

    ids = asyncio.run(_seed())
    calls = {"n": 0}
    from app.routers import loads as loads_router

    real = {
        "create": loads_router.loads_service.create_load,
        "list": loads_router.loads_service.list_loads,
        "get": loads_router.loads_service.get_load,
        "update": loads_router.loads_service.update_load,
    }

    def _wrap(fn):
        async def _inner(*args, **kwargs):
            calls["n"] += 1
            return await fn(*args, **kwargs)

        return _inner

    loads_router.loads_service.create_load = _wrap(real["create"])
    loads_router.loads_service.list_loads = _wrap(real["list"])
    loads_router.loads_service.get_load = _wrap(real["get"])
    loads_router.loads_service.update_load = _wrap(real["update"])
    with TestClient(app) as client:
        yield {"client": client, "ids": ids, "calls": calls, "app": app}
    loads_router.loads_service.create_load = real["create"]
    loads_router.loads_service.list_loads = real["list"]
    loads_router.loads_service.get_load = real["get"]
    loads_router.loads_service.update_load = real["update"]


def _token(user_id: str, tenant_id: int, *, roles: list[str]) -> str:
    return create_access_token(
        user_id=user_id,
        tenant_id=tenant_id,
        tenant_slug=_HOME_SLUG,
        roles=roles,
        sv=1,
    )


def _headers(token: str, slug: str = _HOME_SLUG, **extra: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "host": f"{slug}.truckerp.me", **extra}


def _authz(response) -> dict:
    body = response.json()
    assert response.status_code == 403
    assert isinstance(body.get("detail"), dict)
    return body["detail"]


def test_real_auth_uses_membership_role_not_jwt_or_headers(phase4c_world, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "casbin_load_pilot_enforcement", True)
    client = phase4c_world["client"]
    ids = phase4c_world["ids"]
    calls = phase4c_world["calls"]
    assert phase4c_world["app"].dependency_overrides.get(get_current_user) is None

    admin = _token(ids["admin_id"], ids["home_id"], roles=["TENANT_MEMBER"])
    member = _token(ids["member_id"], ids["home_id"], roles=["OWNER"])
    member_headers = _headers(member, **{"X-Role": "OWNER", "X-Tenant-Id": str(ids["other_id"])})

    before = calls["n"]
    denied_create = client.post("/api/v1/loads", json={"status": "draft"}, headers=member_headers)
    denied_update = client.patch(
        "/api/v1/loads/1",
        json={"expected_concurrency_version": 1, "commodity": "grain"},
        headers=member_headers,
    )
    assert _authz(denied_create)["code"] == "AUTHZ_FORBIDDEN"
    assert _authz(denied_update)["code"] == "AUTHZ_FORBIDDEN"
    assert calls["n"] == before

    listed = client.get("/api/v1/loads", headers=_headers(member))
    assert listed.status_code == 200

    created = client.post(
        "/api/v1/loads",
        json={"status": "draft", "load_number": f"P4C-{uuid.uuid4().hex[:8]}"},
        headers=_headers(admin),
    )
    assert created.status_code == 201, created.text
    load_id = created.json()["id"]
    detail = client.get(f"/api/v1/loads/{load_id}", headers=_headers(admin))
    updated = client.patch(
        f"/api/v1/loads/{load_id}",
        json={"expected_concurrency_version": 1},
        headers=_headers(admin),
    )
    assert detail.status_code == 200
    assert updated.status_code == 200
    assert calls["n"] > before


def test_switch_off_preserves_read_only_write(phase4c_world, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "casbin_load_pilot_enforcement", False)
    client = phase4c_world["client"]
    ids = phase4c_world["ids"]
    member = _token(ids["member_id"], ids["home_id"], roles=["OWNER"])
    created = client.post("/api/v1/loads", json={"status": "draft"}, headers=_headers(member))
    assert created.status_code == 201, created.text


def test_cross_tenant_host_never_reaches_load_services(phase4c_world, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "casbin_load_pilot_enforcement", True)
    client = phase4c_world["client"]
    ids = phase4c_world["ids"]
    calls = phase4c_world["calls"]
    token = _token(ids["admin_id"], ids["other_id"], roles=["OWNER"])
    before = calls["n"]
    response = client.get("/api/v1/loads", headers=_headers(token, slug=_OTHER_SLUG))
    assert response.status_code == 403
    assert calls["n"] == before
    assert "access" in str(response.json()["detail"]).lower()


def test_missing_token_is_rejected_by_real_middleware(phase4c_world) -> None:
    before = phase4c_world["calls"]["n"]
    response = phase4c_world["client"].get("/api/v1/loads", headers={"host": f"{_HOME_SLUG}.truckerp.me"})
    assert response.status_code == 401
    assert phase4c_world["calls"]["n"] == before


def test_ready_guard_still_runs_for_an_authorized_admin(phase4c_world, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "casbin_load_pilot_enforcement", True)
    ids = phase4c_world["ids"]
    admin = _token(ids["admin_id"], ids["home_id"], roles=["DISPATCHER"])
    response = phase4c_world["client"].post(
        "/api/v1/loads",
        json={"status": "ready"},
        headers=_headers(admin),
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "LOAD_CREATE_STATUS_MUST_BE_DRAFT"


def test_cached_policy_ignores_a_later_loader_until_reset(phase4c_world, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "casbin_load_pilot_enforcement", True)
    from app.authz.enforce import reset_pilot_policy_cache

    client = phase4c_world["client"]
    ids = phase4c_world["ids"]
    admin = _headers(_token(ids["admin_id"], ids["home_id"], roles=["TENANT_MEMBER"]))
    assert client.get("/api/v1/loads", headers=admin).status_code == 200

    def _broken():
        raise PolicyLoadError("replaced policy is not visible until restart or reset")

    monkeypatch.setattr("app.authz.enforce.load_prospective_policy", _broken)
    assert client.get("/api/v1/loads", headers=admin).status_code == 200
    reset_pilot_policy_cache()
    failed = client.get("/api/v1/loads", headers=admin)
    assert failed.status_code == 403
    assert failed.json()["detail"]["reason"] == "policy_load_failed"
