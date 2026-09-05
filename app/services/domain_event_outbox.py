"""Enqueue durable domain events in the same DB transaction as application state."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.domain_event_outbox import DomainEventOutbox

AGGREGATE_TYPE_PERSON_APPLICATION = "person_application"

EVENT_DRIVER_LICENCE_FRONT_PROCESSED = "driver_licence.front_processed"
EVENT_DRIVER_LICENCE_BACK_PROCESSED = "driver_licence.back_processed"
EVENT_DRIVER_LICENCE_PROCESSING_FAILED = "driver_licence.processing_failed"
EVENT_DRIVER_LICENCE_CAPTURE_COMPLETE = "driver_licence.capture_complete"


async def enqueue_domain_event(
    db: AsyncSession,
    *,
    tenant_id: int,
    aggregate_type: str,
    aggregate_id: str,
    event_type: str,
    payload: dict[str, Any] | None = None,
) -> DomainEventOutbox:
    row = DomainEventOutbox(
        event_id=uuid.uuid4(),
        event_type=event_type,
        aggregate_type=aggregate_type,
        aggregate_id=str(aggregate_id),
        tenant_id=int(tenant_id),
        payload=dict(payload or {}),
    )
    db.add(row)
    await db.flush()
    return row


def build_dl_licence_domain_events(
    *,
    old_front: str,
    old_back: str,
    new_front: str,
    new_back: str,
    doc_type: str,
    upload_failed: bool,
) -> list[tuple[str, dict[str, Any]]]:
    """Return (event_type, payload) pairs from OLD→NEW DL side status transitions."""
    events: list[tuple[str, dict[str, Any]]] = []

    if old_front != "PROCESSED" and new_front == "PROCESSED":
        events.append((EVENT_DRIVER_LICENCE_FRONT_PROCESSED, {}))
    if old_back != "PROCESSED" and new_back == "PROCESSED":
        events.append((EVENT_DRIVER_LICENCE_BACK_PROCESSED, {}))
    if upload_failed:
        events.append((EVENT_DRIVER_LICENCE_PROCESSING_FAILED, {"side": doc_type}))

    old_both = old_front == "PROCESSED" and old_back == "PROCESSED"
    new_both = new_front == "PROCESSED" and new_back == "PROCESSED"
    if not old_both and new_both:
        events.append((EVENT_DRIVER_LICENCE_CAPTURE_COMPLETE, {}))

    return events
