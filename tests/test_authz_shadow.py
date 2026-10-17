"""Shadow authorization comparisons. No database and no live request path."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from app.authz.decision import DecisionCode, decide
from app.authz.loader import MODEL_PATH, load_policy
from app.authz.registry import ADMIN_ROLES, OPERATIONAL_FULL_ACCESS_ROLE, TENANT_MEMBER_ROLE
from app.authz.shadow import (
    ExistingCode,
    ShadowCasbin,
    ShadowContextError,
    ShadowOutcome,
    evaluate_shadow,
    principal_from_member,
)
from app.deps.admin import access_level_to_role

_ADMIN_ENTITLEMENTS = frozenset({"admin_sensitive", "payroll"})


class _Tenant:
    def __init__(self, tenant_id: int, mode: str) -> None:
        self.id = tenant_id
        self.tenant_auth_mode = mode


def _member(
    role: str | None,
    *,
    mode: str = "platform",
    tenant_id: int = 17,
    tenant_user: object | None = None,
    with_tenant_user: bool = True,
):
    tenant = _Tenant(tenant_id, mode)
    if mode == "tenant" and with_tenant_user and tenant_user is None:
        tenant_user = SimpleNamespace(id=1)
    if mode != "tenant":
        tenant_user = None
    return SimpleNamespace(role=role, tenant=tenant, tenant_user=tenant_user, tenant_id=tenant_id)


def _eval(role: str, method: str, path: str, **kwargs):
    mode = kwargs.pop("mode", "platform")
    tenant_id = kwargs.pop("tenant_id", 17)
    principal = principal_from_member(_member(role, mode=mode, tenant_id=tenant_id))
    return evaluate_shadow(principal, method=method, path=path, **kwargs)


@pytest.mark.parametrize("role", sorted(ADMIN_ROLES))
def test_four_admin_roles_match_on_fuel_and_invites(role: str) -> None:
    fuel = _eval(
        role,
        "GET",
        "/api/v1/fuel/providers",
        granted_entitlements=_ADMIN_ENTITLEMENTS,
    )
    invite = _eval(
        role,
        "POST",
        "/api/v1/admin/users/invite",
        granted_entitlements=_ADMIN_ENTITLEMENTS,
    )
    assert fuel.outcome is ShadowOutcome.MATCH
    assert fuel.existing is ExistingCode.ALLOW
    assert fuel.casbin is ShadowCasbin.ALLOW
    assert invite.outcome is ShadowOutcome.MATCH
    assert invite.existing is ExistingCode.ALLOW


def test_operational_full_access_is_not_an_admin_grant() -> None:
    denied = _eval(
        OPERATIONAL_FULL_ACCESS_ROLE,
        "PATCH",
        "/api/v1/people/{person_id}",
        granted_entitlements=_ADMIN_ENTITLEMENTS,
    )
    fuel = _eval(OPERATIONAL_FULL_ACCESS_ROLE, "GET", "/api/v1/fuel/providers")
    assert denied.outcome is ShadowOutcome.CONFLICT_EXISTING_DENY
    assert denied.existing is ExistingCode.DENY
    assert denied.casbin is ShadowCasbin.ALLOW
    assert fuel.outcome is ShadowOutcome.MATCH
    assert fuel.existing is ExistingCode.DENY
    assert fuel.casbin is ShadowCasbin.DENY


def test_tenant_member_read_only_label_uses_member_role() -> None:
    assert access_level_to_role("READ_ONLY") == TENANT_MEMBER_ROLE
    listed = _eval(
        TENANT_MEMBER_ROLE,
        "GET",
        "/api/v1/admin/users",
        granted_entitlements=_ADMIN_ENTITLEMENTS,
    )
    invite = _eval(TENANT_MEMBER_ROLE, "POST", "/api/v1/admin/users/invite")
    assert listed.outcome is ShadowOutcome.MATCH
    assert listed.existing is ExistingCode.ALLOW
    assert invite.outcome is ShadowOutcome.MATCH
    assert invite.existing is ExistingCode.DENY
    assert invite.casbin is ShadowCasbin.DENY


def test_platform_and_tenant_local_modes_agree() -> None:
    platform = _eval(
        "TENANT_OWNER",
        "GET",
        "/api/v1/fuel/providers",
        mode="platform",
        granted_entitlements=_ADMIN_ENTITLEMENTS,
    )
    local = _eval(
        "TENANT_OWNER",
        "GET",
        "/api/v1/fuel/providers",
        mode="tenant",
        granted_entitlements=_ADMIN_ENTITLEMENTS,
    )
    assert platform.auth_mode == "platform"
    assert local.auth_mode == "tenant_local"
    assert platform.outcome == local.outcome
    assert platform.existing == local.existing
    assert platform.casbin == local.casbin


def test_tenant_local_without_workspace_member_is_rejected() -> None:
    member = _member("TENANT_ADMIN", mode="tenant", with_tenant_user=False)
    with pytest.raises(ShadowContextError, match="TenantWorkspaceMember"):
        principal_from_member(member)


def test_cross_tenant_request_is_rejected() -> None:
    result = _eval(
        "OWNER",
        "GET",
        "/api/v1/fuel/providers",
        tenant_id=17,
        requested_tenant_id=42,
        granted_entitlements=_ADMIN_ENTITLEMENTS,
    )
    assert result.outcome is ShadowOutcome.CROSS_TENANT
    assert result.tenant_id == 17
    assert result.casbin is ShadowCasbin.DENY
    assert result.existing is ExistingCode.DENY


def test_people_and_payroll_reads_stay_pending() -> None:
    people = _eval(
        "OWNER",
        "GET",
        "/api/v1/people",
        granted_entitlements=_ADMIN_ENTITLEMENTS,
    )
    payroll = _eval("TENANT_ADMIN", "GET", "/api/v1/payroll/pay-runs")
    assert people.outcome is ShadowOutcome.PENDING_OWNER_APPROVAL
    assert people.existing is ExistingCode.ALLOW
    assert people.casbin is ShadowCasbin.PENDING
    assert people.casbin is not ShadowCasbin.DENY
    assert payroll.outcome is ShadowOutcome.PENDING_OWNER_APPROVAL
    assert payroll.existing is ExistingCode.UNKNOWN
    assert payroll.existing_reason == "no_role_gate"


def test_mapped_and_unmapped_routes() -> None:
    mapped = _eval(
        "ADMIN",
        "GET",
        "/api/v1/fuel/providers",
        granted_entitlements=_ADMIN_ENTITLEMENTS,
    )
    missing = _eval("ADMIN", "GET", "/api/v1/brokers")
    assert mapped.resource == "fuel.providers"
    assert mapped.outcome is ShadowOutcome.MATCH
    assert missing.outcome is ShadowOutcome.UNMAPPED
    assert missing.existing is ExistingCode.UNKNOWN
    assert missing.casbin is ShadowCasbin.UNAVAILABLE


def test_unavailable_casbin_is_not_an_allow() -> None:
    result = _eval(
        "OWNER",
        "GET",
        "/api/v1/fuel/providers",
        granted_entitlements=_ADMIN_ENTITLEMENTS,
        enforcer=None,
    )
    assert result.casbin is ShadowCasbin.UNAVAILABLE
    assert result.outcome is ShadowOutcome.CASBIN_UNAVAILABLE
    assert result.casbin is not ShadowCasbin.ALLOW


def test_existing_allow_versus_prospective_deny(tmp_path: Path) -> None:
    policy = tmp_path / "policy.csv"
    policy.write_text(
        "# policy_version: 1\np, TENANT_MEMBER, *, tenant.users, list, deny\n",
        encoding="utf-8",
    )
    enforcer = load_policy(MODEL_PATH, policy, shipped=False).enforcer
    result = _eval(
        TENANT_MEMBER_ROLE,
        "GET",
        "/api/v1/admin/users",
        granted_entitlements=_ADMIN_ENTITLEMENTS,
        enforcer=enforcer,
    )
    raw = decide(
        enforcer,
        role=TENANT_MEMBER_ROLE,
        domain="17",
        resource="tenant.users",
        action="list",
    )
    assert raw.code is DecisionCode.DENY
    assert result.existing is ExistingCode.ALLOW
    assert result.casbin is ShadowCasbin.DENY
    assert result.outcome is ShadowOutcome.CONFLICT_EXISTING_ALLOW


def test_existing_deny_versus_prospective_allow() -> None:
    result = _eval(
        OPERATIONAL_FULL_ACCESS_ROLE,
        "PATCH",
        "/api/v1/people/{person_id}",
        granted_entitlements=_ADMIN_ENTITLEMENTS,
    )
    assert result.existing is ExistingCode.DENY
    assert result.existing_reason == "tenant_admin"
    assert result.casbin is ShadowCasbin.ALLOW
    assert result.outcome is ShadowOutcome.CONFLICT_EXISTING_DENY


def test_missing_role_gate_is_unknown_not_allow() -> None:
    result = _eval("TENANT_ADMIN", "GET", "/api/v1/loads")
    assert result.existing is ExistingCode.UNKNOWN
    assert result.existing_reason == "no_role_gate"
    assert result.casbin is ShadowCasbin.ALLOW
    assert result.outcome is ShadowOutcome.EXISTING_UNKNOWN


def test_load_delete_stays_unresolved_and_shadow_is_not_wired() -> None:
    result = _eval("OWNER", "DELETE", "/api/v1/loads/{load_id}")
    assert result.outcome is ShadowOutcome.UNRESOLVED_DOMAIN_POLICY
    assert result.existing is ExistingCode.UNKNOWN
    assert result.casbin is ShadowCasbin.UNAVAILABLE
    assert result.resource is None
    main = Path("app/main.py").read_text(encoding="utf-8")
    assert "authz.shadow" not in main
    assert "evaluate_shadow" not in main
