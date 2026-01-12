from __future__ import annotations

import logging
import re
import time
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import SQLAlchemyError

from app.models.platform import PlatformTenant, ReservedSlug

logger = logging.getLogger(__name__)

SLUG_REGEX = re.compile(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$")
FALLBACK_RESERVED = {"admin"}


def normalize_slug(text: str) -> str:
    """
    Normalize arbitrary text into a slug:
    - lowercase
    - non [a-z0-9-] chars replaced with "-"
    - collapse repeated "-"
    - trim leading/trailing "-"
    - truncate to 63 chars
    """
    slug = re.sub(r"[^a-z0-9-]", "-", text.strip().lower())
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug[:63]


async def is_slug_reserved(db: AsyncSession, slug: str) -> bool:
    normalized = normalize_slug(slug)
    if normalized in FALLBACK_RESERVED:
        return True
    try:
        exists = await db.scalar(select(ReservedSlug.id).where(ReservedSlug.slug == normalized))
        return bool(exists)
    except SQLAlchemyError as exc:
        logger.debug("slug_reserved_check_failed error=%s", exc)
        try:
            await db.rollback()
        except Exception:
            pass
        return False


async def is_slug_available(db: AsyncSession, slug: str) -> bool:
    normalized = normalize_slug(slug)
    try:
        if await is_slug_reserved(db, normalized):
            return False
        in_use = await db.scalar(select(PlatformTenant.id).where(PlatformTenant.slug == normalized))
        return not bool(in_use)
    except SQLAlchemyError as exc:
        logger.debug("slug_availability_check_failed error=%s", exc)
        try:
            await db.rollback()
        except Exception:
            pass
        # Fallback to "available" when lookup fails to avoid blocking signup on reserved table issues
        return True


async def generate_slug_suggestions(
    db: AsyncSession, base_slug: str, country: Optional[str] = None, limit: int = 3
) -> List[str]:
    """
    Generate up to `limit` unique slug suggestions based on base_slug.
    Uses a timestamp suffix for low collision risk and checks availability.
    """
    suggestions: list[str] = []
    normalized_base = normalize_slug(base_slug) or "tenant"
    suffix_seed = int(time.time())
    attempt = 1
    while len(suggestions) < limit and attempt < limit * 4:
        suffix = f"{country.lower()}-{suffix_seed + attempt}" if country else f"{suffix_seed + attempt}"
        candidate = normalize_slug(f"{normalized_base}-{suffix}")
        if candidate:
            try:
                if await is_slug_available(db, candidate):
                    suggestions.append(candidate)
            except SQLAlchemyError as exc:
                logger.debug("slug_suggestion_check_failed candidate=%s error=%s", candidate, exc)
                try:
                    await db.rollback()
                except Exception:
                    pass
        attempt += 1
    return suggestions or ([normalized_base] if normalized_base else [])
