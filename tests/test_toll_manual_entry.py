"""Toll MANUAL review-stage foundation. No TollTransaction writes."""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.deps.auth import get_current_user
from app.deps.entitlements import require_admin_sensitive_entitlement
from app.deps.tenant import require_tenant, require_tenant_slug
from app.deps.tenant_db import get_tenant_db
from app.models.base import Base
from app.models.toll import (
    MANUAL_STAGE_DRAFT,
    MANUAL_STAGE_NEEDS_REVIEW,
    SOURCE_TYPE_MANUAL,
    TollManualEntryStage,
    TollTransaction,
)
from app.routers import tolls as tolls_router
from app.services.toll_manual_entry import (
    TollManualEntryError,
    create_manual_stage,
    discard_manual_stage,
    get_manual_stage,
    patch_manual_stage,
    stage_to_dict,
    validate_manual_stage,
)
from tests.test_toll_segment_1 import FORBIDDEN_TOLL_COLUMNS
from tests.test_toll_segment_2 import FakeResult, FakeTollSession, _eq_filters, _stmt_limit_offset


class FakeManualSession(FakeTollSession):
    def __init__(self) -> None:
        super().__init__()
        self.stages: list[TollManualEntryStage] = []

    async def flush(self) -> None:
        if self.raise_on_flush:
            raise RuntimeError("flush failed")
        for obj in self._pending:
            if getattr(obj, "id", None) is None:
                obj.id = self._next_id
                self._next_id += 1
            if isinstance(obj, TollManualEntryStage):
                if obj not in self.stages:
                    self.stages.append(obj)
            elif isinstance(obj, TollTransaction):
                self.transactions.append(obj)
        self._pending.clear()

    async def execute(self, stmt: Any):
        self.execute_calls += 1
        filters = _eq_filters(stmt)
        tenant_id = filters.get("tenant_id")
        object_id = filters.get("id")
        limit, _offset = _stmt_limit_offset(stmt)
        descs = list(getattr(stmt, "column_descriptions", []) or [])
        entities = [d.get("entity") for d in descs]
        if TollManualEntryStage in entities or [d.get("name") for d in descs] == ["TollManualEntryStage"]:
            rows = [
                stage
                for stage in self.stages
                if (tenant_id is None or stage.tenant_id == tenant_id)
                and (object_id is None or stage.id == object_id)
                and stage.status != "DISCARDED"
            ]
            rows.sort(key=lambda stage: int(stage.id or 0), reverse=True)
            if limit is not None:
                rows = rows[:limit]
            return FakeResult(rows)
        return FakeResult([])

    async def scalar(self, stmt: Any):
        result = await self.execute(stmt)
        items = result.scalars().all()
        return items[0] if items else None


VALID_DRAFT = {
    "event_date": "2026-03-01",
    "event_time": "10:15",
    "agency_raw": "ILTOLL",
    "entry_location": "I-90-WEST",
    "exit_location": "I-94-EAST",
    "transponder_number": "02400000001",
    "trip_charge": "7.35",
    "notes": "roadside receipt",
}


def _app(db: FakeManualSession, tenant_id: int = 53) -> FastAPI:
    async def _yield_db():
        yield db

    app = FastAPI()
    app.include_router(tolls_router.router, prefix="/api/v1")
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(user_id="u1")
    app.dependency_overrides[require_admin_sensitive_entitlement] = lambda: None
    app.dependency_overrides[require_tenant] = lambda: tenant_id
    app.dependency_overrides[require_tenant_slug] = lambda: "demo"
    app.dependency_overrides[get_tenant_db] = _yield_db
    return app


@pytest.mark.asyncio
async def test_manual_stage_is_source_type_manual_with_null_file_format() -> None:
    db = FakeManualSession()
    stage = await create_manual_stage(db, tenant_id=7, created_by="u1", payload=VALID_DRAFT)
    assert stage.source_type == SOURCE_TYPE_MANUAL
    assert stage.file_format is None
    payload = stage_to_dict(stage)
    assert payload["source_type"] == "MANUAL"
    assert payload["file_format"] is None
    assert db.transactions == []


