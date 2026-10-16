"""Disabled-by-default Loads pilot enforcement.

The dependency is a no-op unless ``casbin_load_pilot_enforcement`` is true.
It does not replace authentication, entitlements, or Load service rules.
"""

from __future__ import annotations

import threading
from typing import NoReturn

from fastapi import Depends, HTTPException

from app.authz.decision import DecisionCode, decide
from app.authz.loader import PolicyLoadError
from app.authz.prospective import load_prospective_policy
from app.authz.shadow import ShadowContextError, principal_from_member
from app.core.config import settings
from app.deps.auth import CurrentUser, get_current_user
from app.deps.tenant import require_tenant

PILOT_CAPABILITIES = frozenset(
    {
        ("loads.records", "view"),
        ("loads.records", "create"),
        ("loads.records", "update"),
    }
)


def pilot_enforcement_enabled() -> bool:
    return bool(settings.casbin_load_pilot_enforcement)


_pilot_enforcer: object | None = None
_pilot_enforcer_lock = threading.Lock()


def reset_pilot_policy_cache() -> None:
    """Drop the process cache. Tests call this so one case cannot leak into the next."""
    global _pilot_enforcer
    with _pilot_enforcer_lock:
        _pilot_enforcer = None


def get_pilot_enforcer() -> object:
    """Return the validated prospective enforcer for this process.

    The policy is loaded once. A missing or invalid policy raises PolicyLoadError
    and is not cached, so a later request still fails closed.
    """
    global _pilot_enforcer
    cached = _pilot_enforcer
    if cached is not None:
        return cached
    with _pilot_enforcer_lock:
        if _pilot_enforcer is not None:
            return _pilot_enforcer
        enforcer = _load_pilot_enforcer()
        _pilot_enforcer = enforcer
        return enforcer


def _load_pilot_enforcer() -> object:
    try:
        loaded = load_prospective_policy()
    except PolicyLoadError:
        raise
    except Exception as exc:
        raise PolicyLoadError("pilot policy failed to load") from exc
    if loaded.enforcer is None:
        raise PolicyLoadError("pilot enforcer missing")
    return loaded.enforcer


def require_pilot_capability(resource: str, action: str):
    """Authorize one pilot capability. Off: return the authenticated user unchanged."""

    async def _dep(
        user: CurrentUser = Depends(get_current_user),
        tenant_id: int = Depends(require_tenant),
    ) -> CurrentUser:
        if not pilot_enforcement_enabled():
            return user
        if (resource, action) not in PILOT_CAPABILITIES:
            _closed("AUTHZ_UNAVAILABLE", "capability_not_in_pilot")
        if int(tenant_id) != int(user.tenant_id):
            _closed("AUTHZ_FORBIDDEN", "cross_tenant")
        try:
            principal = principal_from_member(user)
        except ShadowContextError:
            _closed("AUTHZ_UNAVAILABLE", "unvalidated_membership")
        if principal.tenant_id != int(tenant_id):
            _closed("AUTHZ_FORBIDDEN", "cross_tenant")
        try:
            enforcer = get_pilot_enforcer()
        except PolicyLoadError:
            _closed("AUTHZ_UNAVAILABLE", "policy_load_failed")
        decision = decide(
            enforcer,
            role=principal.role,
            domain=str(principal.tenant_id),
            resource=resource,
            action=action,
        )
        if decision.code is DecisionCode.ALLOW:
            return user
        if decision.code is DecisionCode.UNAVAILABLE:
            _closed("AUTHZ_UNAVAILABLE", decision.reason)
        _closed("AUTHZ_FORBIDDEN", decision.reason)

    _dep.pilot_capability = (resource, action)  # type: ignore[attr-defined]
    return _dep


def _closed(code: str, reason: str) -> NoReturn:
    raise HTTPException(
        status_code=403,
        detail={"code": code, "reason": reason},
    )
