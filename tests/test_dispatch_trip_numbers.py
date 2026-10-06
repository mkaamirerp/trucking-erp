"""Trip number lifecycle: legacy Load status/assignment writes frozen on generic PATCH (Slice 1 + Issue 0A),
prefix lock, historical trip pointers preserved, schema guards.

Requires DATABASE_URL (integration), tenant migrations through dispatch_trips / numbering.
Tests that need pre-dispatched state use TENANT_DATABASE_URL + seed_load_dispatched_legacy_state.

- Admin double-PUT 409: idempotent across repeat runs on a shared DB.

Integration pytest is typically run inside the API image with the same code as /app; if the container
uses a baked image without the repo bind-mount, copy this file in or rebuild so overrides stay in sync.
"""

from __future__ import annotations

import os
import uuid

# Before importing Settings/app: allow tenant resolution shortcuts + safe test env (matches tests/conftest.py).
# Overwrite container/prod env when pytest loads this module so TEST_BYPASS_AUTH tenant middleware works.
os.environ["ENVIRONMENT"] = "test"
os.environ["ALLOW_TENANT_RESOLUTION_SHORTCUTS"] = "true"

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.constants.trip_dispatch import (
    LEGACY_LOAD_STATUS_DISPATCH_DEPRECATED,
    LEGACY_LOAD_STATUS_TRANSITION_BLOCKED,
    TRIP_NUMERIC_WIDTH,
)
from app.core.db_url import to_async_pg_url
from tests.support.integration_auth import (
    clear_current_user_and_tenant_overrides,
    install_host_aligned_current_user_and_tenant,
)
from tests.support.legacy_dispatch_test_seed import seed_load_dispatched_legacy_state
from tests.support.tenant_test_ids import platform_tenant_id_for_slug

REQUIRES_DB = not os.environ.get("DATABASE_URL")
REQUIRES_TENANT_DB = not (os.environ.get("TENANT_DATABASE_URL") or os.environ.get("ALEMBIC_TENANT_DATABASE_URL"))
AUTH_HEADERS = {"host": "pytest.truckerp.me"}


def _tenant_async_url() -> str | None:
    raw = os.environ.get("TENANT_DATABASE_URL") or os.environ.get("ALEMBIC_TENANT_DATABASE_URL")
    if not raw:
        return None
    return to_async_pg_url(raw)


def _cv(data: dict) -> int:
    return int(data["concurrency_version"])


def _detail_code(payload: dict) -> str | None:
    """Extract error code from API JSON (FastAPI may nest detail)."""
    d = payload.get("detail")
    if isinstance(d, dict):
        return d.get("code")
    return None


@pytest.fixture(autouse=True)
def test_bypass_env():
    old = os.environ.get("TEST_BYPASS_AUTH")
    os.environ["TEST_BYPASS_AUTH"] = "1"
    yield
    if old is None:
        os.environ.pop("TEST_BYPASS_AUTH", None)
    else:
        os.environ["TEST_BYPASS_AUTH"] = old


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest.fixture
def override_auth_tenant(test_bypass_env):
    install_host_aligned_current_user_and_tenant(app)
    yield
    clear_current_user_and_tenant_overrides(app)


class TestTripNumberSchema:
    """No database."""

    def test_default_next_numeric_formats_as_prefix_plus_10001(self) -> None:
        """First allocated string is PREFIX + zero-padded DEFAULT_NEXT_TRIP_NUMERIC (see trip_dispatch constants)."""
        from app.constants.trip_dispatch import DEFAULT_NEXT_TRIP_NUMERIC, TRIP_NUMERIC_WIDTH

        prefix = "IKL"
        assert f"{prefix}{DEFAULT_NEXT_TRIP_NUMERIC:0{TRIP_NUMERIC_WIDTH}d}" == "IKL10001"

    def test_load_update_rejects_trip_number(self) -> None:
        from pydantic import ValidationError

        from app.schemas.load import LoadUpdate

        with pytest.raises(ValidationError):
            LoadUpdate(trip_number="IKL10001", expected_concurrency_version=1)

    def test_load_update_rejects_active_dispatch_trip_id(self) -> None:
        from pydantic import ValidationError

        from app.schemas.load import LoadUpdate

        with pytest.raises(ValidationError):
            LoadUpdate(active_dispatch_trip_id=99, expected_concurrency_version=1)

    def test_load_update_rejects_active_trip_id(self) -> None:
        from pydantic import ValidationError

        from app.schemas.load import LoadUpdate

        with pytest.raises(ValidationError):
            LoadUpdate(active_trip_id=99, expected_concurrency_version=1)


