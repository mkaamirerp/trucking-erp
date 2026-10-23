"""Trip read models tolerate loads with no commercial stops."""

from __future__ import annotations

import pytest

from app.services.trips import _stop_route_summary_map


@pytest.mark.asyncio
async def test_stop_route_summary_map_empty_load_ids() -> None:
    class _NoDb:
        async def execute(self, *_a, **_k):
            raise AssertionError("should not query when load_ids empty")

    assert await _stop_route_summary_map(_NoDb(), 1, []) == {}
