"""In-process domain-event dispatcher + SSE subscriber registry.

V1 assumes a single uvicorn process (see module docstring). When TruckERP scales to
multiple API workers/containers, keep the durable outbox but replace in-memory fan-out
with a shared bridge (PostgreSQL LISTEN/NOTIFY and/or Redis pub/sub).
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.deps.tenant_db import dispose_cached_engine_for_tenant_id, open_tenant_session_by_id
from app.models.domain_event_outbox import DomainEventOutbox
from app.models.platform import PlatformTenant

logger = logging.getLogger(__name__)

RECOVERY_INTERVAL_SECONDS = 10.0
DISPATCH_BATCH_LIMIT = 100


def _is_unsweepable_tenant_error(exc: BaseException) -> bool:
    """True when this tenant cannot be swept and should be skipped, not retried every 10s."""
    name = type(exc).__name__
    if name in {"HTTPException", "InvalidCatalogNameError"}:
        return True
    text_blob = str(exc).lower()
    return "database" in text_blob and "does not exist" in text_blob


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SubscriberRegistry:
    """In-memory SSE subscriber queues keyed by (tenant_id, application_id)."""

    def __init__(self) -> None:
        self._subscribers: dict[tuple[int, int], set[asyncio.Queue[dict[str, str]]]] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def subscribe(self, tenant_id: int, application_id: int, queue: asyncio.Queue[dict[str, str]]) -> None:
        async with self._lock:
            self._subscribers[(int(tenant_id), int(application_id))].add(queue)

    async def unsubscribe(self, tenant_id: int, application_id: int, queue: asyncio.Queue[dict[str, str]]) -> None:
        async with self._lock:
            key = (int(tenant_id), int(application_id))
            bucket = self._subscribers.get(key)
            if not bucket:
                return
            bucket.discard(queue)
            if not bucket:
                self._subscribers.pop(key, None)

    async def publish(self, tenant_id: int, application_id: int, message: dict[str, str]) -> None:
        key = (int(tenant_id), int(application_id))
        async with self._lock:
            queues = list(self._subscribers.get(key, ()))
        for queue in queues:
            try:
                queue.put_nowait(message)
            except asyncio.QueueFull:
                logger.warning(
                    "domain_event_sse_queue_full tenant_id=%s application_id=%s",
                    tenant_id,
                    application_id,
                )


class DomainEventDispatcher:
    def __init__(self) -> None:
        self.registry = SubscriberRegistry()
        self._wake = asyncio.Event()
        self._task: asyncio.Task[None] | None = None
        self._running = False
        # Tenants whose DBs lack domain_event_outbox or the catalog itself.
        # Skip without re-querying so Postgres is not flooded with ERROR/FATAL.
        self._skip_tenant_ids: set[int] = set()

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run_loop(), name="domain-event-dispatcher")
        try:
            await self.sweep_all_active_tenants()
        except Exception:
            logger.exception("domain_event_startup_sweep_failed")

    async def stop(self) -> None:
        self._running = False
        self._wake.set()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    def wake(self, tenant_id: int) -> None:
        """Fast in-process wake after a successful outbox commit."""
        self._wake.set()

    async def sweep_all_active_tenants(self) -> None:
        async with AsyncSessionLocal() as platform_db:
            tenant_ids = list(
                await platform_db.scalars(
                    select(PlatformTenant.id).where(
                        PlatformTenant.status == "ACTIVE",
                        PlatformTenant.db_status == "READY",
                    )
                )
            )
        for tenant_id in tenant_ids:
            try:
                await self.process_pending_for_tenant(int(tenant_id))
            except Exception:
                logger.exception("domain_event_sweep_failed tenant_id=%s", tenant_id)

    async def process_pending_for_tenant(self, tenant_id: int) -> None:
        if tenant_id in self._skip_tenant_ids:
            return
        try:
            should_forget_engine = False
            async for db in open_tenant_session_by_id(tenant_id):
                should_forget_engine = await self._process_pending_session(db, tenant_id)
            if should_forget_engine:
                await dispose_cached_engine_for_tenant_id(tenant_id)
        except Exception as exc:
            if not _is_unsweepable_tenant_error(exc):
                raise
            self._skip_tenant_ids.add(int(tenant_id))
            logger.warning(
                "domain_event_skip_tenant tenant_id=%s reason=%s",
                tenant_id,
                type(exc).__name__,
            )
            await dispose_cached_engine_for_tenant_id(tenant_id)

    async def _process_pending_session(self, db: AsyncSession, tenant_id: int) -> bool:
        """Return True when the cached tenant engine should be disposed."""
        try:
            present = await db.scalar(text("SELECT to_regclass('public.domain_event_outbox')"))
            if present is None:
                self._skip_tenant_ids.add(int(tenant_id))
                logger.warning(
                    "domain_event_outbox table missing for tenant_id=%s — skip pending sweep",
                    tenant_id,
                )
                return True
            while True:
                rows = list(
                    await db.scalars(
                        select(DomainEventOutbox)
                        .where(
                            DomainEventOutbox.tenant_id == tenant_id,
                            DomainEventOutbox.published_at.is_(None),
                        )
                        .order_by(DomainEventOutbox.id.asc())
                        .limit(DISPATCH_BATCH_LIMIT)
                    )
                )
                if not rows:
                    break
                for row in rows:
                    await self._dispatch_row(db, row)
        except ProgrammingError as exc:
            await db.rollback()
            if "domain_event_outbox" in str(exc).lower():
                self._skip_tenant_ids.add(int(tenant_id))
                logger.warning(
                    "domain_event_outbox table missing for tenant_id=%s — skip pending sweep",
                    tenant_id,
                )
                return True
            raise
        return False

    async def _dispatch_row(self, db: AsyncSession, row: DomainEventOutbox) -> None:
        try:
            application_id = int(row.aggregate_id)
        except (TypeError, ValueError):
            row.attempt_count = int(row.attempt_count or 0) + 1
            row.last_error = "invalid aggregate_id for SSE fan-out"
            await db.commit()
            return

        message = {
            "event_id": str(row.event_id),
            "event_type": row.event_type,
        }
        try:
            await self.registry.publish(row.tenant_id, application_id, message)
            row.published_at = _utcnow()
            row.last_error = None
        except Exception as exc:
            row.last_error = str(exc)[:2000]
            logger.exception(
                "domain_event_dispatch_failed event_id=%s event_type=%s",
                row.event_id,
                row.event_type,
            )
        row.attempt_count = int(row.attempt_count or 0) + 1
        await db.commit()

    async def _run_loop(self) -> None:
        while self._running:
            try:
                try:
                    await asyncio.wait_for(self._wake.wait(), timeout=RECOVERY_INTERVAL_SECONDS)
                except asyncio.TimeoutError:
                    pass
                self._wake.clear()
                await self.sweep_all_active_tenants()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("domain_event_dispatcher_loop_error")
                await asyncio.sleep(1.0)


_dispatcher: DomainEventDispatcher | None = None


def get_domain_event_dispatcher() -> DomainEventDispatcher:
    global _dispatcher
    if _dispatcher is None:
        _dispatcher = DomainEventDispatcher()
    return _dispatcher


def format_sse_application_changed(event_id: str, event_type: str) -> str:
    data = json.dumps({"event_id": event_id, "event_type": event_type}, separators=(",", ":"))
    return f"id: {event_id}\nevent: application_changed\ndata: {data}\n\n"
