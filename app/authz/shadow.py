"""Non-enforcing comparison of live gates and the prospective Casbin policy.

Call ``evaluate_shadow`` from tests or a development harness only.
Do not import this module from application startup or route dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from app.authz.catalog import CAPABILITIES
from app.authz.decision import DecisionCode, decide, membership_role_for_decision
from app.authz.loader import PolicyLoadError
from app.authz.prospective import load_prospective_policy
from app.authz.routes import RouteBinding, binding_for
from app.deps.admin import has_full_access, is_tenant_admin
from app.deps.fuel_rbac import fuel_capability_allowed
from app.services.tenant_auth_constants import tenant_uses_tenant_db_auth

_PROSPECTIVE = object()


class ShadowContextError(ValueError):
    """The caller did not supply a membership role resolved by authentication."""


class ExistingCode(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    UNKNOWN = "unknown"


class ShadowCasbin(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    UNAVAILABLE = "unavailable"
    PENDING = "pending"


class ShadowOutcome(str, Enum):
    MATCH = "match"
    CONFLICT_EXISTING_ALLOW = "conflict_existing_allow_prospective_deny"
    CONFLICT_EXISTING_DENY = "conflict_existing_deny_prospective_allow"
    EXISTING_UNKNOWN = "existing_unknown"
    CASBIN_UNAVAILABLE = "casbin_unavailable"
    PENDING_OWNER_APPROVAL = "pending_owner_approval"
    UNMAPPED = "unmapped"
    CROSS_TENANT = "cross_tenant"
    UNRESOLVED_DOMAIN_POLICY = "unresolved_domain_policy"


@dataclass(frozen=True)
class ShadowPrincipal:
    """Membership role and tenant id already resolved by authentication."""

    auth_mode: str
    role: str | None
    tenant_id: int


@dataclass(frozen=True)
class ShadowResult:
    outcome: ShadowOutcome
    existing: ExistingCode
    existing_reason: str
    casbin: ShadowCasbin
    casbin_reason: str
    auth_mode: str
    role: str | None
    tenant_id: int
    method: str
    path: str
    resource: str | None
    action: str | None
    note: str = ""


def principal_from_member(member: Any) -> ShadowPrincipal:
    """Read the role and tenant already stored on an authenticated member.

    Platform mode uses ``PlatformTenantMember.role`` via ``CurrentUser.role``.
    Tenant-local mode uses ``TenantWorkspaceMember.role`` via the same field,
    and requires the tenant-local user object authentication attaches.
    This function does not read a request body or a JWT claim.
    """
    tenant = getattr(member, "tenant", None)
    if tenant is None or not hasattr(member, "role") or not hasattr(member, "tenant_user"):
        raise ShadowContextError("missing trusted membership fields")
    tenant_id = getattr(member, "tenant_id", None)
    if tenant_id is None:
        tenant_id = getattr(tenant, "id", None)
    try:
        tenant_id_int = int(tenant_id)
    except (TypeError, ValueError):
        raise ShadowContextError("tenant id is not a validated integer") from None
    if tenant_id_int < 1:
        raise ShadowContextError("tenant id is not a validated integer")
    raw_mode = getattr(tenant, "tenant_auth_mode", None) or "platform"
    if tenant_uses_tenant_db_auth(raw_mode):
        auth_mode = "tenant_local"
        if getattr(member, "tenant_user", None) is None:
            raise ShadowContextError(
                "tenant-local role was not loaded from TenantWorkspaceMember"
            )
    elif str(raw_mode).lower() == "platform":
        auth_mode = "platform"
        if getattr(member, "tenant_user", None) is not None:
            raise ShadowContextError(
                "platform mode cannot use a tenant-local user as the role source"
            )
    else:
        raise ShadowContextError(f"unsupported auth mode: {raw_mode}")
    role = membership_role_for_decision(auth_mode, getattr(member, "role", None))
    return ShadowPrincipal(auth_mode=auth_mode, role=role, tenant_id=tenant_id_int)


def evaluate_shadow(
    principal: ShadowPrincipal,
    *,
    method: str,
    path: str,
    granted_entitlements: frozenset[str] | None = None,
    requested_tenant_id: int | None = None,
    enforcer: object | None = _PROSPECTIVE,
) -> ShadowResult:
    """Compare one route. Does not change authorization and does not query a database."""
    if requested_tenant_id is not None and int(requested_tenant_id) != principal.tenant_id:
        return _result(
            principal,
            method,
            path,
            None,
            ExistingCode.DENY,
            "cross_tenant",
            ShadowCasbin.DENY,
            "cross_tenant",
            ShadowOutcome.CROSS_TENANT,
        )
    binding = _binding(method, path)
    if binding is None:
        return _result(
            principal,
            method,
            path,
            None,
            ExistingCode.UNKNOWN,
            "unmapped",
            ShadowCasbin.UNAVAILABLE,
            "unmapped",
            ShadowOutcome.UNMAPPED,
        )
    existing, existing_reason = _existing(principal, binding, granted_entitlements)
    if binding.kind == "domain_policy_unresolved":
        return _result(
            principal,
            method,
            path,
            binding,
            existing,
            existing_reason,
            ShadowCasbin.UNAVAILABLE,
            "no_delete_grant",
            ShadowOutcome.UNRESOLVED_DOMAIN_POLICY,
        )
    spec = CAPABILITIES.get(binding.pair) if binding.pair else None
    if spec is not None and spec.enforcement_approval == "owner_required":
        return _result(
            principal,
            method,
            path,
            binding,
            existing,
            existing_reason,
            ShadowCasbin.PENDING,
            "owner_required",
            ShadowOutcome.PENDING_OWNER_APPROVAL,
        )
    casbin, casbin_reason = _casbin(principal, binding, _resolve_enforcer(enforcer))
    return _result(
        principal,
        method,
        path,
        binding,
        existing,
        existing_reason,
        casbin,
        casbin_reason,
        _outcome(existing, casbin),
    )


def _binding(method: str, path: str) -> RouteBinding | None:
    try:
        return binding_for(method, path)
    except KeyError:
        return None


def _resolve_enforcer(enforcer: object | None) -> object | None:
    if enforcer is not _PROSPECTIVE:
        return enforcer
    try:
        return load_prospective_policy().enforcer
    except PolicyLoadError:
        return None


def _existing(
    principal: ShadowPrincipal,
    binding: RouteBinding,
    granted_entitlements: frozenset[str] | None,
) -> tuple[ExistingCode, str]:
    if binding.kind == "domain_policy_unresolved":
        return ExistingCode.UNKNOWN, "load_integrity_unresolved"
    if binding.kind == "not_a_grant":
        return ExistingCode.DENY, "handler_rejects"
    if binding.kind == "infrastructure":
        return ExistingCode.UNKNOWN, "not_a_membership_gate"
    if (
        binding.entitlement
        and granted_entitlements is not None
        and binding.entitlement not in granted_entitlements
    ):
        return ExistingCode.DENY, "entitlement_denied"
    if binding.kind == "self_service":
        if not (principal.role or "").strip():
            return ExistingCode.UNKNOWN, "missing_role"
        return ExistingCode.ALLOW, "authenticated_self_service"
    spec = CAPABILITIES.get(binding.pair) if binding.pair else None
    if spec is None:
        return ExistingCode.UNKNOWN, "no_capability"
    role_code, role_reason = _role_gate(principal.role, spec.module, spec.resource, spec.action, spec.current_contract)
    if role_code is not ExistingCode.ALLOW:
        return role_code, role_reason
    if binding.entitlement and granted_entitlements is None:
        return ExistingCode.UNKNOWN, "entitlement_unknown"
    return role_code, role_reason


def _role_gate(
    role: str | None,
    module: str,
    resource: str,
    action: str,
    contract: str,
) -> tuple[ExistingCode, str]:
    if contract == "admin":
        if module == "fuel":
            allowed = fuel_capability_allowed(role, f"{resource}.{action}")
            return (ExistingCode.ALLOW if allowed else ExistingCode.DENY), "fuel_admin_only"
        return (ExistingCode.ALLOW if is_tenant_admin(role) else ExistingCode.DENY), "tenant_admin"
    if contract == "full_access_same_as_admin":
        return (ExistingCode.ALLOW if has_full_access(role) else ExistingCode.DENY), "full_access"
    if contract == "member":
        if not (role or "").strip():
            return ExistingCode.UNKNOWN, "missing_role"
        return ExistingCode.ALLOW, "active_member"
    if contract == "ungated":
        return ExistingCode.UNKNOWN, "no_role_gate"
    return ExistingCode.UNKNOWN, "unclassified_contract"


def _casbin(
    principal: ShadowPrincipal,
    binding: RouteBinding,
    enforcer: object | None,
) -> tuple[ShadowCasbin, str]:
    if binding.pair is None:
        return ShadowCasbin.UNAVAILABLE, "no_capability"
    resource, action = binding.pair
    decision = decide(
        enforcer,  # type: ignore[arg-type]
        role=membership_role_for_decision(principal.auth_mode, principal.role),
        domain=str(principal.tenant_id),
        resource=resource,
        action=action,
    )
    if decision.code is DecisionCode.ALLOW:
        return ShadowCasbin.ALLOW, decision.reason
    if decision.code is DecisionCode.DENY:
        return ShadowCasbin.DENY, decision.reason
    return ShadowCasbin.UNAVAILABLE, decision.reason


def _outcome(existing: ExistingCode, casbin: ShadowCasbin) -> ShadowOutcome:
    if casbin is ShadowCasbin.UNAVAILABLE:
        return ShadowOutcome.CASBIN_UNAVAILABLE
    if existing is ExistingCode.UNKNOWN:
        return ShadowOutcome.EXISTING_UNKNOWN
    if existing is ExistingCode.ALLOW and casbin is ShadowCasbin.ALLOW:
        return ShadowOutcome.MATCH
    if existing is ExistingCode.DENY and casbin is ShadowCasbin.DENY:
        return ShadowOutcome.MATCH
    if existing is ExistingCode.ALLOW and casbin is ShadowCasbin.DENY:
        return ShadowOutcome.CONFLICT_EXISTING_ALLOW
    if existing is ExistingCode.DENY and casbin is ShadowCasbin.ALLOW:
        return ShadowOutcome.CONFLICT_EXISTING_DENY
    return ShadowOutcome.CASBIN_UNAVAILABLE


def _result(
    principal: ShadowPrincipal,
    method: str,
    path: str,
    binding: RouteBinding | None,
    existing: ExistingCode,
    existing_reason: str,
    casbin: ShadowCasbin,
    casbin_reason: str,
    outcome: ShadowOutcome,
) -> ShadowResult:
    return ShadowResult(
        outcome=outcome,
        existing=existing,
        existing_reason=existing_reason,
        casbin=casbin,
        casbin_reason=casbin_reason,
        auth_mode=principal.auth_mode,
        role=principal.role,
        tenant_id=principal.tenant_id,
        method=method.upper(),
        path=path,
        resource=binding.resource if binding else None,
        action=binding.action if binding else None,
        note=binding.note if binding else "",
    )
