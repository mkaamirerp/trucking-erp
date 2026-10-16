"""Fleet asset capabilities. Trucks, trailers, and the fleet list."""

from __future__ import annotations

from app.authz.spec import CapabilitySpec, ModuleCatalog


def _spec(resource: str, action: str, prospective: str) -> CapabilitySpec:
    return CapabilitySpec("assets", resource, action, prospective, "ungated", False)


CATALOG = ModuleCatalog(
    module="assets",
    prefixes=("assets.",),
    capabilities=(
        _spec("assets.trucks", "view", "read"),
        _spec("assets.trucks", "manage", "operational"),
        _spec("assets.trailers", "view", "read"),
        _spec("assets.trailers", "manage", "operational"),
        _spec("assets.fleet", "view", "read"),
    ),
)
