"""Operational driver payee + compensation_profiles for combined-mode onboarding (no driver_person_extensions writes)."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.driver import Driver
from app.models.driver_person_extension import DriverPersonExtension
from app.models.enums import GrossCalcType, PayeeType, WorkerType
from app.models.payee import CompensationProfile, Payee
from app.models.person_application import PersonApplication
from app.schemas.driver_compensation_setup import DriverCompensationSetupOut, DriverCompensationSetupWrite


COMPENSATION_CONFLICT_DETAILS: dict[str, str] = {
    "compensation_effective_from_in_past": "Compensation changes cannot start before today; earlier pay periods keep their rates.",
    "compensation_future_version_exists": "A later compensation change is already scheduled; edit that version's date instead.",
    "driver_classification_unknown": "Driver classification must be company driver or owner-operator before compensation can be saved.",
}


def _utc_today() -> date:
    return datetime.now(timezone.utc).date()


def worker_type_for_employment_relationship(employment_relationship_type: str | None) -> WorkerType:
    ert = (employment_relationship_type or "").strip().lower()
    if ert == "owner_operator":
        return WorkerType.OWNER_OPERATOR_LEASED_ON
    if ert == "company_driver":
        return WorkerType.EMPLOYEE_DRIVER
    raise ValueError("driver_classification_unknown")


def _profile_covers(p: CompensationProfile, work_date: date) -> bool:
    """effective_to is the inclusive last day of a version."""
    if p.effective_from > work_date:
        return False
    return p.effective_to is None or p.effective_to >= work_date


async def _get_operational_driver_for_person(
    db: AsyncSession, *, tenant_id: int, person_id: int, include_provisional: bool = False
) -> Driver | None:
    """Active operational driver; ``include_provisional`` also accepts the inactive, non-terminated
    row created for combined-mode setup before approval (application-scoped callers only)."""
    stmt = select(Driver).where(Driver.tenant_id == tenant_id, Driver.person_id == person_id)
    if include_provisional:
        stmt = stmt.where(Driver.termination_date.is_(None)).order_by(
            Driver.is_active.desc(), Driver.id.asc()
        )
    else:
        stmt = stmt.where(Driver.is_active.is_(True)).order_by(Driver.id.asc())
    res = await db.scalars(stmt)
    return res.first()


async def _get_driver_extension(
    db: AsyncSession, *, tenant_id: int, person_id: int
) -> DriverPersonExtension | None:
    return await db.scalar(
        select(DriverPersonExtension).where(
            DriverPersonExtension.tenant_id == tenant_id,
            DriverPersonExtension.person_id == person_id,
        )
    )


async def select_compensation_profile_for_work_date(
    db: AsyncSession, *, tenant_id: int, payee_id: int, work_date: date
) -> CompensationProfile | None:
    """The single compensation version covering ``work_date`` (versions never overlap)."""
    return await db.scalar(
        select(CompensationProfile)
        .where(
            CompensationProfile.tenant_id == tenant_id,
            CompensationProfile.payee_id == payee_id,
            CompensationProfile.effective_from <= work_date,
            or_(CompensationProfile.effective_to.is_(None), CompensationProfile.effective_to >= work_date),
        )
        .order_by(CompensationProfile.effective_from.desc(), CompensationProfile.id.desc())
        .limit(1)
    )


async def _select_current_profile_for_payee(
    db: AsyncSession, *, tenant_id: int, payee_id: int
) -> CompensationProfile | None:
    return await select_compensation_profile_for_work_date(
        db, tenant_id=tenant_id, payee_id=payee_id, work_date=_utc_today()
    )


async def _next_scheduled_effective_from(
    db: AsyncSession, *, tenant_id: int, payee_id: int
) -> date | None:
    return await db.scalar(
        select(func.min(CompensationProfile.effective_from)).where(
            CompensationProfile.tenant_id == tenant_id,
            CompensationProfile.payee_id == payee_id,
            CompensationProfile.effective_from > _utc_today(),
        )
    )


async def _apply_driver_compensation_write(
    db: AsyncSession,
    *,
    tenant_id: int,
    payee: Payee,
    payload: DriverCompensationSetupWrite,
) -> None:
    """Write an effective-dated compensation version for ``payee``.

    * ``effective_from`` defaults to today; past dates are rejected so history used by earlier
      pay periods is never rewritten.
    * Unchanged values on the covering version: no-op.
    * Version starting on the same date: corrected in place.
    * Otherwise the covering version is closed the day before and a new version starts.
    * A version starting after ``effective_from`` already exists: rejected (no overlap, no reorder).
    """
    gross = GrossCalcType(payload.gross_calc_type.value)
    cpm_empty = payload.cpm_empty
    if gross == GrossCalcType.CPM and cpm_empty is None:
        cpm_empty = payload.cpm_loaded

    today = _utc_today()
    start = payload.effective_from or today
    if start < today:
        raise ValueError("compensation_effective_from_in_past")

    values: dict[str, Any] = {
        "worker_type_snapshot": payee.worker_type,
        "gross_calc_type": gross,
        "percent_rate": payload.percent_rate,
        "cpm_loaded": payload.cpm_loaded,
        "cpm_empty": cpm_empty,
        "hourly_rate": payload.hourly_rate,
        "salary_amount": payload.salary_amount,
        "flat_amount": payload.flat_amount,
        "dispatch_fee_enabled": payload.dispatch_fee_enabled,
        "dispatch_fee_rate": payload.dispatch_fee_rate,
        "dispatch_fee_basis": (payload.dispatch_fee_basis or "GROSS").strip() or "GROSS",
        "settlement_frequency": payload.settlement_frequency,
        "participates_in_fuel_discount_program": payload.participates_in_fuel_discount_program,
    }

    versions = list(
        (
            await db.scalars(
                select(CompensationProfile)
                .where(
                    CompensationProfile.tenant_id == tenant_id,
                    CompensationProfile.payee_id == payee.id,
                )
                .order_by(CompensationProfile.effective_from.asc(), CompensationProfile.id.asc())
                .with_for_update()
            )
        ).all()
    )
    if any(v.effective_from > start for v in versions):
        raise ValueError("compensation_future_version_exists")
    covering = next((v for v in versions if _profile_covers(v, start)), None)

    if covering is not None and all(getattr(covering, k) == v for k, v in values.items()):
        return
    if covering is not None and covering.effective_from == start:
        for k, v in values.items():
            setattr(covering, k, v)
        await db.flush()
        return

    new_effective_to = None
    if covering is not None:
        new_effective_to = covering.effective_to
        covering.effective_to = start - timedelta(days=1)
        await db.flush()
    db.add(
        CompensationProfile(
            tenant_id=tenant_id,
            payee_id=payee.id,
            effective_from=start,
            effective_to=new_effective_to,
            **values,
        )
    )
    await db.flush()


async def get_driver_compensation_setup(
    db: AsyncSession,
    *,
    tenant_id: int,
    person_id: int,
    include_provisional: bool = False,
) -> DriverCompensationSetupOut:
    ext = await _get_driver_extension(db, tenant_id=tenant_id, person_id=person_id)
    employment = ext.employment_relationship_type if ext else None

    op_driver = await _get_operational_driver_for_person(
        db, tenant_id=tenant_id, person_id=person_id, include_provisional=include_provisional
    )
    if not op_driver or not op_driver.payee_id:
        return DriverCompensationSetupOut(employment_relationship_type=employment)

    payee = await db.get(Payee, op_driver.payee_id)
    if not payee or payee.tenant_id != tenant_id:
        return DriverCompensationSetupOut(employment_relationship_type=employment)

    prof = await _select_current_profile_for_payee(db, tenant_id=tenant_id, payee_id=payee.id)
    scheduled = await _next_scheduled_effective_from(db, tenant_id=tenant_id, payee_id=payee.id)
    if not prof:
        return DriverCompensationSetupOut(
            payee_id=payee.id,
            worker_type=payee.worker_type.value,
            employment_relationship_type=employment,
            scheduled_change_effective_from=scheduled,
        )

    return DriverCompensationSetupOut(
        payee_id=payee.id,
        worker_type=payee.worker_type.value,
        gross_calc_type=prof.gross_calc_type.value,
        percent_rate=prof.percent_rate,
        cpm_loaded=prof.cpm_loaded,
        cpm_empty=prof.cpm_empty,
        hourly_rate=prof.hourly_rate,
        salary_amount=prof.salary_amount,
        flat_amount=prof.flat_amount,
        settlement_frequency=prof.settlement_frequency.value,
        participates_in_fuel_discount_program=bool(
            getattr(prof, "participates_in_fuel_discount_program", False)
        ),
        dispatch_fee_enabled=prof.dispatch_fee_enabled,
        dispatch_fee_rate=prof.dispatch_fee_rate,
        dispatch_fee_basis=prof.dispatch_fee_basis,
        employment_relationship_type=employment,
        effective_from=prof.effective_from,
        scheduled_change_effective_from=scheduled,
    )


async def upsert_driver_compensation_setup(
    db: AsyncSession,
    *,
    tenant_id: int,
    person_id: int,
    payload: DriverCompensationSetupWrite,
    include_provisional: bool = False,
) -> DriverCompensationSetupOut:
    ext = await _get_driver_extension(db, tenant_id=tenant_id, person_id=person_id)
    if ext is None:
        raise ValueError("driver_person_extension_required")
    worker_type = worker_type_for_employment_relationship(ext.employment_relationship_type)

    op_driver = await _get_operational_driver_for_person(
        db, tenant_id=tenant_id, person_id=person_id, include_provisional=include_provisional
    )
    if not op_driver:
        raise ValueError("operational_driver_missing")

    if not op_driver.payee_id:
        display_name = f"{op_driver.first_name} {op_driver.last_name}".strip() or f"Driver {op_driver.id}"
        payee = Payee(
            tenant_id=tenant_id,
            payee_type=PayeeType.DRIVER,
            worker_type=worker_type,
            display_name=display_name,
            is_active=True,
        )
        db.add(payee)
        await db.flush()
        op_driver.payee_id = payee.id
    else:
        payee = await db.get(Payee, op_driver.payee_id)
        if not payee or payee.tenant_id != tenant_id:
            raise ValueError("payee_not_found")
        payee.worker_type = worker_type

    await _apply_driver_compensation_write(db, tenant_id=tenant_id, payee=payee, payload=payload)
    return await get_driver_compensation_setup(
        db, tenant_id=tenant_id, person_id=person_id, include_provisional=include_provisional
    )


async def apply_people_workspace_compensation_correction(
    db: AsyncSession,
    *,
    tenant_id: int,
    person_id: int,
    payload: DriverCompensationSetupWrite,
) -> None:
    """
    People workspace: correct payee + open compensation profile for the person's active operational driver.

    * Requires an active operational `drivers` row for the person.
    * If `drivers.payee_id` is null, creates a payee only when `driver_person_extensions` exists (worker type).
    * If payee exists and extension exists, refreshes `payees.worker_type` from extension; if extension is missing,
      leaves `payees.worker_type` unchanged (correction-only path).
    """
    op_driver = await _get_operational_driver_for_person(db, tenant_id=tenant_id, person_id=person_id)
    if not op_driver:
        raise ValueError("operational_driver_missing")

    ext = await _get_driver_extension(db, tenant_id=tenant_id, person_id=person_id)

    if not op_driver.payee_id:
        if ext is None:
            raise ValueError("driver_classification_required_for_payee")
        worker_type = worker_type_for_employment_relationship(ext.employment_relationship_type)
        display_name = f"{op_driver.first_name} {op_driver.last_name}".strip() or f"Driver {op_driver.id}"
        payee = Payee(
            tenant_id=tenant_id,
            payee_type=PayeeType.DRIVER,
            worker_type=worker_type,
            display_name=display_name,
            is_active=True,
        )
        db.add(payee)
        await db.flush()
        op_driver.payee_id = payee.id
        await db.flush()
    else:
        payee = await db.get(Payee, op_driver.payee_id)
        if not payee or payee.tenant_id != tenant_id:
            raise ValueError("payee_not_found")
        if ext is not None:
            payee.worker_type = worker_type_for_employment_relationship(ext.employment_relationship_type)

    await _apply_driver_compensation_write(db, tenant_id=tenant_id, payee=payee, payload=payload)


def compensation_setup_audit_diff(
    before: DriverCompensationSetupOut,
    after: DriverCompensationSetupOut,
) -> dict[str, dict[str, Any]]:
    """Field-level before/after for tenant audit (JSON-serializable)."""
    keys = (
        "payee_id",
        "worker_type",
        "gross_calc_type",
        "percent_rate",
        "cpm_loaded",
        "cpm_empty",
        "hourly_rate",
        "salary_amount",
        "flat_amount",
        "settlement_frequency",
        "participates_in_fuel_discount_program",
        "dispatch_fee_enabled",
        "dispatch_fee_rate",
        "dispatch_fee_basis",
        "effective_from",
        "scheduled_change_effective_from",
    )
    bd = before.model_dump(mode="json")
    ad = after.model_dump(mode="json")
    changed: dict[str, dict[str, Any]] = {}
    for k in keys:
        if bd.get(k) != ad.get(k):
            changed[k] = {"before": bd.get(k), "after": ad.get(k)}
    return changed


def compensation_profile_meets_onboarding_minimum(prof: CompensationProfile) -> bool:
    """True when gross model has the required primary rate fields populated."""
    g = prof.gross_calc_type
    if g == GrossCalcType.PERCENT_REVENUE:
        return prof.percent_rate is not None and 0 < prof.percent_rate <= 1
    if g == GrossCalcType.CPM:
        return prof.cpm_loaded is not None and prof.cpm_loaded > 0
    if g == GrossCalcType.HOURLY:
        return prof.hourly_rate is not None and prof.hourly_rate > 0
    if g == GrossCalcType.SALARY:
        return prof.salary_amount is not None and prof.salary_amount > 0
    if g == GrossCalcType.FLAT_PER_LOAD:
        return prof.flat_amount is not None and prof.flat_amount > 0
    return False


async def assert_combined_driver_onboarding_ready(
    db: AsyncSession,
    *,
    tenant_id: int,
    app: PersonApplication,
) -> None:
    """Raise ValueError with stable code if DRIVER+combined mandatory blocks are incomplete."""
    if not app.person_id:
        raise ValueError("onboarding_person_missing")

    ext = await _get_driver_extension(db, tenant_id=tenant_id, person_id=int(app.person_id))
    if ext is None:
        raise ValueError("onboarding_driver_configuration_incomplete")

    op_driver = await _get_operational_driver_for_person(
        db, tenant_id=tenant_id, person_id=int(app.person_id), include_provisional=True
    )
    if not op_driver:
        raise ValueError("onboarding_operational_driver_missing")

    if not op_driver.payee_id:
        raise ValueError("onboarding_compensation_incomplete")

    prof = await _select_current_profile_for_payee(db, tenant_id=tenant_id, payee_id=int(op_driver.payee_id))
    if prof is None or not compensation_profile_meets_onboarding_minimum(prof):
        raise ValueError("onboarding_compensation_incomplete")