@pytest.mark.skipif(REQUIRES_DB, reason="DATABASE_URL required")
class TestTripNumber01Early409:
    """Slice 1: generic PATCH to dispatched is rejected before any numbering/mint."""

    async def test_patch_to_dispatched_returns_deprecated_before_numbering_gate(
        self, client, override_auth_tenant
    ) -> None:
        cr = await client.post(
            "/api/v1/loads",
            headers=AUTH_HEADERS,
            json={"status": "draft", "load_number": f"TRIP409-{uuid.uuid4().hex[:8]}"},
        )
        assert cr.status_code == 201
        load_id = cr.json()["id"]

        patch = await client.patch(
            f"/api/v1/loads/{load_id}",
            headers=AUTH_HEADERS,
            json={"status": "dispatched", "expected_concurrency_version": _cv(cr.json())},
        )
        assert patch.status_code == 409
        assert _detail_code(patch.json()) == LEGACY_LOAD_STATUS_DISPATCH_DEPRECATED


@pytest.mark.skipif(REQUIRES_DB, reason="DATABASE_URL required")
class TestTripNumberAdminPrefix:
    async def test_second_put_returns_409_when_locked(self, client, override_auth_tenant) -> None:
        r0 = await client.get("/api/v1/admin/dispatch-numbering", headers=AUTH_HEADERS)
        assert r0.status_code == 200
        body = r0.json()
        if not body.get("prefix_locked"):
            p1 = f"T{uuid.uuid4().hex[:7].upper()}"
            r1 = await client.put(
                "/api/v1/admin/dispatch-numbering",
                headers=AUTH_HEADERS,
                json={"trip_number_prefix": p1},
            )
            assert r1.status_code == 200
            assert r1.json().get("prefix_locked") is True

        r2 = await client.put(
            "/api/v1/admin/dispatch-numbering",
            headers=AUTH_HEADERS,
            json={"trip_number_prefix": f"T{uuid.uuid4().hex[:7].upper()}"},
        )
        assert r2.status_code == 409
        assert _detail_code(r2.json()) == "TRIP_PREFIX_ALREADY_LOCKED"


