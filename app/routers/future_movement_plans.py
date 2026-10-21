from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.authz.enforce import require_pilot_capability
from app.deps.auth import CurrentUser, get_current_user
from app.deps.tenant import require_tenant
from app.deps.tenant_db import get_tenant_db
from app.schemas.future_movement_plan import (
    FutureMovementConvertBody,
    FutureMovementPlanCreate,
    FutureMovementPlanListPage,
    FutureMovementPlanOut,
    FutureMovementPlanCancelBody,
    FutureMovementPlanUpdate,
    YardDropInstructionBody,
)
from app.schemas.trip_read import TripDetailResponse
from app.services import future_movement_plans as fmp_service

router = APIRouter(prefix="/future-movement-plans", tags=["future-movement-plans"])


@router.post("", response_model=FutureMovementPlanOut, status_code=status.HTTP_201_CREATED)
async def create_plan(
    body: FutureMovementPlanCreate,
    tenant_id: int = Depends(require_tenant),
    user: CurrentUser = Depends(require_pilot_capability("trips.records", "create")),
    db: AsyncSession = Depends(get_tenant_db),
) -> FutureMovementPlanOut:
    out = await fmp_service.create_future_movement_plan(
        db,
        tenant_id,
        body,
        actor_user_id=int(user.tenant_user.id) if user.tenant_user else None,
    )
    await db.commit()
    return out


@router.get("", response_model=FutureMovementPlanListPage)
async def list_plans(
    tenant_id: int = Depends(require_tenant),
    _user: CurrentUser = Depends(require_pilot_capability("trips.records", "view")),
    db: AsyncSession = Depends(get_tenant_db),
    status_filter: str | None = Query(default="unassigned", alias="status"),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=50, ge=1, le=200),
) -> FutureMovementPlanListPage:
    return await fmp_service.list_future_movement_plans(
        db, tenant_id, status_filter=status_filter, page=page, size=size
    )


@router.get("/terminal-pool-loads")
async def terminal_pool_loads(
    terminal_id: int = Query(..., ge=1),
    tenant_id: int = Depends(require_tenant),
    _user: CurrentUser = Depends(require_pilot_capability("trips.records", "view")),
    db: AsyncSession = Depends(get_tenant_db),
):
    return {
        "items": await fmp_service.list_terminal_pool_ready_loads(db, tenant_id, terminal_id)
    }


@router.get("/{plan_id}", response_model=FutureMovementPlanOut)
async def get_plan(
    plan_id: int,
    tenant_id: int = Depends(require_tenant),
    _user: CurrentUser = Depends(require_pilot_capability("trips.records", "view")),
    db: AsyncSession = Depends(get_tenant_db),
) -> FutureMovementPlanOut:
    return await fmp_service.get_future_movement_plan(db, tenant_id, plan_id)


@router.put("/{plan_id}", response_model=FutureMovementPlanOut)
async def update_plan(
    plan_id: int,
    body: FutureMovementPlanUpdate,
    tenant_id: int = Depends(require_tenant),
    _user: CurrentUser = Depends(require_pilot_capability("trips.records", "create")),
    db: AsyncSession = Depends(get_tenant_db),
) -> FutureMovementPlanOut:
    out = await fmp_service.update_future_movement_plan(db, tenant_id, plan_id, body)
    await db.commit()
    return out


@router.post("/{plan_id}/cancel", response_model=FutureMovementPlanOut)
async def cancel_plan(
    plan_id: int,
    body: FutureMovementPlanCancelBody,
    tenant_id: int = Depends(require_tenant),
    _user: CurrentUser = Depends(require_pilot_capability("trips.records", "cancel")),
    db: AsyncSession = Depends(get_tenant_db),
) -> FutureMovementPlanOut:
    out = await fmp_service.cancel_future_movement_plan(
        db, tenant_id, plan_id, concurrency_version=body.concurrency_version
    )
    await db.commit()
    return out


@router.post("/{plan_id}/convert", response_model=TripDetailResponse)
async def convert_plan(
    plan_id: int,
    body: FutureMovementConvertBody,
    tenant_id: int = Depends(require_tenant),
    user: CurrentUser = Depends(require_pilot_capability("trips.records", "create")),
    db: AsyncSession = Depends(get_tenant_db),
) -> TripDetailResponse:
    out = await fmp_service.convert_future_movement_plan(
        db,
        tenant_id,
        plan_id,
        body,
        actor_user_id=int(user.tenant_user.id) if user.tenant_user else None,
    )
    await db.commit()
    return out


@router.post("/loads/{load_id}/yard-drop-instruction")
async def yard_drop_instruction(
    load_id: int,
    body: YardDropInstructionBody,
    tenant_id: int = Depends(require_tenant),
    user: CurrentUser = Depends(require_pilot_capability("trips.custody", "transition")),
    db: AsyncSession = Depends(get_tenant_db),
):
    out = await fmp_service.record_yard_drop_instruction(
        db,
        tenant_id,
        load_id,
        body,
        actor_user_id=int(user.tenant_user.id) if user.tenant_user else None,
    )
    await db.commit()
    return out
