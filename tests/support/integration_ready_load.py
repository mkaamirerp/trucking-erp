"""Create isolated ready Loads for integration tests (avoid first-page list dependence)."""

from __future__ import annotations

import uuid

from typing import TYPE_CHECKING

from httpx import AsyncClient

if TYPE_CHECKING:
    from tests.support.integration_test_resources import IntegrationResourceTracker

INTEGRATION_READY_LOAD_STOPS = [
    {"stop_type": "PICKUP", "sequence": 0, "city": "Austin", "state_or_province": "TX"},
    {"stop_type": "DROP", "sequence": 1, "city": "Dallas", "state_or_province": "TX"},
]


async def api_create_draft_load(
    client: AsyncClient,
    headers: dict[str, str],
    tag: str,
    *,
    tracker: IntegrationResourceTracker | None = None,
    **extra,
) -> dict:
    r = await client.post(
        "/api/v1/loads",
        headers=headers,
        json={
            "status": "draft",
            **extra,
        },
    )
    if r.status_code != 201:
        raise AssertionError(f"create draft load failed: {r.status_code} {r.text}")
    body = r.json()
    if tracker is not None:
        tracker.track_load(int(body["id"]))
    return body


async def api_mark_load_ready(
    client: AsyncClient,
    headers: dict[str, str],
    load_body: dict,
) -> dict:
    cv = int(load_body["concurrency_version"])
    load_id = int(load_body["id"])
    r = await client.post(
        f"/api/v1/loads/{load_id}/mark-ready",
        headers=headers,
        json={"expected_concurrency_version": cv},
    )
    if r.status_code != 200:
        raise AssertionError(f"mark-ready failed: {r.status_code} {r.text}")
    return r.json()


async def api_create_ready_load(
    client: AsyncClient,
    headers: dict[str, str],
    tag: str,
    *,
    broker_name_snapshot: str = "Integration Broker",
    broker_load_reference: str = "INT-READY",
    tracker: IntegrationResourceTracker | None = None,
    **draft_extra,
) -> dict:
    draft = await api_create_draft_load(
        client,
        headers,
        tag,
        tracker=tracker,
        broker_name_snapshot=broker_name_snapshot,
        broker_load_reference=broker_load_reference,
        stops=INTEGRATION_READY_LOAD_STOPS,
        **draft_extra,
    )
    return await api_mark_load_ready(client, headers, draft)


async def api_create_ready_load_ids(
    client: AsyncClient,
    headers: dict[str, str],
    n: int,
    tag_prefix: str = "TRIP",
    *,
    tracker: IntegrationResourceTracker | None = None,
) -> list[int]:
    if n < 1:
        return []
    out: list[int] = []
    for i in range(n):
        body = await api_create_ready_load(
            client,
            headers,
            f"{tag_prefix}-{i}",
            tracker=tracker,
        )
        out.append(int(body["id"]))
    return out
