"""EQ02 — tenant-scoped, explicitly confirmed physical equipment state.

No HTTP routes, migration, Trip/Load writes, or commit in this service.
The caller must enforce authenticated RBAC, supply the operator identity,
and commit or rollback the entire transaction. All state changes are audited
in that SAME tenant transaction (strict audit, never best effort).

A current driver–truck association is not a Trip assignment. A physical
trailer hook is not a custody/Load transition. Trip completion never calls
these commands. Caller-provided expected_version prevents stale edits.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.driver import Driver
from app.models.equipment_attachment import DriverEquipmentDefault, EquipmentCurrentAttachment
from app.models.trailer import Trailer
from app.models.truck import Truck
from app.services.audit_events import write_audit_event
from app.services.equipment_assignment_policy import (
    DriverTruckLink,
    EquipmentContext,
    TruckTrailerLink,
)


class EquipmentStateError(ValueError):
    """Invalid physical-state command; transaction should not be committed."""


class EquipmentStateConflict(EquipmentStateError):
    """Stale version, missing current link, or replacement without explicit release."""


class EquipmentStateNotFound(EquipmentStateError):
    """Asset is absent from the specified tenant (no cross-tenant disclosure)."""


def _id(value: int, name: str) -> int:
    if type(value) is not int or value <= 0:
        raise EquipmentStateError(f"{name} must be a positive integer")
    return value


def _require_actor(actor_user_id: int) -> int:
    return _id(actor_user_id, "actor_user_id")


async def _require_asset(
    db: AsyncSession, tenant_id: int, entity: type, asset_id: int
) -> None:
    found = await db.scalar(
        select(entity.id).where(entity.tenant_id == tenant_id, entity.id == asset_id)
    )
    if found is None:
        raise EquipmentStateNotFound("Equipment identity not found in tenant")


async def _lock_truck(db: AsyncSession, tenant_id: int, truck_id: int) -> None:
    # Serializes first-insert and update for this truck, even if no current row
    # exists yet. Distinct trucks racing for one trailer/driver are protected by
    # the EQ01 partial-unique indexes (IntegrityError -> caller rollback).
    found = await db.scalar(
        select(Truck.id)
        .where(Truck.tenant_id == tenant_id, Truck.id == truck_id)
        .with_for_update()
    )
    if found is None:
        raise EquipmentStateNotFound("Truck not found in tenant")


def _physical_snapshot(row: EquipmentCurrentAttachment | None, truck_id: int) -> dict:
    return {
        "truck_id": truck_id,
        "driver_id": row.driver_id if row else None,
        "trailer_id": row.trailer_id if row else None,
    }


async def _audit(
    db: AsyncSession,
    *,
    tenant_id: int,
    entity_type: str,
    entity_id: int,
    action: str,
    actor_user_id: int,
    before: dict,
    after: dict,
    request_id: str | None,
) -> None:
    await write_audit_event(
        db,
        tenant_id=tenant_id,
        module="fleet",
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        source="api",
        actor_user_id=actor_user_id,
        request_id=request_id,
        snapshot_before=before,
        snapshot_after=after,
        best_effort=False,
    )


async def change_current_attachment(
    db: AsyncSession,
    *,
    tenant_id: int,
    truck_id: int,
    operation: Literal[
        "confirm_driver", "release_driver", "hook_trailer", "drop_trailer"
    ],
    expected_version: int,
    actor_user_id: int,
    driver_id: int | None = None,
    trailer_id: int | None = None,
    request_id: str | None = None,
) -> EquipmentCurrentAttachment:
    """Apply ONE explicitly confirmed physical change.

    expected_version=0 means no row may exist yet. For an existing row,
    the version MUST match, including no-op replays. Replacing an existing
    driver or trailer requires the explicit release/drop first. The service
    does not auto-commit and never changes Trip, Load, or driver duty state.

    Unique-claim races across different trucks raise SQLAlchemy IntegrityError;
    the caller must rollback the transaction and show a conflict.
    """
    tenant_id = _id(tenant_id, "tenant_id")
    truck_id = _id(truck_id, "truck_id")
    _require_actor(actor_user_id)
    if type(expected_version) is not int or expected_version < 0:
        raise EquipmentStateError("expected_version must be a nonnegative integer")
    if operation not in {"confirm_driver", "release_driver", "hook_trailer", "drop_trailer"}:
        raise EquipmentStateError("Unknown equipment operation")
    if operation == "confirm_driver":
        driver_id = _id(driver_id, "driver_id")
        if trailer_id is not None:
            raise EquipmentStateError("confirm_driver cannot also change trailer")
        await _require_asset(db, tenant_id, Driver, driver_id)
    elif operation == "hook_trailer":
        trailer_id = _id(trailer_id, "trailer_id")
        if driver_id is not None:
            raise EquipmentStateError("hook_trailer cannot also change driver")
        await _require_asset(db, tenant_id, Trailer, trailer_id)
    elif driver_id is not None or trailer_id is not None:
        raise EquipmentStateError("release/drop operations do not accept equipment IDs")

    await _lock_truck(db, tenant_id, truck_id)
    row = await db.scalar(
        select(EquipmentCurrentAttachment)
        .where(
            EquipmentCurrentAttachment.tenant_id == tenant_id,
            EquipmentCurrentAttachment.truck_id == truck_id,
        )
        .with_for_update()
    )
    if row is None and expected_version != 0:
        raise EquipmentStateConflict("No confirmed row exists at expected_version")
    if row is not None and int(row.version) != expected_version:
        raise EquipmentStateConflict("Equipment state version mismatch")
    if row is None and operation in {"release_driver", "drop_trailer"}:
        raise EquipmentStateConflict("No confirmed association to release")

    before = _physical_snapshot(row, truck_id)
    existing_driver = row.driver_id if row else None
    existing_trailer = row.trailer_id if row else None
    if operation == "confirm_driver":
        if existing_driver is not None and existing_driver != driver_id:
            raise EquipmentStateConflict("Release existing driver before changing drivers")
        new_driver, new_trailer = driver_id, existing_trailer
    elif operation == "release_driver":
        new_driver, new_trailer = None, existing_trailer
    elif operation == "hook_trailer":
        if existing_trailer is not None and existing_trailer != trailer_id:
            raise EquipmentStateConflict("Drop existing trailer before changing trailers")
        new_driver, new_trailer = existing_driver, trailer_id
    else:
        new_driver, new_trailer = existing_driver, None

    # A no-op is not another physical event. The matching version is still
    # required; a stale request must never appear to succeed silently.
    if new_driver == existing_driver and new_trailer == existing_trailer:
        return row

    now = datetime.now(timezone.utc)
    if row is None:
        row = EquipmentCurrentAttachment(
            tenant_id=tenant_id,
            truck_id=truck_id,
            driver_id=new_driver,
            trailer_id=new_trailer,
            version=1,
            confirmed_at=now,
            updated_at=now,
        )
        db.add(row)
    else:
        row.driver_id = new_driver
        row.trailer_id = new_trailer
        row.version = expected_version + 1
        row.confirmed_at = now
        row.updated_at = now

    # Strict flush precedes audit. An audit failure rolls back the same
    # transaction via the existing audit writer; no commit is made here.
    await db.flush()
    await _audit(
        db,
        tenant_id=tenant_id,
        entity_type="equipment_current_attachment",
        entity_id=truck_id,
        action=f"equipment_{operation}",
        actor_user_id=actor_user_id,
        before=before,
        after=_physical_snapshot(row, truck_id),
        request_id=request_id,
    )
    return row


async def set_driver_equipment_default(
    db: AsyncSession,
    *,
    tenant_id: int,
    driver_id: int,
    default_truck_id: int | None,
    equipment_binding_mode: Literal["dedicated", "owner_bound", "shift_based", "pooled"],
    actor_user_id: int,
    expected_before: tuple[int | None, str] | None,
    request_id: str | None = None,
) -> DriverEquipmentDefault:
    """Update an equipment preference, NOT current physical attachment.

    expected_before=None asserts that the row does not exist. Otherwise it
    must exactly match (truck_id, binding_mode), preventing lost updates.
    """
    tenant_id = _id(tenant_id, "tenant_id")
    driver_id = _id(driver_id, "driver_id")
    _require_actor(actor_user_id)
    if default_truck_id is not None:
        default_truck_id = _id(default_truck_id, "default_truck_id")
    if equipment_binding_mode not in {"dedicated", "owner_bound", "shift_based", "pooled"}:
        raise EquipmentStateError("Unknown equipment binding mode")
    # Lock driver identity to serialize even simultaneous first inserts.
    driver = await db.scalar(
        select(Driver.id).where(Driver.tenant_id == tenant_id, Driver.id == driver_id).with_for_update()
    )
    if driver is None:
        raise EquipmentStateNotFound("Driver not found in tenant")
    if default_truck_id is not None:
        await _require_asset(db, tenant_id, Truck, default_truck_id)

    row = await db.scalar(
        select(DriverEquipmentDefault)
        .where(
            DriverEquipmentDefault.tenant_id == tenant_id,
            DriverEquipmentDefault.driver_id == driver_id,
        )
        .with_for_update()
    )
    if row is None and expected_before is not None:
        raise EquipmentStateConflict("Equipment default was removed or never existed")
    if row is not None and expected_before != (row.default_truck_id, row.equipment_binding_mode):
        raise EquipmentStateConflict("Equipment default changed since it was read")
    before = {
        "driver_id": driver_id,
        "default_truck_id": row.default_truck_id if row else None,
        "equipment_binding_mode": row.equipment_binding_mode if row else None,
    }
    after = {
        "driver_id": driver_id,
        "default_truck_id": default_truck_id,
        "equipment_binding_mode": equipment_binding_mode,
    }
    if before == after:
        return row

    now = datetime.now(timezone.utc)
    if row is None:
        row = DriverEquipmentDefault(
            tenant_id=tenant_id,
            driver_id=driver_id,
            default_truck_id=default_truck_id,
            equipment_binding_mode=equipment_binding_mode,
            created_at=now,
            updated_at=now,
        )
        db.add(row)
    else:
        row.default_truck_id = default_truck_id
        row.equipment_binding_mode = equipment_binding_mode
        row.updated_at = now
    await db.flush()
    await _audit(
        db,
        tenant_id=tenant_id,
        entity_type="driver_equipment_default",
        entity_id=driver_id,
        action="equipment_default_set",
        actor_user_id=actor_user_id,
        before=before,
        after=after,
        request_id=request_id,
    )
    return row


async def load_confirmed_equipment_context(
    db: AsyncSession, tenant_id: int
) -> EquipmentContext:
    """Read only EQ01-confirmed state; NEVER consult Trip, Load, owner, or duty."""
    tenant_id = _id(tenant_id, "tenant_id")
    currents = (
        await db.scalars(
            select(EquipmentCurrentAttachment).where(
                EquipmentCurrentAttachment.tenant_id == tenant_id
            )
        )
    ).all()
    defaults = (
        await db.scalars(
            select(DriverEquipmentDefault).where(
                DriverEquipmentDefault.tenant_id == tenant_id
            )
        )
    ).all()
    return EquipmentContext(
        current_driver_trucks=tuple(
            DriverTruckLink(int(row.driver_id), int(row.truck_id))
            for row in currents if row.driver_id is not None
        ),
        hooked_trailers=tuple(
            TruckTrailerLink(int(row.truck_id), int(row.trailer_id))
            for row in currents if row.trailer_id is not None
        ),
        default_driver_trucks=tuple(
            DriverTruckLink(int(row.driver_id), int(row.default_truck_id))
            for row in defaults if row.default_truck_id is not None
        ),
    )
