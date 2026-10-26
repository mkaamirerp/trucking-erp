"""Cheap tenant-scoped exact-PDF duplicate review before any semantic AI call.

V1 is SHA-256 equality against immutable, promoted Load commercial evidence.
It deliberately makes NO uncertain broker/MC/city text guesses or semantic
calls. The candidate broker, cities, trip status and assignment are read from
the *existing* Load and Trip, not guessed from the uploaded PDF.

A changed/resaved PDF may have a different checksum; V1 will not detect it.
"""

from __future__ import annotations

from hashlib import sha256

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.load import Load
from app.models.load_commercial_evidence import LoadCommercialEvidence
from app.services.load_rate_confirmation_duplicate import snapshot_existing_load


class DuplicatePrecheckUnavailable(RuntimeError):
    """Fail closed: do not spend AI tokens when the DB precheck could not run."""


async def find_exact_pdf_duplicate_candidates(
    db: AsyncSession,
    *,
    tenant_id: int,
    pdf_bytes: bytes,
    exclude_load_id: int | None = None,
    limit: int = 5,
) -> list[dict]:
    """Return existing Load snapshots for an exact hash match in this tenant.

    Only an exact SHA-256 match blocks the semantic parse for operator review.
    The lookup is read-only; the request never changes an existing Load.
    """
    if tenant_id <= 0:
        raise ValueError("tenant_id must be positive")
    if not pdf_bytes:
        raise ValueError("pdf_bytes required")

    try:
        existing = await db.scalar(select(func.to_regclass("public.load_commercial_evidence")))
        if existing is None:
            # Older tenant migrations have no immutable commercial-evidence
            # table yet; there is no exact-hash history to match.
            return []

        digest = sha256(pdf_bytes).hexdigest()
        stmt = (
            select(Load)
            .join(
                LoadCommercialEvidence,
                and_(
                    LoadCommercialEvidence.tenant_id == Load.tenant_id,
                    LoadCommercialEvidence.load_id == Load.id,
                ),
            )
            .where(
                Load.tenant_id == tenant_id,
                LoadCommercialEvidence.tenant_id == tenant_id,
                LoadCommercialEvidence.file_sha256 == digest,
                LoadCommercialEvidence.evidence_kind == "rate_confirmation_pdf",
                Load.status != "cancelled",
            )
            .order_by(LoadCommercialEvidence.promoted_at.desc())
            .limit(max(1, min(limit, 10)))
        )
        if exclude_load_id is not None and int(exclude_load_id) > 0:
            stmt = stmt.where(Load.id != int(exclude_load_id))
        results = await db.execute(stmt)
        loads = list(results.scalars().all())
        candidates: list[dict] = []
        for load in loads:
            snap = await snapshot_existing_load(db, tenant_id, load)
            candidates.append({"match_type": "exact_pdf_sha256", **snap})
        return candidates
    except Exception as exc:
        raise DuplicatePrecheckUnavailable("Duplicate check unavailable; AI parse not started") from exc
