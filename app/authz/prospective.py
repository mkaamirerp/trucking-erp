"""Prospective Phase 1 policy. Not loaded by application startup and not enforced."""

from __future__ import annotations

from pathlib import Path

from app.authz.catalog import CAPABILITIES
from app.authz.loader import MODEL_PATH, LoadedPolicy, load_policy
from app.authz.registry import ADMIN_ROLES, OPERATIONAL_FULL_ACCESS_ROLE, TENANT_MEMBER_ROLE
from app.authz.spec import CapabilitySpec

_PACKAGE_DIR = Path(__file__).resolve().parent
PROSPECTIVE_POLICY_PATH = _PACKAGE_DIR / "casbin" / "policy_prospective.csv"

ROLE_ORDER = (
    "OWNER",
    "ADMIN",
    "TENANT_ADMIN",
    "TENANT_OWNER",
    OPERATIONAL_FULL_ACCESS_ROLE,
    TENANT_MEMBER_ROLE,
)


def subjects_for(spec: CapabilitySpec) -> tuple[str, ...]:
    """Roles the prospective policy may grant. Stored invites are not changed.

    ``owner_required`` capabilities stay in the catalog and are omitted from
    this file until the owner approves enforcement.
    """
    if spec.enforcement_approval == "owner_required":
        return ()
    if spec.prospective == "admin":
        allowed = set(ADMIN_ROLES)
    elif spec.prospective == "operational":
        allowed = set(ADMIN_ROLES) | {OPERATIONAL_FULL_ACCESS_ROLE}
    elif spec.prospective == "read":
        allowed = set(ADMIN_ROLES) | {OPERATIONAL_FULL_ACCESS_ROLE, TENANT_MEMBER_ROLE}
    else:
        raise ValueError(f"unknown prospective grant {spec.prospective!r}")
    return tuple(role for role in ROLE_ORDER if role in allowed)


def render_prospective_policy() -> str:
    lines = [
        "# policy_version: 1",
        "# Prospective Phase 1 policy. load_shipped_policy() does not read this file.",
        "# OPERATIONAL_FULL_ACCESS is not stored by invites. FULL_ACCESS still maps to TENANT_ADMIN.",
        "# TENANT_MEMBER is the read-only subject. READ_ONLY is not a policy subject.",
        "# Fuel stays on the four admin roles. There is no loads delete grant.",
        "# People and payroll reads marked owner_required are omitted until that approval.",
        "",
    ]
    for spec in CAPABILITIES.values():
        for role in subjects_for(spec):
            lines.append(f"p, {role}, *, {spec.resource}, {spec.action}, allow")
    lines.append("")
    return "\n".join(lines)


def load_prospective_policy() -> LoadedPolicy:
    """Validate and load the unenforced prospective file."""
    return load_policy(MODEL_PATH, PROSPECTIVE_POLICY_PATH, shipped=False)
