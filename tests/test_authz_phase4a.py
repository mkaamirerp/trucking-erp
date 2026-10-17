"""Phase 4A Loads pilot. No database. Enforcement stays off unless the test turns it on."""

from __future__ import annotations

import asyncio
import inspect
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.routing import APIRoute

from app.authz.enforce import require_pilot_capability
from app.authz.loader import PolicyLoadError
from app.core.config import Settings, settings
from app.deps.admin import access_level_to_role
from app.deps.auth import get_current_user
from app.authz.registry import ADMIN_ROLES
from app.routers.loads import (
    add_load_note,
    confirm_document_snapshot,
    create_load,
    delete_load,
    get_load_custody,
    get_load_detail,
    list_load_custody_events,
    list_load_notes,
    list_loads,
    mark_load_ready,
    parse_load_workspace_document,
    router,
    update_load,
)
from app.schemas.load import LoadUpdate
from app.services.loads import _guard_update_payload


class _Tenant:
    def __init__(self, tenant_id: int, mode: str) -> None:
        self.id = tenant_id
        self.tenant_auth_mode = mode


def _user(role: str | None, *, mode: str = "platform", tenant_id: int = 17, with_local: bool = True):
    tenant_user = SimpleNamespace(id=1) if mode == "tenant" and with_local else None
    return SimpleNamespace(
        role=role,
        tenant=_Tenant(tenant_id, mode),
        tenant_user=tenant_user,
        tenant_id=tenant_id,
    )


def _run(user, resource: str, action: str, tenant_id: int = 17):
    dep = require_pilot_capability(resource, action)
    return asyncio.run(dep(user=user, tenant_id=tenant_id))


def _enable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "casbin_load_pilot_enforcement", True)


def _detail(exc: HTTPException) -> dict:
    assert exc.status_code == 403
    assert isinstance(exc.detail, dict)
    return exc.detail


def test_switch_defaults_off_and_preserves_ungated_write(monkeypatch: pytest.MonkeyPatch) -> None:
    assert Settings.model_fields["casbin_load_pilot_enforcement"].default is False
    monkeypatch.setattr(settings, "casbin_load_pilot_enforcement", False)

    def _explode():
        raise AssertionError("policy must not load while enforcement is off")

    monkeypatch.setattr("app.authz.enforce.get_pilot_enforcer", _explode)
    user = _user("TENANT_MEMBER")
    assert _run(user, "loads.records", "create") is user
    assert _run(user, "loads.records", "update") is user


@pytest.mark.parametrize("role", sorted(ADMIN_ROLES))
def test_switch_on_allows_admin_view_and_write(monkeypatch: pytest.MonkeyPatch, role: str) -> None:
    _enable(monkeypatch)
    user = _user(role)
    assert _run(user, "loads.records", "view") is user
    assert _run(user, "loads.records", "create") is user
    assert _run(user, "loads.records", "update") is user


def test_switch_on_allows_operational_full_access(monkeypatch: pytest.MonkeyPatch) -> None:
    _enable(monkeypatch)
    user = _user("OPERATIONAL_FULL_ACCESS")
    assert _run(user, "loads.records", "view") is user
    assert _run(user, "loads.records", "create") is user
    assert _run(user, "loads.records", "update") is user


def test_switch_on_read_only_can_view_but_not_write(monkeypatch: pytest.MonkeyPatch) -> None:
    _enable(monkeypatch)
    assert access_level_to_role("READ_ONLY") == "TENANT_MEMBER"
    user = _user("TENANT_MEMBER")
    assert _run(user, "loads.records", "view") is user
    with pytest.raises(HTTPException) as create_error:
        _run(user, "loads.records", "create")
    with pytest.raises(HTTPException) as update_error:
        _run(user, "loads.records", "update")
    assert _detail(create_error.value)["code"] == "AUTHZ_FORBIDDEN"
    assert _detail(update_error.value)["code"] == "AUTHZ_FORBIDDEN"


