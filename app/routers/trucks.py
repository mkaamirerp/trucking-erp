"""Truck API router - tenant-safe CRUD for inventory-only fleet."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field
from fastapi import Request
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps.auth import CurrentUser, get_current_user
from app.deps.admin import has_full_access
from app.models.equipment_attachment import EquipmentCurrentAttachment
from app.models.truck import Truck
from app.services.equipment_state import (
    EquipmentStateError, EquipmentStateConflict, EquipmentStateNotFound,
    change_current_attachment,
)
from app.deps.tenant import require_tenant
from app.deps.tenant_db import get_tenant_db
from app.schemas.dispatch_hints import TruckAssignmentHintsOut, TruckSuggestedTrailerOut
from app.services.equipment_assignment_context import (
    assignment_suggestion_to_hints,
    suggest_assignment_for_truck,
)
from app.schemas.truck import TruckCreate, TruckResponse, TruckUpdate
from app.services import trucks as trucks_service

router = APIRouter(prefix="/trucks", tags=["trucks"])


class EquipmentStateOut(BaseModel):
    truck_id: int
    driver_id: int | None = None
    trailer_id: int | None = None
    version: int = 0


class ConfirmCurrentEquipmentBody(BaseModel):
    driver_id: int = Field(gt=0)
    trailer_id: int = Field(gt=0)
    expected_version: int = Field(ge=0)


class PhysicalEquipmentOperationBody(BaseModel):
    operation: Literal["confirm_driver", "release_driver", "hook_trailer", "drop_trailer"]
    expected_version: int = Field(ge=0)
    driver_id: int | None = None
    trailer_id: int | None = None


def _equipment_out(truck_id: int, row: EquipmentCurrentAttachment | None) -> EquipmentStateOut:
    return EquipmentStateOut(
        truck_id=truck_id,
        driver_id=row.driver_id if row else None,
        trailer_id=row.trailer_id if row else None,
        version=int(row.version) if row else 0,
    )


def _equipment_actor(user: CurrentUser) -> dict:
    return {
        "actor_user_id": int(user.tenant_user.id) if user.tenant_user else None,
        "actor_label": None if user.tenant_user else f"platform:{user.user.id}",
    }


def _require_equipment_write(user: CurrentUser) -> None:
    if not has_full_access(user.role):
        raise HTTPException(status_code=403, detail="FULL_ACCESS required to confirm physical equipment")


async def _require_eq01(db: AsyncSession) -> None:
    available = await db.scalar(select(func.to_regclass("public.equipment_current_attachments")))
    if available is None:
        raise HTTPException(status_code=409, detail="Equipment confirmation unavailable until tenant EQ01 migration")


def _equipment_error(exc: EquipmentStateError) -> HTTPException:
    return HTTPException(
        status_code=404 if isinstance(exc, EquipmentStateNotFound)
        else 409 if isinstance(exc, EquipmentStateConflict) else 422,
        detail=str(exc),
    )


@router.get("/{truck_id}/equipment-state", response_model=EquipmentStateOut)
async def read_current_equipment(
    truck_id: int,
    tenant_id: int = Depends(require_tenant),
    _user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    await _require_eq01(db)
    if not await trucks_service.get_truck(db, tenant_id, truck_id):
        raise HTTPException(status_code=404, detail="Truck not found")
    row = await db.scalar(
        select(EquipmentCurrentAttachment).where(
            EquipmentCurrentAttachment.tenant_id == tenant_id,
            EquipmentCurrentAttachment.truck_id == truck_id,
        )
    )
    return _equipment_out(truck_id, row)


@router.post("/{truck_id}/equipment-state", response_model=EquipmentStateOut)
async def change_physical_equipment(
    truck_id: int,
    body: PhysicalEquipmentOperationBody,
    request: Request,
    tenant_id: int = Depends(require_tenant),
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    _require_equipment_write(user)
    await _require_eq01(db)
    try:
        row = await change_current_attachment(
            db,
            tenant_id=tenant_id, truck_id=truck_id,
            operation=body.operation, expected_version=body.expected_version,
            driver_id=body.driver_id, trailer_id=body.trailer_id,
            request_id=getattr(request.state, "request_id", None),
            **_equipment_actor(user),
        )
        result = _equipment_out(truck_id, row)
        await db.commit()
        return result
    except EquipmentStateError as exc:
        await db.rollback()
        raise _equipment_error(exc) from exc
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Equipment already confirmed on another truck") from exc
    except Exception:
        await db.rollback()
        raise


@router.post("/{truck_id}/confirm-current", response_model=EquipmentStateOut)
async def confirm_current_equipment_pair(
    truck_id: int,
    body: ConfirmCurrentEquipmentBody,
    request: Request,
    tenant_id: int = Depends(require_tenant),
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    """Explicit human confirmation; two strict audit steps in ONE transaction.

    Does not modify any Trip or Load. Different current driver/trailer requires
    separate explicit release/drop; never silently replace physical state.
    """
    _require_equipment_write(user)
    await _require_eq01(db)
    try:
        # Same lock order as EQ02 service: Truck first, attachment second.
        # Prevents stale no-op confirmation and races against Drop/Release.
        owned_truck = await db.scalar(
            select(Truck.id).where(
                Truck.tenant_id == tenant_id, Truck.id == truck_id,
            ).with_for_update()
        )
        if owned_truck is None:
            raise EquipmentStateNotFound("Truck not found in tenant")
        row = await db.scalar(
            select(EquipmentCurrentAttachment).where(
                EquipmentCurrentAttachment.tenant_id == tenant_id,
                EquipmentCurrentAttachment.truck_id == truck_id,
            ).with_for_update()
        )
        if row and int(row.version) != body.expected_version:
            raise EquipmentStateConflict("Equipment state version mismatch")
        if not row and body.expected_version != 0:
            raise EquipmentStateConflict("Equipment state version mismatch")
        if row and (
            row.driver_id not in (None, body.driver_id)
            or row.trailer_id not in (None, body.trailer_id)
        ):
            raise EquipmentStateConflict("Different equipment already confirmed: release/drop first")
        version = body.expected_version
        if row is None or row.driver_id is None:
            row = await change_current_attachment(
                db, tenant_id=tenant_id, truck_id=truck_id,
                operation="confirm_driver", expected_version=version,
                driver_id=body.driver_id,
                request_id=getattr(request.state, "request_id", None),
                **_equipment_actor(user),
            )
            version = int(row.version)
        if row.trailer_id is None:
            row = await change_current_attachment(
                db, tenant_id=tenant_id, truck_id=truck_id,
                operation="hook_trailer", expected_version=version,
                trailer_id=body.trailer_id,
                request_id=getattr(request.state, "request_id", None),
                **_equipment_actor(user),
            )
        result = _equipment_out(truck_id, row)
        await db.commit()
        return result
    except EquipmentStateError as exc:
        await db.rollback()
        raise _equipment_error(exc) from exc
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Driver or trailer is confirmed on another truck") from exc
    except Exception:
        await db.rollback()
        raise



@router.post("", response_model=TruckResponse, status_code=status.HTTP_201_CREATED)
async def create_truck(
    payload: TruckCreate,
    tenant_id: int = Depends(require_tenant),
    _user=Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    return await trucks_service.create_truck(db, tenant_id, payload)


@router.get("", response_model=dict)
async def list_trucks(
    tenant_id: int = Depends(require_tenant),
    _user=Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
    status_filter: Optional[list[str]] = Query(None, alias="status"),
    ownership_type: Optional[str] = Query(None),
    unit_number: Optional[str] = Query(None),
    vin: Optional[str] = Query(None),
    plate_number: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(25, ge=1, le=200),
):
    paged = await trucks_service.list_trucks(
        db,
        tenant_id=tenant_id,
        status_filter=status_filter,
        ownership_type=ownership_type,
        unit_number=unit_number,
        vin=vin,
        plate_number=plate_number,
        page=page,
        size=size,
    )
    items = [TruckResponse.model_validate(item) for item in paged["items"]]
    return {**paged, "items": items}


@router.get("/{truck_id}/assignment-hints", response_model=TruckAssignmentHintsOut)
async def get_truck_assignment_hints(
    truck_id: int,
    tenant_id: int = Depends(require_tenant),
    _user=Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    truck = await trucks_service.get_truck(db, tenant_id, truck_id)
    if not truck:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Truck not found")
    suggestion = await suggest_assignment_for_truck(db, tenant_id, truck_id)
    payload = assignment_suggestion_to_hints(suggestion, anchor_truck_id=truck_id)
    return TruckAssignmentHintsOut(**payload)


@router.get("/{truck_id}/suggested-trailer", response_model=TruckSuggestedTrailerOut)
async def get_truck_suggested_trailer(
    truck_id: int,
    tenant_id: int = Depends(require_tenant),
    _user=Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    truck = await trucks_service.get_truck(db, tenant_id, truck_id)
    if not truck:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Truck not found")

    # A prior Load does not prove the trailer is still physically hooked.
    suggestion = await suggest_assignment_for_truck(db, tenant_id, truck_id)
    return TruckSuggestedTrailerOut(trailer_id=suggestion.trailer_id)



@router.get("/{truck_id}", response_model=TruckResponse)
async def get_truck(
    truck_id: int,
    tenant_id: int = Depends(require_tenant),
    _user=Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    truck = await trucks_service.get_truck(db, tenant_id, truck_id)
    if not truck:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Truck not found")
    return truck


@router.patch("/{truck_id}", response_model=TruckResponse)
async def update_truck(
    truck_id: int,
    payload: TruckUpdate,
    tenant_id: int = Depends(require_tenant),
    _user=Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    return await trucks_service.update_truck(db, tenant_id, truck_id, payload)
