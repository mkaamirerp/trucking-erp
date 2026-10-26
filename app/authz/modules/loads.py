"""Load capabilities. Hard delete is intentionally absent (Load Integrity I5)."""

from __future__ import annotations

from app.authz.spec import CapabilitySpec, ModuleCatalog


def _spec(resource: str, action: str, prospective: str, note: str = "") -> CapabilitySpec:
    return CapabilitySpec("loads", resource, action, prospective, "ungated", False, note)


CATALOG = ModuleCatalog(
    module="loads",
    prefixes=("loads.",),
    capabilities=(
        _spec("loads.records", "view", "read"),
        _spec("loads.records", "create", "operational"),
        _spec("loads.records", "update", "operational", "Does not authorize status=ready on PATCH."),
        _spec(
            "loads.records",
            "mark_ready",
            "operational",
            "Does not replace mark_load_ready transition rules.",
        ),
        _spec("loads.records", "cancel", "operational", "Commercial cancel; preserves row and audit history."),
        _spec("loads.documents", "parse", "operational"),
        _spec("loads.documents", "confirm", "operational"),
        _spec("loads.custody", "view", "read", "Read model only. Custody changes belong to trips."),
        _spec("loads.notes", "view", "read"),
        _spec("loads.notes", "create", "operational"),
    ),
)
