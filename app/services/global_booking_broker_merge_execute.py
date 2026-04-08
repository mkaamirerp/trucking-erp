"""Global booking broker merge execute (platform): preview-anchored, single transaction."""

from __future__ import annotations

import json
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.global_booking_broker import (
    GlobalBookingBroker,
    GlobalBookingBrokerAlias,
    GlobalBookingBrokerAuditEvent,
    GlobalBookingBrokerDomain,
    GlobalBookingBrokerKnownSender,
    GlobalBookingBrokerMergePreview,
)
from app.services.global_booking_broker_merge_preview import (
    PREVIEW_SCHEMA_VERSION,
    build_merge_preview,
    classify_regulatory_pair,
)
from app.utils import global_booking_broker_merge as merge_guard
from app.utils.broker_identity import (
    normalize_cvor_number_digits,
    normalize_dot_number_digits,
    normalize_mc_number_digits,
)

# Short stable audit actions (≤64 chars)
AUDIT_MERGE_SURVIVOR = "merge_exec_survivor"
AUDIT_MERGE_SOURCE = "merge_exec_source"

MergeExecuteStatus = Literal["completed", "already_completed"]


def _norm_cvor_safe(raw: str | None) -> str | None:
    if raw is None:
        return None
    if not str(raw).strip():
        return None
    try:
        return normalize_cvor_number_digits(raw)
    except ValueError:
        return None


def _regulatory_blocking(source: GlobalBookingBroker, survivor: GlobalBookingBroker) -> bool:
    smc = normalize_mc_number_digits(source.mc_number)
    zmc = normalize_mc_number_digits(survivor.mc_number)
    if classify_regulatory_pair(smc, zmc) == "blocking_conflict":
        return True
    sdot = normalize_dot_number_digits(source.dot_number)
    zdot = normalize_dot_number_digits(survivor.dot_number)
    if classify_regulatory_pair(sdot, zdot) == "blocking_conflict":
        return True
    sc = _norm_cvor_safe(source.cvor_number)
    zc = _norm_cvor_safe(survivor.cvor_number)
    if classify_regulatory_pair(sc, zc) == "blocking_conflict":
        return True
    return False


def _parse_preview_payload(raw: str) -> dict[str, Any]:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="merge_preview_payload_invalid",
        ) from exc
    if not isinstance(data, dict):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="merge_preview_payload_invalid",
        )
    return data


def _validate_operator_resolutions(preview: dict[str, Any], body: Any) -> None:
    summary = preview.get("summary") or {}
    required: list[str] = list(summary.get("operator_choice_required_fields") or [])
    mapping = {
        "name": body.name_resolution,
        "legal_name": body.legal_name_resolution,
        "display_name": body.display_name_resolution,
    }
    for f in required:
        if mapping.get(f) is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"merge_resolution_required:{f}",
            )


def _apply_survivor_identity(
    source: GlobalBookingBroker,
    survivor: GlobalBookingBroker,
    comparisons: list[dict[str, Any]],
    body: Any,
) -> None:
    by_field = {str(c.get("field")): c for c in comparisons}

    for field in ("mc_number", "dot_number", "cvor_number"):
        c = by_field.get(field)
        if not c:
            continue
        cls = c.get("classification")
        if cls == "aligned":
            continue
        if cls == "safe_default":
            if field == "mc_number":
                if normalize_mc_number_digits(survivor.mc_number) is None and normalize_mc_number_digits(
                    source.mc_number
                ):
                    survivor.mc_number = normalize_mc_number_digits(source.mc_number)
            elif field == "dot_number":
                if normalize_dot_number_digits(survivor.dot_number) is None and normalize_dot_number_digits(
                    source.dot_number
                ):
                    survivor.dot_number = normalize_dot_number_digits(source.dot_number)
            elif field == "cvor_number":
                if _norm_cvor_safe(survivor.cvor_number) is None and _norm_cvor_safe(source.cvor_number):
                    survivor.cvor_number = source.cvor_number
            continue
        if cls == "blocking_conflict":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="merge_regulatory_blocking_conflict",
            )

    for field in ("name", "legal_name", "display_name"):
        c = by_field.get(field)
        if not c:
            continue
        cls = c.get("classification")
        if cls == "aligned":
            continue
        if cls == "safe_default":
            s_val = getattr(source, field)
            z_val = getattr(survivor, field)
            if field == "name":
                zs = (z_val or "").strip()
                if not zs and (s_val or "").strip():
                    survivor.name = (s_val or "").strip()
            else:
                zz = (z_val or "").strip() if z_val else ""
                ss = (s_val or "").strip() if s_val else ""
                if not zz and ss:
                    setattr(survivor, field, ss)
                elif not zz and not ss:
                    setattr(survivor, field, None)
            continue
        if cls == "operator_choice_required":
            if field == "name":
                side = body.name_resolution
            elif field == "legal_name":
                side = body.legal_name_resolution
            else:
                side = body.display_name_resolution
            if side == "source":
                picked = getattr(source, field)
            else:
                picked = getattr(survivor, field)
            if field == "name":
                survivor.name = (picked or "").strip() or survivor.name
            else:
                p = (picked or "").strip() if picked else ""
                setattr(survivor, field, p or None)


