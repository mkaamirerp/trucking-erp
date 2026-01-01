from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.core.database import get_db
from app.models.payroll import PayEntry, PayPeriod, PayRun, PayRunItem
from app.schemas.pay_runs import (
    PayRunCreate,
    PayRunFinalizeResponse,
    PayRunGenerateResponse,
    PayRunItemOut,
    PayRunOut,
)

router = APIRouter(prefix="/api/v1/payroll", tags=["Payroll Runs"])


def get_tenant_id(request: Request) -> int:
    tenant_id = getattr(request.state, "tenant_id", None)
    if tenant_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Tenant context missing")
    return int(tenant_id)


def run_error(detail: str, code: str, status_code: int) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"detail": detail, "code": code})


def _to_json_amount(value: Decimal) -> float:
    return float(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


async def _get_period(db: AsyncSession, tenant_id: int, period_id: int) -> PayPeriod:
    period = await db.scalar(select(PayPeriod).where(PayPeriod.id == period_id, PayPeriod.tenant_id == tenant_id))
    if not period:
        raise run_error("Pay period not found", "PAYRUN_PERIOD_NOT_FOUND", status.HTTP_404_NOT_FOUND)
    return period


async def _get_run(db: AsyncSession, tenant_id: int, run_id: int) -> PayRun:
    run = await db.scalar(select(PayRun).where(PayRun.id == run_id, PayRun.tenant_id == tenant_id))
    if not run:
        raise run_error("Pay run not found", "PAYRUN_NOT_FOUND", status.HTTP_404_NOT_FOUND)
    return run


@router.post("/pay-runs", response_model=PayRunOut, status_code=status.HTTP_201_CREATED)
async def create_pay_run(payload: PayRunCreate, request: Request, db: AsyncSession = Depends(get_db)):
    tenant_id = get_tenant_id(request)
    await _get_period(db, tenant_id, payload.pay_period_id)
    # get or create
    existing = await db.scalar(
        select(PayRun).where(PayRun.tenant_id == tenant_id, PayRun.pay_period_id == payload.pay_period_id)
    )
    if existing:
        items = await db.execute(select(PayRunItem).where(PayRunItem.pay_run_id == existing.id))
        existing.items = list(items.scalars().all())
        return existing

    run = PayRun(tenant_id=tenant_id, pay_period_id=payload.pay_period_id, status="DRAFT")
    db.add(run)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise run_error("Pay run already exists", "PAYRUN_DUPLICATE", status.HTTP_409_CONFLICT)
    await db.refresh(run)
    run.items = []
    return run


@router.post("/pay-runs/{run_id}/generate", response_model=PayRunGenerateResponse)
async def generate_pay_run(run_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    tenant_id = get_tenant_id(request)
    async with db.begin():
        run = await db.scalar(select(PayRun).where(PayRun.id == run_id, PayRun.tenant_id == tenant_id).with_for_update())
        if not run:
            raise run_error("Pay run not found", "PAYRUN_NOT_FOUND", status.HTTP_404_NOT_FOUND)
        if run.status == "FINALIZED":
            raise run_error("Cannot regenerate finalized pay run", "PAYRUN_FINALIZED", status.HTTP_409_CONFLICT)

        period = await db.scalar(select(PayPeriod).where(PayPeriod.id == run.pay_period_id, PayPeriod.tenant_id == tenant_id))
        if not period:
            raise run_error("Pay period not found", "PAYRUN_PERIOD_NOT_FOUND", status.HTTP_404_NOT_FOUND)
        if period.status != "CLOSED":
            raise run_error("Pay period must be closed before generation", "PAYRUN_PERIOD_OPEN", status.HTTP_409_CONFLICT)

        # clear existing items
        await db.execute(select(PayRunItem).where(PayRunItem.pay_run_id == run.id).execution_options(synchronize_session=False))
        await db.execute(PayRunItem.__table__.delete().where(PayRunItem.pay_run_id == run.id))

        entries = await db.execute(
            select(PayEntry).where(
                PayEntry.tenant_id == tenant_id,
                PayEntry.pay_period_id == run.pay_period_id,
                PayEntry.is_active.is_(True),
                PayEntry.status != "VOID",
            )
        )
        entries_list = list(entries.scalars().all())
        items = []
        for e in entries_list:
            amt = e.amount
            if amt is None:
                amt = (e.quantity or Decimal("0")) * (e.rate_amount or Decimal("0"))
            amt = (amt or Decimal("0")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            item = PayRunItem(
                pay_run_id=run.id,
                driver_id=e.driver_id,
                entry_type=e.entry_type,
                amount=amt,
                source_entry_id=e.id,
            )
            db.add(item)
            items.append(item)
        run.totals_snapshot = None  # regenerated, will set at finalize
    return PayRunGenerateResponse(pay_run_id=run.id, item_count=len(items))


@router.post("/pay-runs/{run_id}/finalize", response_model=PayRunFinalizeResponse)
async def finalize_pay_run(run_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    tenant_id = get_tenant_id(request)
    async with db.begin():
        run = await db.scalar(select(PayRun).where(PayRun.id == run_id, PayRun.tenant_id == tenant_id).with_for_update())
        if not run:
            raise run_error("Pay run not found", "PAYRUN_NOT_FOUND", status.HTTP_404_NOT_FOUND)
        if run.status == "FINALIZED":
            raise run_error("Pay run already finalized", "PAYRUN_FINALIZED", status.HTTP_409_CONFLICT)

        period = await db.scalar(select(PayPeriod).where(PayPeriod.id == run.pay_period_id, PayPeriod.tenant_id == tenant_id))
        if not period:
            raise run_error("Pay period not found", "PAYRUN_PERIOD_NOT_FOUND", status.HTTP_404_NOT_FOUND)
        if period.status != "CLOSED":
            raise run_error("Pay period must be closed before finalize", "PAYRUN_PERIOD_OPEN", status.HTTP_409_CONFLICT)

        items_res = await db.execute(select(PayRunItem).where(PayRunItem.pay_run_id == run.id))
        items = list(items_res.scalars().all())
        if not items:
            raise run_error("No items to finalize", "PAYRUN_NO_ITEMS", status.HTTP_422_UNPROCESSABLE_ENTITY)

        totals = {
            "gross": Decimal("0.00"),
            "by_type": {},
            "count": len(items),
        }
        for item in items:
            amt = (item.amount or Decimal("0")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            totals["gross"] += amt
            totals["by_type"][item.entry_type] = totals["by_type"].get(item.entry_type, Decimal("0.00")) + amt
        # quantize totals
        totals["gross"] = totals["gross"].quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        for k, v in totals["by_type"].items():
            totals["by_type"][k] = v.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        run.status = "FINALIZED"
        run.finalized_at = datetime.now(timezone.utc)
        totals_snapshot = {
            "gross": _to_json_amount(totals["gross"]),
            "by_type": {k: _to_json_amount(v) for k, v in totals["by_type"].items()},
            "count": totals["count"],
        }
        run.totals_snapshot = totals_snapshot

    return PayRunFinalizeResponse(pay_run_id=run.id, status=run.status, totals_snapshot=totals_snapshot)


@router.get("/pay-runs/{run_id}", response_model=PayRunOut)
async def get_pay_run(run_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    tenant_id = get_tenant_id(request)
    run = await _get_run(db, tenant_id, run_id)
    items_res = await db.execute(select(PayRunItem).where(PayRunItem.pay_run_id == run.id))
    run.items = list(items_res.scalars().all())
    return run
