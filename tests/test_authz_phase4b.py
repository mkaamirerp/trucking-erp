"""Phase 4B HTTP checks for the four Loads pilot routes.

Requests go through FastAPI routing and the production route functions.
The tenant database is not opened: get_tenant_db is overridden with an inert
session, and successful handlers return a stub row. Integrity denials call the
real Load service guards. Production enforcement stays off outside each test.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app.authz.enforce import get_pilot_enforcer, reset_pilot_policy_cache
from app.authz.loader import LoadedPolicy, PolicyLoadError
from app.core.config import settings
from app.deps.admin import access_level_to_role
from app.deps.auth import CurrentUser, get_current_user
from app.deps.tenant_db import get_tenant_db
from app.routers.loads import router as loads_router
from app.utils.jwt_auth import create_access_token

HOST_TENANT_ID = 17
OTHER_TENANT_ID = 42


class _Calls:
    def __init__(self) -> None:
        self.items: list[tuple[str, int]] = []


def _member(role: str, *, mode: str = "platform", tenant_id: int = HOST_TENANT_ID) -> CurrentUser:
    tenant = SimpleNamespace(id=tenant_id, tenant_auth_mode=mode, slug="pytest")
    local_user = SimpleNamespace(id=9) if mode == "tenant" else None
    return CurrentUser(
        user=SimpleNamespace(id="platform-user-1"),
        tenant=tenant,
        role=role,
        member_id=1,
        tenant_user=local_user,
    )


def _row() -> SimpleNamespace:
    return SimpleNamespace(
        id=7,
        tenant_id=HOST_TENANT_ID,
        load_number="DRAFT-HTTP",
        status="draft",
        concurrency_version=1,
        stops=[],
        references=[],
        driver=None,
        broker=None,
        broker_contact=None,
        customs_broker=None,
        customs_snapshot=None,
        truck=None,
        trailer=None,
    )


def _app(tenant_id: int | None, user: CurrentUser | None) -> FastAPI:
    app = FastAPI()

    @app.middleware("http")
    async def _bind_host_tenant(request: Request, call_next):
        if tenant_id is not None:
            request.state.tenant_id = tenant_id
            request.state.tenant_slug = "pytest"
        return await call_next(request)

    app.include_router(loads_router, prefix="/api/v1")

    async def _session():
        yield SimpleNamespace(pilot_test_session=True)

    app.dependency_overrides[get_tenant_db] = _session
    if user is not None:
        async def _user() -> CurrentUser:
            return user

        app.dependency_overrides[get_current_user] = _user
    return app


def _client(tenant_id: int | None, user: CurrentUser | None) -> TestClient:
    return TestClient(_app(tenant_id, user), raise_server_exceptions=False)


def _stub_success(monkeypatch: pytest.MonkeyPatch, calls: _Calls) -> None:
    row = _row()

    async def _create(db, tenant_id, payload):
        calls.items.append(("create", int(tenant_id)))
        assert getattr(db, "pilot_test_session", False) is True
        return row

    async def _list(db, tenant_id, **kwargs):
        calls.items.append(("list", int(tenant_id)))
        return {"items": [row], "total": 1, "page": 1, "size": 25}

    async def _get(db, tenant_id, load_id):
        calls.items.append(("get", int(tenant_id)))
        assert load_id == 7
        return row

    async def _update(db, tenant_id, load_id, payload, **kwargs):
        calls.items.append(("update", int(tenant_id)))
        assert load_id == 7
        return row

    monkeypatch.setattr("app.routers.loads.loads_service.create_load", _create)
    monkeypatch.setattr("app.routers.loads.loads_service.list_loads", _list)
    monkeypatch.setattr("app.routers.loads.loads_service.get_load", _get)
    monkeypatch.setattr("app.routers.loads.loads_service.update_load", _update)


def _enable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "casbin_load_pilot_enforcement", True)


def _authz(response) -> dict:
    body = response.json()
    assert response.status_code == 403
    assert isinstance(body.get("detail"), dict)
    return body["detail"]


def _exercise(client: TestClient) -> dict[str, object]:
    return {
        "list": client.get("/api/v1/loads"),
        "detail": client.get("/api/v1/loads/7"),
        "create": client.post("/api/v1/loads", json={"status": "draft"}),
        "update": client.patch(
            "/api/v1/loads/7",
            json={"expected_concurrency_version": 1, "commodity": "grain"},
        ),
    }


def test_validated_enforcer_is_reused_until_the_cache_resets(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"n": 0}
    real = __import__("app.authz.prospective", fromlist=["load_prospective_policy"]).load_prospective_policy

    def _count():
        calls["n"] += 1
        return real()

    monkeypatch.setattr("app.authz.enforce.load_prospective_policy", _count)
    reset_pilot_policy_cache()
    first = get_pilot_enforcer()
    second = get_pilot_enforcer()
    assert first is second
    assert calls["n"] == 1
    reset_pilot_policy_cache()
    assert get_pilot_enforcer() is not None
    assert calls["n"] == 2


def test_invalid_policy_is_not_cached_and_stays_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    def _bad():
        raise PolicyLoadError("policy file missing")

    monkeypatch.setattr("app.authz.enforce.load_prospective_policy", _bad)
    reset_pilot_policy_cache()
    with pytest.raises(PolicyLoadError):
        get_pilot_enforcer()
    with pytest.raises(PolicyLoadError):
        get_pilot_enforcer()


@pytest.mark.parametrize("role", ["OWNER", "ADMIN", "TENANT_ADMIN", "TENANT_OWNER"])
def test_http_switch_on_allows_admin_pilot_routes(
    monkeypatch: pytest.MonkeyPatch, role: str
) -> None:
    _enable(monkeypatch)
    calls = _Calls()
    _stub_success(monkeypatch, calls)
    responses = _exercise(_client(HOST_TENANT_ID, _member(role)))
    assert responses["list"].status_code == 200
    assert responses["detail"].status_code == 200
    assert responses["detail"].json()["id"] == 7
    assert responses["create"].status_code == 201
    assert responses["update"].status_code == 200
    assert [name for name, _tenant in calls.items] == ["list", "get", "create", "update"]


def test_http_switch_off_lets_read_only_write(monkeypatch: pytest.MonkeyPatch) -> None:
    assert settings.casbin_load_pilot_enforcement is False
    assert access_level_to_role("READ_ONLY") == "TENANT_MEMBER"
    calls = _Calls()
    _stub_success(monkeypatch, calls)
    responses = _exercise(_client(HOST_TENANT_ID, _member("TENANT_MEMBER")))
    assert responses["create"].status_code == 201
    assert responses["update"].status_code == 200
    assert ("create", HOST_TENANT_ID) in calls.items
    assert ("update", HOST_TENANT_ID) in calls.items


def test_http_switch_on_read_only_can_view_but_not_write(monkeypatch: pytest.MonkeyPatch) -> None:
    _enable(monkeypatch)
    calls = _Calls()
    _stub_success(monkeypatch, calls)
    responses = _exercise(_client(HOST_TENANT_ID, _member("TENANT_MEMBER")))
    assert responses["list"].status_code == 200
    assert responses["detail"].status_code == 200
    assert _authz(responses["create"])["code"] == "AUTHZ_FORBIDDEN"
    assert _authz(responses["update"])["code"] == "AUTHZ_FORBIDDEN"
    assert [name for name, _tenant in calls.items] == ["list", "get"]


def test_http_unknown_role_denies_all_four(monkeypatch: pytest.MonkeyPatch) -> None:
    _enable(monkeypatch)
    calls = _Calls()
    _stub_success(monkeypatch, calls)
    responses = _exercise(_client(HOST_TENANT_ID, _member("DISPATCHER")))
    for response in responses.values():
        assert _authz(response)["reason"] == "unknown_role"
    assert calls.items == []


def test_http_cross_tenant_denies_when_enforcement_is_on(monkeypatch: pytest.MonkeyPatch) -> None:
    _enable(monkeypatch)
    calls = _Calls()
    _stub_success(monkeypatch, calls)
    response = _client(OTHER_TENANT_ID, _member("TENANT_ADMIN", tenant_id=HOST_TENANT_ID)).get(
        "/api/v1/loads"
    )
    assert _authz(response)["reason"] == "cross_tenant"
    assert calls.items == []


def test_http_platform_and_tenant_local_admin_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    _enable(monkeypatch)
    calls = _Calls()
    _stub_success(monkeypatch, calls)
    platform = _client(HOST_TENANT_ID, _member("TENANT_ADMIN", mode="platform")).get("/api/v1/loads/7")
    local = _client(HOST_TENANT_ID, _member("TENANT_ADMIN", mode="tenant")).post(
        "/api/v1/loads", json={"status": "draft"}
    )
    assert platform.status_code == 200
    assert local.status_code == 201
    assert ("get", HOST_TENANT_ID) in calls.items
    assert ("create", HOST_TENANT_ID) in calls.items


def test_http_client_role_header_does_not_grant_a_write(monkeypatch: pytest.MonkeyPatch) -> None:
    _enable(monkeypatch)
    calls = _Calls()
    _stub_success(monkeypatch, calls)
    response = _client(HOST_TENANT_ID, _member("TENANT_MEMBER")).post(
        "/api/v1/loads",
        json={"status": "draft"},
        headers={"X-Role": "OWNER", "X-Tenant-Id": "1"},
    )
    assert _authz(response)["code"] == "AUTHZ_FORBIDDEN"
    assert calls.items == []


def test_http_missing_policy_and_enforcer_exception_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    _enable(monkeypatch)
    calls = _Calls()
    _stub_success(monkeypatch, calls)

    def _missing():
        raise PolicyLoadError("policy file missing")

    monkeypatch.setattr("app.authz.enforce.load_prospective_policy", _missing)
    reset_pilot_policy_cache()
    client = _client(HOST_TENANT_ID, _member("TENANT_ADMIN"))
    first = client.get("/api/v1/loads")
    second = client.get("/api/v1/loads/7")
    assert _authz(first)["reason"] == "policy_load_failed"
    assert _authz(second)["reason"] == "policy_load_failed"

    class _Boom:
        def enforce(self, *_args: str) -> bool:
            raise RuntimeError("casbin failed")

    def _broken():
        return LoadedPolicy(
            version=1,
            enforcer=_Boom(),
            model_path=__import__("pathlib").Path("model.conf"),
            policy_path=__import__("pathlib").Path("policy.csv"),
            rows=(),
        )

    monkeypatch.setattr("app.authz.enforce.load_prospective_policy", _broken)
    reset_pilot_policy_cache()
    loaded = client.get("/api/v1/loads")
    reused = client.post("/api/v1/loads", json={"status": "draft"})
    assert _authz(loaded)["code"] == "AUTHZ_UNAVAILABLE"
    assert _authz(reused)["code"] == "AUTHZ_UNAVAILABLE"
    assert calls.items == []


def test_http_authentication_and_tenant_context_still_reject(monkeypatch: pytest.MonkeyPatch) -> None:
    _enable(monkeypatch)
    missing_token = _client(HOST_TENANT_ID, user=None).get("/api/v1/loads")
    assert missing_token.status_code == 401
    assert missing_token.json()["detail"] == "Not authenticated"

    bad_token = _client(HOST_TENANT_ID, user=None).get(
        "/api/v1/loads",
        headers={"Authorization": "Bearer not-a-jwt"},
    )
    assert bad_token.status_code == 401

    missing_tenant = _client(None, _member("TENANT_ADMIN")).get("/api/v1/loads")
    assert missing_tenant.status_code == 400
    assert missing_tenant.json()["detail"] == "Missing tenant context"

    token = create_access_token(
        user_id="platform-user-1",
        tenant_id=OTHER_TENANT_ID,
        tenant_slug="other",
        roles=["OWNER"],
        sv=1,
    )
    mismatch = _client(HOST_TENANT_ID, user=None).get(
        "/api/v1/loads",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert mismatch.status_code == 403
    assert "workspace" in str(mismatch.json()["detail"]).lower()


@pytest.mark.parametrize("enabled", [False, True])
def test_http_load_integrity_guards_still_apply(
    monkeypatch: pytest.MonkeyPatch, enabled: bool
) -> None:
    monkeypatch.setattr(settings, "casbin_load_pilot_enforcement", enabled)

    async def _existing_draft(db, tenant_id, load_id):
        return _row()

    monkeypatch.setattr("app.services.loads.get_load", _existing_draft)
    client = _client(HOST_TENANT_ID, _member("TENANT_ADMIN"))
    created = client.post("/api/v1/loads", json={"status": "ready"})
    updated = client.patch(
        "/api/v1/loads/7",
        json={"expected_concurrency_version": 1, "status": "ready"},
    )
    assigned = client.post("/api/v1/loads", json={"status": "draft", "driver_id": 4})
    assert created.status_code == 409
    assert created.json()["detail"]["code"] == "LOAD_CREATE_STATUS_MUST_BE_DRAFT"
    assert updated.status_code == 409
    assert updated.json()["detail"]["code"] == "LOAD_STATUS_READY_USE_MARK_READY_ENDPOINT"
    assert assigned.status_code == 409
    assert assigned.json()["detail"]["code"] == "LEGACY_LOAD_ASSIGNMENT_DEPRECATED"


def test_http_nonpilot_routes_stay_outside_enforcement(monkeypatch: pytest.MonkeyPatch) -> None:
    _enable(monkeypatch)

    async def _notes(db, tenant_id, load_id):
        return []

    async def _delete(db, tenant_id, load_id, expected_concurrency_version):
        return None

    monkeypatch.setattr("app.routers.loads.loads_service.list_load_notes", _notes)
    monkeypatch.setattr("app.routers.loads.loads_service.delete_load", _delete)
    client = _client(HOST_TENANT_ID, _member("TENANT_MEMBER"))
    notes = client.get("/api/v1/loads/7/notes")
    deleted = client.delete("/api/v1/loads/7?expected_concurrency_version=1")
    assert notes.status_code == 200
    assert notes.json() == []
    assert deleted.status_code == 204
