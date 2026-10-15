"""Toll capabilities. Subscription entitlement stays outside this catalog."""

from __future__ import annotations

from app.authz.spec import CapabilitySpec, ModuleCatalog


def _spec(resource: str, action: str, prospective: str) -> CapabilitySpec:
    return CapabilitySpec("tolls", resource, action, prospective, "ungated", False)


CATALOG = ModuleCatalog(
    module="tolls",
    prefixes=("tolls.",),
    capabilities=(
        _spec("tolls.records", "view", "read"),
        _spec("tolls.imports", "manage", "operational"),
        _spec("tolls.review", "manage", "operational"),
        _spec("tolls.manual", "manage", "operational"),
    ),
)
