"""Pure allow/deny decision. No request, JWT, database, or HTTP imports.

Phase 0 does not authenticate the caller. ``decide()`` receives a membership
role and a tenant domain that the caller claims are already validated.
``membership_role_for_decision()`` does not look up a user, membership row,
tenant, or token. It only labels which future auth mode supplied that role.
"""

from __future__ import annotations

from enum import Enum
from typing import Protocol

from app.authz.registry import AUTH_MODES, CAPABILITY_SET, KNOWN_ROLES


class DecisionCode(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    UNAVAILABLE = "unavailable"


class Decision:
    __slots__ = ("code", "reason")

    def __init__(self, code: DecisionCode, reason: str) -> None:
        self.code = code
        self.reason = reason

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Decision):
            return NotImplemented
        return self.code == other.code and self.reason == other.reason

    def __repr__(self) -> str:
        return f"Decision({self.code.value}, {self.reason})"


class Enforcer(Protocol):
    def enforce(self, *args: str) -> bool: ...


def membership_role_for_decision(auth_mode: str, membership_role: str | None) -> str | None:
    """Return the membership role a future adapter would pass into ``decide()``.

    This does not verify that the role belongs to a member, that the tenant
    domain is the request host, or that a JWT is valid. ``auth_mode`` is only
    the label ``platform`` or ``tenant_local``. Both labels return
    ``membership_role`` unchanged. Platform callers will eventually pass
    ``PlatformTenantMember.role``. Tenant-local callers will pass
    ``TenantWorkspaceMember.role``. The JWT ``roles`` claim is not an input.
    """
    if auth_mode not in AUTH_MODES:
        raise ValueError(f"unsupported auth mode: {auth_mode}")
    return membership_role


def _normalize_role(role: str | None) -> str:
    return (role or "").strip().upper()


def _valid_request_domain(domain: str) -> bool:
    # A request domain is one concrete tenant id. "*" is policy syntax, not a caller domain.
    return domain.isdigit() and not domain.startswith("0") and int(domain) >= 1


def decide(
    enforcer: Enforcer | None,
    *,
    role: str | None,
    domain: str,
    resource: str,
    action: str,
) -> Decision:
    """Decide a capability for an already validated role and tenant domain.

    ``role`` is the membership role string. ``domain`` is that tenant's id.
    Neither value is checked against a session, JWT, or database here.
    """
    if enforcer is None:
        return Decision(DecisionCode.UNAVAILABLE, "enforcer_unavailable")
    if (resource, action) not in CAPABILITY_SET:
        return Decision(DecisionCode.UNAVAILABLE, "unknown_capability")
    normalized = _normalize_role(role)
    if normalized not in KNOWN_ROLES:
        return Decision(DecisionCode.DENY, "unknown_role")
    if not isinstance(domain, str) or not _valid_request_domain(domain):
        return Decision(DecisionCode.DENY, "invalid_domain")
    try:
        allowed = enforcer.enforce(normalized, domain, resource, action)
    except Exception:
        return Decision(DecisionCode.UNAVAILABLE, "enforcer_error")
    if allowed is True:
        return Decision(DecisionCode.ALLOW, "policy_allow")
    if allowed is False:
        return Decision(DecisionCode.DENY, "policy_deny")
    return Decision(DecisionCode.UNAVAILABLE, "enforcer_error")