def test_unknown_role_and_cross_tenant_deny(monkeypatch: pytest.MonkeyPatch) -> None:
    _enable(monkeypatch)
    with pytest.raises(HTTPException) as unknown:
        _run(_user("DISPATCHER"), "loads.records", "view")
    assert _detail(unknown.value)["reason"] == "unknown_role"
    with pytest.raises(HTTPException) as crossed:
        _run(_user("OWNER", tenant_id=17), "loads.records", "view", tenant_id=42)
    assert _detail(crossed.value)["reason"] == "cross_tenant"


def test_platform_and_tenant_local_admin_both_allowed(monkeypatch: pytest.MonkeyPatch) -> None:
    _enable(monkeypatch)
    assert _run(_user("TENANT_ADMIN", mode="platform"), "loads.records", "view") is not None
    assert _run(_user("TENANT_ADMIN", mode="tenant"), "loads.records", "create") is not None


def test_missing_policy_and_enforcer_errors_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    _enable(monkeypatch)

    def _missing():
        raise PolicyLoadError("policy file missing")

    monkeypatch.setattr("app.authz.enforce.get_pilot_enforcer", _missing)
    with pytest.raises(HTTPException) as missing:
        _run(_user("OWNER"), "loads.records", "view")
    assert _detail(missing.value)["code"] == "AUTHZ_UNAVAILABLE"
    assert _detail(missing.value)["reason"] == "policy_load_failed"

    class _Boom:
        def enforce(self, *_args: str) -> bool:
            raise RuntimeError("casbin failed")

    monkeypatch.setattr("app.authz.enforce.get_pilot_enforcer", lambda: _Boom())
    with pytest.raises(HTTPException) as exploded:
        _run(_user("OWNER"), "loads.records", "view")
    assert _detail(exploded.value)["code"] == "AUTHZ_UNAVAILABLE"
    assert exploded.value.status_code == 403


def test_pilot_is_only_on_the_four_load_routes() -> None:
    expected = {
        ("POST", "/loads"): ("loads.records", "create"),
        ("GET", "/loads"): ("loads.records", "view"),
        ("GET", "/loads/{load_id}"): ("loads.records", "view"),
        ("PATCH", "/loads/{load_id}"): ("loads.records", "update"),
    }
    found: dict[tuple[str, str], tuple[str, str]] = {}
    for route in router.routes:
        if not isinstance(route, APIRoute):
            continue
        caps = _pilot_caps(route)
        for method in route.methods or ():
            if method in {"HEAD", "OPTIONS"}:
                continue
            key = (method, route.path)
            if caps:
                assert len(caps) == 1
                found[key] = caps[0]
            else:
                assert key not in expected
    assert found == expected
    for endpoint in (
        parse_load_workspace_document,
        confirm_document_snapshot,
        mark_load_ready,
        get_load_custody,
        list_load_custody_events,
        list_load_notes,
        add_load_note,
        delete_load,
    ):
        assert "require_pilot_capability" not in inspect.getsource(endpoint)


def test_authentication_dependency_and_ready_guard_remain() -> None:
    dep = require_pilot_capability("loads.records", "view")
    user_default = inspect.signature(dep).parameters["user"].default
    assert getattr(user_default, "dependency", None) is get_current_user
    for endpoint in (list_loads, get_load_detail, create_load, update_load):
        assert "Depends" in inspect.getsource(endpoint)
    with pytest.raises(HTTPException) as ready:
        _guard_update_payload(SimpleNamespace(status="draft"), LoadUpdate(expected_concurrency_version=1, status="ready"))
    assert ready.value.status_code == 409
    assert ready.value.detail["code"] == "LOAD_STATUS_READY_USE_MARK_READY_ENDPOINT"


def _pilot_caps(route: APIRoute) -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []

    def walk(dependant) -> None:
        for item in dependant.dependencies:
            cap = getattr(item.call, "pilot_capability", None)
            if cap is not None:
                found.append(cap)
            walk(item)

    walk(route.dependant)
    return found
