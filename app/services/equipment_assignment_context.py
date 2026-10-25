"""Tenant-scoped physical equipment hints backed by explicitly confirmed EQ01 facts.

No Trip, Load, ownership or most-recent-trip fallback: an empty state means
unconfirmed, not unhooked. Planner assignments never assert a physical hook.
"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.equipment_assignment_policy import (
    AssignmentSuggestion, EquipmentContext, suggest_for_driver, suggest_for_truck,
)
from app.services.equipment_state import load_confirmed_equipment_context


async def load_equipment_context(db: AsyncSession, tenant_id: int) -> EquipmentContext:
    # Legacy tenants may not have received EQ01 yet; report no confirmed
    # equipment instead of raising SQL errors or guessing from open Trips.
    available = await db.scalar(
        select(func.to_regclass("public.equipment_current_attachments"))
    )
    if available is None:
        return EquipmentContext()
    return await load_confirmed_equipment_context(db, tenant_id)


async def suggest_assignment_for_driver(
    db: AsyncSession, tenant_id: int, driver_id: int
) -> AssignmentSuggestion:
    return suggest_for_driver(driver_id, await load_equipment_context(db, tenant_id))


async def suggest_assignment_for_truck(
    db: AsyncSession, tenant_id: int, truck_id: int
) -> AssignmentSuggestion:
    return suggest_for_truck(truck_id, await load_equipment_context(db, tenant_id))


def assignment_suggestion_to_hints(
    suggestion: AssignmentSuggestion,
    *,
    anchor_driver_id: int | None = None,
    anchor_truck_id: int | None = None,
) -> dict:
    return {
        "driver_id": suggestion.driver_id if suggestion.driver_id is not None else anchor_driver_id,
        "truck_id": suggestion.truck_id if suggestion.truck_id is not None else anchor_truck_id,
        "trailer_id": suggestion.trailer_id,
        "truck_source": suggestion.truck_source,
        "trailer_source": suggestion.trailer_source,
        "driver_source": suggestion.driver_source,
        "warnings": list(suggestion.warnings),
    }
