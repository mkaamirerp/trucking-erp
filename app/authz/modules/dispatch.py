"""Trip and legacy dispatch-board capabilities. Custody rules stay in the trip service."""

from __future__ import annotations

from app.authz.spec import CapabilitySpec, ModuleCatalog


def _spec(resource: str, action: str, prospective: str, note: str = "") -> CapabilitySpec:
    return CapabilitySpec("dispatch", resource, action, prospective, "ungated", False, note)


CATALOG = ModuleCatalog(
    module="dispatch",
    prefixes=("trips.", "dispatch."),
    capabilities=(
        _spec("trips.records", "view", "read"),
        _spec("trips.records", "create", "operational"),
        _spec("trips.records", "cancel", "operational"),
        _spec("trips.records", "complete", "operational"),
        _spec("trips.membership", "manage", "operational"),
        _spec("trips.assignment", "manage", "operational"),
        _spec("trips.schedule", "manage", "operational"),
        _spec("trips.execution", "signal", "operational"),
        _spec(
            "trips.custody",
            "transition",
            "operational",
            "RBAC only. Accept, handoff, and take-custody rules stay in the trip service.",
        ),
        _spec(
            "dispatch.board",
            "view",
            "read",
            "Legacy board read. This does not make /dispatch the operational authority.",
        ),
    ),
)
