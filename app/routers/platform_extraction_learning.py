"""Platform admin: upsert **sanitized** extraction priors (no tenant PII in patterns)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.platform_extraction_learning import PlatformExtractionSanitizedPattern
from app.routers.platform_tenants import require_platform_admin_key
from app.schemas.platform_extraction_learning import (
    PlatformExtractionSanitizedPatternOut,
    PlatformExtractionSanitizedPatternUpsertIn,
)
from app.services.extraction_field_learning import sanitized_pattern_looks_unsafe

router = APIRouter(prefix="/api/v1/platform", tags=["platform-extraction-learning"])


@router.get("/extraction-sanitized-patterns", response_model=list[PlatformExtractionSanitizedPatternOut])
async def list_sanitized_patterns(
    is_active: bool | None = None,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_platform_admin_key),
):
    q = select(PlatformExtractionSanitizedPattern).order_by(PlatformExtractionSanitizedPattern.id.desc())
    if is_active is not None:
        q = q.where(PlatformExtractionSanitizedPattern.is_active.is_(is_active))
    r = await db.execute(q.limit(500))
    return list(r.scalars().all())


@router.put("/extraction-sanitized-patterns", response_model=PlatformExtractionSanitizedPatternOut)
async def upsert_sanitized_pattern(
    body: PlatformExtractionSanitizedPatternUpsertIn,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_platform_admin_key),
):
    reason = sanitized_pattern_looks_unsafe(
        body.broker_family_key.strip(),
        body.source_label_pattern.strip(),
        body.source_section_pattern.strip() if body.source_section_pattern else "",
        body.notes,
    )
    if reason:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Refusing unsanitized pattern: {reason}",
        )
    key = body.broker_family_key.strip()
    fpath = body.field_path.strip()
    lpat = body.source_label_pattern.strip()
    spat = (body.source_section_pattern or "").strip()[:256]
    vsh = body.value_shape_class.strip()

    r = await db.execute(
        select(PlatformExtractionSanitizedPattern).where(
            PlatformExtractionSanitizedPattern.broker_family_key == key,
            PlatformExtractionSanitizedPattern.field_path == fpath,
            PlatformExtractionSanitizedPattern.source_label_pattern == lpat,
            PlatformExtractionSanitizedPattern.source_section_pattern == spat,
            PlatformExtractionSanitizedPattern.value_shape_class == vsh,
        )
    )
    row = r.scalars().first()
    if row is None:
        row = PlatformExtractionSanitizedPattern(
            broker_family_key=key,
            field_path=fpath,
            source_label_pattern=lpat,
            source_section_pattern=spat,
            value_shape_class=vsh,
            section_role=body.section_role.strip()[:64],
            positive_count=body.positive_count,
            negative_count=body.negative_count,
            confidence=body.confidence,
            maturity=body.maturity[:32],
            is_active=body.is_active,
            notes=body.notes,
        )
        db.add(row)
    else:
        row.section_role = body.section_role.strip()[:64]
        row.positive_count = body.positive_count
        row.negative_count = body.negative_count
        row.confidence = body.confidence
        row.maturity = body.maturity[:32]
        row.is_active = body.is_active
        row.notes = body.notes
    await db.commit()
    await db.refresh(row)
    return PlatformExtractionSanitizedPatternOut.model_validate(row)
