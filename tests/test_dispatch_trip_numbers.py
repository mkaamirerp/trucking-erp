"""Trip number lifecycle: dispatched-only mint, prefix lock, cancel rules, schema guards.

Requires DATABASE_URL (integration), tenant migrations through dispatch_trips / numbering, and
TENANT_DATABASE_URL or ALEMBIC_TENANT_DATABASE_URL for the TRIP_NUMBER_PREFIX_NOT_CONFIGURED test
(which temporarily removes the demo workspace `tenant_dispatch_numbering` row and restores it).

- Fleet: skips if no driver+truck rows.
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
from app.constants.trip_dispatch import TRIP_NUMERIC_WIDTH
from tests.support.dispatch_numbering_test_utils import temporarily_remove_dispatch_numbering_row
from tests.support.integration_auth import (
    clear_current_user_and_tenant_overrides,
    install_host_aligned_current_user_and_tenant,
)
from tests.support.tenant_test_ids import platform_tenant_id_for_slug

REQUIRES_DB = not os.environ.get("DATABASE_URL")
AUTH_HEADERS = {"host": "demo.truckerp.me"}


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


@pytest.fixture
async def demo_workspace_tenant_id():
    return await platform_tenant_id_for_slug("demo")


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
    """Runs before other DB classes (name sorts first): dispatch without locked prefix → 409."""

    async def _first_driver_truck(self, client) -> tuple[int, int] | None:
        dr = await client.get("/api/v1/drivers?limit=5", headers=AUTH_HEADERS)
        tr = await client.get("/api/v1/trucks?page=1&size=5", headers=AUTH_HEADERS)
        if dr.status_code != 200 or tr.status_code != 200:
            return None
        dlist = dr.json()
        titems = tr.json().get("items") or []
        if not dlist or not titems:
            return None
        return int(dlist[0]["id"]), int(titems[0]["id"])

    async def test_dispatch_without_locked_prefix_returns_409(
        self, client, override_auth_tenant, demo_workspace_tenant_id
    ) -> None:
        async with temporarily_remove_dispatch_numbering_row(demo_workspace_tenant_id):
            r0 = await client.get("/api/v1/admin/dispatch-numbering", headers=AUTH_HEADERS)
            assert r0.status_code == 200
            assert r0.json().get("prefix_locked") is False

            ids = await self._first_driver_truck(client)
            if ids is None:
                pytest.skip("No driver/truck in tenant DB")
            driver_id, truck_id = ids

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
                json={
                    "driver_id": driver_id,
                    "truck_id": truck_id,
                    "status": "dispatched",
                    "expected_concurrency_version": _cv(cr.json()),
                },
            )
            assert patch.status_code == 409
            assert _detail_code(patch.json()) == "TRIP_NUMBER_PREFIX_NOT_CONFIGURED"


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

    async def _first_driver_truck(self, client) -> tuple[int, int] | None:
        dr = await client.get("/api/v1/drivers?limit=5", headers=AUTH_HEADERS)
        tr = await client.get("/api/v1/trucks?page=1&size=5", headers=AUTH_HEADERS)
        if dr.status_code != 200 or tr.status_code != 200:
            return None
        dlist = dr.json()
        titems = tr.json().get("items") or []
        if not dlist or not titems:
            return None
        return int(dlist[0]["id"]), int(titems[0]["id"])

    async def test_assigned_alone_does_not_mint_trip(self, client, override_auth_tenant, locked_prefix) -> None:
        ids = await self._first_driver_truck(client)
        if ids is None:
            pytest.skip("No driver/truck in tenant DB")
        driver_id, truck_id = ids

        cr = await client.post(
            "/api/v1/loads",
            headers=AUTH_HEADERS,
            json={"status": "draft", "load_number": f"TRIPAS-{uuid.uuid4().hex[:8]}"},
        )
        assert cr.status_code == 201
        load_id = cr.json()["id"]

        up = await client.patch(
            f"/api/v1/loads/{load_id}",
            headers=AUTH_HEADERS,
            json={
                "driver_id": driver_id,
                "truck_id": truck_id,
                "status": "assigned",
                "expected_concurrency_version": _cv(cr.json()),
            },
        )
        assert up.status_code == 200
        data = up.json()
        assert data["status"] == "assigned"
        assert data.get("trip_number") in (None, "")
        assert data.get("active_dispatch_trip_id") in (None,)

    async def test_first_dispatched_mints_one_trip(self, client, override_auth_tenant, locked_prefix) -> None:
        ids = await self._first_driver_truck(client)
        if ids is None:
            pytest.skip("No driver/truck in tenant DB")
        driver_id, truck_id = ids

        cr = await client.post(
            "/api/v1/loads",
            headers=AUTH_HEADERS,
            json={"status": "draft", "load_number": f"TRIP1-{uuid.uuid4().hex[:8]}"},
        )
        assert cr.status_code == 201
        load_id = cr.json()["id"]

        d1 = await client.patch(
            f"/api/v1/loads/{load_id}",
            headers=AUTH_HEADERS,
            json={
                "driver_id": driver_id,
                "truck_id": truck_id,
                "status": "dispatched",
                "expected_concurrency_version": _cv(cr.json()),
            },
        )
        assert d1.status_code == 200, d1.text
        body = d1.json()
        assert body["status"] == "dispatched"
        tn = body.get("trip_number")
        assert tn, body
        assert tn.startswith(locked_prefix)
        suffix = tn[len(locked_prefix) :]
        assert len(suffix) == TRIP_NUMERIC_WIDTH
        assert suffix.isdigit()
        tid = body.get("active_dispatch_trip_id")
        assert tid is not None

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
        assert d3.status_code == 200, d3.text
        assert d3.json().get("trip_number") == tn
        assert d3.json().get("active_dispatch_trip_id") == tid

    async def test_forward_in_transit_does_not_clear_trip(self, client, override_auth_tenant, locked_prefix) -> None:
        ids = await self._first_driver_truck(client)
        if ids is None:
            pytest.skip("No driver/truck in tenant DB")
        driver_id, truck_id = ids

        cr = await client.post(
            "/api/v1/loads",
            headers=AUTH_HEADERS,
            json={"status": "draft", "load_number": f"TRIPFW-{uuid.uuid4().hex[:8]}"},
        )
        assert cr.status_code == 201
        load_id = cr.json()["id"]
        d_disp = await client.patch(
            f"/api/v1/loads/{load_id}",
            headers=AUTH_HEADERS,
            json={
                "driver_id": driver_id,
                "truck_id": truck_id,
                "status": "dispatched",
                "expected_concurrency_version": _cv(cr.json()),
            },
        )
        assert d_disp.status_code == 200, d_disp.text
        r0 = await client.get(f"/api/v1/loads/{load_id}", headers=AUTH_HEADERS)
        tn = r0.json().get("trip_number")
        assert tn

        r1 = await client.patch(
            f"/api/v1/loads/{load_id}",
            headers=AUTH_HEADERS,
            json={"status": "in_transit", "expected_concurrency_version": _cv(d_disp.json())},
        )
        assert r1.status_code == 200, r1.text
        assert r1.json().get("trip_number") == tn
        assert r1.json().get("active_dispatch_trip_id") is not None

    async def test_back_to_ready_cancels_and_clears_read_model(self, client, override_auth_tenant, locked_prefix) -> None:
        ids = await self._first_driver_truck(client)
        if ids is None:
            pytest.skip("No driver/truck in tenant DB")
        driver_id, truck_id = ids

        cr = await client.post(
            "/api/v1/loads",
            headers=AUTH_HEADERS,
            json={"status": "draft", "load_number": f"TRIPCN-{uuid.uuid4().hex[:8]}"},
        )
        assert cr.status_code == 201
        load_id = cr.json()["id"]
        d_disp = await client.patch(
            f"/api/v1/loads/{load_id}",
            headers=AUTH_HEADERS,
            json={
                "driver_id": driver_id,
                "truck_id": truck_id,
                "status": "dispatched",
                "expected_concurrency_version": _cv(cr.json()),
            },
        )
        assert d_disp.status_code == 200, d_disp.text
        r_back = await client.patch(
            f"/api/v1/loads/{load_id}",
            headers=AUTH_HEADERS,
            json={"status": "ready", "expected_concurrency_version": _cv(d_disp.json())},
        )
        assert r_back.status_code == 200, r_back.text
        body = r_back.json()
        assert body["status"] == "ready"
        assert body.get("trip_number") in (None, "")
        assert body.get("active_dispatch_trip_id") in (None,)

    async def test_search_finds_load_by_trip_number(self, client, override_auth_tenant, locked_prefix) -> None:
        ids = await self._first_driver_truck(client)
        if ids is None:
            pytest.skip("No driver/truck in tenant DB")
        driver_id, truck_id = ids

        cr = await client.post(
            "/api/v1/loads",
            headers=AUTH_HEADERS,
            json={"status": "draft", "load_number": f"TRIPSCH-{uuid.uuid4().hex[:8]}"},
        )
        assert cr.status_code == 201
        load_id = cr.json()["id"]
        d = await client.patch(
            f"/api/v1/loads/{load_id}",
            headers=AUTH_HEADERS,
            json={
                "driver_id": driver_id,
                "truck_id": truck_id,
                "status": "dispatched",
                "expected_concurrency_version": _cv(cr.json()),
            },
        )
        assert d.status_code == 200
        tn = d.json().get("trip_number")
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
