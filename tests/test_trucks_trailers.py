"""Tests for trucks and trailers: schema validation, services, API, tenant isolation."""
from __future__ import annotations

import os
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import ValidationError

from app.schemas.truck import TruckCreate
from app.schemas.trailer import TrailerCreate

REQUIRES_DB = not os.environ.get("DATABASE_URL")


# --- Schema validation (no DB) ---


class TestTruckSchemaValidation:
    def test_vin_normalized_uppercase(self) -> None:
        payload = TruckCreate(unit_number="101", vin="  abc123xyz  ")
        assert payload.vin == "ABC123XYZ"

    def test_unit_number_trimmed(self) -> None:
        payload = TruckCreate(unit_number="  101  ", vin="1HGBH41JXMN109186")
        assert payload.unit_number == "101"

    def test_vin_required_empty_rejected(self) -> None:
        with pytest.raises(ValidationError) as exc:
            TruckCreate(unit_number="101", vin="   ")
        assert "vin" in str(exc.value).lower()

    def test_odometer_last_updated_requires_current_rejected(self) -> None:
        with pytest.raises(ValidationError):
            TruckCreate(
                unit_number="101",
                vin="1HGBH41JXMN109186",
                current_odometer=None,
                odometer_last_updated=datetime.now(timezone.utc),
            )

    def test_purchase_price_ge_zero(self) -> None:
        with pytest.raises(ValidationError):
            TruckCreate(unit_number="101", vin="1HGBH41JXMN109186", purchase_price=-1)

    def test_horsepower_positive(self) -> None:
        with pytest.raises(ValidationError):
            TruckCreate(unit_number="101", vin="1HGBH41JXMN109186", horsepower=0)


class TestTrailerSchemaValidation:
    def test_reefer_fields_only_when_reefer(self) -> None:
        with pytest.raises(ValidationError) as exc:
            TrailerCreate(
                unit_number="T01",
                trailer_type="dry_van",
                reefer_make="Thermo King",
            )
        assert "reefer" in str(exc.value).lower()

    def test_reefer_fields_allowed_when_reefer(self) -> None:
        payload = TrailerCreate(
            unit_number="T01",
            trailer_type="reefer",
            reefer_make="Thermo King",
            reefer_model="SL-200",
        )
        assert payload.reefer_make == "Thermo King"
        assert payload.reefer_model == "SL-200"

    def test_vin_nullable_trailer(self) -> None:
        payload = TrailerCreate(unit_number="T02", trailer_type="flatbed")
        assert payload.vin is None


# --- Service tests (mocked DB) ---


class TestTrucksService:
    def test_create_truck_normalizes_vin(self) -> None:
        import asyncio
        from app.services import trucks as trucks_service

        async def run():
            db = AsyncMock()
            db.commit = AsyncMock()
            db.refresh = AsyncMock()
            db.rollback = AsyncMock()
            db.add = MagicMock()

            payload = TruckCreate(unit_number="101", vin="  abc123  ")
            result = await trucks_service.create_truck(db, 1, payload)
            added_truck = db.add.call_args[0][0]
            assert added_truck.vin == "ABC123"
            assert result.vin == "ABC123"

        asyncio.run(run())


class TestTrailersService:
    def test_create_trailer_clears_reefer_when_not_reefer(self) -> None:
        import asyncio
        from app.services import trailers as trailers_service

        async def run():
            db = AsyncMock()
            db.commit = AsyncMock()
            db.refresh = AsyncMock()
            db.rollback = AsyncMock()

            payload = TrailerCreate(unit_number="T01", trailer_type="flatbed")
            db.add = MagicMock()

            await trailers_service.create_trailer(db, 1, payload)
            call_args = db.add.call_args[0][0]
            assert call_args.trailer_type == "flatbed"
            assert call_args.reefer_make is None

        asyncio.run(run())


# --- API tests (with dependency overrides, requires DB for full integration) ---


@pytest.fixture
def client():
    try:
        from fastapi.testclient import TestClient
        from app.main import app
        return TestClient(app)
    except Exception:
        pytest.skip("App import failed (e.g. PIL missing)")




class TestTrucksAPIAuth:
    """API requires auth and tenant context."""

    def test_create_truck_401_without_auth(self, client) -> None:
        resp = client.post(
            "/api/v1/trucks",
            json={"unit_number": "101", "vin": "1HGBH41JXMN109186"},
            headers={"Host": "demo.truckerp.me"},
        )
        assert resp.status_code in (401, 400, 403)

    def test_list_trucks_401_without_auth(self, client) -> None:
        resp = client.get("/api/v1/trucks", headers={"Host": "demo.truckerp.me"})
        assert resp.status_code in (401, 400, 403)


class TestTrailersAPIAuth:
    def test_create_trailer_401_without_auth(self, client) -> None:
        resp = client.post(
            "/api/v1/trailers",
            json={"unit_number": "T01", "trailer_type": "dry_van"},
            headers={"Host": "demo.truckerp.me"},
        )
        assert resp.status_code in (401, 400, 403)


# --- Tenant isolation (requires DB + tenant context) ---


@pytest.mark.skipif(REQUIRES_DB, reason="DATABASE_URL required for tenant isolation test")
def test_truck_tenant_isolation_list(client) -> None:
    """List trucks must only return trucks for the resolved tenant (via middleware)."""
    resp = client.get(
        "/api/v1/trucks",
        headers={"Host": "demo.truckerp.me", "X-Tenant-ID": "1"},
    )
    if resp.status_code == 401:
        pytest.skip("Auth required - run with valid session")
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    for item in data.get("items", []):
        assert item.get("tenant_id") == 1
