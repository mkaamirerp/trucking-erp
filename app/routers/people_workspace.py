"""Tenant admin People workspace: maintained `people` master data (not onboarding workflow)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps.admin import is_tenant_admin
from app.deps.auth import CurrentUser, get_current_user
from app.deps.entitlements import require_entitlement
from app.deps.tenant import require_tenant
from app.deps.tenant_db import get_tenant_db
from app.models.driver_person_extension import DriverPersonExtension
from app.models.platform import PlatformTenantMember, PlatformUser
from app.models.person import DriverProfile, Person
from app.schemas.driver_compensation_setup import DriverCompensationSetupOut, DriverCompensationSetupWrite
from app.schemas.driver_person_extension import DriverPersonExtensionOut, DriverPersonExtensionWrite
from app.schemas.people_workspace import (
    DriverProfilePatch,
    PeopleAuditLogEntryOut,
    PeopleCorePatch,
    PeopleDetailOut,
    PeopleListItemOut,
    PeoplePatchResultOut,
)
from app.services.driver_compensation_setup import (
    apply_people_workspace_compensation_correction,
    compensation_setup_audit_diff,
    get_driver_compensation_setup,
)
from app.services.people_workspace import (
    build_people_detail_out,
    build_people_list_items_out,
    driver_role_attached_config_audit_snapshot,
    driver_role_attached_configuration_audit_diff,
    list_people_maintenance_audit_entries,
    people_search_filter,
    person_has_active_driver_role,
    sync_operational_drivers_core_from_person,
    sync_operational_drivers_license_from_driver_profile,
    write_people_patch_audit,
)

router = APIRouter(
    prefix="/api/v1/people",
    tags=["people-workspace"],
    dependencies=[Depends(require_entitlement("admin_sensitive"))],
)


def _require_admin(current_user: CurrentUser) -> None:
    if not is_tenant_admin(current_user.role):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin role required")


@router.get("", response_model=list[PeopleListItemOut])
async def list_people(
    tenant_id: int = Depends(require_tenant),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
    q: str | None = Query(None, description="Search first name, last name, email, phone"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    _require_admin(current_user)
    stmt = select(Person).where(Person.tenant_id == tenant_id)
    if q and q.strip():
        stmt = people_search_filter(stmt, q=q.strip())
    stmt = stmt.order_by(Person.id.desc()).offset(offset).limit(limit)
    result = await db.execute(stmt)
    rows = result.scalars().all()
    return await build_people_list_items_out(db, tenant_id=tenant_id, people=list(rows))


@router.patch("/{person_id}/driver-profile", response_model=PeoplePatchResultOut)
async def patch_person_driver_profile(
    person_id: int,
    payload: DriverProfilePatch,
    request: Request,
    tenant_id: int = Depends(require_tenant),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    """Update `driver_profiles` license fields; sync active operational `drivers` license duplicates."""
    _require_admin(current_user)
    person = await db.scalar(
        select(Person).where(Person.tenant_id == tenant_id, Person.id == person_id).with_for_update()
    )
    if not person:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Person not found")
    if not await person_has_active_driver_role(db, tenant_id=tenant_id, person_id=person_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Driver profile edits require an active DRIVER role on this person",
        )

    data = payload.model_dump(exclude_unset=True)
    if not data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No fields to update")

    dp = await db.scalar(
        select(DriverProfile)
        .where(DriverProfile.tenant_id == tenant_id, DriverProfile.person_id == person_id)
        .with_for_update()
    )
    if dp is None:
        dp = DriverProfile(
            tenant_id=tenant_id,
            person_id=person_id,
            license_number=None,
            license_region=None,
            license_expiry=None,
            is_active=True,
        )
        db.add(dp)
        await db.flush()

    changed: dict[str, Any] = {}
    touched_keys: set[str] = set()
    for key in ("license_number", "license_region", "license_expiry", "is_active"):
        if key not in data:
            continue
        new_val = data[key]
        old = getattr(dp, key)
        if old != new_val:
            changed[key] = {"before": old, "after": new_val}
            setattr(dp, key, new_val)
            touched_keys.add(key)

    if not changed:
        detail = await build_people_detail_out(db, tenant_id=tenant_id, person=person)
        return PeoplePatchResultOut(person=detail, synced_operational_driver_ids=[])

    synced = await sync_operational_drivers_license_from_driver_profile(
        db,
        tenant_id=tenant_id,
        person_id=person_id,
        profile=dp,
        touched_keys=touched_keys,
    )

    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent")
    await write_people_patch_audit(
        db,
        tenant_id=tenant_id,
        person_id=person_id,
        actor_user_id=current_user.member_id,
        changed=changed,
        ip=ip,
        user_agent=ua,
        request_id=getattr(request.state, "request_id", None),
        action="people_driver_profile_patch",
    )

    await db.commit()
    await db.refresh(person)
    await db.refresh(dp)
    detail = await build_people_detail_out(db, tenant_id=tenant_id, person=person)
    return PeoplePatchResultOut(person=detail, synced_operational_driver_ids=synced)


@router.get("/{person_id}/compensation-setup", response_model=DriverCompensationSetupOut)
async def get_person_compensation_setup(
    person_id: int,
    tenant_id: int = Depends(require_tenant),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    """Read payee + current open `compensation_profiles` row via active operational driver (same model as onboarding)."""
    _require_admin(current_user)
    person = await db.scalar(select(Person).where(Person.tenant_id == tenant_id, Person.id == person_id))
    if not person:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Person not found")
    return await get_driver_compensation_setup(db, tenant_id=tenant_id, person_id=person_id)


@router.patch("/{person_id}/compensation-setup", response_model=PeoplePatchResultOut)
async def patch_person_compensation_setup(
    person_id: int,
    body: DriverCompensationSetupWrite,
    request: Request,
    tenant_id: int = Depends(require_tenant),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    """Correct compensation on `payees` + open `compensation_profiles` for this person's active operational driver."""
    _require_admin(current_user)
    person = await db.scalar(
        select(Person).where(Person.tenant_id == tenant_id, Person.id == person_id).with_for_update()
    )
    if not person:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Person not found")

    before = await get_driver_compensation_setup(db, tenant_id=tenant_id, person_id=person_id)
    try:
        await apply_people_workspace_compensation_correction(
            db, tenant_id=tenant_id, person_id=person_id, payload=body
        )
    except ValueError as exc:
        code = str(exc)
        if code == "operational_driver_missing":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Compensation edits require an active operational driver row for this person.",
            ) from exc
        if code == "driver_classification_required_for_payee":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "No payee is linked on the operational driver row. "
                    "Save driver classification (driver person extension) first, then retry — "
                    "or link an existing payee on the operational driver record."
                ),
            ) from exc
        if code == "payee_not_found":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payee not found") from exc
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=code) from exc

    after = await get_driver_compensation_setup(db, tenant_id=tenant_id, person_id=person_id)
    changed = compensation_setup_audit_diff(before, after)
    if changed:
        ip = request.client.host if request.client else None
        ua = request.headers.get("user-agent")
        await write_people_patch_audit(
            db,
            tenant_id=tenant_id,
            person_id=person_id,
            actor_user_id=current_user.member_id,
            changed=changed,
            ip=ip,
            user_agent=ua,
                request_id=getattr(request.state, "request_id", None),
            action="people_compensation_patch",
        )

    await db.commit()
    await db.refresh(person)
    detail = await build_people_detail_out(db, tenant_id=tenant_id, person=person)
    return PeoplePatchResultOut(person=detail, synced_operational_driver_ids=[])


