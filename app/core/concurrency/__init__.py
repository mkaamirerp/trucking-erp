"""Tenant-scoped concurrency helpers (optimistic locking, conflict contracts).

Rollout (load mutations):
1. Apply tenant Alembic migration adding loads.concurrency_version (backfilled to 1).
2. Deploy API + web together: PATCH/POST/DELETE require expected_concurrency_version.
   Older clients omitting it receive HTTP 422 (validation) — not silent last-write-wins.
3. Phase 2: LISTEN/NOTIFY → SSE (signal-only) — see design docs; not implemented here.
"""

from app.core.concurrency.conflicts import (
    LOAD_VERSION_CONFLICT,
    load_version_conflict_exception,
    load_version_conflict_payload,
)

__all__ = [
    "LOAD_VERSION_CONFLICT",
    "load_version_conflict_exception",
    "load_version_conflict_payload",
]
