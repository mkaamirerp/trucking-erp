from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.driver import Driver
from app.models.payroll import PayEntry, PayPeriod, PayProfile
from app.schemas.payroll import (
    PAY_PERIOD_STATUSES,
    PayDriverSummary,
    PayEntryCreate,
    PayEntryOut,
    PayEntryUpdate,
    PayPeriodCreate,
    PayPeriodOut,
    PayPeriodSummary,
    PayPeriodUpdate,
    PayProfileCreate,
    PayProfileOut,
    PayProfileUpdate,
)

router = APIRouter(prefix="/api/v1/payroll", tags=["Payroll"])


def get_tenant_id(request: Request) -> int:
    tenant_id = getattr(request.state, "tenant_id", None)
    if tenant_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Tenant context missing")
    return int(tenant_id)


# ---- Pay Periods ----
async def _pay_period_overlap_exists(
    db: AsyncSession, tenant_id: int, start_date: date, end_date: date, exclude_id: int | None = None
) -> bool:
    stmt = select(PayPeriod).where(
        PayPeriod.tenant_id == tenant_id,
        PayPeriod.start_date <= end_date,
        PayPeriod.end_date >= start_date,
        PayPeriod.status.in_(["DRAFT", "OPEN"]),
    )
    if exclude_id:
        stmt = stmt.where(PayPeriod.id != exclude_id)
    res = await db.execute(stmt.limit(1))
    return res.scalar_one_or_none() is not None


@router.post("/pay-periods", response_model=PayPeriodOut, status_code=status.HTTP_201_CREATED)
async def create_pay_period(payload: PayPeriodCreate, request: Request, db: AsyncSession = Depends(get_db)):
    tenant_id = get_tenant_id(request)
    if await _pay_period_overlap_exists(db, tenant_id, payload.start_date, payload.end_date):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Pay period overlaps an existing period")

    period = PayPeriod(
        tenant_id=tenant_id,
        name=payload.name,
        start_date=payload.start_date,
        end_date=payload.end_date,
        status="DRAFT",
    )
    db.add(period)
    await db.commit()
    await db.refresh(period)
    return period


@router.get("/pay-periods", response_model=list[PayPeriodOut])
async def list_pay_periods(
    request: Request,
    db: AsyncSession = Depends(get_db),
    status_filter: str | None = Query(default=None, alias="status"),
):
    tenant_id = get_tenant_id(request)
    stmt = select(PayPeriod).where(PayPeriod.tenant_id == tenant_id)
    if status_filter:
        status_val = status_filter.upper()
        if status_val not in PAY_PERIOD_STATUSES:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid pay period status filter")
        stmt = stmt.where(PayPeriod.status == status_val)
    stmt = stmt.order_by(PayPeriod.start_date.desc(), PayPeriod.id.desc())
    res = await db.execute(stmt)
    return list(res.scalars().all())


async def _get_pay_period_or_404(db: AsyncSession, tenant_id: int, pay_period_id: int) -> PayPeriod:
    period = await db.scalar(
        select(PayPeriod).where(PayPeriod.id == pay_period_id, PayPeriod.tenant_id == tenant_id)
    )
    if not period:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pay period not found")
    return period


@router.get("/pay-periods/{pay_period_id}", response_model=PayPeriodOut)
async def get_pay_period(pay_period_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    tenant_id = get_tenant_id(request)
    return await _get_pay_period_or_404(db, tenant_id, pay_period_id)


@router.patch("/pay-periods/{pay_period_id}", response_model=PayPeriodOut)
async def update_pay_period(
    pay_period_id: int, payload: PayPeriodUpdate, request: Request, db: AsyncSession = Depends(get_db)
):
    tenant_id = get_tenant_id(request)
    period = await _get_pay_period_or_404(db, tenant_id, pay_period_id)

    if period.status == "CLOSED":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Closed pay periods cannot be edited")

    data = payload.model_dump(exclude_unset=True)
    new_start = data.get("start_date", period.start_date)
    new_end = data.get("end_date", period.end_date)
    if new_end < new_start:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="end_date cannot be before start_date")

    if (new_start != period.start_date or new_end != period.end_date) and await _pay_period_overlap_exists(
        db, tenant_id, new_start, new_end, exclude_id=period.id
    ):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Pay period overlaps an existing period")

    for k, v in data.items():
        setattr(period, k, v)
    await db.commit()
    await db.refresh(period)
    return period


