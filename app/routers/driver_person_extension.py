"""Phase 3A: admin API for driver_person_extensions (person-centered, tenant-safe)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps.admin import is_tenant_admin
from app.deps.auth import CurrentUser, get_current_user
from app.deps.entitlements import require_entitlement
from app.deps.tenant import require_tenant
from app.deps.tenant_db import get_tenant_db
from app.models.driver_person_extension import DriverPersonExtension
from app.models.person import Person
from app.schemas.driver_person_extension import DriverPersonExtensionOut, DriverPersonExtensionWrite

router = APIRouter(
    prefix="/driver-person-extensions",
    tags=["driver-person-extensions"],
    dependencies=[Depends(require_entitlement("admin_sensitive"))],
)


@router.get("/{person_id}", response_model=DriverPersonExtensionOut)
async def get_driver_person_extension(
    person_id: int,
    tenant_id: int = Depends(require_tenant),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    if not is_tenant_admin(current_user.role):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin role required")

    person = await db.scalar(
        select(Person).where(Person.tenant_id == tenant_id, Person.id == person_id)
    )
    if not person:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Person not found")

    row = await db.scalar(
        select(DriverPersonExtension).where(
            DriverPersonExtension.tenant_id == tenant_id,
            DriverPersonExtension.person_id == person_id,
        )
    )
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Driver extension not found")
    return row


@router.put("/{person_id}", response_model=DriverPersonExtensionOut)
async def upsert_driver_person_extension(
    person_id: int,
    payload: DriverPersonExtensionWrite,
    tenant_id: int = Depends(require_tenant),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    if not is_tenant_admin(current_user.role):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin role required")

    person = await db.scalar(
        select(Person).where(Person.tenant_id == tenant_id, Person.id == person_id)
    )
    if not person:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Person not found")

    row = await db.scalar(
        select(DriverPersonExtension).where(
            DriverPersonExtension.tenant_id == tenant_id,
            DriverPersonExtension.person_id == person_id,
        )
    )
    data = payload.model_dump()
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

    await db.commit()
    await db.refresh(row)
    return row