@router.get(
    "/{person_id}/driver-role-configuration",
    response_model=DriverPersonExtensionOut | None,
)
async def get_person_driver_role_configuration(
    person_id: int,
    tenant_id: int = Depends(require_tenant),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    """People-first read for role-attached driver configuration row (`driver_person_extensions`); null if none yet."""
    _require_admin(current_user)
    person = await db.scalar(select(Person).where(Person.tenant_id == tenant_id, Person.id == person_id))
    if not person:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Person not found")
    row = await db.scalar(
        select(DriverPersonExtension).where(
            DriverPersonExtension.tenant_id == tenant_id,
            DriverPersonExtension.person_id == person_id,
        )
    )
    return row


@router.patch("/{person_id}/driver-role-configuration", response_model=PeoplePatchResultOut)
async def patch_person_driver_role_configuration(
    person_id: int,
    body: DriverPersonExtensionWrite,
    request: Request,
    tenant_id: int = Depends(require_tenant),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    """
    People workspace: upsert role-attached driver configuration on `driver_person_extensions`.

    Concrete table today: driver person extension (not onboarding-specific; workflow remains separate).
    Requires an active DRIVER role on the person.
    """
    _require_admin(current_user)
    person = await db.scalar(
        select(Person).where(Person.tenant_id == tenant_id, Person.id == person_id).with_for_update()
    )
    if not person:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Person not found")
    if not await person_has_active_driver_role(db, tenant_id=tenant_id, person_id=person_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Role-attached driver configuration requires an active DRIVER role on this person. "
                "Assign or activate the role, then edit here."
            ),
        )

    row = await db.scalar(
        select(DriverPersonExtension)
        .where(
            DriverPersonExtension.tenant_id == tenant_id,
            DriverPersonExtension.person_id == person_id,
        )
        .with_for_update()
    )
    before_snap = driver_role_attached_config_audit_snapshot(row)
    data = body.model_dump()
    if row is None:
        row = DriverPersonExtension(
            tenant_id=tenant_id,
            person_id=person_id,
            **data,
        )
        db.add(row)
    else:
        for k, v in data.items():
            setattr(row, k, v)
    await db.flush()
    await db.refresh(row)
    after_snap = driver_role_attached_config_audit_snapshot(row)
    assert after_snap is not None
    changed = driver_role_attached_configuration_audit_diff(before_snap, after_snap)
    if changed:
        ip = request.client.host if request.client else None
        ua = request.headers.get("user-agent")
        await write_people_patch_audit(
            db,
            tenant_id=tenant_id,
            person_id=person_id,
            actor_user_id=current_user.member_id,
            changed=changed,
            ip=ip,
            user_agent=ua,
            request_id=getattr(request.state, "request_id", None),
            action="people_driver_role_configuration_patch",
        )

    await db.commit()
    await db.refresh(person)
    detail = await build_people_detail_out(db, tenant_id=tenant_id, person=person)
    return PeoplePatchResultOut(person=detail, synced_operational_driver_ids=[])


@router.get("/{person_id}/audit-log", response_model=list[PeopleAuditLogEntryOut])
async def list_person_maintenance_audit_log(
    person_id: int,
    tenant_id: int = Depends(require_tenant),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
    platform_db: AsyncSession = Depends(get_db),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """Read-only history of People workspace corrections (tenant audit log subset)."""
    _require_admin(current_user)
    person = await db.scalar(select(Person).where(Person.tenant_id == tenant_id, Person.id == person_id))
    if not person:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Person not found")

    rows = await list_people_maintenance_audit_entries(
        db,
        tenant_id=tenant_id,
        person_id=person_id,
        limit=limit,
        offset=offset,
    )
    member_ids = [int(r.actor_user_id) for r in rows if r.actor_user_id is not None]
    emails: dict[int, str] = {}
    if member_ids:
        res = await platform_db.execute(
            select(PlatformTenantMember.id, PlatformUser.email)
            .join(PlatformUser, PlatformUser.id == PlatformTenantMember.platform_user_id)
            .where(PlatformTenantMember.id.in_(member_ids))
        )
        emails = {int(i): str(em) for i, em in res.all()}

    out: list[PeopleAuditLogEntryOut] = []
    for r in rows:
        dj = r.details_json if isinstance(r.details_json, dict) else {}
        raw_keys = dj.get("changed_keys")
        if isinstance(raw_keys, list):
            changed_keys = [str(x) for x in raw_keys]
        else:
            changed_keys = []
        snap = dj.get("snapshot")
        snapshot = snap if isinstance(snap, dict) else {}
        aid = int(r.actor_user_id) if r.actor_user_id is not None else None
        out.append(
            PeopleAuditLogEntryOut(
                id=int(r.id),
                action=str(r.action),
                created_at=r.created_at,
                actor_user_id=aid,
                actor_email=emails.get(aid) if aid is not None else None,
                ip=r.ip,
                user_agent=r.user_agent,
                changed_keys=changed_keys,
                snapshot=snapshot,
            )
        )
    return out


@router.get("/{person_id}", response_model=PeopleDetailOut)
async def get_person_detail(
    person_id: int,
    tenant_id: int = Depends(require_tenant),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    _require_admin(current_user)
    person = await db.scalar(
        select(Person).where(Person.tenant_id == tenant_id, Person.id == person_id)
    )
    if not person:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Person not found")
    return await build_people_detail_out(db, tenant_id=tenant_id, person=person)


@router.patch("/{person_id}", response_model=PeoplePatchResultOut)
async def patch_person_core(
    person_id: int,
    payload: PeopleCorePatch,
    request: Request,
    tenant_id: int = Depends(require_tenant),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    """Update canonical `people` core fields; refresh duplicate contact/name on linked operational `drivers`."""
    _require_admin(current_user)
    person = await db.scalar(
        select(Person)
        .where(Person.tenant_id == tenant_id, Person.id == person_id)
        .with_for_update()
    )
    if not person:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Person not found")

    data = payload.model_dump(exclude_unset=True)
    if not data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No fields to update")

    changed: dict[str, Any] = {}
    for key, new_val in data.items():
        old = getattr(person, key)
        # Normalize email to str for comparison/storage
        if key == "email" and new_val is not None:
            new_val = str(new_val).strip() or None
        if old != new_val:
            changed[key] = {"before": old, "after": new_val}
            setattr(person, key, new_val)

    if not changed:
        detail = await build_people_detail_out(db, tenant_id=tenant_id, person=person)
        return PeoplePatchResultOut(person=detail, synced_operational_driver_ids=[])

    synced = await sync_operational_drivers_core_from_person(db, tenant_id=tenant_id, person=person)

    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent")
    await write_people_patch_audit(
        db,
        tenant_id=tenant_id,
        person_id=int(person.id),
        actor_user_id=current_user.member_id,
        changed=changed,
        ip=ip,
        user_agent=ua,
        request_id=getattr(request.state, "request_id", None),
    )

    await db.commit()
    await db.refresh(person)
    detail = await build_people_detail_out(db, tenant_id=tenant_id, person=person)
    return PeoplePatchResultOut(person=detail, synced_operational_driver_ids=synced)
