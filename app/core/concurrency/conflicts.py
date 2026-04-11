"""Shared HTTP conflict payloads for versioned entities."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status

LOAD_VERSION_CONFLICT = "LOAD_VERSION_CONFLICT"


def load_version_conflict_payload(
    *,
    load_id: int,
    client_version: int,
    server_version: int | None,
    server_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Stable JSON shape for every load row CAS failure (HTTP 409)."""
    payload: dict[str, Any] = {
        "code": LOAD_VERSION_CONFLICT,
        "load_id": load_id,
        "client_version": client_version,
        "server_version": server_version,
    }
    if server_snapshot is not None:
        payload["server_snapshot"] = server_snapshot
    return payload


def load_version_conflict_exception(
    *,
    load_id: int,
    client_version: int,
    server_version: int | None,
    server_snapshot: dict[str, Any] | None = None,
) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=load_version_conflict_payload(
            load_id=load_id,
            client_version=client_version,
            server_version=server_version,
            server_snapshot=server_snapshot,
        ),
    )
