"""People workspace: aggregate reads and operational-driver sync from canonical `people`."""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.driver import Driver
from app.models.driver_person_extension import DriverPersonExtension
from app.models.person import DriverProfile, Person, PersonRole
from app.models.person_application import PersonApplication
from app.schemas.people_workspace import (
    CompensationSummary,
    DriverPersonExtensionSummary,
    DriverProfileSummary,
    LinkedPersonApplicationSummary,
    OperationalDriverSummary,
    PeopleDetailOut,
    PersonRoleSummary,
)
from app.services.driver_compensation_setup import get_driver_compensation_setup

logger = logging.getLogger(__name__)

# People workspace: audit diff for role-attached driver configuration (`driver_person_extensions`).
DRIVER_ROLE_ATTACHED_CONFIG_AUDIT_FIELDS: tuple[str, ...] = (
    "employment_relationship_type",
    "driver_operating_subtype",
    "is_team_driver",
    "team_role_type",
    "provides_own_truck",
    "provides_own_trailer",
    "equipment_contribution_type",
    "insurance_commercial_approved",
)


def driver_role_attached_config_audit_snapshot(ext: DriverPersonExtension | None) -> dict[str, Any] | None:
    """JSON-friendly field snapshot for tenant audit (no ORM object)."""
    if ext is None:
        return None
    return {k: getattr(ext, k) for k in DRIVER_ROLE_ATTACHED_CONFIG_AUDIT_FIELDS}