@pytest.mark.asyncio
async def test_manual_stage_does_not_require_file_or_provider() -> None:
    db = FakeManualSession()
    stage = await create_manual_stage(db, tenant_id=7, payload={"event_date": "2026-03-01"})
    assert stage.source_type == SOURCE_TYPE_MANUAL
    assert getattr(stage, "source_storage_ref", None) is None
    assert getattr(stage, "provider_connection_id", None) is None
    assert getattr(stage, "account_reference", None) is None
    assert "source_filename" not in TollManualEntryStage.__table__.c.keys()


@pytest.mark.asyncio
async def test_manual_amount_is_decimal_safe() -> None:
    db = FakeManualSession()
    stage = await create_manual_stage(db, tenant_id=7, payload=VALID_DRAFT)
    assert isinstance(stage.trip_charge, Decimal)
    assert stage.trip_charge == Decimal("7.35")
    assert stage_to_dict(stage)["trip_charge"] == "7.35"


@pytest.mark.asyncio
async def test_invalid_amount_rejected() -> None:
    db = FakeManualSession()
    with pytest.raises(TollManualEntryError) as err:
        await create_manual_stage(db, tenant_id=7, payload={**VALID_DRAFT, "trip_charge": "abc"})
    assert err.value.code == "TOLL_MANUAL_INVALID_CHARGE"
    with pytest.raises(TollManualEntryError) as neg:
        await create_manual_stage(db, tenant_id=7, payload={**VALID_DRAFT, "trip_charge": "-1.00"})
    assert neg.value.code == "TOLL_MANUAL_INVALID_CHARGE"
    with pytest.raises(TollManualEntryError) as floated:
        await create_manual_stage(db, tenant_id=7, payload={**VALID_DRAFT, "trip_charge": 1.25})
    assert floated.value.code == "TOLL_MANUAL_INVALID_CHARGE"
    assert db.transactions == []


@pytest.mark.asyncio
async def test_event_date_and_agency_retained() -> None:
    db = FakeManualSession()
    stage = await create_manual_stage(db, tenant_id=7, payload=VALID_DRAFT)
    assert stage.event_date.isoformat() == "2026-03-01"
    assert stage.agency_raw == "ILTOLL"


@pytest.mark.asyncio
async def test_transponder_and_plate_are_optional() -> None:
    db = FakeManualSession()
    stage = await create_manual_stage(
        db,
        tenant_id=7,
        payload={
            "event_date": "2026-03-01",
            "trip_charge": "4.00",
            "unresolved_vehicle_identity": True,
        },
    )
    assert stage.transponder_number is None
    assert stage.plate_number is None
    validated, errors = await validate_manual_stage(db, tenant_id=7, stage_id=stage.id)
    assert errors == []
    assert validated.status == MANUAL_STAGE_NEEDS_REVIEW
    assert validated.vehicle_identity_status == "UNRESOLVED"


@pytest.mark.asyncio
async def test_notes_and_raw_evidence_retained() -> None:
    db = FakeManualSession()
    stage = await create_manual_stage(db, tenant_id=7, payload=VALID_DRAFT)
    assert stage.notes == "roadside receipt"
    assert stage.source_evidence_json["source_type"] == "MANUAL"
    assert stage.source_evidence_json["file_format"] is None


@pytest.mark.asyncio
async def test_manual_tenant_isolation() -> None:
    db = FakeManualSession()
    stage = await create_manual_stage(db, tenant_id=53, payload=VALID_DRAFT)
    with pytest.raises(TollManualEntryError) as err:
        await get_manual_stage(db, tenant_id=54, stage_id=stage.id)
    assert err.value.http_status == 404
    assert err.value.code == "TOLL_MANUAL_NOT_FOUND"


