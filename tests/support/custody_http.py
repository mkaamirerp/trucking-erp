"""HTTP helpers for Custody Slice 2 transitions (integration tests)."""

from __future__ import annotations

import uuid

from httpx import AsyncClient, Response
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


def _tenant_async_url() -> str | None:
    from app.core.db_url import to_async_pg_url
    import os

    raw = os.environ.get("TENANT_DATABASE_URL") or os.environ.get("ALEMBIC_TENANT_DATABASE_URL")
    if not raw:
        return None
    return to_async_pg_url(raw)


async def reset_custody_to_unknown(load_id: int) -> None:
    url = _tenant_async_url()
    assert url
    engine = create_async_engine(url, pool_pre_ping=True)
    Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    try:
        async with Session() as session:
            await session.execute(
                text(
                    "UPDATE loads SET custody_owner = 'unknown', custody_trip_id = NULL, "
                    "custody_terminal_id = NULL, custody_placement = 'unknown', "
                    "custody_trailer_id = NULL, custody_since_at = NULL, "
                    "last_custody_event_id = NULL WHERE id = :lid"
                ),
                {"lid": load_id},
            )
            await session.execute(
                text(
                    "DELETE FROM load_custody_events WHERE load_id = :lid "
                    "AND event_type = 'custody_bootstrap'"
                ),
                {"lid": load_id},
            )
            await session.commit()
    finally:
        await engine.dispose()


async def ensure_active_terminal(client: AsyncClient, headers: dict, *, name: str | None = None) -> int:
    label = name or f"Yard-{uuid.uuid4().hex[:8]}"
    created = await client.post(
        "/api/v1/terminals",
        headers=headers,
        json={"name": label, "city": "Testville"},
    )
    assert created.status_code == 201, created.text
    return int(created.json()["id"])


async def accept_custody(
    client: AsyncClient,
    headers: dict,
    trip_id: int,
    load_id: int,
    *,
    reset_unknown: bool = True,
    body: dict | None = None,
) -> Response:
    if reset_unknown:
        await reset_custody_to_unknown(load_id)
    return await client.post(
        f"/api/v1/trips/{trip_id}/loads/{load_id}/accept-custody",
        headers=headers,
        json=body or {},
    )


async def yard_handoff(
    client: AsyncClient,
    headers: dict,
    trip_id: int,
    load_id: int,
    *,
    terminal_id: int,
    placement: str = "staged",
    body: dict | None = None,
) -> Response:
    payload = {"terminal_id": terminal_id, "placement": placement}
    if body:
        payload.update(body)
    return await client.post(
        f"/api/v1/trips/{trip_id}/loads/{load_id}/yard-handoff",
        headers=headers,
        json=payload,
    )


async def take_custody(
    client: AsyncClient,
    headers: dict,
    trip_id: int,
    load_id: int,
    *,
    body: dict | None = None,
) -> Response:
    return await client.post(
        f"/api/v1/trips/{trip_id}/loads/{load_id}/take-custody",
        headers=headers,
        json=body or {},
    )


async def activate_via_custody(
    client: AsyncClient,
    headers: dict,
    trip_id: int,
    load_id: int,
) -> Response:
    """Choose accept-custody vs take-custody from current snapshot.

    Never wipe an existing trip snapshot when it may belong to another OPEN ACTIVE
    membership — that would break custody invariants mid-flow.
    """
    snap = await client.get(f"/api/v1/loads/{load_id}/custody", headers=headers)
    body = snap.json() if snap.status_code == 200 else {}
    owner = body.get("custody_owner") or "unknown"
    trip_c = body.get("custody_trip_id")
    if owner == "terminal":
        return await take_custody(client, headers, trip_id, load_id)
    if owner == "trip":
        same_trip = trip_c is not None and int(trip_c) == int(trip_id)
        if same_trip:
            # Idempotent replay may be accept or take depending on last event.
            r = await accept_custody(
                client, headers, trip_id, load_id, reset_unknown=False, body={}
            )
            if r.status_code == 200:
                return r
            return await take_custody(client, headers, trip_id, load_id)
        # Other trip's custody: do not wipe; let API reject.
        return await accept_custody(
            client, headers, trip_id, load_id, reset_unknown=False, body={}
        )
    return await accept_custody(client, headers, trip_id, load_id, reset_unknown=True)


async def complete_via_custody(
    client: AsyncClient,
    headers: dict,
    trip_id: int,
    load_id: int,
    *,
    terminal_id: int | None = None,
    placement: str = "staged",
) -> Response:
    tid = terminal_id
    if tid is None:
        tid = await ensure_active_terminal(client, headers)
    return await yard_handoff(
        client, headers, trip_id, load_id, terminal_id=tid, placement=placement
    )
