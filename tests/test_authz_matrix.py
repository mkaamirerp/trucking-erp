"""Decision matrix checks. Simulations only; no live HTTP calls."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.authz.catalog import CAPABILITIES
from app.authz.decision import DecisionCode, decide
from app.authz.prospective import load_prospective_policy
from app.authz.matrix import (
    EVIDENCE,
    MATRIX_ROLES,
    NO_EXPLICIT_ROLE_GATE,
    REPRESENTATIVE_ADMIN_ROLE,
    UNMAPPED_MODULES,
    _REPORT_PATH,
    _pair_outcome,
    _route_outcome_lines,
    build_matrix,
    entitlement_display,
    entitlement_names,
    render_decision_report,
    ungated_write_lines,
)
from app.authz.registry import ADMIN_ROLES, KNOWN_ROLES, OPERATIONAL_FULL_ACCESS_ROLE, TENANT_MEMBER_ROLE
from app.authz.routes import RouteBinding, binding_for
from app.authz.shadow import ExistingCode, ShadowCasbin, ShadowOutcome, ShadowPrincipal, evaluate_shadow
from app.deps.admin import is_tenant_admin

_REPORT = Path(__file__).resolve().parents[1] / "app" / "authz" / "DECISION_REPORT.md"


def test_matrix_covers_catalog_and_agrees_with_shadow() -> None:
    matrix = build_matrix()
    assert matrix.evidence == EVIDENCE
    pairs = {(spec.resource, spec.action) for spec in CAPABILITIES.values()}
    grouped: dict[tuple[str, str], dict[str, object]] = {}
    for cell in matrix.cells:
        assert cell.evidence == EVIDENCE
        assert cell.evidence != "live_request"
        grouped.setdefault(cell.pair, {})[cell.role] = cell
    assert set(grouped) == pairs
    for role_cells in grouped.values():
        assert set(role_cells) == set(MATRIX_ROLES)
        admins = [role_cells[role] for role in ADMIN_ROLES]
        assert len({(cell.existing_role_gate, cell.prospective, cell.status) for cell in admins}) == 1
        sample = next(iter(role_cells.values()))
        if sample.sample_route is None:
            continue
        if sample.status == "split":
            continue
        method, path = sample.sample_route.split(" ", 1)
        for role, cell in role_cells.items():
            assert cell.simulated_auth_modes == ("platform", "tenant_local")
            for mode in cell.simulated_auth_modes:
                shadow = evaluate_shadow(
                    ShadowPrincipal(mode, role, 17),
                    method=method,
                    path=path,
                    granted_entitlements=cell.granted_entitlements,
                )
                assert cell.existing_role_gate == shadow.existing.value
                assert cell.prospective == shadow.casbin.value
                assert cell.status == shadow.outcome.value


def test_pending_reads_do_not_deny_current_admin_access() -> None:
    matrix = build_matrix()
    people = _cell(matrix, "people.directory", "view", REPRESENTATIVE_ADMIN_ROLE)
    assert people.owner_approval_required is True
    assert people.existing_role_gate == ExistingCode.ALLOW.value
    assert people.prospective == ShadowCasbin.PENDING.value
    assert people.prospective != ShadowCasbin.DENY.value
    assert people.status == ShadowOutcome.PENDING_OWNER_APPROVAL.value
    payroll = _cell(matrix, "payroll.runs", "view", "TENANT_ADMIN")
    assert payroll.owner_approval_required is True
    assert payroll.prospective == ShadowCasbin.PENDING.value
    assert payroll.existing_role_gate == ExistingCode.UNKNOWN.value


def test_fuel_stays_admin_only_and_ungated_routes_stay_unknown() -> None:
    matrix = build_matrix()
    for role in (OPERATIONAL_FULL_ACCESS_ROLE, TENANT_MEMBER_ROLE):
        fuel = _cell(matrix, "fuel.providers", "view", role)
        assert fuel.existing_role_gate == ExistingCode.DENY.value
        assert fuel.prospective == ShadowCasbin.DENY.value
        assert fuel.status == ShadowOutcome.MATCH.value
    loads = _cell(matrix, "loads.records", "view", "OWNER")
    assert loads.contract == "ungated"
    assert loads.existing_role_gate == ExistingCode.UNKNOWN.value
    assert loads.existing_role_gate != ExistingCode.ALLOW.value
    assert loads.risk_label == NO_EXPLICIT_ROLE_GATE
    assert loads.status == ShadowOutcome.EXISTING_UNKNOWN.value
    assert ungated_write_lines()
    assert all("universally accessible" not in line for line in ungated_write_lines())


def test_operational_role_disagrees_with_live_admin_gate() -> None:
    matrix = build_matrix()
    cell = _cell(matrix, "people.directory", "manage", OPERATIONAL_FULL_ACCESS_ROLE)
    assert cell.existing_role_gate == ExistingCode.DENY.value
    assert cell.prospective == ShadowCasbin.ALLOW.value
    assert cell.status == ShadowOutcome.CONFLICT_EXISTING_DENY.value
    coarse = _cell(matrix, "tenant.admin", "access", "TENANT_ADMIN")
    assert coarse.sample_route is None
    assert coarse.existing_role_gate == ExistingCode.ALLOW.value
    assert is_tenant_admin("TENANT_ADMIN") is True
    decision = decide(
        load_prospective_policy().enforcer,
        role="TENANT_ADMIN",
        domain="17",
        resource="tenant.admin",
        action="access",
    )
    assert decision.code is DecisionCode.ALLOW
    assert coarse.prospective == ShadowCasbin.ALLOW.value
    assert coarse.status == ShadowOutcome.MATCH.value


def test_unresolved_list_and_report_are_owner_review_not_live_tests() -> None:
    matrix = build_matrix()
    topics = [item.topic for item in matrix.unresolved]
    assert topics == [
        "Operational access versus tenant administration",
        "People and Payroll sensitive reads",
        "Existing ungated operational routes",
        "Mixed route-level decisions",
        "Unmapped modules",
        "Load Integrity I5 hard deletion",
    ]
    text = " ".join(item.detail for item in matrix.unresolved)
    for name, _prefix in UNMAPPED_MODULES:
        assert name in text
    assert "LOAD_PHYSICAL_DELETE_TEMPORARILY_DISABLED" in text
    assert "hard-delete" not in text
    assert NO_EXPLICIT_ROLE_GATE in text
    assert "not a stored invite role" in matrix.unresolved[0].detail or "TENANT_ADMIN" in matrix.unresolved[0].detail
    report = render_decision_report(matrix)
    assert report == _REPORT.read_text(encoding="utf-8")
    assert _REPORT == _REPORT_PATH
    assert "not a live HTTP test" in report
    assert "not a denial of current admin access" in report
    assert "TENANT_MEMBER (READ_ONLY)" in report
    assert "simulations, not live requests" in report
    assert "Ungated writes" in report
    assert "people.directory/view" in report
    main = Path("app/main.py").read_text(encoding="utf-8")
    assert "authz.matrix" not in main


def test_mixed_entitlement_names_are_not_one_display_string() -> None:
    routes = (
        binding_for("GET", "/api/v1/admin/users"),
        binding_for("GET", "/api/v1/payroll/pay-runs"),
    )
    assert routes[0].entitlement == "admin_sensitive"
    assert routes[1].entitlement == "payroll"
    names = entitlement_names(routes)
    display = entitlement_display(names)
    assert names == frozenset({"admin_sensitive", "payroll"})
    assert display == "admin_sensitive, payroll"
    assert display not in names
    for route in routes:
        allowed = evaluate_shadow(
            ShadowPrincipal("platform", REPRESENTATIVE_ADMIN_ROLE, 17),
            method=route.method,
            path=route.path,
            granted_entitlements=names,
        )
        denied = evaluate_shadow(
            ShadowPrincipal("platform", REPRESENTATIVE_ADMIN_ROLE, 17),
            method=route.method,
            path=route.path,
            granted_entitlements=frozenset({display}),
        )
        assert allowed.existing_reason != "entitlement_denied"
        assert denied.existing_reason == "entitlement_denied"


def test_unknown_role_is_denied_and_is_not_a_stored_role() -> None:
    assert "DISPATCHER" not in KNOWN_ROLES
    assert "READ_ONLY" not in KNOWN_ROLES
    decision = decide(
        load_prospective_policy().enforcer,
        role="DISPATCHER",
        domain="17",
        resource="loads.records",
        action="view",
    )
    assert decision.code is DecisionCode.DENY
    assert decision.reason == "unknown_role"
    shadow = evaluate_shadow(
        ShadowPrincipal("tenant_local", "DISPATCHER", 17),
        method="GET",
        path="/api/v1/loads",
    )
    assert shadow.casbin is ShadowCasbin.DENY
    assert shadow.existing is ExistingCode.UNKNOWN


def test_pair_outcome_rejects_unsupported_combinations() -> None:
    with pytest.raises(ValueError, match="unsupported existing/casbin combination"):
        _pair_outcome("not-a-code", DecisionCode.ALLOW)


def test_split_route_lines_name_each_route_and_outcome() -> None:
    routes = (
        RouteBinding("POST", "/api/v1/example/a", "example", "loads.records", "create", "write", None),
        RouteBinding("GET", "/api/v1/example/b", "example", "loads.records", "view", "read", None),
    )
    left = evaluate_shadow(ShadowPrincipal("platform", "TENANT_ADMIN", 17), method="POST", path="/api/v1/loads")
    right = evaluate_shadow(ShadowPrincipal("platform", TENANT_MEMBER_ROLE, 17), method="POST", path="/api/v1/loads")
    lines = _route_outcome_lines(routes, (left, right))
    assert lines[0].startswith("POST /api/v1/example/a:")
    assert "existing unknown, prospective allow" in lines[0]
    assert lines[1].startswith("GET /api/v1/example/b:")
    assert "existing unknown, prospective deny" in lines[1]


def _cell(matrix, resource: str, action: str, role: str):
    for cell in matrix.cells:
        if cell.resource == resource and cell.action == action and cell.role == role:
            return cell
    raise AssertionError(f"missing {resource}/{action} for {role}")