async def _survivor_has_active_domain(db: AsyncSession, survivor_id: int, domain: str) -> bool:
    row = await db.scalar(
        select(GlobalBookingBrokerDomain.id).where(
            GlobalBookingBrokerDomain.global_broker_id == survivor_id,
            GlobalBookingBrokerDomain.domain == domain,
            GlobalBookingBrokerDomain.is_active.is_(True),
        )
    )
    return row is not None


async def _survivor_has_active_sender(db: AsyncSession, survivor_id: int, email: str) -> bool:
    row = await db.scalar(
        select(GlobalBookingBrokerKnownSender.id).where(
            GlobalBookingBrokerKnownSender.global_broker_id == survivor_id,
            GlobalBookingBrokerKnownSender.email_normalized == email,
            GlobalBookingBrokerKnownSender.is_active.is_(True),
        )
    )
    return row is not None


async def _survivor_has_active_alias(db: AsyncSession, survivor_id: int, alias: str) -> bool:
    row = await db.scalar(
        select(GlobalBookingBrokerAlias.id).where(
            GlobalBookingBrokerAlias.global_broker_id == survivor_id,
            GlobalBookingBrokerAlias.alias == alias,
            GlobalBookingBrokerAlias.is_active.is_(True),
        )
    )
    return row is not None


async def _rehome_active_children(
    db: AsyncSession,
    *,
    source_id: int,
    survivor_id: int,
) -> dict[str, int]:
    """Move active child rows from source to survivor; deactivate source-side duplicates when survivor already has key."""
    stats = {"domains_rehomed": 0, "domains_deactivated": 0, "senders_rehomed": 0, "senders_deactivated": 0, "aliases_rehomed": 0, "aliases_deactivated": 0}

    dom_res = await db.execute(
        select(GlobalBookingBrokerDomain).where(
            GlobalBookingBrokerDomain.global_broker_id == source_id,
            GlobalBookingBrokerDomain.is_active.is_(True),
        )
    )
    for row in dom_res.scalars().all():
        if await _survivor_has_active_domain(db, survivor_id, row.domain):
            row.is_active = False
            stats["domains_deactivated"] += 1
        else:
            row.global_broker_id = survivor_id
            stats["domains_rehomed"] += 1

    ks_res = await db.execute(
        select(GlobalBookingBrokerKnownSender).where(
            GlobalBookingBrokerKnownSender.global_broker_id == source_id,
            GlobalBookingBrokerKnownSender.is_active.is_(True),
        )
    )
    for row in ks_res.scalars().all():
        if await _survivor_has_active_sender(db, survivor_id, row.email_normalized):
            row.is_active = False
            stats["senders_deactivated"] += 1
        else:
            row.global_broker_id = survivor_id
            stats["senders_rehomed"] += 1

    al_res = await db.execute(
        select(GlobalBookingBrokerAlias).where(
            GlobalBookingBrokerAlias.global_broker_id == source_id,
            GlobalBookingBrokerAlias.is_active.is_(True),
        )
    )
    for row in al_res.scalars().all():
        if await _survivor_has_active_alias(db, survivor_id, row.alias):
            row.is_active = False
            stats["aliases_deactivated"] += 1
        else:
            row.global_broker_id = survivor_id
            stats["aliases_rehomed"] += 1

    return stats


def _audit(db: AsyncSession, *, global_broker_id: int, action: str, detail: dict[str, Any]) -> None:
    db.add(
        GlobalBookingBrokerAuditEvent(
            global_broker_id=global_broker_id,
            action=action,
            detail=json.dumps(detail, separators=(",", ":"), ensure_ascii=False),
        )
    )


