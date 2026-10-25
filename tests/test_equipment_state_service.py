"""EQ02 unit contract tests. No DB, no HTTP, no migration or deployment."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.models.driver import Driver
from app.models.equipment_attachment import DriverEquipmentDefault, EquipmentCurrentAttachment
from app.models.trailer import Trailer
from app.models.truck import Truck
from app.services import equipment_state as service
from app.services.equipment_assignment_policy import suggest_for_driver, suggest_for_truck


class FakeScalars:
    def __init__(self, rows):
        self.rows = rows

    def all(self):
        return self.rows


class FakeSession:
    def __init__(self):
        self.driver = Driver(id=7, tenant_id=53, first_name="Test", last_name="Driver")
        self.truck = Truck(id=104, tenant_id=53, unit_number="104", vin="EQ02TRUCK")
        self.trailer = Trailer(id=5307, tenant_id=53, unit_number="5307")
        self.current = None
        self.default = None
        self.flush_count = 0
        self.commits = 0

    def _entity(self, statement):
        return statement.column_descriptions[0]["entity"]

    async def scalar(self, statement):
        entity = self._entity(statement)
        if entity is Driver:
            return self.driver.id
        if entity is Truck:
            return self.truck.id
        if entity is Trailer:
            return self.trailer.id
        if entity is EquipmentCurrentAttachment:
            return self.current
        if entity is DriverEquipmentDefault:
            return self.default
        raise AssertionError(f"Unexpected entity {entity}")

    async def scalars(self, statement):
        entity = self._entity(statement)
        if entity is EquipmentCurrentAttachment:
            return FakeScalars([self.current] if self.current else [])
        if entity is DriverEquipmentDefault:
            return FakeScalars([self.default] if self.default else [])
        raise AssertionError(f"Unexpected collection {entity}")

    def add(self, row):
        if isinstance(row, EquipmentCurrentAttachment):
            assert self.current is None
            self.current = row
        elif isinstance(row, DriverEquipmentDefault):
            assert self.default is None
            self.default = row
        else:
            raise AssertionError("Unexpected add")

    async def flush(self):
        self.flush_count += 1

    async def commit(self):
        self.commits += 1


@pytest.fixture
def fake(monkeypatch):
    db = FakeSession()
    audits = []
    async def capture(_db, **kwargs):
        audits.append(kwargs)
        assert kwargs["best_effort"] is False
        assert kwargs["actor_user_id"] == 19
    monkeypatch.setattr(service, "write_audit_event", capture)
    return db, audits


def current_args(db, *, operation, expected_version, driver_id=None, trailer_id=None):
    return service.change_current_attachment(
        db,
        tenant_id=53, truck_id=104, operation=operation,
        expected_version=expected_version, actor_user_id=19,
        driver_id=driver_id, trailer_id=trailer_id,
        request_id="eq02-test",
    )


@pytest.mark.asyncio
async def test_confirm_hook_trip_completion_independent_drop_and_release(fake):
    db, audits = fake
    row = await current_args(db, operation="confirm_driver", expected_version=0, driver_id=7)
    assert (row.driver_id, row.trailer_id, row.version) == (7, None, 1)
    row = await current_args(db, operation="hook_trailer", expected_version=1, trailer_id=5307)
    assert (row.driver_id, row.trailer_id, row.version) == (7, 5307, 2)

    # No Trip references or implicit completion-triggered release exist here.
    context = await service.load_confirmed_equipment_context(db, 53)
    assert suggest_for_driver(7, context).trailer_id == 5307
    assert suggest_for_truck(104, context).driver_id == 7

    row = await current_args(db, operation="drop_trailer", expected_version=2)
    assert (row.driver_id, row.trailer_id, row.version) == (7, None, 3)
    row = await current_args(db, operation="release_driver", expected_version=3)
    assert (row.driver_id, row.trailer_id, row.version) == (None, None, 4)
    assert [event["action"] for event in audits] == [
        "equipment_confirm_driver", "equipment_hook_trailer",
        "equipment_drop_trailer", "equipment_release_driver",
    ]
    assert db.commits == 0


@pytest.mark.asyncio
async def test_stale_version_rejected_without_mutation_or_audit(fake):
    db, audits = fake
    await current_args(db, operation="confirm_driver", expected_version=0, driver_id=7)
    with pytest.raises(service.EquipmentStateConflict, match="version mismatch"):
        await current_args(db, operation="hook_trailer", expected_version=0, trailer_id=5307)
    assert db.current.version == 1 and db.current.trailer_id is None
    assert len(audits) == 1


@pytest.mark.asyncio
async def test_noop_does_not_inflate_event_or_version(fake):
    db, audits = fake
    await current_args(db, operation="confirm_driver", expected_version=0, driver_id=7)
    again = await current_args(db, operation="confirm_driver", expected_version=1, driver_id=7)
    assert again.version == 1
    assert len(audits) == 1
    assert db.flush_count == 1


@pytest.mark.asyncio
async def test_replacements_and_missing_release_require_explicit_actions(fake):
    db, audits = fake
    with pytest.raises(service.EquipmentStateConflict, match="No confirmed association"):
        await current_args(db, operation="drop_trailer", expected_version=0)
    await current_args(db, operation="hook_trailer", expected_version=0, trailer_id=5307)
    # A hook is never implicitly replaced by a different trailer.
    with pytest.raises(service.EquipmentStateConflict, match="Drop existing trailer"):
        await current_args(db, operation="hook_trailer", expected_version=1, trailer_id=6201)
    assert db.current.trailer_id == 5307
    assert len(audits) == 1


@pytest.mark.asyncio
async def test_default_does_not_imply_physical_attachment(fake):
    db, audits = fake
    default = await service.set_driver_equipment_default(
        db, tenant_id=53, driver_id=7, default_truck_id=104,
        equipment_binding_mode="dedicated", actor_user_id=19,
        expected_before=None,
    )
    assert (default.default_truck_id, default.equipment_binding_mode) == (104, "dedicated")
    assert db.current is None
    context = await service.load_confirmed_equipment_context(db, 53)
    suggested = suggest_for_driver(7, context)
    assert (suggested.truck_id, suggested.trailer_id) == (104, None)
    assert suggested.truck_source == "default"
    assert len(audits) == 1 and audits[0]["action"] == "equipment_default_set"
    with pytest.raises(service.EquipmentStateConflict, match="changed since"):
        await service.set_driver_equipment_default(
            db, tenant_id=53, driver_id=7, default_truck_id=None,
            equipment_binding_mode="pooled", actor_user_id=19,
            expected_before=(None, "pooled"),
        )


@pytest.mark.asyncio
async def test_invalid_identity_operation_or_actor_fails_closed(fake):
    db, audits = fake
    with pytest.raises(service.EquipmentStateError, match="actor_user_id"):
        await service.change_current_attachment(
            db, tenant_id=53, truck_id=104, operation="confirm_driver",
            expected_version=0, actor_user_id=0, driver_id=7
        )
    with pytest.raises(service.EquipmentStateError, match="Unknown equipment operation"):
        await current_args(db, operation="plan_trip", expected_version=0)
    with pytest.raises(service.EquipmentStateError, match="cannot also change"):
        await current_args(db, operation="confirm_driver", expected_version=0, driver_id=7, trailer_id=5307)
    assert db.current is None
    assert audits == []


@pytest.mark.asyncio
async def test_audit_failure_propagates_without_committing(fake, monkeypatch):
    db, _ = fake
    async def audit_failure(*_args, **_kwargs):
        raise RuntimeError("audit unavailable")
    monkeypatch.setattr(service, "write_audit_event", audit_failure)
    with pytest.raises(RuntimeError, match="audit unavailable"):
        await current_args(db, operation="confirm_driver", expected_version=0, driver_id=7)
    assert db.commits == 0


def test_no_trip_load_or_legacy_assignment_writes_in_service():
    from pathlib import Path
    path = Path(service.__file__)
    content = path.read_text()
    assert "from app.models.trip import" not in content
    assert "from app.models.load import" not in content
    assert "await db.commit(" not in content
    assert "best_effort=False" in content
