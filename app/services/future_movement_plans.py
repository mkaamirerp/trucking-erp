"""Future Movement Plan (§9A) — pre-Trip planning; converts to numbered Trip atomically."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.constants.future_movement import (
    DISPATCH_INSTRUCTION_YARD_DROP,
    FMP_OPEN_STATUSES,
    FMP_STATUS_CANCELLED,
    FMP_STATUS_CONVERTED,
    FMP_STATUS_CONVERTING,
    FMP_STATUS_UNASSIGNED,
    LOAD_HAS_OPEN_FUTURE_MOVEMENT_PLAN,
)
from app.constants.trip_dispatch import (
    JOB_TYPE_FREIGHT_LOAD,
    TRIP_CONTAINER_STATUS_ASSIGNED,
    TRIP_CONTAINER_STATUS_PLANNED,
)
from app.models.future_movement_plan import FutureMovementPlan, FutureMovementPlanLoad
from app.models.load import Load
from app.models.load_dispatch_instruction import LoadDispatchInstruction
from app.models.terminal import Terminal
from app.models.trip import Trip
from app.schemas.future_movement_plan import (
    FutureMovementConvertBody,
    FutureMovementPlanCreate,
    FutureMovementPlanLineIn,
    FutureMovementPlanListPage,
    FutureMovementPlanOut,
    FutureMovementPlanUpdate,
    YardDropInstructionBody,
)
from app.schemas.trip_read import TripDetailResponse
from app.services.dispatch_trips import mint_next_trip_number
from app.services.trips import (
    _insert_trip_load_row,
    _lock_load_for_membership,
    _validate_assignment_targets,
    _validate_decision10_schedule_overlap,
    assert_load_reservation_clear,
    get_trip_detail,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _lock_plan(db: AsyncSession, tenant_id: int, plan_id: int) -> FutureMovementPlan:
    plan = await db.scalar(
        select(FutureMovementPlan)
        .where(
            FutureMovementPlan.tenant_id == tenant_id,
            FutureMovementPlan.id == plan_id,
        )
        .with_for_update()
    )
    if plan is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"detail": "Future movement plan not found", "code": "FMP_NOT_FOUND"},
        )
    return plan


async def _validate_terminal(db: AsyncSession, tenant_id: int, terminal_id: int | None) -> None:
    if terminal_id is None:
        return
    row = await db.scalar(
        select(Terminal.id).where(Terminal.id == terminal_id, Terminal.tenant_id == tenant_id)
    )
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"detail": "Terminal not found", "code": "TERMINAL_NOT_FOUND"},
        )


async def _assert_loads_tenant_ready(
    db: AsyncSession, tenant_id: int, lines: list[FutureMovementPlanLineIn]
) -> None:
    if not lines:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"detail": "At least one load line is required", "code": "FMP_LINES_REQUIRED"},
        )
    seen: set[int] = set()
    for ln in lines:
        lid = int(ln.load_id)
        if lid in seen:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"detail": "Duplicate load in plan", "code": "FMP_DUPLICATE_LOAD"},
            )
        seen.add(lid)
        load = await db.scalar(select(Load).where(Load.tenant_id == tenant_id, Load.id == lid))
        if load is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"detail": f"Load {lid} not found", "code": "LOAD_NOT_FOUND"},
            )
        st = (load.status or "").strip().lower()
        if st != "ready":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "detail": "Load must be ready for future movement planning",
                    "code": "LOAD_NOT_READY_FOR_PLAN",
                },
            )


async def _attach_lines(
    db: AsyncSession,
    tenant_id: int,
    plan_id: int,
    lines: list[FutureMovementPlanLineIn],
) -> None:
    for ln in sorted(lines, key=lambda x: int(x.load_id)):
        lid = int(ln.load_id)
        await _lock_load_for_membership(db, tenant_id, lid)
        await assert_load_reservation_clear(db, tenant_id, lid)
        db.add(
            FutureMovementPlanLoad(
                tenant_id=tenant_id,
                plan_id=plan_id,
                load_id=lid,
                sequence_hint=ln.sequence_hint,
                inbound_trip_id=ln.inbound_trip_id,
            )
        )
    await db.flush()


async def _plan_to_out(db: AsyncSession, plan: FutureMovementPlan) -> FutureMovementPlanOut:
    await db.refresh(plan, attribute_names=["lines"])
    trip_number: str | None = None
    if plan.converted_trip_id is not None:
        trip_number = await db.scalar(
            select(Trip.trip_number).where(
                Trip.tenant_id == plan.tenant_id,
                Trip.id == plan.converted_trip_id,
            )
        )
    load_ids = [int(ln.load_id) for ln in plan.lines]
    load_numbers: dict[int, str | None] = {}
    if load_ids:
        rows = (
            await db.execute(
                select(Load.id, Load.load_number).where(
                    Load.tenant_id == plan.tenant_id,
                    Load.id.in_(load_ids),
                )
            )
        ).all()
        load_numbers = {int(r[0]): r[1] for r in rows}
    line_out = []
    for ln in sorted(plan.lines, key=lambda x: (x.sequence_hint or 0, x.load_id)):
        line_out.append(
            {
                "id": int(ln.id),
                "load_id": int(ln.load_id),
                "sequence_hint": ln.sequence_hint,
                "inbound_trip_id": ln.inbound_trip_id,
                "load_number": load_numbers.get(int(ln.load_id)),
            }
        )
    return FutureMovementPlanOut(
        id=int(plan.id),
        tenant_id=int(plan.tenant_id),
        status=plan.status,
        origin_kind=plan.origin_kind,
        pickup_terminal_id=plan.pickup_terminal_id,
        planned_start_at=plan.planned_start_at,
        expected_completion_at=plan.expected_completion_at,
        driver_id=plan.driver_id,
        truck_id=plan.truck_id,
        trailer_id=plan.trailer_id,
        converted_trip_id=plan.converted_trip_id,
        converted_trip_number=trip_number,
        notes=plan.notes,
        concurrency_version=int(plan.concurrency_version),
        created_at=plan.created_at,
        updated_at=plan.updated_at,
        lines=line_out,
    )


async def get_open_future_movement_plan_id(
    db: AsyncSession, tenant_id: int, load_id: int
) -> int | None:
    row = await db.scalar(
        select(FutureMovementPlanLoad.plan_id).where(
            FutureMovementPlanLoad.tenant_id == tenant_id,
            FutureMovementPlanLoad.load_id == load_id,
            FutureMovementPlanLoad.released_at.is_(None),
            FutureMovementPlanLoad.converted_at.is_(None),
        )
    )
    return int(row) if row is not None else None


async def load_has_open_future_movement_plan(
    db: AsyncSession, tenant_id: int, load_id: int
) -> bool:
    return await get_open_future_movement_plan_id(db, tenant_id, load_id) is not None


async def create_future_movement_plan(
    db: AsyncSession,
    tenant_id: int,
    body: FutureMovementPlanCreate,
    *,
    actor_user_id: int | None = None,
) -> FutureMovementPlanOut:
    await _validate_terminal(db, tenant_id, body.pickup_terminal_id)
    await _assert_loads_tenant_ready(db, tenant_id, body.lines)
    if body.driver_id or body.truck_id or body.trailer_id:
        await _validate_assignment_targets(
            db,
            tenant_id,
            driver_id=body.driver_id,
            truck_id=body.truck_id,
            trailer_id=body.trailer_id,
        )

    plan = FutureMovementPlan(
        tenant_id=tenant_id,
        status=FMP_STATUS_UNASSIGNED,
        origin_kind=(body.origin_kind or "manual").strip()[:32],
        pickup_terminal_id=body.pickup_terminal_id,
        planned_start_at=body.planned_start_at,
        expected_completion_at=body.expected_completion_at,
        driver_id=body.driver_id,
        truck_id=body.truck_id,
        trailer_id=body.trailer_id,
        notes=body.notes,
        created_by_user_id=actor_user_id,
    )
    db.add(plan)
    await db.flush()
    await _attach_lines(db, tenant_id, int(plan.id), body.lines)
    return await _plan_to_out(db, plan)


async def list_future_movement_plans(
    db: AsyncSession,
    tenant_id: int,
    *,
    status_filter: str | None = FMP_STATUS_UNASSIGNED,
    page: int = 1,
    size: int = 50,
) -> FutureMovementPlanListPage:
    page = max(1, page)
    size = min(max(1, size), 200)
    q = select(FutureMovementPlan).where(FutureMovementPlan.tenant_id == tenant_id)
    if status_filter:
        q = q.where(FutureMovementPlan.status == status_filter)
    count_q = select(func.count(FutureMovementPlan.id)).where(FutureMovementPlan.tenant_id == tenant_id)
    if status_filter:
        count_q = count_q.where(FutureMovementPlan.status == status_filter)
    total = int(await db.scalar(count_q) or 0)
    rows = (
        await db.scalars(
            q.options(selectinload(FutureMovementPlan.lines))
            .order_by(FutureMovementPlan.updated_at.desc())
            .offset((page - 1) * size)
            .limit(size)
        )
    ).all()
    items = [await _plan_to_out(db, p) for p in rows]
    return FutureMovementPlanListPage(items=items, page=page, size=size, total=total)


async def get_future_movement_plan(
    db: AsyncSession, tenant_id: int, plan_id: int
) -> FutureMovementPlanOut:
    plan = await db.scalar(
        select(FutureMovementPlan)
        .where(FutureMovementPlan.tenant_id == tenant_id, FutureMovementPlan.id == plan_id)
        .options(selectinload(FutureMovementPlan.lines))
    )
    if plan is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"detail": "Future movement plan not found", "code": "FMP_NOT_FOUND"},
        )
    return await _plan_to_out(db, plan)


async def update_future_movement_plan(
    db: AsyncSession,
    tenant_id: int,
    plan_id: int,
    body: FutureMovementPlanUpdate,
) -> FutureMovementPlanOut:
    plan = await _lock_plan(db, tenant_id, plan_id)
    if plan.status not in FMP_OPEN_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"detail": "Plan is not editable", "code": "FMP_NOT_EDITABLE"},
        )
    if int(plan.concurrency_version) != int(body.concurrency_version):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"detail": "Plan was modified elsewhere", "code": "FMP_VERSION_CONFLICT"},
        )

    await _validate_terminal(db, tenant_id, body.pickup_terminal_id)
    if body.driver_id is not None or body.truck_id is not None or body.trailer_id is not None:
        await _validate_assignment_targets(
            db,
            tenant_id,
            driver_id=body.driver_id,
            truck_id=body.truck_id,
            trailer_id=body.trailer_id,
        )

    if body.lines is not None:
        await _assert_loads_tenant_ready(db, tenant_id, body.lines)
        now = _now()
        for ln in plan.lines:
            if ln.released_at is None and ln.converted_at is None:
                ln.released_at = now
        await db.flush()
        await _attach_lines(db, tenant_id, int(plan.id), body.lines)

    plan.pickup_terminal_id = body.pickup_terminal_id
    plan.planned_start_at = body.planned_start_at
    plan.expected_completion_at = body.expected_completion_at
    plan.driver_id = body.driver_id
    plan.truck_id = body.truck_id
    plan.trailer_id = body.trailer_id
    plan.notes = body.notes
    plan.concurrency_version = int(plan.concurrency_version) + 1
    plan.updated_at = _now()
    await db.flush()
    return await _plan_to_out(db, plan)


async def cancel_future_movement_plan(
    db: AsyncSession, tenant_id: int, plan_id: int, *, concurrency_version: int
) -> FutureMovementPlanOut:
    plan = await _lock_plan(db, tenant_id, plan_id)
    if plan.status == FMP_STATUS_CANCELLED:
        return await _plan_to_out(db, plan)
    if plan.status == FMP_STATUS_CONVERTED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"detail": "Converted plan cannot be cancelled", "code": "FMP_ALREADY_CONVERTED"},
        )
    if int(plan.concurrency_version) != int(concurrency_version):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"detail": "Plan was modified elsewhere", "code": "FMP_VERSION_CONFLICT"},
        )
    now = _now()
    for ln in plan.lines:
        if ln.released_at is None and ln.converted_at is None:
            ln.released_at = now
    plan.status = FMP_STATUS_CANCELLED
    plan.concurrency_version = int(plan.concurrency_version) + 1
    plan.updated_at = now
    await db.flush()
    return await _plan_to_out(db, plan)


async def _convert_replay(
    db: AsyncSession, tenant_id: int, plan: FutureMovementPlan
) -> TripDetailResponse:
    assert plan.converted_trip_id is not None
    detail = await get_trip_detail(db, tenant_id, int(plan.converted_trip_id))
    if detail is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"detail": "Converted trip missing", "code": "FMP_CONVERTED_TRIP_MISSING"},
        )
    return detail


async def convert_future_movement_plan(
    db: AsyncSession,
    tenant_id: int,
    plan_id: int,
    body: FutureMovementConvertBody,
    *,
    actor_user_id: int | None = None,
) -> TripDetailResponse:
    plan = await _lock_plan(db, tenant_id, plan_id)

    if body.conversion_idempotency_key:
        other = await db.scalar(
            select(FutureMovementPlan).where(
                FutureMovementPlan.tenant_id == tenant_id,
                FutureMovementPlan.conversion_idempotency_key == body.conversion_idempotency_key,
                FutureMovementPlan.id != plan_id,
            )
        )
        if other is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "detail": "conversion_idempotency_key already used on another plan",
                    "code": "FMP_IDEMPOTENCY_KEY_CONFLICT",
                },
            )

    if plan.status == FMP_STATUS_CONVERTED and plan.converted_trip_id:
        if body.conversion_idempotency_key and plan.conversion_idempotency_key != body.conversion_idempotency_key:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"detail": "Plan already converted with a different key", "code": "FMP_IDEMPOTENCY_KEY_CONFLICT"},
            )
        return await _convert_replay(db, tenant_id, plan)

    if plan.status == FMP_STATUS_CONVERTING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"detail": "Conversion in progress", "code": "FMP_CONVERTING"},
        )

    if plan.status not in FMP_OPEN_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"detail": "Plan cannot be converted", "code": "FMP_NOT_CONVERTIBLE"},
        )

    if int(plan.concurrency_version) != int(body.concurrency_version):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"detail": "Plan was modified elsewhere", "code": "FMP_VERSION_CONFLICT"},
        )

    open_lines = [ln for ln in plan.lines if ln.released_at is None and ln.converted_at is None]
    if not open_lines:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"detail": "Plan has no open load lines", "code": "FMP_NO_OPEN_LINES"},
        )

    driver_id = int(body.driver_id)
    truck_id = body.truck_id
    trailer_id = body.trailer_id
    await _validate_assignment_targets(
        db, tenant_id, driver_id=driver_id, truck_id=truck_id, trailer_id=trailer_id
    )

    plan.status = FMP_STATUS_CONVERTING
    if body.conversion_idempotency_key:
        plan.conversion_idempotency_key = body.conversion_idempotency_key
    await db.flush()

    trip_number = await mint_next_trip_number(db, tenant_id)
    trip = Trip(
        tenant_id=tenant_id,
        trip_number=trip_number,
        status=TRIP_CONTAINER_STATUS_PLANNED,
        job_type=JOB_TYPE_FREIGHT_LOAD,
        trailer_move_id=None,
        legacy_dispatch_trip_id=None,
        driver_id=driver_id,
        truck_id=truck_id,
        trailer_id=trailer_id,
        planned_start_at=plan.planned_start_at,
        expected_completion_at=plan.expected_completion_at,
        assigned_at=None,
        cancelled_at=None,
    )
    complete = driver_id is not None and truck_id is not None and trailer_id is not None
    if complete:
        trip.status = TRIP_CONTAINER_STATUS_ASSIGNED
        trip.assigned_at = _now()

    db.add(trip)
    await db.flush()

    await _validate_decision10_schedule_overlap(
        db,
        tenant_id,
        trip=trip,
        driver_id=driver_id,
        truck_id=truck_id,
        trailer_id=trailer_id,
    )

    pid = int(plan.id)
    for ln in sorted(open_lines, key=lambda x: int(x.load_id)):
        lid = int(ln.load_id)
        await assert_load_reservation_clear(db, tenant_id, lid, converting_plan_id=pid)
        await _insert_trip_load_row(
            db,
            tenant_id,
            int(trip.id),
            lid,
            sequence_hint=ln.sequence_hint,
        )

    now = _now()
    for ln in open_lines:
        ln.converted_at = now
    plan.status = FMP_STATUS_CONVERTED
    plan.converted_trip_id = int(trip.id)
    plan.driver_id = driver_id
    plan.truck_id = truck_id
    plan.trailer_id = trailer_id
    plan.concurrency_version = int(plan.concurrency_version) + 1
    plan.updated_at = now
    await db.flush()

    detail = await get_trip_detail(db, tenant_id, int(trip.id))
    assert detail is not None
    return detail


async def record_yard_drop_instruction(
    db: AsyncSession,
    tenant_id: int,
    load_id: int,
    body: YardDropInstructionBody,
    *,
    actor_user_id: int | None = None,
) -> dict[str, Any]:
    load = await db.scalar(select(Load).where(Load.tenant_id == tenant_id, Load.id == load_id))
    if load is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"detail": "Load not found", "code": "LOAD_NOT_FOUND"},
        )
    await _validate_terminal(db, tenant_id, body.terminal_id)
    trip = await db.scalar(
        select(Trip).where(Trip.tenant_id == tenant_id, Trip.id == body.inbound_trip_id)
    )
    if trip is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"detail": "Inbound trip not found", "code": "TRIP_NOT_FOUND"},
        )
    row = LoadDispatchInstruction(
        tenant_id=tenant_id,
        load_id=load_id,
        inbound_trip_id=body.inbound_trip_id,
        terminal_id=body.terminal_id,
        instruction_type=DISPATCH_INSTRUCTION_YARD_DROP,
        notes=body.notes,
        actor_user_id=actor_user_id,
    )
    db.add(row)
    await db.flush()
    return {
        "id": int(row.id),
        "load_id": load_id,
        "inbound_trip_id": body.inbound_trip_id,
        "terminal_id": body.terminal_id,
        "instruction_type": DISPATCH_INSTRUCTION_YARD_DROP,
        "notes": body.notes,
        "created_at": row.created_at,
    }
