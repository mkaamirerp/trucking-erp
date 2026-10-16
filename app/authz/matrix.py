"""Simulated permission decision matrix. Not a live request test and not enforcement."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.authz.catalog import CAPABILITIES
from app.authz.decision import DecisionCode, decide, membership_role_for_decision
from app.authz.prospective import load_prospective_policy
from app.authz.registry import ADMIN_ROLES, OPERATIONAL_FULL_ACCESS_ROLE, TENANT_MEMBER_ROLE
from app.authz.routes import ROUTE_BINDINGS, RouteBinding
from app.authz.shadow import (
    ExistingCode,
    ShadowCasbin,
    ShadowOutcome,
    ShadowPrincipal,
    evaluate_shadow,
)
from app.authz.spec import CapabilitySpec
from app.deps.admin import has_full_access, is_tenant_admin
from app.deps.fuel_rbac import fuel_capability_allowed

EVIDENCE = "simulated_role_gate"
NO_EXPLICIT_ROLE_GATE = "NO_EXPLICIT_ROLE_GATE"
_SIMULATED_TENANT_ID = 17
_AUTH_MODES = ("platform", "tenant_local")
_WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

# Admin subjects come from the registry. Invite mapping stays in access_level_to_role.
MATRIX_ROLES: tuple[str, ...] = tuple(sorted(ADMIN_ROLES)) + (
    OPERATIONAL_FULL_ACCESS_ROLE,
    TENANT_MEMBER_ROLE,
)
REPRESENTATIVE_ADMIN_ROLE = next(iter(sorted(ADMIN_ROLES)))

# Registered business areas that the catalog intentionally does not map yet.
UNMAPPED_MODULES: tuple[tuple[str, str], ...] = (
    ("brokers", "/api/v1/brokers"),
    ("customs_brokers", "/api/v1/customs-brokers"),
    ("terminals", "/api/v1/terminals"),
    ("load_lab", "/api/v1/load-lab"),
    ("email_intake", "/api/v1/email-threads"),
)

_REPORT_PATH = Path(__file__).resolve().parent / "DECISION_REPORT.md"


@dataclass(frozen=True)
class MatrixCell:
    module: str
    resource: str
    action: str
    role: str
    contract: str
    existing_role_gate: str
    existing_reason: str
    prospective: str
    entitlement: str | None
    granted_entitlements: frozenset[str] | None
    status: str
    owner_approval_required: bool
    evidence: str
    sample_route: str | None
    risk_label: str | None = None
    simulated_auth_modes: tuple[str, ...] = _AUTH_MODES
    route_outcomes: tuple[str, ...] = ()

    @property
    def pair(self) -> tuple[str, str]:
        return (self.resource, self.action)


@dataclass(frozen=True)
class UnresolvedDecision:
    topic: str
    detail: str


@dataclass(frozen=True)
class DecisionMatrix:
    cells: tuple[MatrixCell, ...]
    unresolved: tuple[UnresolvedDecision, ...]
    evidence: str


def build_matrix(enforcer: object | None = None) -> DecisionMatrix:
    """Compare catalog capabilities with simulated role gates and the prospective policy."""
    if enforcer is None:
        enforcer = load_prospective_policy().enforcer
    by_pair: dict[tuple[str, str], list[RouteBinding]] = {}
    for binding in ROUTE_BINDINGS.values():
        if binding.pair is None:
            continue
        by_pair.setdefault(binding.pair, []).append(binding)
    cells: list[MatrixCell] = []
    for spec in CAPABILITIES.values():
        routes = tuple(sorted(by_pair.get(spec.pair, []), key=lambda row: (row.method, row.path)))
        granted = entitlement_names(routes)
        entitlement = entitlement_display(granted)
        for role in MATRIX_ROLES:
            cells.append(_cell(spec, role, routes, entitlement, granted, enforcer))
    return DecisionMatrix(
        cells=tuple(cells),
        unresolved=_unresolved(tuple(cells)),
        evidence=EVIDENCE,
    )


def render_decision_report(matrix: DecisionMatrix | None = None) -> str:
    """Concise owner report. Every result is a simulation."""
    matrix = matrix or build_matrix()
    lines = [
        "# Casbin permission decision report",
        "",
        "Simulated role-gate comparison for owner review. This is not a live HTTP test,",
        "and it does not change authentication, entitlements, or route behavior.",
        "",
        "Each cell is `existing role gate → prospective Casbin (status)`.",
        "The existing side assumes each listed entitlement name is granted.",
        "The entitlement column is a display string. It is not itself an entitlement name.",
        "A missing subscription can still deny the live route.",
        "`pending` means owner approval is required. It is not a denial of current admin access.",
        "`OPERATIONAL_FULL_ACCESS` is not a stored invite role.",
        "`TENANT_MEMBER (READ_ONLY)` is the stored membership for a READ_ONLY invite.",
        "READ_ONLY is not a separate role and not a Casbin subject.",
        "Every cell simulates platform and tenant-local membership resolution.",
        "Those results are simulations, not live requests.",
        f"`{NO_EXPLICIT_ROLE_GATE}` means no explicit membership role gate was found.",
        "The existing decision stays UNKNOWN. Other protections may still apply.",
        "The label is not evidence that a route is universally accessible.",
        "",
        "## Unresolved decisions",
        "",
    ]
    for index, item in enumerate(matrix.unresolved, start=1):
        lines.append(f"{index}. **{item.topic}.** {item.detail}")
    writes = ungated_write_lines()
    lines.extend(
        [
            "",
            "## Ungated writes",
            "",
            f"Risk label `{NO_EXPLICIT_ROLE_GATE}`.",
            "These write routes have no explicit membership role gate in the simulation.",
            "The existing decision stays UNKNOWN.",
            "Authentication, tenant isolation, entitlements, or domain rules may still apply.",
            "This list is not evidence that the routes are universally accessible.",
            "",
        ]
    )
    lines.extend(f"- {line}" for line in writes)
    lines.extend(["", "## Matrix", ""])
    modules: list[str] = []
    for cell in matrix.cells:
        if cell.module not in modules:
            modules.append(cell.module)
    for module in modules:
        lines.extend(_module_table(matrix, module))
    lines.append("")
    return "\n".join(lines)


def write_decision_report(path: Path | None = None) -> Path:
    target = path or _REPORT_PATH
    target.write_text(render_decision_report(), encoding="utf-8")
    return target


def _cell(
    spec: CapabilitySpec,
    role: str,
    routes: tuple[RouteBinding, ...],
    entitlement: str | None,
    granted: frozenset[str] | None,
    enforcer: object,
) -> MatrixCell:
    if not routes:
        return _catalog_only_cell(spec, role, enforcer)
    results, split_reason = _simulate_routes(role, routes, granted, enforcer)
    route_outcomes = _route_outcome_lines(routes, results) if split_reason else ()
    first = results[0]
    if split_reason:
        status = "split"
        prospective = "split"
        existing = "split"
        reason = split_reason
    else:
        status = first.outcome.value
        prospective = first.casbin.value
        existing = first.existing.value
        reason = first.existing_reason
    sample = routes[0]
    return MatrixCell(
        module=spec.module,
        resource=spec.resource,
        action=spec.action,
        role=role,
        contract=spec.current_contract,
        existing_role_gate=existing,
        existing_reason=reason,
        prospective=prospective,
        entitlement=entitlement,
        granted_entitlements=granted,
        status=status,
        owner_approval_required=spec.enforcement_approval == "owner_required",
        evidence=EVIDENCE,
        sample_route=f"{sample.method} {sample.path}",
        risk_label=NO_EXPLICIT_ROLE_GATE if reason == "no_role_gate" or (split_reason and first.existing_reason == "no_role_gate") else None,
        route_outcomes=route_outcomes,
    )


def _catalog_only_cell(spec: CapabilitySpec, role: str, enforcer: object) -> MatrixCell:
    """Coarse capability with no HTTP binding. Still simulated, still not a live test."""
    existing, reason = _catalog_role_gate(role, spec)
    if spec.enforcement_approval == "owner_required":
        prospective = ShadowCasbin.PENDING.value
        status = ShadowOutcome.PENDING_OWNER_APPROVAL.value
    else:
        decisions = [
            decide(
                enforcer,  # type: ignore[arg-type]
                role=membership_role_for_decision(mode, role),
                domain=str(_SIMULATED_TENANT_ID),
                resource=spec.resource,
                action=spec.action,
            )
            for mode in _AUTH_MODES
        ]
        if any(item.code is not decisions[0].code for item in decisions[1:]):
            raise ValueError(f"auth modes disagree for {spec.resource}/{spec.action} {role}")
        prospective, status = _pair_outcome(existing, decisions[0].code)
    return MatrixCell(
        module=spec.module,
        resource=spec.resource,
        action=spec.action,
        role=role,
        contract=spec.current_contract,
        existing_role_gate=existing,
        existing_reason=reason,
        prospective=prospective,
        entitlement=None,
        granted_entitlements=None,
        status=status,
        owner_approval_required=spec.enforcement_approval == "owner_required",
        evidence=EVIDENCE,
        sample_route=None,
        risk_label=NO_EXPLICIT_ROLE_GATE if reason == "no_role_gate" else None,
    )


def _catalog_role_gate(role: str | None, spec: CapabilitySpec) -> tuple[str, str]:
    if spec.current_contract == "admin":
        if spec.module == "fuel":
            allowed = fuel_capability_allowed(role, f"{spec.resource}.{spec.action}")
            code = ExistingCode.ALLOW if allowed else ExistingCode.DENY
            return code.value, "fuel_admin_only"
        code = ExistingCode.ALLOW if is_tenant_admin(role) else ExistingCode.DENY
        return code.value, "tenant_admin"
    if spec.current_contract == "full_access_same_as_admin":
        code = ExistingCode.ALLOW if has_full_access(role) else ExistingCode.DENY
        return code.value, "full_access"
    if spec.current_contract == "ungated":
        return ExistingCode.UNKNOWN.value, "no_role_gate"
    if spec.current_contract == "member":
        if not (role or "").strip():
            return ExistingCode.UNKNOWN.value, "missing_role"
        return ExistingCode.ALLOW.value, "active_member"
    return ExistingCode.UNKNOWN.value, "unclassified_contract"


def _pair_outcome(existing: str, casbin_code: DecisionCode) -> tuple[str, str]:
    if casbin_code is DecisionCode.UNAVAILABLE:
        return ShadowCasbin.UNAVAILABLE.value, ShadowOutcome.CASBIN_UNAVAILABLE.value
    prospective = ShadowCasbin.ALLOW.value if casbin_code is DecisionCode.ALLOW else ShadowCasbin.DENY.value
    if existing == ExistingCode.UNKNOWN.value:
        return prospective, ShadowOutcome.EXISTING_UNKNOWN.value
    if existing == ExistingCode.ALLOW.value and prospective == ShadowCasbin.ALLOW.value:
        return prospective, ShadowOutcome.MATCH.value
    if existing == ExistingCode.DENY.value and prospective == ShadowCasbin.DENY.value:
        return prospective, ShadowOutcome.MATCH.value
    if existing == ExistingCode.ALLOW.value and prospective == ShadowCasbin.DENY.value:
        return prospective, ShadowOutcome.CONFLICT_EXISTING_ALLOW.value
    if existing == ExistingCode.DENY.value and prospective == ShadowCasbin.ALLOW.value:
        return prospective, ShadowOutcome.CONFLICT_EXISTING_DENY.value
    raise ValueError(
        f"unsupported existing/casbin combination: {existing} / {casbin_code.value}"
    )


def entitlement_names(routes: tuple[RouteBinding, ...]) -> frozenset[str] | None:
    """Individual entitlement names. None when the routes declare none."""
    names = frozenset(route.entitlement for route in routes if route.entitlement)
    return names or None


def entitlement_display(names: frozenset[str] | None) -> str | None:
    """Readable list. Not a value to pass to evaluate_shadow()."""
    if not names:
        return None
    return ", ".join(sorted(names))


def _simulate_routes(
    role: str,
    routes: tuple[RouteBinding, ...],
    granted: frozenset[str] | None,
    enforcer: object,
) -> tuple[tuple, str | None]:
    by_mode = {
        mode: tuple(
            evaluate_shadow(
                ShadowPrincipal(mode, role, _SIMULATED_TENANT_ID),
                method=route.method,
                path=route.path,
                granted_entitlements=granted,
                enforcer=enforcer,
            )
            for route in routes
        )
        for mode in _AUTH_MODES
    }
    platform_results = by_mode["platform"]
    if any(_shadow_signature(left) != _shadow_signature(right) for left, right in zip(platform_results, by_mode["tenant_local"])):
        return platform_results, "auth_modes_disagree"
    if len({_shadow_signature(row) for row in platform_results}) > 1:
        return platform_results, "routes_disagree"
    return platform_results, None


def _shadow_signature(result: object) -> tuple[str, str, str]:
    return (result.existing.value, result.casbin.value, result.outcome.value)  # type: ignore[attr-defined]


def _route_outcome_lines(routes: tuple[RouteBinding, ...], results: tuple) -> tuple[str, ...]:
    return tuple(
        f"{route.method} {route.path}: existing {result.existing.value}, "
        f"prospective {result.casbin.value}, {result.outcome.value}"
        for route, result in zip(routes, results)
    )


def _unresolved(cells: tuple[MatrixCell, ...]) -> tuple[UnresolvedDecision, ...]:
    operational = sorted(
        {
            f"{cell.resource}/{cell.action}"
            for cell in cells
            if cell.role == OPERATIONAL_FULL_ACCESS_ROLE
            and cell.status == ShadowOutcome.CONFLICT_EXISTING_DENY.value
        }
    )
    pending = sorted(
        {
            f"{cell.resource}/{cell.action}"
            for cell in cells
            if cell.owner_approval_required and cell.role == REPRESENTATIVE_ADMIN_ROLE
        }
    )
    ungated = sorted(
        {
            f"{cell.resource}/{cell.action}"
            for cell in cells
            if cell.contract == "ungated" and cell.role == TENANT_MEMBER_ROLE
        }
    )
    admin_pending_allows = sorted(
        {
            f"{cell.resource}/{cell.action}"
            for cell in cells
            if cell.owner_approval_required
            and cell.role == REPRESENTATIVE_ADMIN_ROLE
            and cell.contract in {"admin", "full_access_same_as_admin"}
            and cell.existing_role_gate == ExistingCode.ALLOW.value
        }
    )
    load_delete = next(
        (f"{binding.method} {binding.path}" for binding in ROUTE_BINDINGS.values() if binding.kind == "domain_policy_unresolved"),
        "DELETE /api/v1/loads/{load_id}",
    )
    unmapped = ", ".join(f"{name} ({prefix})" for name, prefix in UNMAPPED_MODULES)
    splits = [
        f"{cell.resource}/{cell.action} for {cell.role}: " + "; ".join(cell.route_outcomes)
        for cell in cells
        if cell.status == "split"
    ]
    split_detail = (
        "No capability currently has routes with different simulated outcomes."
        if not splits
        else "Routes under one capability do not share one outcome. " + " | ".join(splits)
    )
    return (
        UnresolvedDecision(
            "Operational access versus tenant administration",
            "FULL_ACCESS invites still store TENANT_ADMIN. "
            f"OPERATIONAL_FULL_ACCESS is simulated only. Live admin gates deny it where the prospective policy would allow: {', '.join(operational)}.",
        ),
        UnresolvedDecision(
            "People and Payroll sensitive reads",
            "These reads stay pending and are not approved denials. "
            f"Current admin role gates that remain allow: {', '.join(admin_pending_allows) or 'none'}. "
            f"All pending reads: {', '.join(pending)}.",
        ),
        UnresolvedDecision(
            "Existing ungated operational routes",
            "No live role gate exists, so the existing side stays UNKNOWN rather than allow. "
            f"Risk label {NO_EXPLICIT_ROLE_GATE}. Other protections may still apply. "
            "This is not evidence that the routes are universally accessible. "
            f"Capabilities: {', '.join(ungated)}.",
        ),
        UnresolvedDecision(
            "Mixed route-level decisions",
            split_detail,
        ),
        UnresolvedDecision(
            "Unmapped modules",
            f"Not in the capability catalog: {unmapped}.",
        ),
        UnresolvedDecision(
            "Load Integrity I5 hard deletion",
            f"{load_delete} does not physically delete an existing Load on current main. "
            "The Load service returns 409 LOAD_PHYSICAL_DELETE_TEMPORARILY_DISABLED. "
            "Casbin has no delete grant. The domain policy remains unresolved.",
        ),
    )


def ungated_write_lines() -> tuple[str, ...]:
    lines: list[str] = []
    for binding in ROUTE_BINDINGS.values():
        if binding.method not in _WRITE_METHODS or binding.pair is None:
            continue
        spec = CAPABILITIES.get(binding.pair)
        if spec is None or spec.current_contract != "ungated":
            continue
        lines.append(f"{binding.method} {binding.path} ({spec.resource}/{spec.action})")
    return tuple(sorted(lines))


def _module_table(matrix: DecisionMatrix, module: str) -> list[str]:
    lines = [
        f"### {module}",
        "",
        "| Capability | Contract | Entitlement | Approval | Admin roles | Operational | TENANT_MEMBER (READ_ONLY) |",
        "|---|---|---|---|---|---|---|",
    ]
    seen: list[tuple[str, str]] = []
    for cell in matrix.cells:
        if cell.module == module and cell.pair not in seen:
            seen.append(cell.pair)
    for pair in seen:
        role_cells = {
            cell.role: cell
            for cell in matrix.cells
            if cell.module == module and cell.pair == pair
        }
        sample = role_cells[REPRESENTATIVE_ADMIN_ROLE]
        lines.append(
            "| {cap} | {contract} | {entitlement} | {approval} | {admin} | {operational} | {member} |".format(
                cap=f"{pair[0]}/{pair[1]}",
                contract=sample.contract,
                entitlement=sample.entitlement or "none",
                approval="required" if sample.owner_approval_required else "no",
                admin=_admin_cell(role_cells),
                operational=_fmt(role_cells[OPERATIONAL_FULL_ACCESS_ROLE]),
                member=_fmt(role_cells[TENANT_MEMBER_ROLE]),
            )
        )
    lines.append("")
    return lines


def _admin_cell(role_cells: dict[str, MatrixCell]) -> str:
    admins = [role_cells[role] for role in sorted(ADMIN_ROLES)]
    first = _fmt(admins[0])
    if all(_fmt(cell) == first for cell in admins[1:]):
        return first
    return "roles differ"


def _fmt(cell: MatrixCell) -> str:
    return f"{cell.existing_role_gate} → {cell.prospective} ({_status_label(cell.status)})"


def _status_label(status: str) -> str:
    labels = {
        ShadowOutcome.MATCH.value: "match",
        ShadowOutcome.EXISTING_UNKNOWN.value: "unknown",
        ShadowOutcome.CONFLICT_EXISTING_ALLOW.value: "disagreement",
        ShadowOutcome.CONFLICT_EXISTING_DENY.value: "disagreement",
        ShadowOutcome.PENDING_OWNER_APPROVAL.value: "pending",
        ShadowOutcome.CASBIN_UNAVAILABLE.value: "unavailable",
    }
    return labels.get(status, status)
