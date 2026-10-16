"""Load audit actor identity. Unit checks always run. HTTP checks need phase4c databases."""

from __future__ import annotations

import asyncio
import os
import uuid
from types import SimpleNamespace
from urllib.parse import urlparse

import pytest
from fastapi import HTTPException
from sqlalchemy import text

from app.services.loads import normalize_load_audit_actor, resolve_load_audit_actor

_PRODUCTION_HOSTS = frozenset({"172.29.0.4", "truckerp-postgres", "localhost", "127.0.0.1", "::1"})
_PLATFORM_SLUG = "phase4c-audit"
_LOCAL_SLUG = "phase4c-local"
_PLATFORM_EMAIL = "phase4c-audit-admin@example.test"
_LOCAL_EMAIL = "phase4c-audit-local@example.test"


def test_platform_actor_uses_label_not_an_integer() -> None:
    platform_id = str(uuid.uuid4())
    user = SimpleNamespace(user=SimpleNamespace(id=platform_id), tenant_user=None, member_id=42)
    actor_id, label, actor_type = resolve_load_audit_actor(user)
    assert actor_id is None
    assert label == f"platform:{platform_id}"
    assert actor_type == "user"


def test_tenant_local_actor_uses_tenant_user_id() -> None:
    user = SimpleNamespace(
        user=SimpleNamespace(id=str(uuid.uuid4())),
        tenant_user=SimpleNamespace(id=17),
        member_id=42,
        tenant_local_member_id=99,
    )
    actor_id, label, actor_type = resolve_load_audit_actor(user)
    assert actor_id == 17
    assert label is None
    assert actor_type == "user"


def test_membership_id_and_uuid_are_rejected() -> None:
    member = SimpleNamespace(user=SimpleNamespace(id="42"), tenant_user=None, member_id=42)
    with pytest.raises(HTTPException) as membership:
        resolve_load_audit_actor(member)
    assert membership.value.detail["code"] == "AUDIT_ACTOR_UNRESOLVED"

    with pytest.raises(HTTPException) as uuid_id:
        normalize_load_audit_actor(str(uuid.uuid4()))
    assert uuid_id.value.detail["code"] == "AUDIT_ACTOR_UNRESOLVED"

    missing = SimpleNamespace(user=SimpleNamespace(id=None), tenant_user=None, member_id=None)
    with pytest.raises(HTTPException):
        resolve_load_audit_actor(missing)


def test_integer_actor_user_id_callers_stay_integer() -> None:
    actor_id, label, actor_type = normalize_load_audit_actor(1)
    assert (actor_id, label, actor_type) == (1, None, "user")


def test_numeric_user_id_without_platform_uuid_stays_integer() -> None:
    user = SimpleNamespace(tenant_user=None, user=None, user_id=1, member_id=1)
    assert resolve_load_audit_actor(user) == (1, None, "user")


def test_uuid_user_id_is_not_converted_to_an_integer() -> None:
    platform_id = str(uuid.uuid4())
    user = SimpleNamespace(tenant_user=None, user=None, user_id=platform_id, member_id=1)
    actor_id, label, actor_type = resolve_load_audit_actor(user)
    assert actor_id is None
    assert label == f"platform:{platform_id}"
    assert actor_type == "user"


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


def _audit_rows(tenant_id: int, load_id: int, action: str) -> list[tuple]:
    from sqlalchemy.ext.asyncio import create_async_engine

    from app.core.db_url import to_async_pg_url

    async def run():
        engine = create_async_engine(to_async_pg_url(os.environ["TENANT_DATABASE_URL"]))
        try:
            async with engine.connect() as conn:
                which = await conn.scalar(text("SELECT current_database()"))
                if which != "tenant_pytest":
                    raise RuntimeError(f"refusing tenant database {which}")
                result = await conn.execute(
                    text(
                        """
                        SELECT actor_type, actor_user_id, actor_label, changed_fields
                        FROM audit_events
                        WHERE tenant_id = :tid
                          AND entity_type = 'load'
                          AND entity_id = :eid
                          AND action = :action
                        ORDER BY id DESC
                        """
                    ),
                    {"tid": tenant_id, "eid": str(load_id), "action": action},
                )
                return [tuple(row) for row in result.all()]
        finally:
            await engine.dispose()

    return asyncio.run(run())


