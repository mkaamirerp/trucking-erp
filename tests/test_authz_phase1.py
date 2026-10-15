"""Phase 1 prospective permissions. No database and no route enforcement."""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from app.authz.catalog import CAPABILITIES
from app.authz.decision import DecisionCode, decide
from app.authz.loader import POLICY_PATH, load_shipped_policy
from app.authz.modules import MODULES
from app.authz.modules.fuel import CATALOG as FUEL_CATALOG
from app.authz.modules.loads import CATALOG as LOADS_CATALOG
from app.authz.prospective import (
    PROSPECTIVE_POLICY_PATH,
    load_prospective_policy,
    render_prospective_policy,
    subjects_for,
)
from app.authz.registry import (
    ADMIN_ROLES,
    CAPABILITIES as SHIPPED_CAPABILITIES,
    FUEL_CAPABILITIES,
    OPERATIONAL_FULL_ACCESS_ROLE,
    TENANT_MEMBER_ROLE,
)
from app.authz.routes import binding_for
from app.authz.spec import CapabilitySpec, CatalogError, ModuleCatalog, compose
from app.deps.admin import (
    FULL_ACCESS_ROLES,
    TENANT_ADMIN_ROLES,
    access_level_to_role,
)
from app.deps.fuel_rbac import fuel_capability_allowed

_DOMAIN_A = "17"
_DOMAIN_B = "42"


def _prospective():
    return load_prospective_policy()


def test_prospective_file_matches_catalog() -> None:
    assert PROSPECTIVE_POLICY_PATH.read_text(encoding="utf-8") == render_prospective_policy()
    loaded = _prospective()
    assert loaded.policy_path == PROSPECTIVE_POLICY_PATH
    assert loaded.policy_path != POLICY_PATH
    assert "OPERATIONAL_FULL_ACCESS" not in POLICY_PATH.read_text(encoding="utf-8")
    assert "loads.records" not in POLICY_PATH.read_text(encoding="utf-8")


def test_shipped_enforcer_does_not_grant_prospective_capabilities() -> None:
    shipped = load_shipped_policy().enforcer
    future = _prospective().enforcer
    shipped_decision = decide(
        shipped, role="OWNER", domain=_DOMAIN_A, resource="loads.records", action="view"
    )
    future_decision = decide(
        future, role="OWNER", domain=_DOMAIN_A, resource="loads.records", action="view"
    )
    assert shipped_decision.code is DecisionCode.DENY
    assert shipped_decision.reason == "policy_deny"
    assert future_decision.code is DecisionCode.ALLOW


def test_current_full_access_mapping_is_unchanged() -> None:
    assert access_level_to_role("FULL_ACCESS") == "TENANT_ADMIN"
    assert access_level_to_role("READ_ONLY") == "TENANT_MEMBER"
    assert FULL_ACCESS_ROLES == TENANT_ADMIN_ROLES
    assert OPERATIONAL_FULL_ACCESS_ROLE not in FULL_ACCESS_ROLES


def test_admin_can_invite_and_operate_operational_role_cannot() -> None:
    enforcer = _prospective().enforcer
    admin = decide(
        enforcer, role="TENANT_ADMIN", domain=_DOMAIN_A, resource="tenant.users", action="invite"
    )
    admin_write = decide(
        enforcer, role="TENANT_ADMIN", domain=_DOMAIN_A, resource="loads.records", action="update"
    )
    operational_write = decide(
        enforcer,
        role=OPERATIONAL_FULL_ACCESS_ROLE,
        domain=_DOMAIN_A,
        resource="loads.records",
        action="update",
    )
    operational_invite = decide(
        enforcer,
        role=OPERATIONAL_FULL_ACCESS_ROLE,
        domain=_DOMAIN_A,
        resource="tenant.users",
        action="invite",
    )
    operational_admin = decide(
        enforcer,
        role=OPERATIONAL_FULL_ACCESS_ROLE,
        domain=_DOMAIN_A,
        resource="tenant.admin",
        action="access",
    )
    assert admin.code is DecisionCode.ALLOW
    assert admin_write.code is DecisionCode.ALLOW
    assert operational_write.code is DecisionCode.ALLOW
    assert operational_invite.code is DecisionCode.DENY
    assert operational_admin.code is DecisionCode.DENY


def test_read_only_subject_can_view_but_not_mutate() -> None:
    enforcer = _prospective().enforcer
    view = decide(
        enforcer, role=TENANT_MEMBER_ROLE, domain=_DOMAIN_A, resource="loads.records", action="view"
    )
    update = decide(
        enforcer,
        role=TENANT_MEMBER_ROLE,
        domain=_DOMAIN_A,
        resource="loads.records",
        action="update",
    )
    invite = decide(
        enforcer, role=TENANT_MEMBER_ROLE, domain=_DOMAIN_A, resource="tenant.users", action="invite"
    )
    users = decide(
        enforcer, role=TENANT_MEMBER_ROLE, domain=_DOMAIN_A, resource="tenant.users", action="list"
    )
    assert view.code is DecisionCode.ALLOW
    assert users.code is DecisionCode.ALLOW
    assert update.code is DecisionCode.DENY
    assert invite.code is DecisionCode.DENY
    subjects = {
        line.split(",")[1].strip()
        for line in PROSPECTIVE_POLICY_PATH.read_text(encoding="utf-8").splitlines()
        if line.startswith("p,")
    }
    assert "READ_ONLY" not in subjects
    assert TENANT_MEMBER_ROLE in subjects


