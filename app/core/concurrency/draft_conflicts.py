"""HTTP conflict payloads for load workspace draft CAS writes."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import HTTPException, status

WORKSPACE_DRAFT_VERSION_CONFLICT = "LOAD_WORKSPACE_DRAFT_VERSION_CONFLICT"


def workspace_draft_version_conflict_payload(
    *,
    draft_id: uuid.UUID,
    client_version: int,
    server_version: int | None,
) -> dict[str, Any]:
    return {
        "code": WORKSPACE_DRAFT_VERSION_CONFLICT,
        "draft_id": str(draft_id),
        "client_version": client_version,
        "server_version": server_version,
    }


def workspace_draft_version_conflict_exception(
    *,
    draft_id: uuid.UUID,
    client_version: int,
    server_version: int | None,
) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=workspace_draft_version_conflict_payload(
            draft_id=draft_id,
            client_version=client_version,
            server_version=server_version,
        ),
    )
