"""Payroll capabilities.

Routes that already use require_tenant_admin stay admin.
Routes with no role gate are operational writes or reads in the prospective policy.
"""

from __future__ import annotations

from app.authz.spec import CapabilitySpec, ModuleCatalog


def _spec(resource: str, action: str, prospective: str, current_contract: str) -> CapabilitySpec:
    return CapabilitySpec("payroll", resource, action, prospective, current_contract, False)


CATALOG = ModuleCatalog(
    module="payroll",
    prefixes=("payroll.",),
    capabilities=(
        _spec("payroll.periods", "view", "read", "ungated"),
        _spec("payroll.periods", "open_close", "admin", "admin"),
        _spec("payroll.periods", "update", "operational", "ungated"),
        _spec("payroll.profiles", "view", "read", "ungated"),
        _spec("payroll.profiles", "manage", "operational", "ungated"),
        _spec("payroll.entries", "view", "read", "ungated"),
        _spec("payroll.entries", "manage", "operational", "ungated"),
        _spec("payroll.runs", "view", "read", "ungated"),
        _spec("payroll.runs", "manage", "admin", "admin"),
        _spec("payroll.documents", "view", "read", "ungated"),
        _spec("payroll.settlement", "view", "read", "ungated"),
    ),
)
