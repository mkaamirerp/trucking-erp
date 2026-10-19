"""Track and tear down integration-test Loads/Trips (tenant_pytest only)."""

from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any, Literal

ResourceKind = Literal["trip", "load", "driver", "truck", "trailer"]


@dataclass(frozen=True)
class IntegrationCleanupFailure:
    resource_type: ResourceKind
    resource_id: int
    error: BaseException


class IntegrationFleetDependencyError(Exception):
    """Untracked trip(s) still reference a test-scoped fleet asset; refuse broad FK nulling."""

    def __init__(
        self,
        *,
        asset_kind: Literal["driver", "truck", "trailer"],
        asset_id: int,
        blocking_trip_ids: list[int],
    ) -> None:
        self.asset_kind = asset_kind
        self.asset_id = int(asset_id)
        self.blocking_trip_ids = [int(x) for x in blocking_trip_ids]
        super().__init__(
            f"cannot delete test {asset_kind} id={asset_id}: "
            f"untracked trip(s) still reference it: {self.blocking_trip_ids}"
        )


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
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.db_url import to_async_pg_url
from app.core.integration_db_guard import IntegrationIsolationError
from tests.support.demo_clone_integration import demo_clone_active, demo_clone_tenant_id
from tests.support.integration_isolation import (
    allowed_integration_db_names,
    assert_mutating_integration_allowed,
    database_name_from_url,
    integration_tenant_db_name,
    require_integration_tenant_database_url,
)
from tests.support.integration_fleet_fixtures import api_create_integration_fleet_bundle
from tests.support.integration_ready_load import (
    api_create_draft_load,
    api_create_ready_load,
    api_create_ready_load_ids,
)
from tests.support.tenant_test_ids import platform_tenant_id_for_slug


async def _assert_mutating_cleanup_allowed(tenant_id: int, *, context: str) -> None:
    """Demo clones use tenant_id=53 from sanitized data; platform registry stays pytest-only."""
    if demo_clone_active():
        return
    await assert_mutating_integration_allowed(tenant_id=tenant_id, context=context)


