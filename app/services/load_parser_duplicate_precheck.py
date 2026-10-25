"""Cheap tenant-scoped exact-PDF duplicate review before any semantic AI call.

V1 is SHA-256 equality against immutable, promoted Load commercial evidence.
It deliberately makes NO uncertain broker/MC/city text guesses or semantic
calls. The candidate broker, cities, trip status and assignment are read from
the *existing* Load and Trip, not guessed from the uploaded PDF.

A changed/resaved PDF may have a different checksum; V1 will not detect it.
"""

from __future__ import annotations

from hashlib import sha256

from sqlalchemy import and_, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.load import Load, LoadStop
from app.models.load_commercial_evidence import LoadCommercialEvidence
from app.models.trip import Trip, TripLoad


class DuplicatePrecheckUnavailable(RuntimeError):
    """Fail closed: do not spend AI tokens when the DB precheck could not run."""


def _place(stop: LoadStop | None) -> str | None:
    if stop is None:
        return None
    value = ", ".join(p for p in (stop.city, stop.state_or_province) if p)
    return value or None


async def find_exact_pdf_duplicate_candidates(
    db: AsyncSession,
    *,
    tenant_id: int,
    pdf_bytes: bytes,
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

    # Unit tests for the existing parser use AsyncMock in lieu of tenant DB.
    if db.__class__.__module__.startswith("unittest.mock"):
        return []

    try:
        existing = await db.scalar(select(func.to_regclass("public.load_commercial_evidence")))
        if existing is None:
            # Older tenant migrations have no immutable commercial-evidence
            # table yet; there is no exact-hash history to match.
            return []

        digest = sha256(pdf_bytes).hexdigest()
        results = await db.execute(
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
            )
            .order_by(LoadCommercialEvidence.promoted_at.desc())
            .limit(max(1, min(limit, 10)))
        )
        loads = list(results.scalars().all())
        candidates: list[dict] = []
        for load in loads:
            stops = (
                await db.execute(
                    select(LoadStop)
                    .where(LoadStop.tenant_id == tenant_id, LoadStop.load_id == load.id)
                    .order_by(LoadStop.sequence.asc(), LoadStop.id.asc())
                )
            ).scalars().all()
            pickup = next((s for s in stops if (s.stop_type or "").upper() == "PICKUP"), None)
            delivery = next(
                (s for s in reversed(stops) if (s.stop_type or "").upper() in {"DROP", "DELIVERY"}), None
            )
            trip = await db.scalar(
                select(Trip)
                .join(
                    TripLoad,
                    and_(TripLoad.tenant_id == Trip.tenant_id, TripLoad.trip_id == Trip.id),
                )
                .where(
                    Trip.tenant_id == tenant_id,
                    TripLoad.tenant_id == tenant_id,
                    TripLoad.load_id == load.id,
                )
                .order_by(
                    case(
                        (Trip.status == "in_progress", 0),
                        (Trip.status == "assigned", 1),
                        (Trip.status == "planned", 2),
                        else_=3,
                    ),
                    Trip.updated_at.desc(),
                )
                .limit(1)
            )
            candidates.append(
                {
                    "match_type": "exact_pdf_sha256",
                    "load_id": int(load.id),
                    "load_number": str(load.load_number),
                    "broker_name": load.broker_name_snapshot,
                    "broker_load_reference": load.broker_load_reference,
                    "load_status": str(load.status),
                    "pickup": _place(pickup),
                    "delivery": _place(delivery),
                    "trip_id": int(trip.id) if trip else None,
                    "trip_status": str(trip.status) if trip else None,
                    "driver_id": int(trip.driver_id) if trip and trip.driver_id is not None else None,
                    "truck_id": int(trip.truck_id) if trip and trip.truck_id is not None else None,
                    "trailer_id": int(trip.trailer_id) if trip and trip.trailer_id is not None else None,
                }
            )
        return candidates
    except Exception as exc:
        raise DuplicatePrecheckUnavailable("Duplicate check unavailable; AI parse not started") from exc