@pytest.mark.parametrize("role", sorted(ADMIN_ROLES))
def test_admin_roles_share_prospective_admin_grants(role: str) -> None:
    enforcer = _prospective().enforcer
    decision = decide(
        enforcer, role=role, domain=_DOMAIN_B, resource="payroll.runs", action="manage"
    )
    assert decision.code is DecisionCode.ALLOW


def test_tenant_scoped_grant_does_not_cross_tenants(tmp_path: Path) -> None:
    policy = tmp_path / "policy.csv"
    policy.write_text(
        "\n".join(
            (
                "# policy_version: 1",
                "p, OPERATIONAL_FULL_ACCESS, 17, loads.records, view, allow",
                "p, OPERATIONAL_FULL_ACCESS, 17, fuel.review, view, deny",
                "",
            )
        ),
        encoding="utf-8",
    )
    from app.authz.loader import MODEL_PATH, load_policy

    enforcer = load_policy(MODEL_PATH, policy, shipped=False).enforcer
    home = decide(
        enforcer,
        role=OPERATIONAL_FULL_ACCESS_ROLE,
        domain=_DOMAIN_A,
        resource="loads.records",
        action="view",
    )
    other = decide(
        enforcer,
        role=OPERATIONAL_FULL_ACCESS_ROLE,
        domain=_DOMAIN_B,
        resource="loads.records",
        action="view",
    )
    assert home.code is DecisionCode.ALLOW
    assert other.code is DecisionCode.DENY


def test_unknown_role_and_delete_capability_stay_closed() -> None:
    enforcer = _prospective().enforcer
    unknown = decide(
        enforcer, role="DISPATCHER", domain=_DOMAIN_A, resource="loads.records", action="view"
    )
    delete = decide(
        enforcer, role="OWNER", domain=_DOMAIN_A, resource="loads", action="delete"
    )
    assert unknown.code is DecisionCode.DENY
    assert unknown.reason == "unknown_role"
    assert delete.code is DecisionCode.UNAVAILABLE
    assert delete.reason == "unknown_capability"
    assert all(spec.action != "delete" for spec in CAPABILITIES.values())


def test_modules_cannot_take_each_others_capabilities() -> None:
    stolen = ModuleCatalog(
        "loads",
        LOADS_CATALOG.prefixes,
        LOADS_CATALOG.capabilities
        + (
            CapabilitySpec(
                "loads",
                "fuel.providers",
                "view",
                "operational",
                "ungated",
                False,
            ),
        ),
    )
    with pytest.raises(CatalogError, match="cannot own"):
        compose((stolen,))
    takeover = ModuleCatalog("fuel_extra", ("fuel.",), ())
    with pytest.raises(CatalogError, match="cannot take prefix"):
        compose(MODULES + (takeover,))


def test_fuel_stays_admin_only() -> None:
    assert all(spec.prospective == "admin" and spec.shipped for spec in FUEL_CATALOG.capabilities)
    assert not any(resource.startswith("fuel.imports") for resource, _ in CAPABILITIES)
    enforcer = _prospective().enforcer
    for resource, action in FUEL_CAPABILITIES:
        assert set(subjects_for(CAPABILITIES[(resource, action)])) == set(ADMIN_ROLES)
        assert (
            decide(
                enforcer,
                role=OPERATIONAL_FULL_ACCESS_ROLE,
                domain=_DOMAIN_A,
                resource=resource,
                action=action,
            ).code
            is DecisionCode.DENY
        )
        assert (
            decide(
                enforcer,
                role=TENANT_MEMBER_ROLE,
                domain=_DOMAIN_A,
                resource=resource,
                action=action,
            ).code
            is DecisionCode.DENY
        )
        dotted = f"{resource}.{action}"
        assert fuel_capability_allowed("TENANT_MEMBER", dotted) is False
        assert fuel_capability_allowed("TENANT_ADMIN", dotted) is True
    assert len(load_shipped_policy().rows) == len(ADMIN_ROLES) * len(SHIPPED_CAPABILITIES)


def test_route_classes_follow_the_handler_not_the_verb() -> None:
    assert binding_for("POST", "/api/v1/auth/workspaces").kind == "self_service"
    fuel = binding_for("GET", "/api/v1/fuel/providers")
    assert fuel.kind == "admin"
    assert fuel.pair == ("fuel.providers", "view")
    assert fuel.entitlement == "admin_sensitive"
    ready = binding_for("POST", "/api/v1/loads/{load_id}/mark-ready")
    assert ready.pair == ("loads.records", "mark_ready")
    assert "mark_load_ready" in ready.note
    deleted = binding_for("DELETE", "/api/v1/loads/{load_id}")
    assert deleted.kind == "domain_blocked"
    assert deleted.pair is None
    assert binding_for("DELETE", "/api/v1/drivers/{driver_id}").kind == "not_a_grant"
    assert binding_for("POST", "/api/v1/tolls/manual-entry/stages/{stage_id}/validate").kind == "write"
    assert binding_for("GET", "/api/v1/admin/users").pair == ("tenant.users", "list")
    assert binding_for("POST", "/api/v1/payroll/pay-runs").kind == "admin"
    assert binding_for("POST", "/api/v1/payroll/pay-entries").kind == "write"
    custody = binding_for("POST", "/api/v1/trips/{trip_id}/loads/{load_id}/accept-custody")
    assert custody.pair == ("trips.custody", "transition")
    assert "trip service" in custody.note
    assert "entitlement" not in inspect.signature(decide).parameters