@router.post("/pay-periods/{pay_period_id}/open", response_model=PayPeriodOut)
async def open_pay_period(pay_period_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    tenant_id = get_tenant_id(request)
    period = await _get_pay_period_or_404(db, tenant_id, pay_period_id)
    if period.status != "DRAFT":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only draft periods can be opened")
    if await _pay_period_overlap_exists(db, tenant_id, period.start_date, period.end_date, exclude_id=period.id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Pay period overlaps an existing period")
    period.status = "OPEN"
    await db.commit()
    await db.refresh(period)
    return period


@router.post("/pay-periods/{pay_period_id}/close", response_model=PayPeriodOut)
async def close_pay_period(pay_period_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    tenant_id = get_tenant_id(request)
    period = await _get_pay_period_or_404(db, tenant_id, pay_period_id)
    if period.status == "CLOSED":
        return period
    period.status = "CLOSED"
    await db.commit()
    await db.refresh(period)
    return period


# ---- Pay Profiles ----
async def _get_driver_or_404(db: AsyncSession, tenant_id: int, driver_id: int) -> Driver:
    driver = await db.scalar(select(Driver).where(Driver.id == driver_id, Driver.tenant_id == tenant_id))
    if not driver:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Driver not found")
    return driver


async def _profile_overlap_exists(
    db: AsyncSession,
    tenant_id: int,
    driver_id: int,
    effective_start: date,
    effective_end: date | None,
    exclude_id: int | None = None,
) -> bool:
    new_end = effective_end or effective_start
    stmt = select(PayProfile).where(
        PayProfile.tenant_id == tenant_id,
        PayProfile.driver_id == driver_id,
        PayProfile.is_active.is_(True),
        PayProfile.effective_start <= new_end,
        or_(PayProfile.effective_end.is_(None), PayProfile.effective_end >= effective_start),
    )
    if exclude_id:
        stmt = stmt.where(PayProfile.id != exclude_id)
    res = await db.execute(stmt.limit(1))
    return res.scalar_one_or_none() is not None


@router.post("/pay-profiles", response_model=PayProfileOut, status_code=status.HTTP_201_CREATED)
async def create_pay_profile(payload: PayProfileCreate, request: Request, db: AsyncSession = Depends(get_db)):
    tenant_id = get_tenant_id(request)
    await _get_driver_or_404(db, tenant_id, payload.driver_id)

    if await _profile_overlap_exists(
        db, tenant_id, payload.driver_id, payload.effective_start, payload.effective_end
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Active pay profile already exists for this driver in the given date range",
        )

    profile = PayProfile(
        tenant_id=tenant_id,
        driver_id=payload.driver_id,
        pay_type=payload.pay_type,
        rate_amount=payload.rate_amount,
        rate_unit=payload.rate_unit,
        percentage_basis_points=payload.percentage_basis_points,
        currency=payload.currency,
        notes=payload.notes,
        effective_start=payload.effective_start,
        effective_end=payload.effective_end,
        is_active=payload.is_active,
    )
    db.add(profile)
    await db.commit()
    await db.refresh(profile)
    return profile


@router.get("/pay-profiles", response_model=list[PayProfileOut])
async def list_pay_profiles(
    request: Request,
    db: AsyncSession = Depends(get_db),
    driver_id: int | None = None,
    include_inactive: bool = False,
):
    tenant_id = get_tenant_id(request)
    stmt = select(PayProfile).where(PayProfile.tenant_id == tenant_id)
    if driver_id is not None:
        stmt = stmt.where(PayProfile.driver_id == driver_id)
    if not include_inactive:
        stmt = stmt.where(PayProfile.is_active.is_(True))
    stmt = stmt.order_by(PayProfile.id.desc())
    res = await db.execute(stmt)
    return list(res.scalars().all())


async def _get_pay_profile_or_404(db: AsyncSession, tenant_id: int, profile_id: int) -> PayProfile:
    profile = await db.scalar(select(PayProfile).where(PayProfile.id == profile_id, PayProfile.tenant_id == tenant_id))
    if not profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pay profile not found")
    return profile


@router.get("/pay-profiles/{profile_id}", response_model=PayProfileOut)
async def get_pay_profile(profile_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    tenant_id = get_tenant_id(request)
    return await _get_pay_profile_or_404(db, tenant_id, profile_id)


@router.patch("/pay-profiles/{profile_id}", response_model=PayProfileOut)
async def update_pay_profile(
    profile_id: int, payload: PayProfileUpdate, request: Request, db: AsyncSession = Depends(get_db)
):
    tenant_id = get_tenant_id(request)
    profile = await _get_pay_profile_or_404(db, tenant_id, profile_id)

    data = payload.model_dump(exclude_unset=True)
    new_start = data.get("effective_start", profile.effective_start)
    new_end = data.get("effective_end", profile.effective_end)
    new_active = data.get("is_active", profile.is_active)

    if new_end and new_end < new_start:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="effective_end cannot be before start")

    if new_active and await _profile_overlap_exists(
        db, tenant_id, profile.driver_id, new_start, new_end, exclude_id=profile.id
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Active pay profile already exists for this driver in the given date range",
        )

    for k, v in data.items():
        setattr(profile, k, v)
    await db.commit()
    await db.refresh(profile)
    return profile


@router.post("/pay-profiles/{profile_id}/deactivate", response_model=PayProfileOut)
async def deactivate_pay_profile(profile_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    tenant_id = get_tenant_id(request)
    profile = await _get_pay_profile_or_404(db, tenant_id, profile_id)
    if not profile.is_active:
        return profile
    profile.is_active = False
    if profile.effective_end is None:
        profile.effective_end = date.today()
    await db.commit()
    await db.refresh(profile)
    return profile


# ---- Pay Entries ----
def _compute_amount(amount: Decimal | None, quantity: Decimal | None, rate_amount: Decimal | None) -> Decimal | None:
    if amount is not None:
        return amount
    if quantity is not None and rate_amount is not None:
        return quantity * rate_amount
    return None


async def _get_pay_entry_or_404(db: AsyncSession, tenant_id: int, entry_id: int) -> PayEntry:
    entry = await db.scalar(select(PayEntry).where(PayEntry.id == entry_id, PayEntry.tenant_id == tenant_id))
    if not entry:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pay entry not found")
    return entry


@router.post("/pay-entries", response_model=PayEntryOut, status_code=status.HTTP_201_CREATED)
async def create_pay_entry(payload: PayEntryCreate, request: Request, db: AsyncSession = Depends(get_db)):
    tenant_id = get_tenant_id(request)
    period = await _get_pay_period_or_404(db, tenant_id, payload.pay_period_id)
    if period.status == "CLOSED":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot add entries to a closed period")

    await _get_driver_or_404(db, tenant_id, payload.driver_id)

    profile = None
    if payload.pay_profile_id is not None:
        profile = await _get_pay_profile_or_404(db, tenant_id, payload.pay_profile_id)
        if profile.driver_id != payload.driver_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Pay profile does not match driver")
        if not profile.is_active:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Pay profile is inactive")

    amount = _compute_amount(payload.amount, payload.quantity, payload.rate_amount)

    entry = PayEntry(
        tenant_id=tenant_id,
        pay_period_id=payload.pay_period_id,
        driver_id=payload.driver_id,
        pay_profile_id=payload.pay_profile_id,
        entry_type=payload.entry_type,
        quantity=payload.quantity,
        rate_amount=payload.rate_amount,
        amount=amount,
        notes=payload.notes,
        is_manual=True,
        status="ACTIVE",
        is_active=True,
    )
    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    return entry


@router.get("/pay-entries", response_model=list[PayEntryOut])
async def list_pay_entries(
    request: Request,
    db: AsyncSession = Depends(get_db),
    pay_period_id: int | None = Query(default=None),
    driver_id: int | None = None,
    include_inactive: bool = False,
):
    tenant_id = get_tenant_id(request)
    if pay_period_id is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="pay_period_id is required")
    stmt = select(PayEntry).where(PayEntry.tenant_id == tenant_id, PayEntry.pay_period_id == pay_period_id)
    if driver_id is not None:
        stmt = stmt.where(PayEntry.driver_id == driver_id)
    if not include_inactive:
        stmt = stmt.where(PayEntry.is_active.is_(True))
    stmt = stmt.order_by(PayEntry.id.desc())
    res = await db.execute(stmt)
    return list(res.scalars().all())


@router.patch("/pay-entries/{entry_id}", response_model=PayEntryOut)
async def update_pay_entry(
    entry_id: int, payload: PayEntryUpdate, request: Request, db: AsyncSession = Depends(get_db)
):
    tenant_id = get_tenant_id(request)
    entry = await _get_pay_entry_or_404(db, tenant_id, entry_id)
    period = await _get_pay_period_or_404(db, tenant_id, entry.pay_period_id)
    if period.status == "CLOSED":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot edit entries in a closed period")

    data = payload.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(entry, k, v)

    provided_amount = data.get("amount")
    entry.amount = _compute_amount(provided_amount, entry.quantity, entry.rate_amount)
    await db.commit()
    await db.refresh(entry)
    return entry


@router.post("/pay-entries/{entry_id}/void", response_model=PayEntryOut)
async def void_pay_entry(entry_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    tenant_id = get_tenant_id(request)
    entry = await _get_pay_entry_or_404(db, tenant_id, entry_id)
    if not entry.is_active:
        return entry
    period = await _get_pay_period_or_404(db, tenant_id, entry.pay_period_id)
    if period.status == "CLOSED":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot void entries in a closed period")
    entry.is_active = False
    entry.status = "VOID"
    entry.deactivated_at = datetime.now(timezone.utc)
    entry.deactivated_reason = "Voided"
    await db.commit()
    await db.refresh(entry)
    return entry


# ---- Summary ----
@router.get("/pay-periods/{pay_period_id}/summary", response_model=PayPeriodSummary)
async def summarize_pay_period(pay_period_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    tenant_id = get_tenant_id(request)
    period = await _get_pay_period_or_404(db, tenant_id, pay_period_id)

    amount_expr = func.coalesce(PayEntry.amount, PayEntry.quantity * PayEntry.rate_amount, 0)

    stmt = (
        select(
            PayEntry.driver_id,
            func.coalesce(
                func.sum(case((PayEntry.entry_type == "MILES", PayEntry.quantity), else_=Decimal("0"))), Decimal("0")
            ).label("miles"),
            func.coalesce(
                func.sum(case((PayEntry.entry_type == "HOURS", PayEntry.quantity), else_=Decimal("0"))), Decimal("0")
            ).label("hours"),
            func.coalesce(
                func.sum(
                    case(
                        (
                            PayEntry.entry_type.in_(["GROSS", "ADJUSTMENT"]),
                            amount_expr,
                        ),
                        else_=Decimal("0"),
                    )
                ),
                Decimal("0"),
            ).label("earnings"),
            func.coalesce(
                func.sum(
                    case(
                        (
                            PayEntry.entry_type == "DEDUCTION",
                            amount_expr,
                        ),
                        else_=Decimal("0"),
                    )
                ),
                Decimal("0"),
            ).label("deductions"),
        )
        .where(
            PayEntry.tenant_id == tenant_id,
            PayEntry.pay_period_id == pay_period_id,
            PayEntry.is_active.is_(True),
            PayEntry.status != "VOID",
        )
        .group_by(PayEntry.driver_id)
    )

    res = await db.execute(stmt)
    totals: list[PayDriverSummary] = []
    for row in res.all():
        driver_id, miles, hours, earnings, deductions = row
        net = (earnings or Decimal("0")) - (deductions or Decimal("0"))
        totals.append(
            PayDriverSummary(
                driver_id=driver_id,
                miles=miles or Decimal("0"),
                hours=hours or Decimal("0"),
                earnings=earnings or Decimal("0"),
                deductions=deductions or Decimal("0"),
                net=net,
            )
        )

    return PayPeriodSummary(pay_period_id=pay_period_id, status=period.status, totals=totals)