@pytest.mark.skipif(REQUIRES_DB, reason="DATABASE_URL required")
class TestTripNumberDispatchLifecycle:
    @pytest.fixture
    async def locked_prefix(self, client, override_auth_tenant) -> str:
        r0 = await client.get("/api/v1/admin/dispatch-numbering", headers=AUTH_HEADERS)
        assert r0.status_code == 200
        body = r0.json()
        if body.get("prefix_locked") and body.get("trip_number_prefix"):
            return str(body["trip_number_prefix"])
        prefix = f"U{uuid.uuid4().hex[:7].upper()}"
        r1 = await client.put(
            "/api/v1/admin/dispatch-numbering",
            headers=AUTH_HEADERS,
            json={"trip_number_prefix": prefix},
        )
        assert r1.status_code == 200, r1.text
        return prefix

    async def _new_draft(self, client, tag: str) -> dict:
        cr = await client.post(
            "/api/v1/loads",
            headers=AUTH_HEADERS,
            json={"status": "draft", "load_number": f"{tag}-{uuid.uuid4().hex[:8]}"},
        )
        assert cr.status_code == 201, cr.text
        return cr.json()

    async def _seed_legacy_dispatched(self, load_id: int) -> None:
        url = _tenant_async_url()
        if url is None:
            pytest.skip("TENANT_DATABASE_URL required to seed legacy dispatched state")
        tenant_id = await platform_tenant_id_for_slug()
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

        engine = create_async_engine(url, pool_pre_ping=True)
        Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
        try:
            async with Session() as session:
                await seed_load_dispatched_legacy_state(session, tenant_id, load_id)
        finally:
            await engine.dispose()

    async def test_patch_to_assigned_is_rejected_and_mints_nothing(
        self, client, override_auth_tenant, locked_prefix
    ) -> None:
        created = await self._new_draft(client, "TRIPAS")
        up = await client.patch(
            f"/api/v1/loads/{created['id']}",
            headers=AUTH_HEADERS,
            json={"status": "assigned", "expected_concurrency_version": _cv(created)},
        )
        assert up.status_code == 409, up.text
        assert _detail_code(up.json()) == LEGACY_LOAD_STATUS_DISPATCH_DEPRECATED
        row = (await client.get(f"/api/v1/loads/{created['id']}", headers=AUTH_HEADERS)).json()
        assert row["status"] == "draft"
        assert row.get("trip_number") in (None, "")
        assert row.get("active_dispatch_trip_id") in (None,)

    async def test_patch_to_dispatched_deprecated_seed_mirrors_trip_numbers(
        self, client, override_auth_tenant, locked_prefix
    ) -> None:
        """Generic PATCH cannot transition to dispatched; service seed matches historical mirrors."""
        created = await self._new_draft(client, "TRIP1")
        load_id = created["id"]

        d1 = await client.patch(
            f"/api/v1/loads/{load_id}",
            headers=AUTH_HEADERS,
            json={"status": "dispatched", "expected_concurrency_version": _cv(created)},
        )
        assert d1.status_code == 409
        assert _detail_code(d1.json()) == LEGACY_LOAD_STATUS_DISPATCH_DEPRECATED

        await self._seed_legacy_dispatched(load_id)
        snap = await client.get(f"/api/v1/loads/{load_id}", headers=AUTH_HEADERS)
        assert snap.status_code == 200
        body = snap.json()
        assert body["status"] == "dispatched"
        tn = body.get("trip_number")
        assert tn
        assert tn.startswith(locked_prefix)
        suffix = tn[len(locked_prefix) :]
        assert len(suffix) == TRIP_NUMERIC_WIDTH
        assert suffix.isdigit()
        tid = body.get("active_dispatch_trip_id")
        assert tid is not None
        assert body.get("active_trip_id") is not None

        d2 = await client.patch(
            f"/api/v1/loads/{load_id}",
            headers=AUTH_HEADERS,
            json={"internal_notes": "noop", "expected_concurrency_version": _cv(body)},
        )
        assert d2.status_code == 200
        assert d2.json().get("trip_number") == tn
        assert d2.json().get("active_dispatch_trip_id") == tid

        d3 = await client.patch(
            f"/api/v1/loads/{load_id}",
            headers=AUTH_HEADERS,
            json={"status": "dispatched", "expected_concurrency_version": _cv(d2.json())},
        )
        assert d3.status_code == 409, d3.text
        assert _detail_code(d3.json()) == LEGACY_LOAD_STATUS_DISPATCH_DEPRECATED
        after = (await client.get(f"/api/v1/loads/{load_id}", headers=AUTH_HEADERS)).json()
        assert after.get("trip_number") == tn
        assert after.get("active_dispatch_trip_id") == tid

    async def test_legacy_row_forward_status_patch_rejected_keeps_trip(
        self, client, override_auth_tenant, locked_prefix
    ) -> None:
        load_id = (await self._new_draft(client, "TRIPFW"))["id"]
        await self._seed_legacy_dispatched(load_id)
        r0 = (await client.get(f"/api/v1/loads/{load_id}", headers=AUTH_HEADERS)).json()
        tn = r0.get("trip_number")
        assert tn

        r1 = await client.patch(
            f"/api/v1/loads/{load_id}",
            headers=AUTH_HEADERS,
            json={"status": "in_transit", "expected_concurrency_version": _cv(r0)},
        )
        assert r1.status_code == 409, r1.text
        assert _detail_code(r1.json()) == LEGACY_LOAD_STATUS_DISPATCH_DEPRECATED
        after = (await client.get(f"/api/v1/loads/{load_id}", headers=AUTH_HEADERS)).json()
        assert after["status"] == "dispatched"
        assert after.get("trip_number") == tn
        assert after.get("active_dispatch_trip_id") == r0.get("active_dispatch_trip_id")

    async def test_legacy_row_back_to_ready_blocked_no_cancel(
        self, client, override_auth_tenant, locked_prefix
    ) -> None:
        """Load PATCH no longer cancels the legacy dispatch trip; leaving dispatched is Issue 0B migration work."""
        load_id = (await self._new_draft(client, "TRIPCN"))["id"]
        await self._seed_legacy_dispatched(load_id)
        snap = (await client.get(f"/api/v1/loads/{load_id}", headers=AUTH_HEADERS)).json()
        assert snap.get("active_trip_id") is not None
        r_back = await client.patch(
            f"/api/v1/loads/{load_id}",
            headers=AUTH_HEADERS,
            json={"status": "ready", "expected_concurrency_version": _cv(snap)},
        )
        assert r_back.status_code == 409, r_back.text
        assert _detail_code(r_back.json()) == LEGACY_LOAD_STATUS_TRANSITION_BLOCKED
        after = (await client.get(f"/api/v1/loads/{load_id}", headers=AUTH_HEADERS)).json()
        assert after["status"] == "dispatched"
        assert after.get("trip_number") == snap.get("trip_number")
        assert after.get("active_dispatch_trip_id") == snap.get("active_dispatch_trip_id")
        assert after.get("active_trip_id") == snap.get("active_trip_id")

    async def test_search_finds_load_by_trip_number(self, client, override_auth_tenant, locked_prefix) -> None:
        load_id = (await self._new_draft(client, "TRIPSCH"))["id"]
        await self._seed_legacy_dispatched(load_id)
        snap = await client.get(f"/api/v1/loads/{load_id}", headers=AUTH_HEADERS)
        tn = snap.json().get("trip_number")
        assert tn
        lr = await client.get(f"/api/v1/loads?search={tn}", headers=AUTH_HEADERS)
        assert lr.status_code == 200
        ids_found = [x["id"] for x in lr.json().get("items", [])]
        assert load_id in ids_found

    async def test_patch_rejects_client_trip_fields_422(self, client, override_auth_tenant) -> None:
        cr = await client.post(
            "/api/v1/loads",
            headers=AUTH_HEADERS,
            json={"status": "draft", "load_number": f"TRIP422-{uuid.uuid4().hex[:8]}"},
        )
        assert cr.status_code == 201
        load_id = cr.json()["id"]
        bad = await client.patch(
            f"/api/v1/loads/{load_id}",
            headers=AUTH_HEADERS,
            json={"trip_number": "HACK99999", "expected_concurrency_version": _cv(cr.json())},
        )
        assert bad.status_code == 422