@dataclass
class IntegrationResourceTracker:
    load_ids: list[int] = field(default_factory=list)
    trip_ids: list[int] = field(default_factory=list)
    driver_ids: list[int] = field(default_factory=list)
    truck_ids: list[int] = field(default_factory=list)
    trailer_ids: list[int] = field(default_factory=list)

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

    def track_driver(self, driver_id: int) -> None:
        did = int(driver_id)
        if did not in self.driver_ids:
            self.driver_ids.append(did)

    def track_truck(self, truck_id: int) -> None:
        tid = int(truck_id)
        if tid not in self.truck_ids:
            self.truck_ids.append(tid)

    def track_trailer(self, trailer_id: int) -> None:
        rid = int(trailer_id)
        if rid not in self.trailer_ids:
            self.trailer_ids.append(rid)


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
        if demo_clone_active():
            allowed = allowed_integration_db_names()
            if db_name not in allowed:
                raise IntegrationIsolationError(
                    f"demo clone database {db_name!r} is not allowed ({sorted(allowed)})."
                )
            self.tenant_id = demo_clone_tenant_id()
            return
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

    async def create_draft_load(self, tag: str, **extra: Any) -> dict:
        return await api_create_draft_load(
            self.client,
            self.headers,
            tag,
            tracker=self.tracker,
            **extra,
        )

    async def create_ready_load(self, tag: str, **extra: Any) -> dict:
        return await api_create_ready_load(
            self.client,
            self.headers,
            tag,
            tracker=self.tracker,
            **extra,
        )

    async def create_fleet_bundle(self, tag: str) -> tuple[int, int, int]:
        return await api_create_integration_fleet_bundle(
            self.client,
            self.headers,
            tag,
            tracker=self.tracker,
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
        if (
            not self.tracker.trip_ids
            and not self.tracker.load_ids
            and not self.tracker.driver_ids
            and not self.tracker.truck_ids
            and not self.tracker.trailer_ids
        ):
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
                    except Exception as exc:
                        failures.append(
                            IntegrationCleanupFailure("trip", int(trip_id), exc)
                        )
                        await db.rollback()
                for load_id in reversed(self.tracker.load_ids):
                    try:
                        await _cleanup_load_rows(
                            db, self.tenant_id, load_id, context=self.context
                        )
                    except Exception as exc:
                        failures.append(
                            IntegrationCleanupFailure("load", int(load_id), exc)
                        )
                        await db.rollback()
                tracked_trip_ids = frozenset(int(x) for x in self.tracker.trip_ids)
                for driver_id in reversed(self.tracker.driver_ids):
                    try:
                        await _cleanup_driver_rows(
                            db,
                            self.tenant_id,
                            driver_id,
                            tracked_trip_ids=tracked_trip_ids,
                            context=self.context,
                        )
                    except Exception as exc:
                        failures.append(
                            IntegrationCleanupFailure("driver", int(driver_id), exc)
                        )
                        await db.rollback()
                for truck_id in reversed(self.tracker.truck_ids):
                    try:
                        await _cleanup_truck_rows(
                            db,
                            self.tenant_id,
                            truck_id,
                            tracked_trip_ids=tracked_trip_ids,
                            context=self.context,
                        )
                    except Exception as exc:
                        failures.append(
                            IntegrationCleanupFailure("truck", int(truck_id), exc)
                        )
                        await db.rollback()
                for trailer_id in reversed(self.tracker.trailer_ids):
                    try:
                        await _cleanup_trailer_rows(
                            db,
                            self.tenant_id,
                            trailer_id,
                            tracked_trip_ids=tracked_trip_ids,
                            context=self.context,
                        )
                    except Exception as exc:
                        failures.append(
                            IntegrationCleanupFailure("trailer", int(trailer_id), exc)
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
    await _assert_mutating_cleanup_allowed(tenant_id=tenant_id, context=f"{context}_cleanup_trip")
    await db.execute(
        text("delete from trip_loads where tenant_id=:t and trip_id=:i"),
        {"t": tenant_id, "i": trip_id},
    )
    await db.execute(
        text("delete from trips where tenant_id=:t and id=:i"),
        {"t": tenant_id, "i": trip_id},
    )
    await db.commit()


async def _trip_ids_referencing_fleet_asset(
    db: AsyncSession,
    tenant_id: int,
    *,
    column: Literal["driver", "truck", "trailer"],
    asset_id: int,
) -> list[int]:
    col = f"{column}_id"
    result = await db.execute(
        text(
            f"select id from trips where tenant_id=:t and {col}=:aid order by id"
        ),
        {"t": tenant_id, "aid": int(asset_id)},
    )
    return [int(row[0]) for row in result.fetchall()]


async def _assert_safe_to_delete_fleet_asset(
    db: AsyncSession,
    tenant_id: int,
    *,
    asset_kind: Literal["driver", "truck", "trailer"],
    asset_id: int,
    tracked_trip_ids: frozenset[int],
) -> None:
    """Refuse delete if any *untracked* trip still references the asset (no broad FK nulling)."""
    refs = await _trip_ids_referencing_fleet_asset(
        db, tenant_id, column=asset_kind, asset_id=asset_id
    )
    untracked = [tid for tid in refs if tid not in tracked_trip_ids]
    if untracked:
        raise IntegrationFleetDependencyError(
            asset_kind=asset_kind,
            asset_id=asset_id,
            blocking_trip_ids=untracked,
        )


async def _cleanup_driver_rows(
    db: AsyncSession,
    tenant_id: int,
    driver_id: int,
    *,
    tracked_trip_ids: frozenset[int],
    context: str,
) -> None:
    await _assert_mutating_cleanup_allowed(tenant_id=tenant_id, context=f"{context}_cleanup_driver")
    await _assert_safe_to_delete_fleet_asset(
        db,
        tenant_id,
        asset_kind="driver",
        asset_id=driver_id,
        tracked_trip_ids=tracked_trip_ids,
    )
    await db.execute(
        text("delete from drivers where tenant_id=:t and id=:i"),
        {"t": tenant_id, "i": driver_id},
    )
    await db.commit()


async def _cleanup_truck_rows(
    db: AsyncSession,
    tenant_id: int,
    truck_id: int,
    *,
    tracked_trip_ids: frozenset[int],
    context: str,
) -> None:
    await _assert_mutating_cleanup_allowed(tenant_id=tenant_id, context=f"{context}_cleanup_truck")
    await _assert_safe_to_delete_fleet_asset(
        db,
        tenant_id,
        asset_kind="truck",
        asset_id=truck_id,
        tracked_trip_ids=tracked_trip_ids,
    )
    await db.execute(
        text("delete from trucks where tenant_id=:t and id=:i"),
        {"t": tenant_id, "i": truck_id},
    )
    await db.commit()


async def _cleanup_trailer_rows(
    db: AsyncSession,
    tenant_id: int,
    trailer_id: int,
    *,
    tracked_trip_ids: frozenset[int],
    context: str,
) -> None:
    await _assert_mutating_cleanup_allowed(tenant_id=tenant_id, context=f"{context}_cleanup_trailer")
    await _assert_safe_to_delete_fleet_asset(
        db,
        tenant_id,
        asset_kind="trailer",
        asset_id=trailer_id,
        tracked_trip_ids=tracked_trip_ids,
    )
    await db.execute(
        text("delete from trailers where tenant_id=:t and id=:i"),
        {"t": tenant_id, "i": trailer_id},
    )
    await db.commit()


async def _cleanup_load_rows(
    db: AsyncSession, tenant_id: int, load_id: int, *, context: str
) -> None:
    await _assert_mutating_cleanup_allowed(tenant_id=tenant_id, context=f"{context}_cleanup_load")
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
    try:
        await db.execute(
            text("delete from load_pod_evidence where tenant_id=:t and load_id=:i"),
            {"t": tenant_id, "i": load_id},
        )
    except ProgrammingError as exc:
        await db.rollback()
        msg = str(exc).lower()
        if "load_pod_evidence" not in msg or "does not exist" not in msg:
            raise
    await db.execute(
        text("delete from loads where tenant_id=:t and id=:i"),
        {"t": tenant_id, "i": load_id},
    )
    await db.commit()
