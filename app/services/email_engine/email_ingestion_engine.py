"""Shared ingestion orchestration: normalize → persist → route."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.email_ingestion import EmailThread
from app.services.email_engine.message_router import route_after_ingestion
from app.services.email_engine.normalized import NormalizedEmailMessage, NormalizedThreadRollup
from app.services.email_engine.persistence import upsert_thread_bundle


@dataclass
class IngestionContext:
    tenant_id: int
    provider: str
    gmail_access_token: str | None = None


async def ingest_normalized_thread(
    tenant_db: AsyncSession,
    ctx: IngestionContext,
    rollup: NormalizedThreadRollup,
    messages: list[NormalizedEmailMessage],
) -> tuple[EmailThread, int, int]:
    """
    Persist a full or partial thread bundle, then run shared routing/classification.
    Providers call this after fetch + normalization.
    """
    thread_row, m, a = await upsert_thread_bundle(
        tenant_db,
        ctx.tenant_id,
        ctx.provider,
        rollup,
        messages,
    )
    await route_after_ingestion(
        tenant_db,
        ctx.tenant_id,
        thread_row.id,
        provider=ctx.provider,
        gmail_access_token=ctx.gmail_access_token,
    )
    return thread_row, m, a
