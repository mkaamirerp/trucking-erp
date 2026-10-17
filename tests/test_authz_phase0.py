"""Isolated Phase 0 Casbin decisions. No database and no application startup."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.authz.decision import DecisionCode, decide, membership_role_for_decision
from app.authz.loader import MODEL_PATH, POLICY_PATH, PolicyLoadError, load_policy, load_shipped_policy
from app.authz.registry import ADMIN_ROLES, CAPABILITIES, FUEL_CAPABILITIES

_ADMIN_RESOURCE = "tenant.admin"
_ADMIN_ACTION = "access"
_FUEL_RESOURCE = "fuel.providers"
_FUEL_ACTION = "view"
_DOMAIN_A = "17"
_DOMAIN_B = "42"


def _write_policy(directory: Path, body: str, *, version: str = "1") -> Path:
    path = directory / "policy.csv"
    path.write_text(f"# policy_version: {version}\n{body}", encoding="utf-8")
    return path


def _shipped():
    return load_shipped_policy()


def test_shipped_policy_version_and_matrix() -> None:
    loaded = _shipped()
    assert loaded.version == 1
    assert len(loaded.rows) == len(ADMIN_ROLES) * len(CAPABILITIES)
    assert {row.effect for row in loaded.rows} == {"allow"}
    assert {row.domain for row in loaded.rows} == {"*"}
    assert {row.subject for row in loaded.rows} == set(ADMIN_ROLES)


@pytest.mark.parametrize("role", sorted(ADMIN_ROLES))
@pytest.mark.parametrize("auth_mode", ["platform", "tenant_local"])
def test_admin_roles_allow_admin_and_fuel_for_both_auth_modes(role: str, auth_mode: str) -> None:
    enforcer = _shipped().enforcer
    stored = membership_role_for_decision(auth_mode, role.lower())
    for resource, action in ((_ADMIN_RESOURCE, _ADMIN_ACTION), (_FUEL_RESOURCE, _FUEL_ACTION)):
        decision = decide(
            enforcer,
            role=stored,
            domain=_DOMAIN_A,
            resource=resource,
            action=action,
        )
        assert decision.code is DecisionCode.ALLOW
        assert decision.reason == "policy_allow"


@pytest.mark.parametrize("auth_mode", ["platform", "tenant_local"])
def test_tenant_member_denied_admin_and_every_fuel_capability(auth_mode: str) -> None:
    enforcer = _shipped().enforcer
    role = membership_role_for_decision(auth_mode, "TENANT_MEMBER")
    pairs = [(_ADMIN_RESOURCE, _ADMIN_ACTION), ("tenant.full_access", "access"), *FUEL_CAPABILITIES]
    for resource, action in pairs:
        decision = decide(enforcer, role=role, domain=_DOMAIN_B, resource=resource, action=action)
        assert decision.code is DecisionCode.DENY
        assert decision.reason == "policy_deny"


def test_same_membership_role_decides_identically_for_both_auth_modes() -> None:
    enforcer = _shipped().enforcer
    platform_role = membership_role_for_decision("platform", "TENANT_OWNER")
    tenant_local_role = membership_role_for_decision("tenant_local", "TENANT_OWNER")
    left = decide(enforcer, role=platform_role, domain=_DOMAIN_A, resource=_FUEL_RESOURCE, action="sync")
    right = decide(enforcer, role=tenant_local_role, domain=_DOMAIN_A, resource=_FUEL_RESOURCE, action="sync")
    assert left == right
    assert left.code is DecisionCode.ALLOW


def test_unknown_role_denies() -> None:
    decision = decide(
        _shipped().enforcer,
        role="DISPATCHER",
        domain=_DOMAIN_A,
        resource=_ADMIN_RESOURCE,
        action=_ADMIN_ACTION,
    )
    assert decision.code is DecisionCode.DENY
    assert decision.reason == "unknown_role"


def test_unknown_capability_is_unavailable() -> None:
    decision = decide(
        _shipped().enforcer,
        role="OWNER",
        domain=_DOMAIN_A,
        resource="loads",
        action="delete",
    )
    assert decision.code is DecisionCode.UNAVAILABLE
    assert decision.reason == "unknown_capability"


def test_wildcard_request_domain_is_denied() -> None:
    decision = decide(
        _shipped().enforcer,
        role="OWNER",
        domain="*",
        resource=_ADMIN_RESOURCE,
        action=_ADMIN_ACTION,
    )
    assert decision.code is DecisionCode.DENY
    assert decision.reason == "invalid_domain"


def test_specific_policy_domain_does_not_apply_to_another_tenant(tmp_path: Path) -> None:
    policy = _write_policy(
        tmp_path,
        "p, TENANT_ADMIN, 17, tenant.admin, access, allow\n",
    )
    enforcer = load_policy(MODEL_PATH, policy, shipped=False).enforcer
    allowed = decide(enforcer, role="TENANT_ADMIN", domain="17", resource=_ADMIN_RESOURCE, action=_ADMIN_ACTION)
    other_tenant = decide(
        enforcer, role="TENANT_ADMIN", domain="42", resource=_ADMIN_RESOURCE, action=_ADMIN_ACTION
    )
    assert allowed.code is DecisionCode.ALLOW
    assert other_tenant.code is DecisionCode.DENY
    assert other_tenant.reason == "policy_deny"


def test_missing_policy_file(tmp_path: Path) -> None:
    with pytest.raises(PolicyLoadError, match="policy file missing"):
        load_policy(MODEL_PATH, tmp_path / "absent.csv", shipped=False)


def test_malformed_policy_row(tmp_path: Path) -> None:
    policy = _write_policy(tmp_path, "p, OWNER, *, tenant.admin\n")
    with pytest.raises(PolicyLoadError, match="malformed policy row"):
        load_policy(MODEL_PATH, policy, shipped=False)


def test_policy_version_mismatch(tmp_path: Path) -> None:
    policy = _write_policy(tmp_path, "p, OWNER, *, tenant.admin, access, allow\n", version="99")
    with pytest.raises(PolicyLoadError, match="policy version"):
        load_policy(MODEL_PATH, policy, shipped=False)


def test_unknown_capability_in_policy_file(tmp_path: Path) -> None:
    policy = _write_policy(tmp_path, "p, OWNER, *, loads, delete, allow\n")
    with pytest.raises(PolicyLoadError, match="unknown capability"):
        load_policy(MODEL_PATH, policy, shipped=False)


def test_conflicting_allow_and_deny_denies(tmp_path: Path) -> None:
    policy = _write_policy(
        tmp_path,
        "\n".join(
            [
                "p, TENANT_ADMIN, *, tenant.admin, access, allow",
                "p, TENANT_ADMIN, *, tenant.admin, access, deny",
                "p, TENANT_ADMIN, *, fuel.providers, view, allow",
            ]
        )
        + "\n",
    )
    enforcer = load_policy(MODEL_PATH, policy, shipped=False).enforcer
    conflict = decide(enforcer, role="TENANT_ADMIN", domain="17", resource=_ADMIN_RESOURCE, action=_ADMIN_ACTION)
    fuel = decide(enforcer, role="TENANT_ADMIN", domain="17", resource=_FUEL_RESOURCE, action=_FUEL_ACTION)
    assert conflict.code is DecisionCode.DENY
    assert conflict.reason == "policy_deny"
    assert fuel.code is DecisionCode.ALLOW


def test_shipped_policy_rejects_a_deny_row(tmp_path: Path) -> None:
    text = POLICY_PATH.read_text(encoding="utf-8") + "p, OWNER, *, tenant.admin, access, deny\n"
    policy = tmp_path / "policy.csv"
    policy.write_text(text, encoding="utf-8")
    with pytest.raises(PolicyLoadError, match="allow rows only"):
        load_policy(MODEL_PATH, policy, shipped=True)


def test_unavailable_enforcer() -> None:
    decision = decide(None, role="OWNER", domain=_DOMAIN_A, resource=_ADMIN_RESOURCE, action=_ADMIN_ACTION)
    assert decision.code is DecisionCode.UNAVAILABLE
    assert decision.reason == "enforcer_unavailable"


def test_enforcer_exception_is_unavailable() -> None:
    class Broken:
        def enforce(self, *args: str) -> bool:
            raise RuntimeError("enforcer down")

    decision = decide(Broken(), role="OWNER", domain=_DOMAIN_A, resource=_ADMIN_RESOURCE, action=_ADMIN_ACTION)
    assert decision.code is DecisionCode.UNAVAILABLE
    assert decision.reason == "enforcer_error"


def test_unsupported_auth_mode_is_rejected() -> None:
    with pytest.raises(ValueError, match="unsupported auth mode"):
        membership_role_for_decision("jwt", "OWNER")


def test_membership_role_helper_does_not_transform_or_verify_identity() -> None:
    assert membership_role_for_decision("platform", "TENANT_ADMIN") == "TENANT_ADMIN"
    assert membership_role_for_decision("tenant_local", "TENANT_ADMIN") == "TENANT_ADMIN"
    assert membership_role_for_decision("platform", None) is None


@pytest.mark.parametrize("role", sorted(ADMIN_ROLES))
@pytest.mark.parametrize("resource,action", CAPABILITIES)
def test_each_admin_role_allows_every_registered_capability(role: str, resource: str, action: str) -> None:
    decision = decide(
        _shipped().enforcer,
        role=role,
        domain=_DOMAIN_A,
        resource=resource,
        action=action,
    )
    assert decision.code is DecisionCode.ALLOW
    assert decision.reason == "policy_allow"


@pytest.mark.parametrize("resource,action", CAPABILITIES)
def test_tenant_member_denied_every_registered_capability(resource: str, action: str) -> None:
    decision = decide(
        _shipped().enforcer,
        role="TENANT_MEMBER",
        domain=_DOMAIN_B,
        resource=resource,
        action=action,
    )
    assert decision.code is DecisionCode.DENY
    assert decision.reason == "policy_deny"


def _approved_model_text() -> str:
    return MODEL_PATH.read_text(encoding="utf-8")


def test_model_allows_comments_and_insignificant_whitespace(tmp_path: Path) -> None:
    model = tmp_path / "model.conf"
    model.write_text(
        "\n".join(
            [
                "# phase 0 model comment",
                "[request_definition]",
                "r   =   sub,   dom,   obj,   act",
                "",
                "; semicolon comment",
                "[policy_definition]",
                "p = sub, dom, obj, act, eft",
                "[policy_effect]",
                "e = some(where (p.eft == allow)) && !some(where (p.eft == deny))",
                "[matchers]",
                'm = r.sub == p.sub && (p.dom == "*" || r.dom == p.dom) && r.obj == p.obj && r.act == p.act',
                "",
            ]
        ),
        encoding="utf-8",
    )
    loaded = load_policy(model, POLICY_PATH, shipped=True)
    decision = decide(
        loaded.enforcer,
        role="ADMIN",
        domain=_DOMAIN_A,
        resource=_FUEL_RESOURCE,
        action=_FUEL_ACTION,
    )
    assert decision.code is DecisionCode.ALLOW


def test_unexpected_model_section_is_rejected(tmp_path: Path) -> None:
    model = tmp_path / "model.conf"
    model.write_text(
        _approved_model_text() + "\n[role_definition]\ng = _, _, _\n",
        encoding="utf-8",
    )
    policy = _write_policy(tmp_path, "p, OWNER, *, tenant.admin, access, allow\n")
    with pytest.raises(PolicyLoadError, match="unexpected model section"):
        load_policy(model, policy, shipped=False)


def test_additional_model_definition_is_rejected(tmp_path: Path) -> None:
    text = _approved_model_text().replace(
        "r = sub, dom, obj, act",
        "r = sub, dom, obj, act\nr2 = sub, dom, obj, act",
    )
    model = tmp_path / "model.conf"
    model.write_text(text, encoding="utf-8")
    policy = _write_policy(tmp_path, "p, OWNER, *, tenant.admin, access, allow\n")
    with pytest.raises(PolicyLoadError, match=r"\[request_definition\]"):
        load_policy(model, policy, shipped=False)


def test_changed_matcher_is_rejected(tmp_path: Path) -> None:
    text = _approved_model_text().replace(
        'm = r.sub == p.sub && (p.dom == "*" || r.dom == p.dom) && r.obj == p.obj && r.act == p.act',
        "m = r.sub == p.sub && r.obj == p.obj && r.act == p.act",
    )
    model = tmp_path / "model.conf"
    model.write_text(text, encoding="utf-8")
    policy = _write_policy(tmp_path, "p, OWNER, *, tenant.admin, access, allow\n")
    with pytest.raises(PolicyLoadError, match=r"\[matchers\]"):
        load_policy(model, policy, shipped=False)


def test_malformed_model_structure_is_rejected(tmp_path: Path) -> None:
    model = tmp_path / "model.conf"
    model.write_text("r = sub, dom, obj, act\n", encoding="utf-8")
    policy = _write_policy(tmp_path, "p, OWNER, *, tenant.admin, access, allow\n")
    with pytest.raises(PolicyLoadError, match="malformed model structure"):
        load_policy(model, policy, shipped=False)


def test_missing_model_file(tmp_path: Path) -> None:
    policy = _write_policy(tmp_path, "p, OWNER, *, tenant.admin, access, allow\n")
    with pytest.raises(PolicyLoadError, match="model file missing"):
        load_policy(tmp_path / "missing.conf", policy, shipped=False)


def test_invalid_utf8_policy_file(tmp_path: Path) -> None:
    policy = tmp_path / "policy.csv"
    policy.write_bytes(b"# policy_version: 1\n\xff\xfe\n")
    with pytest.raises(PolicyLoadError, match="not valid UTF-8"):
        load_policy(MODEL_PATH, policy, shipped=False)


def test_invalid_utf8_model_file(tmp_path: Path) -> None:
    model = tmp_path / "model.conf"
    model.write_bytes(b"\xff\xfe")
    policy = _write_policy(tmp_path, "p, OWNER, *, tenant.admin, access, allow\n")
    with pytest.raises(PolicyLoadError, match="not valid UTF-8"):
        load_policy(model, policy, shipped=False)


def test_unreadable_policy_file(tmp_path: Path) -> None:
    blocked = tmp_path / "policy.csv"
    blocked.mkdir()
    with pytest.raises(PolicyLoadError, match="unreadable"):
        load_policy(MODEL_PATH, blocked, shipped=False)


def test_cross_tenant_grants_do_not_cross_domains(tmp_path: Path) -> None:
    policy = _write_policy(
        tmp_path,
        "\n".join(
            [
                "p, OWNER, 17, fuel.providers, view, allow",
                "p, OWNER, 42, fuel.review, view, allow",
            ]
        )
        + "\n",
    )
    enforcer = load_policy(MODEL_PATH, policy, shipped=False).enforcer
    own_fuel = decide(enforcer, role="OWNER", domain="17", resource="fuel.providers", action="view")
    other_fuel = decide(enforcer, role="OWNER", domain="42", resource="fuel.providers", action="view")
    own_review = decide(enforcer, role="OWNER", domain="42", resource="fuel.review", action="view")
    other_review = decide(enforcer, role="OWNER", domain="17", resource="fuel.review", action="view")
    assert own_fuel.code is DecisionCode.ALLOW
    assert other_fuel.code is DecisionCode.DENY
    assert own_review.code is DecisionCode.ALLOW
    assert other_review.code is DecisionCode.DENY