def driver_role_attached_configuration_audit_diff(
    before: dict[str, Any] | None,
    after: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    changed: dict[str, dict[str, Any]] = {}
    for k in DRIVER_ROLE_ATTACHED_CONFIG_AUDIT_FIELDS:
        av = after.get(k)
        bv = before.get(k) if before is not None else None
        if bv != av:
            changed[k] = {"before": bv, "after": av}
    return changed


# People workspace correction flows that write to tenant_audit_logs (object_type=person).
PEOPLE_MAINTENANCE_AUDIT_ACTIONS: frozenset[str] = frozenset(
    {
        "people_core_patch",
        "people_driver_profile_patch",
        "people_compensation_patch",
        "people_driver_role_configuration_patch",
    }
)


async def list_people_maintenance_audit_entries(
    db: AsyncSession,
    *,
    tenant_id: int,
    person_id: int,
    limit: int = 50,
    offset: int = 0,
) -> list[Any]:
    """Return tenant audit rows for People-maintained corrections only (newest first)."""
    from app.models.tenant import TenantAuditLog

    cap = max(1, min(int(limit), 200))
    off = max(0, int(offset))
    stmt = (
        select(TenantAuditLog)
        .where(
            TenantAuditLog.tenant_id == tenant_id,
            TenantAuditLog.object_type == "person",
            TenantAuditLog.object_id == str(int(person_id)),
            TenantAuditLog.action.in_(PEOPLE_MAINTENANCE_AUDIT_ACTIONS),
        )
        .order_by(TenantAuditLog.created_at.desc(), TenantAuditLog.id.desc())
        .offset(off)
        .limit(cap)
    )
    result = await db.scalars(stmt)
    return list(result.all())


def _dec_str(v: Decimal | None) -> str | None:
    if v is None:
        return None
    return format(v, "f").rstrip("0").rstrip(".") if "." in format(v, "f") else str(v)


async def sync_operational_drivers_core_from_person(
    db: AsyncSession,
    *,
    tenant_id: int,
    person: Person,
) -> list[int]:
    """Refresh duplicate name/contact on active `drivers` rows linked by person_id (canonical = `people`)."""
    result = await db.scalars(
        select(Driver).where(
            Driver.tenant_id == tenant_id,
            Driver.person_id == person.id,
            Driver.is_active.is_(True),
        )
    )
    rows = list(result.all())
    touched: list[int] = []
    for d in rows:
        d.first_name = person.first_name
        d.last_name = person.last_name
        d.email = person.email
        d.phone = person.phone
        touched.append(int(d.id))
    if touched:
        await db.flush()
    return touched


async def person_has_active_driver_role(
    db: AsyncSession,
    *,
    tenant_id: int,
    person_id: int,
) -> bool:
    row = await db.scalar(
        select(PersonRole.id).where(
            PersonRole.tenant_id == tenant_id,
            PersonRole.person_id == person_id,
            PersonRole.is_active.is_(True),
            func.upper(PersonRole.role_code) == "DRIVER",
        )
    )
    return row is not None


async def sync_operational_drivers_license_from_driver_profile(
    db: AsyncSession,
    *,
    tenant_id: int,
    person_id: int,
    profile: DriverProfile,
    touched_keys: set[str],
) -> list[int]:
    """Copy license fields from `driver_profiles` onto active `drivers` for same person_id."""
    if not touched_keys:
        return []
    result = await db.scalars(
        select(Driver).where(
            Driver.tenant_id == tenant_id,
            Driver.person_id == person_id,
            Driver.is_active.is_(True),
        )
    )
    rows = list(result.all())
    out: list[int] = []
    for d in rows:
        if "license_number" in touched_keys:
            d.license_number = profile.license_number
        if "license_region" in touched_keys:
            d.issuing_region = profile.license_region
        if "license_expiry" in touched_keys:
            d.license_expiry_date = profile.license_expiry
        out.append(int(d.id))
    if out:
        await db.flush()
    return out


async def build_people_detail_out(
    db: AsyncSession,
    *,
    tenant_id: int,
    person: Person,
) -> PeopleDetailOut:
    roles_result = await db.scalars(
        select(PersonRole).where(
            PersonRole.tenant_id == tenant_id,
            PersonRole.person_id == person.id,
        )
    )
    roles = [
        PersonRoleSummary(
            role_code=r.role_code,
            is_primary=bool(r.is_primary),
            is_active=bool(r.is_active),
        )
        for r in roles_result.all()
    ]

    dp = await db.scalar(
        select(DriverProfile).where(
            DriverProfile.tenant_id == tenant_id,
            DriverProfile.person_id == person.id,
        )
    )
    driver_profile: DriverProfileSummary | None = None
    if dp:
        driver_profile = DriverProfileSummary(
            license_number=dp.license_number,
            license_region=dp.license_region,
            license_expiry=dp.license_expiry,
            is_active=bool(dp.is_active),
        )

    ext = await db.scalar(
        select(DriverPersonExtension).where(
            DriverPersonExtension.tenant_id == tenant_id,
            DriverPersonExtension.person_id == person.id,
        )
    )
    driver_ext: DriverPersonExtensionSummary | None = None
    if ext:
        driver_ext = DriverPersonExtensionSummary(
            employment_relationship_type=ext.employment_relationship_type,
            driver_operating_subtype=ext.driver_operating_subtype,
            is_team_driver=bool(ext.is_team_driver),
            provides_own_truck=bool(ext.provides_own_truck),
            provides_own_trailer=bool(ext.provides_own_trailer),
            equipment_contribution_type=ext.equipment_contribution_type,
            insurance_commercial_approved=bool(ext.insurance_commercial_approved),
        )

    drv_result = await db.scalars(
        select(Driver).where(
            Driver.tenant_id == tenant_id,
            Driver.person_id == person.id,
        ).order_by(Driver.id.asc())
    )
    operational: list[OperationalDriverSummary] = []
    for d in drv_result.all():
        operational.append(
            OperationalDriverSummary(
                driver_id=int(d.id),
                is_active=bool(d.is_active),
                first_name=d.first_name,
                last_name=d.last_name,
                payee_id=int(d.payee_id) if d.payee_id is not None else None,
            )
        )

    comp_raw = await get_driver_compensation_setup(db, tenant_id=tenant_id, person_id=int(person.id))
    compensation = CompensationSummary(
        payee_id=comp_raw.payee_id,
        worker_type=comp_raw.worker_type,
        gross_calc_type=comp_raw.gross_calc_type,
        hourly_rate=_dec_str(comp_raw.hourly_rate) if comp_raw.hourly_rate is not None else None,
        cpm_loaded=_dec_str(comp_raw.cpm_loaded) if comp_raw.cpm_loaded is not None else None,
        cpm_empty=_dec_str(comp_raw.cpm_empty) if comp_raw.cpm_empty is not None else None,
        percent_rate=_dec_str(comp_raw.percent_rate) if comp_raw.percent_rate is not None else None,
        salary_amount=_dec_str(comp_raw.salary_amount) if comp_raw.salary_amount is not None else None,
        flat_amount=_dec_str(comp_raw.flat_amount) if comp_raw.flat_amount is not None else None,
        settlement_frequency=comp_raw.settlement_frequency,
        participates_in_fuel_discount_program=comp_raw.participates_in_fuel_discount_program,
        dispatch_fee_enabled=comp_raw.dispatch_fee_enabled,
        dispatch_fee_rate=_dec_str(comp_raw.dispatch_fee_rate),
        dispatch_fee_basis=comp_raw.dispatch_fee_basis,
    )

    latest_app = await db.scalar(
        select(PersonApplication)
        .where(
            PersonApplication.tenant_id == tenant_id,
            PersonApplication.person_id == person.id,
        )
        .order_by(PersonApplication.updated_at.desc(), PersonApplication.id.desc())
        .limit(1)
    )
    latest_application: LinkedPersonApplicationSummary | None = None
    if latest_app:
        latest_application = LinkedPersonApplicationSummary(
            id=int(latest_app.id),
            status=str(latest_app.status),
            setup_status=getattr(latest_app, "setup_status", None),
        )

    return PeopleDetailOut(
        id=int(person.id),
        tenant_id=int(person.tenant_id),
        first_name=person.first_name,
        last_name=person.last_name,
        phone=person.phone,
        email=person.email,
        city=person.city,
        region=person.region,
        is_active=bool(person.is_active),
        created_at=person.created_at,
        updated_at=person.updated_at,
        street_address=person.street_address,
        postal_code=person.postal_code,
        zip_code=person.zip_code,
        country=person.country,
        notes=person.notes,
        platform_user_id=person.platform_user_id,
        roles=roles,
        driver_profile=driver_profile,
        driver_person_extension=driver_ext,
        operational_drivers=operational,
        compensation=compensation,
        latest_application=latest_application,
    )


def people_search_filter(stmt: Any, *, q: str) -> Any:
    """Apply case-insensitive search on name / email / phone."""
    pattern = f"%{q.strip()}%"
    return stmt.where(
        or_(
            Person.first_name.ilike(pattern),
            Person.last_name.ilike(pattern),
            Person.email.ilike(pattern),
            Person.phone.ilike(pattern),
        )
    )


async def write_people_patch_audit(
    db: AsyncSession,
    *,
    tenant_id: int,
    person_id: int,
    actor_user_id: int | None,
    changed: dict[str, Any],
    ip: str | None,
    user_agent: str | None,
    action: str = "people_core_patch",
) -> None:
    """Best-effort tenant audit row; never raises."""
    try:
        from app.models.tenant import TenantAuditLog

        row = TenantAuditLog(
            tenant_id=int(tenant_id),
            actor_user_id=actor_user_id,
            action=action[:64],
            object_type="person",
            object_id=str(int(person_id)),
            details_json={"changed_keys": list(changed.keys()), "snapshot": changed},
            ip=(ip or None),
            user_agent=(user_agent[:256] if user_agent else None),
        )
        db.add(row)
        await db.flush()
    except Exception:
        logger.exception("%s audit insert failed; continuing", action)
