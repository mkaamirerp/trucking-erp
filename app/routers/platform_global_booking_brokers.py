"""Platform admin: global booking broker reference (tenant read-only; no tenant writes)."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.global_booking_broker_duplicate_review_reason_codes import (
    GlobalBookingBrokerDuplicateCandidateReviewIn,
    duplicate_review_operator_hint,
)
from app.constants.global_booking_broker_promotion_reason_codes import (
    normalize_and_validate_promotion_reason,
    promotion_operator_hint,
)
from app.core.database import get_db
from app.models.global_booking_broker import (
    GlobalBookingBroker,
    GlobalBookingBrokerAlias,
    GlobalBookingBrokerAuditEvent,
    GlobalBookingBrokerDomain,
    GlobalBookingBrokerDuplicateCandidate,
    GlobalBookingBrokerKnownSender,
)
from app.routers.platform_tenants import require_platform_admin_key
from app.schemas.platform_global_booking_broker import (
    GlobalBookingBrokerAuditEventOut,
    GlobalBookingBrokerCreateIn,
    GlobalBookingBrokerDuplicateBrokersMini,
    GlobalBookingBrokerDuplicateCandidateOut,
    GlobalBookingBrokerDuplicateRefreshOut,
    GlobalBookingBrokerOut,
    GlobalBookingBrokerPatchIn,
    GlobalBookingBrokerProfilePatchIn,
)
from app.schemas.platform_global_booking_broker_merge_preview import (
    GlobalBookingBrokerMergeExecuteIn,
    GlobalBookingBrokerMergeExecuteOut,
    GlobalBookingBrokerMergePreviewIn,
    GlobalBookingBrokerMergePreviewOut,
)
from app.services.global_booking_broker_merge_execute import execute_global_booking_broker_merge
from app.services.global_booking_broker_merge_preview import build_and_persist_merge_preview
from app.services.global_broker_duplicate_candidates import refresh_global_broker_duplicate_candidates
from app.utils.broker_identity import (
    normalize_alias,
    normalize_domain,
    normalize_dot_number_digits,
    normalize_known_sender_email,
    normalize_mc_number_digits,
)

router = APIRouter(prefix="/api/v1/platform", tags=["platform-global-booking-brokers"])


def _audit_global_booking_broker(
    db: AsyncSession,
    *,
    global_broker_id: int,
    action: str,
    detail: dict | None,
) -> None:
    db.add(
        GlobalBookingBrokerAuditEvent(
            global_broker_id=global_broker_id,
            action=action,
            detail=json.dumps(detail) if detail is not None else None,
        )
    )


@router.get("/global-booking-brokers", response_model=list[GlobalBookingBrokerOut])
async def list_global_booking_brokers(
    canonical_status: str | None = Query(None, description="Filter e.g. approved, pending"),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_platform_admin_key),
):
    stmt = select(GlobalBookingBroker).order_by(GlobalBookingBroker.id.asc())
    if canonical_status:
        st = canonical_status.strip().lower()
        stmt = stmt.where(GlobalBookingBroker.canonical_status == st)
    result = await db.execute(stmt)
    return list(result.scalars().all())


def _duplicate_match_signals_list(raw: str | None) -> list[str]:
    if not raw or not str(raw).strip():
        return []
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            return sorted({str(x) for x in data})
    except json.JSONDecodeError:
        return []
    return []


@router.get(
    "/global-booking-broker-duplicate-candidates",
    response_model=list[GlobalBookingBrokerDuplicateCandidateOut],
)
async def list_global_booking_broker_duplicate_candidates(
    review_status: str | None = Query(None, description="Filter: open, dismissed, acknowledged; omit for all"),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_platform_admin_key),
):
    stmt = select(GlobalBookingBrokerDuplicateCandidate).order_by(GlobalBookingBrokerDuplicateCandidate.id.desc())
    if review_status and review_status.strip().lower() not in ("all", ""):
        stmt = stmt.where(
            GlobalBookingBrokerDuplicateCandidate.review_status == review_status.strip().lower()
        )
    res = await db.execute(stmt)
    rows = list(res.scalars().all())
    if not rows:
        return []

    id_set: set[int] = set()
    for r in rows:
        id_set.add(r.broker_id_low)
        id_set.add(r.broker_id_high)
    brokers_res = await db.execute(select(GlobalBookingBroker).where(GlobalBookingBroker.id.in_(id_set)))
    by_id: dict[int, GlobalBookingBroker] = {b.id: b for b in brokers_res.scalars().all()}

    rs_filter = (review_status or "").strip().lower()
    suppress_non_actionable_open = rs_filter == "open"

    out: list[GlobalBookingBrokerDuplicateCandidateOut] = []
    for r in rows:
        low = by_id.get(r.broker_id_low)
        high = by_id.get(r.broker_id_high)
        if low is None or high is None:
            continue
        if suppress_non_actionable_open and r.review_status == "open":
            if low.merged_into_global_broker_id is not None or high.merged_into_global_broker_id is not None:
                continue
        out.append(
            GlobalBookingBrokerDuplicateCandidateOut(
                id=r.id,
                broker_low=GlobalBookingBrokerDuplicateBrokersMini.model_validate(low),
                broker_high=GlobalBookingBrokerDuplicateBrokersMini.model_validate(high),
                match_signals=_duplicate_match_signals_list(r.match_signals),
                review_status=r.review_status,
                duplicate_review_reason_code=r.duplicate_review_reason_code,
                note=r.note,
                created_at=r.created_at,
                updated_at=r.updated_at,
            )
        )
    return out


@router.post(
    "/global-booking-brokers/merge/preview",
    response_model=GlobalBookingBrokerMergePreviewOut,
)
async def preview_global_booking_broker_merge(
    body: GlobalBookingBrokerMergePreviewIn,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_platform_admin_key),
):
    src = await db.get(GlobalBookingBroker, body.source_global_broker_id)
    surv = await db.get(GlobalBookingBroker, body.survivor_global_broker_id)
    if src is None or surv is None:
        raise HTTPException(status_code=404, detail="global_booking_broker_not_found")

    dup_id = body.duplicate_candidate_id
    if dup_id is not None:
        cand = await db.get(GlobalBookingBrokerDuplicateCandidate, dup_id)
        if cand is None:
            raise HTTPException(status_code=400, detail="duplicate_candidate_not_found")
        pair = {body.source_global_broker_id, body.survivor_global_broker_id}
        if pair != {cand.broker_id_low, cand.broker_id_high}:
            raise HTTPException(status_code=400, detail="duplicate_candidate_pair_mismatch")

    preview_id, preview_hash, preview_body = await build_and_persist_merge_preview(
        db,
        source=src,
        survivor=surv,
        duplicate_candidate_id=dup_id,
    )
    await db.commit()
    return GlobalBookingBrokerMergePreviewOut(
        preview_id=preview_id,
        preview_hash=preview_hash,
        preview=preview_body,
    )


@router.post(
    "/global-booking-brokers/merge/execute",
    response_model=GlobalBookingBrokerMergeExecuteOut,
)
async def execute_global_booking_broker_merge_endpoint(
    body: GlobalBookingBrokerMergeExecuteIn,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_platform_admin_key),
):
    out = await execute_global_booking_broker_merge(
        db,
        preview_id=body.preview_id,
        preview_hash=body.preview_hash,
        name_resolution=body.name_resolution,
        legal_name_resolution=body.legal_name_resolution,
        display_name_resolution=body.display_name_resolution,
    )
    return GlobalBookingBrokerMergeExecuteOut(
        status=out.status,
        preview_id=out.preview_id,
        preview_hash=out.preview_hash,
        source_global_broker_id=out.source_global_broker_id,
        survivor_global_broker_id=out.survivor_global_broker_id,
        duplicate_candidate_id=out.duplicate_candidate_id,
        child_stats=out.child_stats,
    )


@router.post(
    "/global-booking-broker-duplicate-candidates/refresh",
    response_model=GlobalBookingBrokerDuplicateRefreshOut,
)
async def refresh_global_booking_broker_duplicate_candidates_endpoint(
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_platform_admin_key),
):
    result = await refresh_global_broker_duplicate_candidates(db)
    await db.commit()
    return GlobalBookingBrokerDuplicateRefreshOut(
        upserted_open=result.upserted_open,
        updated_open_signals=result.updated_open_signals,
        removed_stale_open=result.removed_stale_open,
        touched_dismissed_or_ack=result.touched_dismissed_or_ack,
    )


@router.patch(
    "/global-booking-broker-duplicate-candidates/{candidate_id}",
    response_model=GlobalBookingBrokerDuplicateCandidateOut,
)
async def patch_global_booking_broker_duplicate_candidate(
    candidate_id: int,
    body: GlobalBookingBrokerDuplicateCandidateReviewIn,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_platform_admin_key),
):
    cand = await db.get(GlobalBookingBrokerDuplicateCandidate, candidate_id)
    if cand is None:
        raise HTTPException(status_code=404, detail="duplicate candidate not found")
    if cand.review_status != "open":
        raise HTTPException(status_code=400, detail="duplicate_candidate_not_open")

    new_status = body.review_status
    code = body.duplicate_review_reason_code
    hint = duplicate_review_operator_hint(code) or code
    note = (body.note or "").strip() or None

    cand.review_status = new_status
    cand.duplicate_review_reason_code = code
    cand.note = note
    await db.flush()

    audit_base: dict = {
        "candidate_id": cand.id,
        "review_status": new_status,
        "duplicate_review_reason_code": code,
        "duplicate_review_reason_hint": hint,
    }
    if note:
        audit_base["note"] = note
    _audit_global_booking_broker(
        db,
        global_broker_id=cand.broker_id_low,
        action="duplicate_candidate_review",
        detail={**audit_base, "peer_broker_id": cand.broker_id_high},
    )
    _audit_global_booking_broker(
        db,
        global_broker_id=cand.broker_id_high,
        action="duplicate_candidate_review",
        detail={**audit_base, "peer_broker_id": cand.broker_id_low},
    )
    await db.commit()

    low = await db.get(GlobalBookingBroker, cand.broker_id_low)
    high = await db.get(GlobalBookingBroker, cand.broker_id_high)
    if low is None or high is None:
        raise HTTPException(status_code=500, detail="broker missing after duplicate review")
    return GlobalBookingBrokerDuplicateCandidateOut(
        id=cand.id,
        broker_low=GlobalBookingBrokerDuplicateBrokersMini.model_validate(low),
        broker_high=GlobalBookingBrokerDuplicateBrokersMini.model_validate(high),
        match_signals=_duplicate_match_signals_list(cand.match_signals),
        review_status=cand.review_status,
        duplicate_review_reason_code=cand.duplicate_review_reason_code,
        note=cand.note,
        created_at=cand.created_at,
        updated_at=cand.updated_at,
    )


@router.post(
    "/global-booking-brokers",
    response_model=GlobalBookingBrokerOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_global_booking_broker(
    body: GlobalBookingBrokerCreateIn,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_platform_admin_key),
):
    st = (body.canonical_status or "pending").strip().lower()
    if st not in ("pending", "approved", "rejected"):
        raise HTTPException(status_code=400, detail="canonical_status must be pending, approved, or rejected")

    row = GlobalBookingBroker(
        name=body.name.strip(),
        legal_name=(body.legal_name or "").strip() or None,
        display_name=(body.display_name or "").strip() or None,
        mc_number=normalize_mc_number_digits((body.mc_number or "").strip()),
        dot_number=normalize_dot_number_digits((body.dot_number or "").strip()),
        cvor_number=body.cvor_number,
        canonical_status=st,
        notes=(body.notes or "").strip() or None,
    )
    db.add(row)
    await db.flush()

    seen_dom: set[str] = set()
    for raw in body.domains:
        s = (raw or "").strip()
        if not s:
            continue
        try:
            dom = normalize_domain(s)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid domain: {raw!r}") from None
        if dom in seen_dom:
            continue
        seen_dom.add(dom)
        db.add(GlobalBookingBrokerDomain(global_broker_id=row.id, domain=dom))

    seen_em: set[str] = set()
    for raw in body.known_sender_emails:
        s = (raw or "").strip()
        if not s:
            continue
        try:
            em = normalize_known_sender_email(s)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid known-sender email: {raw!r}") from None
        if em in seen_em:
            continue
        seen_em.add(em)
        db.add(GlobalBookingBrokerKnownSender(global_broker_id=row.id, email_normalized=em))

    seen_al: set[str] = set()
    for raw in body.aliases:
        s = (raw or "").strip()
        if not s:
            continue
        try:
            al = normalize_alias(s)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid alias: {raw!r}") from None
        if al in seen_al:
            continue
        seen_al.add(al)
        db.add(GlobalBookingBrokerAlias(global_broker_id=row.id, alias=al))

    created_detail: dict = {"canonical_status": st, "name": row.name}
    if row.cvor_number:
        created_detail["cvor_number"] = row.cvor_number
    _audit_global_booking_broker(
        db,
        global_broker_id=row.id,
        action="created",
        detail=created_detail,
    )

    await db.commit()
    await db.refresh(row)
    return row


def _audit_detail_from_row(ev: GlobalBookingBrokerAuditEvent) -> dict | None:
    if ev.detail is None or not str(ev.detail).strip():
        return None
    try:
        parsed = json.loads(ev.detail)
        return parsed if isinstance(parsed, dict) else {"value": parsed}
    except json.JSONDecodeError:
        return {"_unparsed": ev.detail}


@router.get(
    "/global-booking-brokers/{broker_id}/audit-events",
    response_model=list[GlobalBookingBrokerAuditEventOut],
)
async def list_global_booking_broker_audit_events(
    broker_id: int,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_platform_admin_key),
    limit: int = Query(50, ge=1, le=200),
):
    row = await db.get(GlobalBookingBroker, broker_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Global booking broker not found")

    stmt = (
        select(GlobalBookingBrokerAuditEvent)
        .where(GlobalBookingBrokerAuditEvent.global_broker_id == broker_id)
        .order_by(GlobalBookingBrokerAuditEvent.id.desc())
        .limit(limit)
    )
    result = await db.execute(stmt)
    events = list(result.scalars().all())
    return [
        GlobalBookingBrokerAuditEventOut(
            id=e.id,
            global_broker_id=e.global_broker_id,
            action=e.action,
            detail=_audit_detail_from_row(e),
            created_at=e.created_at,
        )
        for e in events
    ]


@router.patch("/global-booking-brokers/{broker_id}/profile", response_model=GlobalBookingBrokerOut)
async def patch_global_booking_broker_profile(
    broker_id: int,
    body: GlobalBookingBrokerProfilePatchIn,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_platform_admin_key),
):
    updates = body.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(status_code=400, detail="no profile fields to update")

    row = await db.get(GlobalBookingBroker, broker_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Global booking broker not found")

    if "cvor_number" in updates:
        prev = row.cvor_number
        new_v = updates["cvor_number"]
        if prev == new_v:
            await db.refresh(row)
            return row
        row.cvor_number = new_v
        await db.flush()
        _audit_global_booking_broker(
            db,
            global_broker_id=row.id,
            action="profile_updated",
            detail={
                "cvor_number": {"from": prev, "to": new_v},
            },
        )

    await db.commit()
    await db.refresh(row)
    return row


@router.patch("/global-booking-brokers/{broker_id}", response_model=GlobalBookingBrokerOut)
async def patch_global_booking_broker(
    broker_id: int,
    body: GlobalBookingBrokerPatchIn,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_platform_admin_key),
):
    st = body.canonical_status.strip().lower()
    if st not in ("pending", "approved", "rejected"):
        raise HTTPException(status_code=400, detail="canonical_status must be pending, approved, or rejected")

    row = await db.get(GlobalBookingBroker, broker_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Global booking broker not found")

    prev = (row.canonical_status or "").strip().lower()
    if prev == st:
        await db.refresh(row)
        return row

    try:
        code, _ = normalize_and_validate_promotion_reason(
            prev_status=prev,
            next_status=st,
            promotion_reason_code=body.promotion_reason_code,
        )
    except ValueError as exc:
        msg = str(exc.args[0]) if exc.args else "invalid promotion reason"
        if msg in (
            "global_broker_promotion_reason_required",
            "global_broker_promotion_reason_not_allowed_for_transition",
        ):
            raise HTTPException(status_code=422, detail=msg) from None
        raise HTTPException(status_code=400, detail=msg) from None

    hint = promotion_operator_hint(code)
    row.canonical_status = st
    await db.flush()
    audit_detail: dict = {
        "from": prev,
        "to": st,
        "promotion_reason_code": code,
        "promotion_reason_hint": hint or code,
    }
    note = (body.note or "").strip() or None
    if note:
        audit_detail["note"] = note
    _audit_global_booking_broker(
        db,
        global_broker_id=row.id,
        action="canonical_status_changed",
        detail=audit_detail,
    )
    await db.commit()
    await db.refresh(row)
    return row