@pytest.fixture(scope="module")
def audit_world():
    if not _isolated_process():
        pytest.skip("isolated phase4c platform_phase4c/tenant_pytest database is not configured")
    if os.environ.get("TEST_BYPASS_AUTH") == "1":
        pytest.fail("Load audit identity tests must not use TEST_BYPASS_AUTH")
    from app.core.config import settings
    from app.core.database import AsyncSessionLocal
    from app.deps.auth import get_current_user
    from app.main import app
    from app.models.platform import (
        PlatformTenant,
        PlatformTenantMember,
        PlatformTenantUserMap,
        PlatformUser,
        TenantMembership,
    )
    from app.models.tenant_auth import TenantUser, TenantWorkspaceMember
    from fastapi.testclient import TestClient
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.core.db_url import to_async_pg_url

    if app.dependency_overrides.get(get_current_user) is not None:
        pytest.fail("get_current_user is overridden")
    if settings.casbin_load_pilot_enforcement:
        pytest.fail("Casbin load pilot must stay off unless a test turns it on")

    async def seed():
        async with AsyncSessionLocal() as db:
            current = await db.scalar(text("SELECT current_database()"))
            if current != "platform_phase4c":
                raise RuntimeError(f"refusing database {current}")
            await db.execute(
                text(
                    "DELETE FROM platform_tenant_user_map WHERE platform_user_id IN "
                    "(SELECT id FROM platform_users WHERE email IN (:platform_email, :local_email))"
                ),
                {"platform_email": _PLATFORM_EMAIL, "local_email": _LOCAL_EMAIL},
            )
            await db.execute(
                text("DELETE FROM platform_tenants WHERE slug IN (:platform_slug, :local_slug)"),
                {"platform_slug": _PLATFORM_SLUG, "local_slug": _LOCAL_SLUG},
            )
            await db.execute(
                text("DELETE FROM platform_users WHERE email IN (:platform_email, :local_email)"),
                {"platform_email": _PLATFORM_EMAIL, "local_email": _LOCAL_EMAIL},
            )
            await db.commit()
            platform_user = PlatformUser(
                id=str(uuid.uuid4()),
                email=_PLATFORM_EMAIL,
                first_name="Audit",
                last_name="Platform",
                status="ACTIVE",
                session_version=1,
            )
            local_platform_user = PlatformUser(
                id=str(uuid.uuid4()),
                email=_LOCAL_EMAIL,
                first_name="Audit",
                last_name="Local",
                status="ACTIVE",
                session_version=1,
            )
            platform_tenant = PlatformTenant(
                name="phase4c audit platform",
                slug=_PLATFORM_SLUG,
                status="ACTIVE",
                db_name="tenant_pytest",
                db_status="READY",
                tenant_auth_mode="platform",
            )
            local_tenant = PlatformTenant(
                name="phase4c audit local",
                slug=_LOCAL_SLUG,
                status="ACTIVE",
                db_name="tenant_pytest",
                db_status="READY",
                tenant_auth_mode="tenant",
            )
            db.add_all([platform_user, local_platform_user, platform_tenant, local_tenant])
            await db.flush()
            for user, tenant in (
                (platform_user, platform_tenant),
                (local_platform_user, local_tenant),
            ):
                db.add(
                    PlatformTenantMember(
                        tenant_id=tenant.id,
                        platform_user_id=user.id,
                        role="TENANT_ADMIN",
                    )
                )
                db.add(TenantMembership(user_id=user.id, tenant_id=tenant.id, status="active"))
            await db.commit()
            ids = {
                "platform_user_id": platform_user.id,
                "local_platform_user_id": local_platform_user.id,
                "platform_tenant_id": int(platform_tenant.id),
                "local_tenant_id": int(local_tenant.id),
            }

        engine = create_async_engine(to_async_pg_url(os.environ["TENANT_DATABASE_URL"]))
        Session = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with Session() as tdb:
                which = await tdb.scalar(text("SELECT current_database()"))
                if which != "tenant_pytest":
                    raise RuntimeError(f"refusing tenant database {which}")
                await tdb.execute(
                    text("DELETE FROM tenant_users WHERE email_norm = :email AND tenant_id = :tid"),
                    {"email": _LOCAL_EMAIL, "tid": ids["local_tenant_id"]},
                )
                await tdb.commit()
                tenant_user = TenantUser(
                    tenant_id=ids["local_tenant_id"],
                    email_norm=_LOCAL_EMAIL,
                    first_name="Audit",
                    last_name="Local",
                    status="ACTIVE",
                    session_version=1,
                )
                tdb.add(tenant_user)
                await tdb.flush()
                tdb.add(
                    TenantWorkspaceMember(
                        tenant_id=ids["local_tenant_id"],
                        tenant_user_id=int(tenant_user.id),
                        status="active",
                        role="TENANT_ADMIN",
                    )
                )
                await tdb.commit()
                ids["tenant_user_id"] = int(tenant_user.id)
        finally:
            await engine.dispose()

        async with AsyncSessionLocal() as db:
            db.add(
                PlatformTenantUserMap(
                    platform_user_id=ids["local_platform_user_id"],
                    tenant_id=ids["local_tenant_id"],
                    tenant_user_id=ids["tenant_user_id"],
                )
            )
            await db.commit()
        return ids

    ids = asyncio.run(seed())
    with TestClient(app) as client:
        yield {"client": client, "ids": ids}


