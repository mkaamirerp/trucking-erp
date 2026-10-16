"""Tenant administration capabilities. Does not grant operational module permissions."""

from __future__ import annotations

from app.authz.spec import CapabilitySpec, ModuleCatalog

def _spec(resource: str, action: str, prospective: str, current_contract: str, *, shipped: bool = False, note: str = "") -> CapabilitySpec:
    return CapabilitySpec(
        "admin", resource, action, prospective, current_contract, shipped, note
    )


CATALOG = ModuleCatalog(
    module="admin",
    prefixes=("tenant.",),
    capabilities=(
        _spec("tenant.admin", "access", "admin", "admin", shipped=True, note="Current is_tenant_admin gate."),
        _spec(
            "tenant.full_access",
            "access",
            "admin",
            "full_access_same_as_admin",
            shipped=True,
            note="Current has_full_access gate. Same four roles as tenant admin today.",
        ),
        _spec("tenant.users", "list", "read", "member", note="GET /admin/users is documented for every member."),
        _spec("tenant.users", "invite", "admin", "full_access_same_as_admin"),
        _spec("tenant.users", "suspend", "admin", "full_access_same_as_admin"),
        _spec("tenant.users", "reactivate", "admin", "full_access_same_as_admin"),
        _spec("tenant.users", "resend_invite", "admin", "full_access_same_as_admin"),
        _spec("tenant.users", "remove", "admin", "full_access_same_as_admin"),
        _spec("tenant.users", "unlock_sign_in", "admin", "full_access_same_as_admin"),
        _spec("tenant.signin_security", "view", "read", "member"),
        _spec("tenant.company", "view", "admin", "admin"),
        _spec("tenant.company", "manage", "admin", "admin"),
        _spec("tenant.broker_intake", "view", "admin", "admin"),
        _spec("tenant.broker_intake", "manage", "admin", "admin"),
    ),
)
