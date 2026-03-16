"""Centralized tenant admin access. Temporary until RBAC is locked.
Do not scatter role checks across routers. Use this module only.
"""

from __future__ import annotations

# Roles allowed into tenant admin/config. Replace with RBAC policy later.
TENANT_ADMIN_ROLES = frozenset({"OWNER", "ADMIN", "TENANT_ADMIN", "TENANT_OWNER"})

# Roles with FULL_ACCESS: can invite/create, suspend, reactivate. READ_ONLY = all others.
# Approved temporary access levels for /admin/users.
FULL_ACCESS_ROLES = frozenset({"OWNER", "ADMIN", "TENANT_ADMIN", "TENANT_OWNER"})


def role_to_access_level(role: str | None) -> str:
    """Map platform role to approved temporary access level (READ_ONLY | FULL_ACCESS)."""
    if not role:
        return "READ_ONLY"
    return "FULL_ACCESS" if role.strip().upper() in FULL_ACCESS_ROLES else "READ_ONLY"


def access_level_to_role(access_level: str) -> str:
    """Map approved access level to platform role."""
    if (access_level or "").strip().upper() == "FULL_ACCESS":
        return "TENANT_ADMIN"
    return "TENANT_MEMBER"


def is_tenant_admin(role: str | None) -> bool:
    """Temporary gate: allow high-privilege roles into admin/config."""
    if not role:
        return False
    return role.strip().upper() in TENANT_ADMIN_ROLES


def has_full_access(role: str | None) -> bool:
    """True if role has FULL_ACCESS (can invite/create, suspend, reactivate). READ_ONLY gets False."""
    if not role:
        return False
    return role.strip().upper() in FULL_ACCESS_ROLES