def _headers(token: str, slug: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "host": f"{slug}.truckerp.me"}


def _token(user_id: str | int, tenant_id: int, slug: str) -> str:
    from app.utils.jwt_auth import create_access_token

    return create_access_token(
        user_id=user_id,
        tenant_id=tenant_id,
        tenant_slug=slug,
        roles=["DISPATCHER"],
        sv=1,
    )


def _create_load(client, headers: dict[str, str]) -> dict:
    created = client.post(
        "/api/v1/loads",
        json={"status": "draft", "load_number": f"AUD-{uuid.uuid4().hex[:8]}"},
        headers=headers,
    )
    assert created.status_code == 201, created.text
    return created.json()


def test_platform_and_tenant_local_audit_identity(audit_world, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.config import settings

    client = audit_world["client"]
    ids = audit_world["ids"]
    platform_headers = _headers(
        _token(ids["platform_user_id"], ids["platform_tenant_id"], _PLATFORM_SLUG),
        _PLATFORM_SLUG,
    )
    local_headers = _headers(
        _token(ids["tenant_user_id"], ids["local_tenant_id"], _LOCAL_SLUG),
        _LOCAL_SLUG,
    )
    expected_label = f"platform:{ids['platform_user_id']}"

    monkeypatch.setattr(settings, "casbin_load_pilot_enforcement", False)
    off_load = _create_load(client, platform_headers)
    off_patch = client.patch(
        f"/api/v1/loads/{off_load['id']}",
        json={"expected_concurrency_version": off_load["concurrency_version"], "commodity": "grain"},
        headers=platform_headers,
    )
    assert off_patch.status_code == 200, off_patch.text
    assert off_patch.json()["commodity"] == "grain"
    assert off_patch.json()["concurrency_version"] == off_load["concurrency_version"] + 1
    off_audit = _audit_rows(ids["platform_tenant_id"], off_load["id"], "load_updated")[0]
    assert off_audit[:3] == ("user", None, expected_label)

    monkeypatch.setattr(settings, "casbin_load_pilot_enforcement", True)
    on_load = _create_load(client, platform_headers)
    on_patch = client.patch(
        f"/api/v1/loads/{on_load['id']}",
        json={"expected_concurrency_version": on_load["concurrency_version"], "commodity": "corn"},
        headers=platform_headers,
    )
    assert on_patch.status_code == 200, on_patch.text
    on_audit = _audit_rows(ids["platform_tenant_id"], on_load["id"], "load_updated")[0]
    assert on_audit[:3] == ("user", None, expected_label)

    stale = client.patch(
        f"/api/v1/loads/{on_load['id']}",
        json={"expected_concurrency_version": on_load["concurrency_version"], "commodity": "late"},
        headers=platform_headers,
    )
    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "LOAD_VERSION_CONFLICT"

    money = client.patch(
        f"/api/v1/loads/{on_load['id']}",
        json={"expected_concurrency_version": on_patch.json()["concurrency_version"], "rate": 1500.5},
        headers=platform_headers,
    )
    assert money.status_code == 200, money.text
    assert float(money.json()["rate"]) == 1500.5
    money_audit = _audit_rows(ids["platform_tenant_id"], on_load["id"], "load_updated")[0]
    assert money_audit[:3] == ("user", None, expected_label)
    assert money_audit[3]["rate"]["after"] == "1500.50"

    note = client.post(
        f"/api/v1/loads/{off_load['id']}/notes",
        json={"body": "platform note"},
        headers=platform_headers,
    )
    assert note.status_code == 201, note.text
    assert note.json()["author_user_id"] == ids["platform_user_id"]
    note_audit = _audit_rows(ids["platform_tenant_id"], off_load["id"], "note_added")[0]
    assert note_audit[:3] == ("user", None, expected_label)

    local_load = _create_load(client, local_headers)
    local_patch = client.patch(
        f"/api/v1/loads/{local_load['id']}",
        json={"expected_concurrency_version": local_load["concurrency_version"], "commodity": "local-grain"},
        headers=local_headers,
    )
    assert local_patch.status_code == 200, local_patch.text
    assert local_patch.json()["commodity"] == "local-grain"
    assert local_patch.json()["concurrency_version"] == local_load["concurrency_version"] + 1
    local_audit = _audit_rows(ids["local_tenant_id"], local_load["id"], "load_updated")[0]
    assert local_audit[:3] == ("user", ids["tenant_user_id"], None)

    local_note = client.post(
        f"/api/v1/loads/{local_load['id']}/notes",
        json={"body": "local note"},
        headers=local_headers,
    )
    assert local_note.status_code == 201, local_note.text
    assert local_note.json()["author_user_id"] == ids["local_platform_user_id"]
    local_note_audit = _audit_rows(ids["local_tenant_id"], local_load["id"], "note_added")[0]
    assert local_note_audit[:3] == ("user", ids["tenant_user_id"], None)

    broker_id = _insert_customs_broker(ids["platform_tenant_id"])
    linked = client.patch(
        f"/api/v1/loads/{off_load['id']}",
        json={
            "expected_concurrency_version": off_patch.json()["concurrency_version"],
            "customs_broker_id": broker_id,
        },
        headers=platform_headers,
    )
    assert linked.status_code == 200, linked.text
    confirmed = client.post(
        f"/api/v1/loads/{off_load['id']}/confirm-document-snapshot",
        json={"expected_concurrency_version": linked.json()["concurrency_version"]},
        headers=platform_headers,
    )
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["document_snapshot_confirmed_by_user_id"] == ids["platform_user_id"]
    confirmed_audit = _audit_rows(ids["platform_tenant_id"], off_load["id"], "document_snapshot_confirmed")[0]
    assert confirmed_audit[:3] == ("user", None, expected_label)

    monkeypatch.setattr(settings, "casbin_load_pilot_enforcement", False)


def _insert_customs_broker(tenant_id: int) -> int:
    from sqlalchemy.ext.asyncio import create_async_engine

    from app.core.db_url import to_async_pg_url

    async def run() -> int:
        engine = create_async_engine(to_async_pg_url(os.environ["TENANT_DATABASE_URL"]))
        try:
            async with engine.begin() as conn:
                which = await conn.scalar(text("SELECT current_database()"))
                if which != "tenant_pytest":
                    raise RuntimeError(f"refusing tenant database {which}")
                broker_id = await conn.scalar(
                    text(
                        """
                        INSERT INTO customs_brokers (tenant_id, legal_name)
                        VALUES (:tid, :name)
                        RETURNING id
                        """
                    ),
                    {"tid": tenant_id, "name": f"Audit Broker {uuid.uuid4().hex[:8]}"},
                )
                return int(broker_id)
        finally:
            await engine.dispose()

    return asyncio.run(run())
