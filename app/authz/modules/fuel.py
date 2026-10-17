"""Fuel capabilities. Names match app.deps.fuel_rbac and stay admin-only."""

from __future__ import annotations

from app.authz.registry import FUEL_CAPABILITIES
from app.authz.spec import CapabilitySpec, ModuleCatalog

CATALOG = ModuleCatalog(
    module="fuel",
    prefixes=("fuel.",),
    capabilities=tuple(
        CapabilitySpec(
            module="fuel",
            resource=resource,
            action=action,
            prospective="admin",
            current_contract="admin",
            shipped=True,
            note="Segment 0A maps this capability to is_tenant_admin.",
        )
        for resource, action in FUEL_CAPABILITIES
    ),
)
