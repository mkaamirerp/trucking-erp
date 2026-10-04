"""Manual Fuel Entry HTTP routes — registration."""

from __future__ import annotations


def test_manual_entry_api_routes_registered() -> None:
    from app.routers.fuel import router

    paths = {getattr(r, "path", None) for r in router.routes}
    assert "/fuel/manual-entry/stages" in paths
    assert "/fuel/manual-entry/stages/receipt" in paths
    assert "/fuel/manual-entry/stages/{stage_id}" in paths
    assert "/fuel/manual-entry/stages/{stage_id}/validate" in paths
    assert "/fuel/manual-entry/stages/{stage_id}/process" in paths
    assert "/fuel/manual-entry/stages/{stage_id}/discard" in paths
