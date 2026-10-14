"""Track and tear down integration-test Loads/Trips (tenant_pytest only)."""

from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any, Literal

ResourceKind = Literal["trip", "load"]


@dataclass(frozen=True)
class IntegrationCleanupFailure:
    resource_type: ResourceKind
    resource_id: int
    error: BaseException


class IntegrationCleanupError(Exception):
    """Raised when one or more tracked integration resources could not be cleaned up."""

    def __init__(self, failures: list[IntegrationCleanupFailure]) -> None:
        self.failures = list(failures)
        parts = [
            f"{f.resource_type} id={f.resource_id}: {f.error!r}" for f in self.failures
        ]
        super().__init__(
            f"integration teardown failed for {len(self.failures)} resource(s): "
            + "; ".join(parts)
        )

from httpx import AsyncClient, Response
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.db_url import to_async_pg_url
from app.core.integration_db_guard import IntegrationIsolationError
from tests.support.integration_isolation import (
    assert_mutating_integration_allowed,
    database_name_from_url,
    integration_tenant_db_name,
    require_integration_tenant_database_url,
)
from tests.support.integration_ready_load import (
    api_create_ready_load,
    api_create_ready_load_ids,
)
from tests.support.tenant_test_ids import platform_tenant_id_for_slug


@dataclass
class IntegrationResourceTracker:
    load_ids: list[int] = field(default_factory=list)
    trip_ids: list[int] = field(default_factory=list)

    def track_load(self, load_id: int) -> None:
        lid = int(load_id)
        if lid not in self.load_ids:
            self.load_ids.append(lid)

    def track_trip(self, trip_id: int) -> None:
        tid = int(trip_id)
        if tid not in self.trip_ids:
            self.trip_ids.append(tid)

    def track_trip_response(self, response: Response) -> None:
        if response.status_code == 201:
            body = response.json()
            if body.get("id") is not None:
                self.track_trip(int(body["id"]))


class IntegrationTestScope:
    """Per-test resource scope with guaranteed teardown (pass/fail/skip)."""

    def __init__(
        self,
        client: AsyncClient,
        headers: dict[str, str],
        *,
        context: str,
    ) -> None:
        self.client = client
        self.headers = headers
        self.context = context
        self.tracker = IntegrationResourceTracker()
        self.tenant_id: int = 0
        self.tenant_url: str = ""

    async def activate(self) -> None:
        self.tenant_url = require_integration_tenant_database_url(context=self.context)
        db_name = database_name_from_url(self.tenant_url)
        expected = integration_tenant_db_name()
        if db_name != expected:
            raise IntegrationIsolationError(
                f"integration scope requires database {expected!r}, got {db_name!r}"
            )
        self.tenant_id = await platform_tenant_id_for_slug()
        await assert_mutating_integration_allowed(
            tenant_id=self.tenant_id,
            host=self.headers.get("host"),
            context=self.context,
        )

    async def create_ready_load(self, tag: str, **extra: Any) -> dict:
        return await api_create_ready_load(
            self.client,
            self.headers,
            tag,
            tracker=self.tracker,
            **extra,
        )

    async def create_ready_load_id(self, tag: str, **extra: Any) -> int:
        return int((await self.create_ready_load(tag, **extra))["id"])

    async def create_ready_load_ids(self, n: int, tag_prefix: str = "TRIP") -> list[int]:
        ids = await api_create_ready_load_ids(
            self.client,
            self.headers,
            n,
            tag_prefix=tag_prefix,
            tracker=self.tracker,
        )
        return ids

    async def post_planned_trip(self, load_ids: list[int] | None = None) -> Response:
        r = await self.client.post(
            "/api/v1/trips",
            headers=self.headers,
            json={
                "status": "planned",
                "job_type": "freight_load",
                "load_ids": [int(x) for x in (load_ids or [])],
            },
        )
        self.tracker.track_trip_response(r)
        return r

    async def load_row_exists(self, load_id: int) -> bool:
        engine = create_async_engine(to_async_pg_url(self.tenant_url), pool_pre_ping=True)
        Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
        try:
            async with Session() as db:
                n = await db.scalar(
                    text("select count(*) from loads where tenant_id=:t and id=:i"),
                    {"t": self.tenant_id, "i": int(load_id)},
                )
                return int(n or 0) > 0
        finally:
            await engine.dispose()

    async def teardown(self) -> None:
        if not self.tracker.trip_ids and not self.tracker.load_ids:
            return
        failures: list[IntegrationCleanupFailure] = []
        engine = create_async_engine(to_async_pg_url(self.tenant_url), pool_pre_ping=True)
        Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
        try:
            async with Session() as db:
                for trip_id in reversed(self.tracker.trip_ids):
                    try:
                        await _cleanup_trip_rows(
                            db, self.tenant_id, trip_id, context=self.context
                        )
                    except BaseException as exc:
                        failures.append(
                            IntegrationCleanupFailure("trip", int(trip_id), exc)
                        )
                        await db.rollback()
                for load_id in reversed(self.tracker.load_ids):
                    try:
                        await _cleanup_load_rows(
                            db, self.tenant_id, load_id, context=self.context
                        )
                    except BaseException as exc:
                        failures.append(
                            IntegrationCleanupFailure("load", int(load_id), exc)
                        )
                        await db.rollback()
        finally:
            await engine.dispose()
        if failures:
            raise IntegrationCleanupError(failures)


@asynccontextmanager
async def integration_scope_context(client: AsyncClient, headers: dict[str, str], context: str):
    scope = IntegrationTestScope(client, headers, context=context)
    await scope.activate()
    test_exc: BaseException | None = None
    try:
        yield scope
    except BaseException as err:
        test_exc = err
        raise
    finally:
        try:
            await scope.teardown()
        except BaseException as teardown_err:
            if test_exc is not None:
                test_exc.add_note(f"Integration teardown also failed: {teardown_err}")
            else:
                raise teardown_err


async def _cleanup_trip_rows(
    db: AsyncSession, tenant_id: int, trip_id: int, *, context: str
) -> None:
    await assert_mutating_integration_allowed(tenant_id=tenant_id, context=f"{context}_cleanup_trip")
    await db.execute(
        text("delete from trip_loads where tenant_id=:t and trip_id=:i"),
        {"t": tenant_id, "i": trip_id},
    )
    await db.execute(
        text("delete from trips where tenant_id=:t and id=:i"),
        {"t": tenant_id, "i": trip_id},
    )
    await db.commit()


async def _cleanup_load_rows(
    db: AsyncSession, tenant_id: int, load_id: int, *, context: str
) -> None:
    await assert_mutating_integration_allowed(tenant_id=tenant_id, context=f"{context}_cleanup_load")
    await db.execute(
        text("delete from trip_loads where tenant_id=:t and load_id=:i"),
        {"t": tenant_id, "i": load_id},
    )
    await db.execute(
        text("delete from load_custody_events where tenant_id=:t and load_id=:i"),
        {"t": tenant_id, "i": load_id},
    )
    await db.execute(
        text(
            "delete from audit_events where tenant_id=:t and entity_type='load' and entity_id=:e"
        ),
        {"t": tenant_id, "e": str(load_id)},
    )
    await db.execute(
        text("delete from load_stops where tenant_id=:t and load_id=:i"),
        {"t": tenant_id, "i": load_id},
    )
    await db.execute(
        text("delete from load_notes where tenant_id=:t and load_id=:i"),
        {"t": tenant_id, "i": load_id},
    )
    await db.execute(
        text("delete from loads where tenant_id=:t and id=:i"),
        {"t": tenant_id, "i": load_id},
    )
    await db.commit()
