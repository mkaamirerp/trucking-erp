"""Fuel capability names and backend enforcement (Segment 0A).

TEMPORARY reuse of existing tenant-admin enforcement. Capability strings are
checked by name so later granular Fuel RBAC can attach to the same gates, but
Segment 0A maps every `fuel.providers.*` check onto `is_tenant_admin`. This is
not fully granular Fuel RBAC and must not be described as such.

`fuel.imports.*` is documented in the Fuel plan as a future conceptual set.
Do not implement import permission gates in Segment 0A.

Hiding a UI button is not authorization. Backend must reject unauthorized
direct endpoint calls.
"""

from __future__ import annotations

from fastapi import Depends, HTTPException, status

from app.deps.admin import is_tenant_admin
from app.deps.auth import CurrentUser, get_current_user

FUEL_PROVIDERS_VIEW = "fuel.providers.view"
FUEL_PROVIDERS_MANAGE = "fuel.providers.manage"
FUEL_PROVIDERS_TEST_CONNECTION = "fuel.providers.test_connection"
FUEL_PROVIDERS_SYNC = "fuel.providers.sync"
FUEL_REVIEW_VIEW = "fuel.review.view"
FUEL_REVIEW_MANAGE = "fuel.review.manage"
FUEL_RECONCILIATION_VIEW = "fuel.reconciliation.view"
FUEL_RECONCILIATION_RUN = "fuel.reconciliation.run"

# Temporary: every Fuel provider/review/reconciliation capability currently
# requires tenant admin.
_ADMIN_CAPABILITIES = frozenset(
    {
        FUEL_PROVIDERS_VIEW,
        FUEL_PROVIDERS_MANAGE,
        FUEL_PROVIDERS_TEST_CONNECTION,
        FUEL_PROVIDERS_SYNC,
        FUEL_REVIEW_VIEW,
        FUEL_REVIEW_MANAGE,
        FUEL_RECONCILIATION_VIEW,
        FUEL_RECONCILIATION_RUN,
    }
)


def fuel_capability_allowed(role: str | None, capability: str) -> bool:
    if capability not in _ADMIN_CAPABILITIES:
        return False
    return is_tenant_admin(role)


def require_fuel_capability(capability: str):
    async def _dep(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if not fuel_capability_allowed(user.role, capability):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "FUEL_RBAC_FORBIDDEN",
                    "capability": capability,
                    "detail": "Not authorized for this Fuel action.",
                },
            )
        return user

    _dep.__name__ = f"require_{capability.replace('.', '_')}"
    return _dep
