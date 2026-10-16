"""Decision matrix checks. Simulations only; no live HTTP calls."""

from __future__ import annotations

from pathlib import Path

from app.authz.catalog import CAPABILITIES
from app.authz.decision import DecisionCode, decide
from app.authz.prospective import load_prospective_policy
from app.authz.matrix import (
    EVIDENCE,
    MATRIX_ROLES,
    UNMAPPED_MODULES,
    _REPORT_PATH,
    build_matrix,
    render_decision_report,
)
from app.authz.registry import ADMIN_ROLES, OPERATIONAL_FULL_ACCESS_ROLE, TENANT_MEMBER_ROLE
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
        method, path = sample.sample_route.split(" ", 1)
        granted = frozenset({sample.entitlement}) if sample.entitlement else None
        for role, cell in role_cells.items():
            shadow = evaluate_shadow(
                ShadowPrincipal("platform", role, 17),
                method=method,
                path=path,
                granted_entitlements=granted,
            )
            assert cell.existing_role_gate == shadow.existing.value
            assert cell.prospective == shadow.casbin.value
            assert cell.status == shadow.outcome.value


def test_pending_reads_do_not_deny_current_admin_access() -> None:
    matrix = build_matrix()
    people = _cell(matrix, "people.directory", "view", "OWNER")
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
    assert loads.status == ShadowOutcome.EXISTING_UNKNOWN.value


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
        "Unmapped modules",
        "Load Integrity I5 hard deletion",
    ]
    text = " ".join(item.detail for item in matrix.unresolved)
    for name, _prefix in UNMAPPED_MODULES:
        assert name in text
    assert "hard-delete" in text
    assert "not a stored invite role" in matrix.unresolved[0].detail or "TENANT_ADMIN" in matrix.unresolved[0].detail
    report = render_decision_report(matrix)
    assert report == _REPORT.read_text(encoding="utf-8")
    assert _REPORT == _REPORT_PATH
    assert "not a live HTTP test" in report
    assert "not a denial of current admin access" in report
    assert "people.directory/view" in report
    main = Path("app/main.py").read_text(encoding="utf-8")
    assert "authz.matrix" not in main


def _cell(matrix, resource: str, action: str, role: str):
    for cell in matrix.cells:
        if cell.resource == resource and cell.action == action and cell.role == role:
            return cell
    raise AssertionError(f"missing {resource}/{action} for {role}")
