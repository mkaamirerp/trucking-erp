from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.driver import Driver
from app.models.driver_document import DriverDocument
from app.deps.tenant import require_tenant
from app.schemas.onboarding import (
    DriverLicenseOCRRequest,
    DriverLicenseOCRResponse,
    DriverLicenseConfirmRequest,
    DriverLicenseConfirmResponse,
)

router = APIRouter(prefix="/api/v1/onboarding", tags=["Onboarding"])


@router.post("/driver-license/ocr", response_model=DriverLicenseOCRResponse)
async def driver_license_ocr(
    _: DriverLicenseOCRRequest,
    tenant_id: int = Depends(require_tenant),
):
    # Placeholder: return empty suggestions; frontend can still integrate contract
    _ = tenant_id
    return DriverLicenseOCRResponse(suggestions={})


@router.post("/driver-license/confirm", response_model=DriverLicenseConfirmResponse)
async def driver_license_confirm(
    payload: DriverLicenseConfirmRequest,
    tenant_id: int = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    driver = await db.scalar(select(Driver).where(Driver.id == payload.driver_id, Driver.tenant_id == tenant_id))
    if not driver:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Driver not found")

    issuing_country = payload.issuing_country.upper()
    if not payload.license_number or not payload.license_expiry_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="license_number and license_expiry_date are required",
        )

    # Update driver license fields
    for field in (
        "issuing_country",
        "issuing_region",
        "license_number",
        "license_class",
        "license_issue_date",
        "license_expiry_date",
    ):
        val = issuing_country if field == "issuing_country" else getattr(payload, field)
        if val is not None:
            setattr(driver, field, val)

    # Optionally enforce single current DRIVER_LICENSE: deactivate others
    await db.execute(
        update(DriverDocument)
        .where(
            DriverDocument.driver_id == payload.driver_id,
            DriverDocument.tenant_id == tenant_id,
            DriverDocument.doc_type == "DRIVER_LICENSE",
            DriverDocument.is_current.is_(True),
        )
        .values(is_current=False)
    )

    doc = DriverDocument(
        driver_id=payload.driver_id,
        tenant_id=tenant_id,
        doc_type="DRIVER_LICENSE",
        doc_subtype=payload.license_class,
        issuing_country_snapshot=issuing_country,
        title="Driver License",
        issue_date=payload.license_issue_date,
        expiry_date=payload.license_expiry_date,
        status="ACTIVE",
        notes=payload.notes or payload.raw_ocr_text,
        is_current=True,
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)
    await db.refresh(driver)

    return DriverLicenseConfirmResponse(
        driver_id=driver.id,
        document_id=doc.id,
        doc_type=doc.doc_type,
        license_number=driver.license_number,
        license_class=driver.license_class,
        license_expiry_date=driver.license_expiry_date,
        issuing_country=driver.issuing_country,
    )
