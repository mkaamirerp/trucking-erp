"""Post-persistence routing: classifier chooses path; intake_service applies policy."""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.email_engine.intake_service import run_post_ingest_intake
from app.services.email_engine.message_classifier import post_ingest_intake_path

logger = logging.getLogger(__name__)


async def route_after_ingestion(
    tenant_db: AsyncSession,
    tenant_id: int,
    thread_id: int,
    *,
    provider: str,
    gmail_access_token: str | None = None,
) -> None:
    """
    Run shared downstream policy after messages are persisted.
    Path comes from `post_ingest_intake_path` (not raw provider string branching beyond that).
    """
    try:
        path = post_ingest_intake_path(provider=provider)
        await run_post_ingest_intake(
            tenant_db,
            tenant_id,
            thread_id,
            path,
            gmail_access_token=gmail_access_token,
        )
    except Exception as exc:
        logger.warning("email intake routing failed tenant_id=%s thread_id=%s: %s", tenant_id, thread_id, exc)
