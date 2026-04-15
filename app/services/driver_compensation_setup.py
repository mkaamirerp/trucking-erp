"""Operational driver payee + compensation_profiles for combined-mode onboarding (no driver_person_extensions writes)."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.driver import Driver
from app.models.driver_person_extension import DriverPersonExtension
from app.models.enums import GrossCalcType, PayeeType, WorkerType
from app.models.payee import CompensationProfile, Payee
from app.models.person_application import PersonApplication
from app.schemas.driver_compensation_setup import DriverCompensationSetupOut, DriverCompensationSetupWrite


def _utc_today() -> date:
    return datetime.now(timezone.utc).date()


def _extension_to_worker_type(employment_relationship_type: str | None) -> WorkerType:
    ert = (employment_relationship_type or "").strip().lower()
    if ert == "owner_operator":
        return WorkerType.OWNER_OPERATOR_LEASED_ON
    return WorkerType.EMPLOYEE_DRIVER


def _is_open_profile_row(p: CompensationProfile, today: date) -> bool:
    if p.effective_to is not None and p.effective_to < today:
        return False
    return True


async def _get_operational_driver_for_person(
    db: AsyncSession, *, tenant_id: int, person_id: int
) -> Driver | None:
    res = await db.scalars(
        select(Driver)
        .where(Driver.tenant_id == tenant_id, Driver.person_id == person_id, Driver.is_active.is_(True))
        .order_by(Driver.id.asc())
    )
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


async def _select_current_profile_for_payee(
    db: AsyncSession, *, tenant_id: int, payee_id: int
) -> CompensationProfile | None:
    today = _utc_today()
    res = await db.scalars(
        select(CompensationProfile)
        .where(
            CompensationProfile.tenant_id == tenant_id,
            CompensationProfile.payee_id == payee_id,
        )
        .order_by(CompensationProfile.effective_from.desc(), CompensationProfile.id.desc())
    )
    for row in res.all():
        if _is_open_profile_row(row, today):
            return row
    return None


async def _apply_driver_compensation_write(
    db: AsyncSession,
    *,
    tenant_id: int,
    payee: Payee,
    payload: DriverCompensationSetupWrite,
) -> None:
    """Upsert the open `compensation_profiles` row for `payee` from a validated write payload."""
    gross = GrossCalcType(payload.gross_calc_type.value)
    cpm_empty = payload.cpm_empty
    if gross == GrossCalcType.CPM and cpm_empty is None:
        cpm_empty = payload.cpm_loaded

    prof = await _select_current_profile_for_payee(db, tenant_id=tenant_id, payee_id=payee.id)
    today = _utc_today()
    wt_snap = payee.worker_type

    if prof is None:
        prof = CompensationProfile(
            tenant_id=tenant_id,
            payee_id=payee.id,
            effective_from=today,
            effective_to=None,
            worker_type_snapshot=wt_snap,
            gross_calc_type=gross,
            percent_rate=payload.percent_rate,
            cpm_loaded=payload.cpm_loaded,
            cpm_empty=cpm_empty,
            hourly_rate=payload.hourly_rate,
            salary_amount=payload.salary_amount,
            flat_amount=payload.flat_amount,
            dispatch_fee_enabled=payload.dispatch_fee_enabled,
            dispatch_fee_rate=payload.dispatch_fee_rate,
            dispatch_fee_basis=(payload.dispatch_fee_basis or "GROSS").strip() or "GROSS",
            settlement_frequency=payload.settlement_frequency,
            participates_in_fuel_discount_program=payload.participates_in_fuel_discount_program,
        )
        db.add(prof)
    else:
        prof.worker_type_snapshot = wt_snap
        prof.gross_calc_type = gross
        prof.percent_rate = payload.percent_rate
        prof.cpm_loaded = payload.cpm_loaded
        prof.cpm_empty = cpm_empty
        prof.hourly_rate = payload.hourly_rate
        prof.salary_amount = payload.salary_amount
        prof.flat_amount = payload.flat_amount
        prof.dispatch_fee_enabled = payload.dispatch_fee_enabled
        prof.dispatch_fee_rate = payload.dispatch_fee_rate
        prof.dispatch_fee_basis = (payload.dispatch_fee_basis or "GROSS").strip() or "GROSS"
        prof.settlement_frequency = payload.settlement_frequency
        prof.participates_in_fuel_discount_program = payload.participates_in_fuel_discount_program

    await db.flush()


async def get_driver_compensation_setup(
    db: AsyncSession,
    *,
    tenant_id: int,
    person_id: int,
) -> DriverCompensationSetupOut:
    ext = await _get_driver_extension(db, tenant_id=tenant_id, person_id=person_id)
    employment = ext.employment_relationship_type if ext else None

    op_driver = await _get_operational_driver_for_person(db, tenant_id=tenant_id, person_id=person_id)
    if not op_driver or not op_driver.payee_id:
        return DriverCompensationSetupOut(employment_relationship_type=employment)

    payee = await db.get(Payee, op_driver.payee_id)
    if not payee or payee.tenant_id != tenant_id:
        return DriverCompensationSetupOut(employment_relationship_type=employment)

    prof = await _select_current_profile_for_payee(db, tenant_id=tenant_id, payee_id=payee.id)
    if not prof:
        return DriverCompensationSetupOut(
            payee_id=payee.id,
            worker_type=payee.worker_type.value,
            employment_relationship_type=employment,
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
    )


async def upsert_driver_compensation_setup(
    db: AsyncSession,
    *,
    tenant_id: int,
    person_id: int,
    payload: DriverCompensationSetupWrite,
) -> DriverCompensationSetupOut:
    ext = await _get_driver_extension(db, tenant_id=tenant_id, person_id=person_id)
    if ext is None:
        raise ValueError("driver_person_extension_required")
    worker_type = _extension_to_worker_type(ext.employment_relationship_type)

    op_driver = await _get_operational_driver_for_person(db, tenant_id=tenant_id, person_id=person_id)
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
    return await get_driver_compensation_setup(db, tenant_id=tenant_id, person_id=person_id)


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
        worker_type = _extension_to_worker_type(ext.employment_relationship_type)
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
            payee.worker_type = _extension_to_worker_type(ext.employment_relationship_type)

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
        return prof.percent_rate is not None and prof.percent_rate > 0
    if g == GrossCalcType.CPM:
        return prof.cpm_loaded is not None and prof.cpm_loaded >= 0
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

    op_driver = await _get_operational_driver_for_person(db, tenant_id=tenant_id, person_id=int(app.person_id))
    if not op_driver:
        raise ValueError("onboarding_operational_driver_missing")

    if not op_driver.payee_id:
        raise ValueError("onboarding_compensation_incomplete")

    prof = await _select_current_profile_for_payee(db, tenant_id=tenant_id, payee_id=int(op_driver.payee_id))
    if prof is None or not compensation_profile_meets_onboarding_minimum(prof):
        raise ValueError("onboarding_compensation_incomplete")