@dataclass(frozen=True)
class MergeExecuteResult:
    status: MergeExecuteStatus
    preview_id: int
    preview_hash: str
    source_global_broker_id: int
    survivor_global_broker_id: int
    duplicate_candidate_id: int | None
    child_stats: dict[str, int] | None = None


async def execute_global_booking_broker_merge(
    db: AsyncSession,
    *,
    preview_id: int,
    preview_hash: str,
    name_resolution: Literal["source", "survivor"] | None,
    legal_name_resolution: Literal["source", "survivor"] | None,
    display_name_resolution: Literal["source", "survivor"] | None,
) -> MergeExecuteResult:
    """Single atomic transaction: verify preview anchor, re-home children, retire loser, audit."""
    async with db.begin():
        row = await db.get(GlobalBookingBrokerMergePreview, preview_id)
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="merge_preview_not_found")

        ph_req = (preview_hash or "").strip()
        ph_row = (row.preview_hash or "").strip()
        if len(ph_req) != len(ph_row) or not secrets.compare_digest(ph_req, ph_row):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="merge_preview_hash_mismatch")

        preview = _parse_preview_payload(row.preview_payload)
        if int(preview.get("schema_version", -1)) != PREVIEW_SCHEMA_VERSION:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="merge_preview_schema_mismatch")

        src = await db.get(GlobalBookingBroker, row.source_global_broker_id)
        surv = await db.get(GlobalBookingBroker, row.survivor_global_broker_id)
        if src is None or surv is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="global_booking_broker_not_found")

        if preview.get("source_global_broker_id") != src.id or preview.get("survivor_global_broker_id") != surv.id:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="merge_preview_payload_mismatch")

        if row.source_global_broker_id != src.id or row.survivor_global_broker_id != surv.id:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="merge_preview_row_mismatch")

        dup_payload = preview.get("duplicate_candidate_id")
        dup_row = row.duplicate_candidate_id
        if dup_payload != dup_row:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="merge_preview_dup_mismatch")

        if merge_guard.global_booking_broker_merge_survivor_violation(surv) is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="merge_survivor_not_eligible")

        if src.merged_into_global_broker_id is not None:
            if src.merged_into_global_broker_id != surv.id:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="merge_source_already_merged_elsewhere")
            return MergeExecuteResult(
                status="already_completed",
                preview_id=preview_id,
                preview_hash=row.preview_hash,
                source_global_broker_id=src.id,
                survivor_global_broker_id=surv.id,
                duplicate_candidate_id=dup_row,
                child_stats=None,
            )

        fresh = build_merge_preview(
            source=src,
            survivor=surv,
            duplicate_candidate_id=dup_row,
        )
        if not fresh.persist_eligible:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="merge_preview_not_eligible")
        if fresh.preview_hash != row.preview_hash:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="merge_preview_stale")

        if _regulatory_blocking(src, surv):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="merge_regulatory_blocking_conflict")

        class _ResBody:
            pass

        rb = _ResBody()
        rb.name_resolution = name_resolution
        rb.legal_name_resolution = legal_name_resolution
        rb.display_name_resolution = display_name_resolution
        _validate_operator_resolutions(preview, rb)

        viol = merge_guard.global_booking_broker_merge_source_violation(src)
        if viol is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=viol)

        comparisons = list(preview.get("field_comparisons") or [])
        _apply_survivor_identity(src, surv, comparisons, rb)

        child_stats = await _rehome_active_children(db, source_id=src.id, survivor_id=surv.id)

        now = datetime.now(UTC)
        src.merged_into_global_broker_id = surv.id
        src.merged_at = now
        src.canonical_status = "rejected"

        dup = dup_row
        base_audit: dict[str, Any] = {
            "preview_id": preview_id,
            "preview_hash": row.preview_hash,
            "duplicate_candidate_id": dup,
        }
        _audit(
            db,
            global_broker_id=surv.id,
            action=AUDIT_MERGE_SURVIVOR,
            detail={
                **base_audit,
                "source_global_broker_id": src.id,
                "child_stats": child_stats,
            },
        )
        _audit(
            db,
            global_broker_id=src.id,
            action=AUDIT_MERGE_SOURCE,
            detail={
                **base_audit,
                "survivor_global_broker_id": surv.id,
                "merged_at": now.isoformat(),
            },
        )

        return MergeExecuteResult(
            status="completed",
            preview_id=preview_id,
            preview_hash=row.preview_hash,
            source_global_broker_id=src.id,
            survivor_global_broker_id=surv.id,
            duplicate_candidate_id=dup_row,
            child_stats=child_stats,
        )

