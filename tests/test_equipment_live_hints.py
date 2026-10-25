"""EQ03 regression: confirmed equipment hints and physical API transaction boundaries.

Unit tests only: no database writes, HTTP server, or migration.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.services.equipment_assignment_policy import (
    DriverTruckLink, EquipmentContext, TruckTrailerLink,
)
from app.services import equipment_assignment_context as hints
from app.routers import trucks as trucks_router
from app.services.equipment_state import EquipmentStateConflict


class FakeReadDB:
    def __init__(self, table_present: bool):
        self.table_present = table_present

    async def scalar(self, _stmt):
        return "equipment_current_attachments" if self.table_present else None


@pytest.mark.asyncio
async def test_confirmed_hint_survives_completed_trip_without_trip_query(monkeypatch):
    async def confirmed(_db, tenant_id):
        assert tenant_id == 53
        return EquipmentContext(
            current_driver_trucks=(DriverTruckLink(7, 104),),
            hooked_trailers=(TruckTrailerLink(104, 5307),),
        )
    monkeypatch.setattr(hints, "load_confirmed_equipment_context", confirmed)
    db = FakeReadDB(table_present=True)
    driver = await hints.suggest_assignment_for_driver(db, 53, 7)
    truck = await hints.suggest_assignment_for_truck(db, 53, 104)
    assert (driver.truck_id, driver.trailer_id) == (104, 5307)
    assert (driver.truck_source, driver.trailer_source) == ("current", "hooked")
    assert (truck.driver_id, truck.trailer_id) == (7, 5307)


@pytest.mark.asyncio
async def test_non_migrated_tenant_returns_no_guessed_physical_links(monkeypatch):
    async def unexpected(*_args):
        raise AssertionError("EQ01 projection called on un-migrated tenant")
    monkeypatch.setattr(hints, "load_confirmed_equipment_context", unexpected)
    driver = await hints.suggest_assignment_for_driver(FakeReadDB(False), 53, 7)
    truck = await hints.suggest_assignment_for_truck(FakeReadDB(False), 53, 104)
    assert driver.truck_id is None and driver.trailer_id is None
    assert truck.driver_id is None and truck.trailer_id is None


def test_live_hints_do_not_query_trip_load_or_owner_heuristics():
    contents = Path(hints.__file__).read_text()
    assert "from app.models.trip import" not in contents
    assert "from app.models.load import" not in contents
    assert "owner_person_id" not in contents
    assert "load_confirmed_equipment_context" in contents


class FakeWriteDB:
    def __init__(self, *, existing=None):
        self.existing = existing
        self.calls = 0
        self.commits = 0
        self.rollbacks = 0

    async def scalar(self, _stmt):
        self.calls += 1
        if self.calls == 1:
            return "equipment_current_attachments"
        if self.calls == 2:
            return 104  # SELECT trucks.id FOR UPDATE
        return self.existing

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1


def actor(role="TENANT_ADMIN"):
    return SimpleNamespace(
        role=role, tenant_user=SimpleNamespace(id=19),
        user=SimpleNamespace(id="platform-actor"),
    )


def request():
    return SimpleNamespace(state=SimpleNamespace(request_id="eq03-test"))


@pytest.mark.asyncio
async def test_confirm_pair_is_atomic_audited_commands_without_trip_write(monkeypatch):
    db = FakeWriteDB()
    seen = []
    async def fake_change(_db, **kwargs):
        seen.append(kwargs)
        return SimpleNamespace(
            driver_id=7,
            trailer_id=5307 if len(seen) == 2 else None,
            version=len(seen),
        )
    monkeypatch.setattr(trucks_router, "change_current_attachment", fake_change)
    result = await trucks_router.confirm_current_equipment_pair(
        truck_id=104,
        body=trucks_router.ConfirmCurrentEquipmentBody(
            driver_id=7, trailer_id=5307, expected_version=0
        ),
        request=request(), tenant_id=53, user=actor(), db=db,
    )
    assert result.driver_id == 7 and result.trailer_id == 5307
    assert result.version == 2 and db.commits == 1 and db.rollbacks == 0
    assert [kw["operation"] for kw in seen] == ["confirm_driver", "hook_trailer"]
    assert all(kw["tenant_id"] == 53 and kw["actor_user_id"] == 19 for kw in seen)


@pytest.mark.asyncio
async def test_pair_second_step_failure_rolls_back_both_steps(monkeypatch):
    db = FakeWriteDB()
    seen = []
    async def fake_change(_db, **kwargs):
        seen.append(kwargs)
        if len(seen) == 2:
            raise EquipmentStateConflict("Trailer was already hooked")
        return SimpleNamespace(driver_id=7, trailer_id=None, version=1)
    monkeypatch.setattr(trucks_router, "change_current_attachment", fake_change)
    with pytest.raises(HTTPException) as exc:
        await trucks_router.confirm_current_equipment_pair(
            truck_id=104,
            body=trucks_router.ConfirmCurrentEquipmentBody(
                driver_id=7, trailer_id=5307, expected_version=0
            ),
            request=request(), tenant_id=53, user=actor(), db=db,
        )
    assert exc.value.status_code == 409
    assert db.rollbacks == 1 and db.commits == 0


@pytest.mark.asyncio
async def test_read_only_cannot_confirm_or_release(monkeypatch):
    db = FakeWriteDB()
    async def unexpected(*_args, **_kwargs):
        raise AssertionError("Unauthorized caller passed to write service")
    monkeypatch.setattr(trucks_router, "change_current_attachment", unexpected)
    with pytest.raises(HTTPException) as exc:
        await trucks_router.confirm_current_equipment_pair(
            truck_id=104,
            body=trucks_router.ConfirmCurrentEquipmentBody(
                driver_id=7, trailer_id=5307, expected_version=0
            ),
            request=request(), tenant_id=53, user=actor("TENANT_MEMBER"), db=db,
        )
    assert exc.value.status_code == 403
    assert db.commits == 0 and db.calls == 0


@pytest.mark.asyncio
async def test_cannot_silently_replace_different_current_driver(monkeypatch):
    db = FakeWriteDB(existing=SimpleNamespace(driver_id=11, trailer_id=5307, version=3))
    with pytest.raises(HTTPException) as exc:
        await trucks_router.confirm_current_equipment_pair(
            truck_id=104,
            body=trucks_router.ConfirmCurrentEquipmentBody(
                driver_id=7, trailer_id=5307, expected_version=3
            ),
            request=request(), tenant_id=53, user=actor(), db=db,
        )
    assert exc.value.status_code == 409
    assert db.commits == 0 and db.rollbacks == 1


@pytest.mark.asyncio
async def test_platform_auth_actor_is_audited_without_integer_id(monkeypatch):
    db = FakeWriteDB()
    async def fake_change(_db, **kwargs):
        assert kwargs["actor_user_id"] is None
        assert kwargs["actor_label"] == "platform:platform-actor"
        return SimpleNamespace(driver_id=7, trailer_id=5307, version=2)
    monkeypatch.setattr(trucks_router, "change_current_attachment", fake_change)
    result = await trucks_router.confirm_current_equipment_pair(
        truck_id=104,
        body=trucks_router.ConfirmCurrentEquipmentBody(
            driver_id=7, trailer_id=5307, expected_version=0
        ),
        request=request(),
        tenant_id=53,
        user=SimpleNamespace(role="TENANT_OWNER", tenant_user=None,
                             user=SimpleNamespace(id="platform-actor")),
        db=db,
    )
    assert result.trailer_id == 5307
    assert db.commits == 1


def test_frontend_never_confirms_equipment_during_trip_assignment():
    root = Path(__file__).resolve().parents[1]
    component = (root / "apps/web/src/components/equipment/ConfirmEquipmentAction.tsx").read_text()
    api = (root / "apps/web/src/api.ts").read_text()
    assert "Confirm equipment in use" in component
    assert "window.confirm" in component
    assert "current.trailer_id !== trailerId" in component
    assert "current.driver_id !== driverId" in component
    assert "confirmCurrentEquipment" in api
    assert "updateTripAssignment(" not in component