@pytest.mark.asyncio
async def test_patch_edit_before_process_resets_draft() -> None:
    db = FakeManualSession()
    stage = await create_manual_stage(db, tenant_id=7, payload=VALID_DRAFT)
    await validate_manual_stage(db, tenant_id=7, stage_id=stage.id)
    patched = await patch_manual_stage(
        db,
        tenant_id=7,
        stage_id=stage.id,
        patch={"trip_charge": "8.00", "agency_raw": "SCC"},
    )
    assert patched.status == MANUAL_STAGE_DRAFT
    assert patched.trip_charge == Decimal("8.00")
    assert patched.agency_raw == "SCC"
    assert db.transactions == []


@pytest.mark.asyncio
async def test_validation_and_discard() -> None:
    db = FakeManualSession()
    stage = await create_manual_stage(db, tenant_id=7, payload={"event_date": "2026-03-01"})
    draft, errors = await validate_manual_stage(db, tenant_id=7, stage_id=stage.id)
    assert draft.status == MANUAL_STAGE_DRAFT
    assert {item["code"] for item in errors} >= {"TOLL_MANUAL_CHARGE_REQUIRED", "TOLL_MANUAL_VEHICLE_REQUIRED"}
    filled = await patch_manual_stage(db, tenant_id=7, stage_id=stage.id, patch=VALID_DRAFT)
    ok, empty = await validate_manual_stage(db, tenant_id=7, stage_id=filled.id)
    assert empty == []
    assert ok.status == MANUAL_STAGE_NEEDS_REVIEW
    await discard_manual_stage(db, tenant_id=7, stage_id=filled.id)
    with pytest.raises(TollManualEntryError) as err:
        await get_manual_stage(db, tenant_id=7, stage_id=filled.id)
    assert err.value.code == "TOLL_MANUAL_NOT_FOUND"
    assert db.transactions == []


def test_manual_models_have_no_driver_payroll_or_unit_fields() -> None:
    cols = set(TollManualEntryStage.__table__.c.keys())
    forbidden = FORBIDDEN_TOLL_COLUMNS | {
        "truck_id",
        "unit_id",
        "unit_number",
        "driver_id",
        "owner_operator_id",
        "payroll",
        "settlement",
    }
    assert forbidden & cols == set()
    assert "toll_manual_entry_stages" in Base.metadata.tables


def test_manual_http_create_edit_validate_discard_and_isolation() -> None:
    db = FakeManualSession()
    client = TestClient(_app(db, tenant_id=53))
    created = client.post("/api/v1/tolls/manual-entry/stages", json=VALID_DRAFT)
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["source_type"] == "MANUAL"
    assert body["file_format"] is None
    assert body["trip_charge"] == "7.35"
    assert body["event_date"] == "2026-03-01"
    assert body["agency_raw"] == "ILTOLL"
    assert "driver_id" not in body
    assert "owner_operator_id" not in body
    assert "payroll" not in body
    assert "settlement" not in body
    stage_id = body["stage_id"]

    patched = client.patch(
        f"/api/v1/tolls/manual-entry/stages/{stage_id}",
        json={"notes": "updated evidence"},
    )
    assert patched.status_code == 200
    assert patched.json()["status"] == "DRAFT"
    assert patched.json()["notes"] == "updated evidence"

    validated = client.post(f"/api/v1/tolls/manual-entry/stages/{stage_id}/validate")
    assert validated.status_code == 200
    assert validated.json()["ok"] is True
    assert validated.json()["stage"]["status"] == "NEEDS_REVIEW"
    assert "APPROVED" not in validated.json()["stage"]["status"]
    assert db.transactions == []
    assert db.transactions == []

    other = TestClient(_app(db, tenant_id=54))
    missing = other.get(f"/api/v1/tolls/manual-entry/stages/{stage_id}")
    assert missing.status_code == 404

    discarded = client.post(f"/api/v1/tolls/manual-entry/stages/{stage_id}/discard")
    assert discarded.status_code == 200
    gone = client.get(f"/api/v1/tolls/manual-entry/stages/{stage_id}")
    assert gone.status_code == 404
    assert db.transactions == []
