"""Explicit Phase 0 capability registry.

Names restate gates that already exist. They do not grant operational routes
that today have no role check, and they do not change Fuel's helper.
"""

from __future__ import annotations

# app/deps/admin.py TENANT_ADMIN_ROLES and FULL_ACCESS_ROLES are the same set.
ADMIN_ROLES: frozenset[str] = frozenset({"OWNER", "ADMIN", "TENANT_ADMIN", "TENANT_OWNER"})

# Request subject the future adapter may pass. Not a policy grant.
TENANT_MEMBER_ROLE = "TENANT_MEMBER"

KNOWN_ROLES: frozenset[str] = ADMIN_ROLES | {TENANT_MEMBER_ROLE}

# Categories B, E, F: is_tenant_admin / require_tenant_admin / People _require_admin.
# Categories C, D: has_full_access, including driver-document writes and user admin mutations.
# The two role sets are identical today; the objects stay separate so a later phase
# can split them without redefining the model.
ADMIN_CAPABILITIES: tuple[tuple[str, str], ...] = (
    ("tenant.admin", "access"),
    ("tenant.full_access", "access"),
)

# app/deps/fuel_rbac.py constants, split into resource + action.
# fuel.providers.view -> ("fuel.providers", "view"), and the same for the other seven.
FUEL_CAPABILITIES: tuple[tuple[str, str], ...] = (
    ("fuel.providers", "view"),
    ("fuel.providers", "manage"),
    ("fuel.providers", "test_connection"),
    ("fuel.providers", "sync"),
    ("fuel.review", "view"),
    ("fuel.review", "manage"),
    ("fuel.reconciliation", "view"),
    ("fuel.reconciliation", "run"),
)

CAPABILITIES: tuple[tuple[str, str], ...] = ADMIN_CAPABILITIES + FUEL_CAPABILITIES
CAPABILITY_SET: frozenset[tuple[str, str]] = frozenset(CAPABILITIES)

POLICY_VERSION = 1

AUTH_MODES: frozenset[str] = frozenset({"platform", "tenant_local"})
