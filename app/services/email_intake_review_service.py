"""Email thread intake review spine: sync from routing_reason, operator workflow, append-only events.

``detail_json`` holds only structured fields we define per review category — not a miscellaneous metadata dump.
``primary_code`` is currently derived from ``routing_reason`` (migration bridge); new intake paths should converge
on setting ``primary_code`` at the source and treating ``routing_reason`` as legacy human/compat text.
Events are append-only; emit when review meaning or workflow state changes — not on every recompute/no-op sync.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.email_intake_review_reason_codes import (
    REASON_DUPLICATE_CONFIRMED,
    REASON_DUPLICATE_FALSE_POSITIVE,
    REASON_DUPLICATE_LINK_PRIOR,
    REASON_THREAD_LINKED_LOAD,
)
from app.constants.email_intake_routing import DUPLICATE_INTAKE_REVIEW_PRIMARIES
from app.deps.auth import CurrentUser
from app.models.email_ingestion import EmailThread
from app.models.email_intake_review import EmailIntakeReview, EmailIntakeReviewEvent
from app.utils.email_intake_routing_parse import detail_json_normalized, parse_routing_reason_structured

REVIEW_STATUS_OPEN = "open"
REVIEW_STATUS_CLAIMED = "claimed"
REVIEW_STATUS_RESOLVED = "resolved"
REVIEW_STATUS_DISMISSED = "dismissed"

ACTOR_SYSTEM = "system"
ACTOR_TENANT_USER = "tenant_user"
ACTOR_PLATFORM_USER = "platform_user"


def _actor_payload(cu: CurrentUser | None) -> tuple[str, str | None, int | None]:
    if cu is None:
        return ACTOR_SYSTEM, None, None
    if cu.tenant_user is not None:
        return ACTOR_TENANT_USER, str(cu.user.id), int(cu.tenant_user.id)
    return ACTOR_PLATFORM_USER, str(cu.user.id), None


async def _append_event(
    db: AsyncSession,
    *,
    tenant_id: int,
    review_id: int,
    event_type: str,
    actor_kind: str,
    actor_platform_user_id: str | None,
    actor_tenant_user_id: int | None,
    old_value: dict[str, Any] | None = None,
    new_value: dict[str, Any] | None = None,
    reason_code: str | None = None,
    payload_note: str | None = None,
) -> None:
    db.add(
        EmailIntakeReviewEvent(
            tenant_id=tenant_id,
            email_intake_review_id=review_id,
            event_type=event_type,
            actor_kind=actor_kind,
            actor_platform_user_id=actor_platform_user_id,
            actor_tenant_user_id=actor_tenant_user_id,
            old_value_json=old_value,
            new_value_json=new_value,
            reason_code=reason_code,
            payload_note=payload_note,
        )
    )


async def sync_email_intake_review_for_thread(
    db: AsyncSession,
    tenant_id: int,
    thread_id: int,
) -> None:
    """
    Upsert review row when thread is in actionable ``needs_review`` queue. ``routing_reason`` is the bridge for
    ``primary_code``/detail today; future paths should write the review fields at the source.
    """
    thread = await db.scalar(
        select(EmailThread).where(EmailThread.id == thread_id, EmailThread.tenant_id == tenant_id)
    )
    if not thread:
        return
    if thread.status != "active":
        return
    if thread.linked_load_id is not None:
        return
    if thread.intake_bucket != "needs_review":
        return

    raw = (thread.routing_reason or "").strip()
    primary, detail = parse_routing_reason_structured(raw if raw else None)
    if not primary:
        primary = "intake_routing_unspecified"
        detail = {**detail, "note": "empty_or_unparsed_routing_reason"}

    rev = await db.scalar(
        select(EmailIntakeReview).where(
            EmailIntakeReview.tenant_id == tenant_id,
            EmailIntakeReview.email_thread_id == thread_id,
        )
    )

    if rev is None:
        rev = EmailIntakeReview(
            tenant_id=tenant_id,
            email_thread_id=thread_id,
            primary_code=primary,
            detail_json=detail,
            status=REVIEW_STATUS_OPEN,
            last_routing_reason_snapshot=raw or None,
        )
        db.add(rev)
        await db.flush()
        await _append_event(
            db,
            tenant_id=tenant_id,
            review_id=rev.id,
            event_type="review_opened",
            actor_kind=ACTOR_SYSTEM,
            actor_platform_user_id=None,
            actor_tenant_user_id=None,
            new_value={"primary_code": primary, "status": REVIEW_STATUS_OPEN, "detail": detail},
        )
        return

    if rev.status in (REVIEW_STATUS_RESOLVED, REVIEW_STATUS_DISMISSED):
        snap_changed = (raw or None) != (rev.last_routing_reason_snapshot or None)
        primary_changed = primary != rev.primary_code
        detail_changed = detail_json_normalized(detail) != detail_json_normalized(rev.detail_json)
        if snap_changed or primary_changed or detail_changed:
            old = {
                "status": rev.status,
                "primary_code": rev.primary_code,
                "detail": rev.detail_json,
                "last_routing_reason_snapshot": rev.last_routing_reason_snapshot,
            }
            rev.status = REVIEW_STATUS_OPEN
            rev.primary_code = primary
            rev.detail_json = detail
            rev.last_routing_reason_snapshot = raw or None
            rev.claimed_by_tenant_user_id = None
            rev.claimed_at = None
            rev.resolved_at = None
            rev.dismissed_at = None
            await _append_event(
                db,
                tenant_id=tenant_id,
                review_id=rev.id,
                event_type="reopened",
                actor_kind=ACTOR_SYSTEM,
                actor_platform_user_id=None,
                actor_tenant_user_id=None,
                old_value=old,
                new_value={
                    "status": REVIEW_STATUS_OPEN,
                    "primary_code": primary,
                    "detail": detail,
                    "reason": "routing_or_detail_changed_after_close",
                },
            )
        return

    detail_changed = detail_json_normalized(detail) != detail_json_normalized(rev.detail_json)
    primary_changed = primary != rev.primary_code
    snap_changed = (raw or None) != (rev.last_routing_reason_snapshot or None)
    if primary_changed or detail_changed or snap_changed:
        old = {
            "primary_code": rev.primary_code,
            "detail": rev.detail_json,
            "last_routing_reason_snapshot": rev.last_routing_reason_snapshot,
        }
        rev.primary_code = primary
        rev.detail_json = detail
        rev.last_routing_reason_snapshot = raw or None
        await _append_event(
            db,
            tenant_id=tenant_id,
            review_id=rev.id,
            event_type="detail_synced",
            actor_kind=ACTOR_SYSTEM,
            actor_platform_user_id=None,
            actor_tenant_user_id=None,
            old_value=old,
            new_value={"primary_code": primary, "detail": detail, "last_routing_reason_snapshot": raw or None},
        )


async def upsert_intake_review_from_intake_source(
    db: AsyncSession,
    tenant_id: int,
    thread_id: int,
    *,
    primary_code: str,
    detail_extensions: dict[str, Any],
    routing_reason_snapshot: str | None = None,
) -> None:
    """Write ``primary_code`` + structured detail at intake source (parses routing tail, merges extensions).

    Keeps ``last_routing_reason_snapshot`` aligned with the thread; avoids extra sync noise when routing tail
    already encodes the same fields (e.g. ``content_sha256`` on duplicate lines).
    """
    thread = await db.scalar(
        select(EmailThread).where(EmailThread.id == thread_id, EmailThread.tenant_id == tenant_id)
    )
    if not thread:
        return
    if thread.status != "active":
        return
    if thread.linked_load_id is not None:
        return
    if thread.intake_bucket != "needs_review":
        return

    raw = (
        (routing_reason_snapshot if routing_reason_snapshot is not None else (thread.routing_reason or "")).strip()
    )
    if not raw:
        return

    _, parsed = parse_routing_reason_structured(raw)
    detail: dict[str, Any] = {**parsed, **detail_extensions}
    primary = primary_code

    rev = await db.scalar(
        select(EmailIntakeReview).where(
            EmailIntakeReview.tenant_id == tenant_id,
            EmailIntakeReview.email_thread_id == thread_id,
        )
    )

    if rev is None:
        rev = EmailIntakeReview(
            tenant_id=tenant_id,
            email_thread_id=thread_id,
            primary_code=primary,
            detail_json=detail,
            status=REVIEW_STATUS_OPEN,
            last_routing_reason_snapshot=raw or None,
        )
        db.add(rev)
        await db.flush()
        await _append_event(
            db,
            tenant_id=tenant_id,
            review_id=rev.id,
            event_type="review_opened",
            actor_kind=ACTOR_SYSTEM,
            actor_platform_user_id=None,
            actor_tenant_user_id=None,
            new_value={"primary_code": primary, "status": REVIEW_STATUS_OPEN, "detail": detail, "source": "intake"},
        )
        return

    if rev.status in (REVIEW_STATUS_RESOLVED, REVIEW_STATUS_DISMISSED):
        snap_changed = (raw or None) != (rev.last_routing_reason_snapshot or None)
        primary_changed = primary != rev.primary_code
        detail_changed = detail_json_normalized(detail) != detail_json_normalized(rev.detail_json)
        if snap_changed or primary_changed or detail_changed:
            old = {
                "status": rev.status,
                "primary_code": rev.primary_code,
                "detail": rev.detail_json,
                "last_routing_reason_snapshot": rev.last_routing_reason_snapshot,
            }
            rev.status = REVIEW_STATUS_OPEN
            rev.primary_code = primary
            rev.detail_json = detail
            rev.last_routing_reason_snapshot = raw or None
            rev.claimed_by_tenant_user_id = None
            rev.claimed_at = None
            rev.resolved_at = None
            rev.dismissed_at = None
            await _append_event(
                db,
                tenant_id=tenant_id,
                review_id=rev.id,
                event_type="reopened",
                actor_kind=ACTOR_SYSTEM,
                actor_platform_user_id=None,
                actor_tenant_user_id=None,
                old_value=old,
                new_value={
                    "status": REVIEW_STATUS_OPEN,
                    "primary_code": primary,
                    "detail": detail,
                    "reason": "intake_source_changed_after_close",
                },
            )
        return

    detail_changed = detail_json_normalized(detail) != detail_json_normalized(rev.detail_json)
    primary_changed = primary != rev.primary_code
    snap_changed = (raw or None) != (rev.last_routing_reason_snapshot or None)
    if primary_changed or detail_changed or snap_changed:
        old = {
            "primary_code": rev.primary_code,
            "detail": rev.detail_json,
            "last_routing_reason_snapshot": rev.last_routing_reason_snapshot,
        }
        rev.primary_code = primary
        rev.detail_json = detail
        rev.last_routing_reason_snapshot = raw or None
        await _append_event(
            db,
            tenant_id=tenant_id,
            review_id=rev.id,
            event_type="detail_synced",
            actor_kind=ACTOR_SYSTEM,
            actor_platform_user_id=None,
            actor_tenant_user_id=None,
            old_value=old,
            new_value={
                "primary_code": primary,
                "detail": detail,
                "last_routing_reason_snapshot": raw or None,
                "source": "intake",
            },
        )


def _detail_prior_load_id(detail: dict[str, Any] | None) -> int | None:
    if not detail:
        return None
    v = detail.get("prior_load_id")
    if v is None:
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def is_duplicate_intake_primary(primary_code: str | None) -> bool:
    return bool(primary_code) and primary_code in DUPLICATE_INTAKE_REVIEW_PRIMARIES


async def duplicate_review_prepare_link_prior(
    db: AsyncSession,
    tenant_id: int,
    thread_id: int,
    cu: CurrentUser,
    *,
    prior_load_id: int | None,
) -> tuple[EmailIntakeReview, int]:
    """Validate duplicate-category review; record ``duplicate_link_prior``; return review and load id to link.

    Caller performs load attach + commit.
    """
    rev = await db.scalar(
        select(EmailIntakeReview).where(
            EmailIntakeReview.tenant_id == tenant_id,
            EmailIntakeReview.email_thread_id == thread_id,
        )
    )
    if not rev:
        raise ValueError("no_review")
    if not is_duplicate_intake_primary(rev.primary_code):
        raise ValueError("not_duplicate_review")
    if rev.status not in (REVIEW_STATUS_OPEN, REVIEW_STATUS_CLAIMED):
        raise ValueError("invalid_state_for_duplicate_action")

    suggested = _detail_prior_load_id(rev.detail_json if isinstance(rev.detail_json, dict) else None)
    target = prior_load_id if prior_load_id is not None else suggested
    if target is None:
        raise ValueError("prior_load_id_required")
    if suggested is not None and int(target) != int(suggested):
        raise ValueError("prior_load_id_mismatch")

    ak, plat, atu = _actor_payload(cu)
    await _append_event(
        db,
        tenant_id=tenant_id,
        review_id=rev.id,
        event_type="duplicate_link_prior",
        actor_kind=ak,
        actor_platform_user_id=plat,
        actor_tenant_user_id=atu,
        new_value={"prior_load_id": int(target)},
        reason_code=REASON_DUPLICATE_LINK_PRIOR,
    )
    await db.flush()
    return rev, int(target)


async def duplicate_review_confirm(
    db: AsyncSession,
    tenant_id: int,
    thread_id: int,
    cu: CurrentUser,
    *,
    note: str | None,
) -> EmailIntakeReview:
    """Append ``duplicate_confirmed`` after the thread is linked to the suggested prior load."""
    thread = await db.scalar(
        select(EmailThread).where(EmailThread.id == thread_id, EmailThread.tenant_id == tenant_id)
    )
    if not thread:
        raise ValueError("no_thread")

    rev = await db.scalar(
        select(EmailIntakeReview).where(
            EmailIntakeReview.tenant_id == tenant_id,
            EmailIntakeReview.email_thread_id == thread_id,
        )
    )
    if not rev:
        raise ValueError("no_review")
    if not is_duplicate_intake_primary(rev.primary_code):
        raise ValueError("not_duplicate_review")

    suggested = _detail_prior_load_id(rev.detail_json if isinstance(rev.detail_json, dict) else None)
    if thread.linked_load_id is None:
        raise ValueError("thread_not_linked_to_load")
    if suggested is not None and int(thread.linked_load_id) != int(suggested):
        raise ValueError("linked_load_neq_suggested_prior")

    ak, plat, atu = _actor_payload(cu)
    await _append_event(
        db,
        tenant_id=tenant_id,
        review_id=rev.id,
        event_type="duplicate_confirmed",
        actor_kind=ak,
        actor_platform_user_id=plat,
        actor_tenant_user_id=atu,
        new_value={
            "linked_load_id": int(thread.linked_load_id),
            "prior_load_id": suggested,
        },
        reason_code=REASON_DUPLICATE_CONFIRMED,
        payload_note=note,
    )
    await db.flush()
    return rev


async def duplicate_review_dismiss_false_positive(
    db: AsyncSession,
    tenant_id: int,
    thread_id: int,
    cu: CurrentUser,
    *,
    note: str | None,
) -> EmailIntakeReview:
    rev = await db.scalar(
        select(EmailIntakeReview).where(
            EmailIntakeReview.tenant_id == tenant_id,
            EmailIntakeReview.email_thread_id == thread_id,
        )
    )
    if not rev:
        raise ValueError("no_review")
    if not is_duplicate_intake_primary(rev.primary_code):
        raise ValueError("not_duplicate_review")
    return await dismiss_email_intake_review(
        db,
        tenant_id,
        thread_id,
        cu,
        reason_code=REASON_DUPLICATE_FALSE_POSITIVE,
        note=note,
    )


async def auto_resolve_email_intake_review_on_thread_linked_load(
    db: AsyncSession,
    tenant_id: int,
    thread_id: int,
    *,
    linked_load_id: int,
) -> None:
    """Close an open or claimed review when the thread is linked to a load (same transaction as the link).

    No-op if there is no review or status is already terminal. Emits one ``auto_resolved_thread_linked_load`` event.
    """
    rev = await db.scalar(
        select(EmailIntakeReview).where(
            EmailIntakeReview.tenant_id == tenant_id,
            EmailIntakeReview.email_thread_id == thread_id,
        )
    )
    if not rev:
        return
    if rev.status not in (REVIEW_STATUS_OPEN, REVIEW_STATUS_CLAIMED):
        return
    now = datetime.now(timezone.utc)
    old = {"status": rev.status, "claimed_by": rev.claimed_by_tenant_user_id}
    rev.status = REVIEW_STATUS_RESOLVED
    rev.resolved_at = now
    rev.dismissed_at = None
    rev.claimed_by_tenant_user_id = None
    rev.claimed_at = None
    await _append_event(
        db,
        tenant_id=tenant_id,
        review_id=rev.id,
        event_type="auto_resolved_thread_linked_load",
        actor_kind=ACTOR_SYSTEM,
        actor_platform_user_id=None,
        actor_tenant_user_id=None,
        old_value=old,
        new_value={"status": REVIEW_STATUS_RESOLVED, "linked_load_id": linked_load_id},
        reason_code=REASON_THREAD_LINKED_LOAD,
    )


async def get_review_with_events(
    db: AsyncSession,
    tenant_id: int,
    thread_id: int,
    *,
    event_limit: int = 200,
) -> tuple[EmailIntakeReview | None, list[EmailIntakeReviewEvent]]:
    rev = await db.scalar(
        select(EmailIntakeReview).where(
            EmailIntakeReview.tenant_id == tenant_id,
            EmailIntakeReview.email_thread_id == thread_id,
        )
    )
    if not rev:
        return None, []
    res = await db.execute(
        select(EmailIntakeReviewEvent)
        .where(
            EmailIntakeReviewEvent.tenant_id == tenant_id,
            EmailIntakeReviewEvent.email_intake_review_id == rev.id,
        )
        .order_by(EmailIntakeReviewEvent.id.asc())
        .limit(event_limit)
    )
    return rev, list(res.scalars().all())


async def claim_email_intake_review(
    db: AsyncSession,
    tenant_id: int,
    thread_id: int,
    cu: CurrentUser,
    *,
    tenant_user_id: int,
) -> EmailIntakeReview:
    rev = await db.scalar(
        select(EmailIntakeReview).where(
            EmailIntakeReview.tenant_id == tenant_id,
            EmailIntakeReview.email_thread_id == thread_id,
        )
    )
    if not rev:
        raise ValueError("no_review")
    if rev.status == REVIEW_STATUS_RESOLVED:
        raise ValueError("already_resolved")
    if rev.status == REVIEW_STATUS_DISMISSED:
        raise ValueError("already_dismissed")
    if rev.status == REVIEW_STATUS_CLAIMED:
        if rev.claimed_by_tenant_user_id == tenant_user_id:
            return rev
        raise ValueError("claimed_by_other")

    ak, plat, atu = _actor_payload(cu)
    old = {"status": rev.status, "claimed_by": rev.claimed_by_tenant_user_id}
    rev.status = REVIEW_STATUS_CLAIMED
    rev.claimed_by_tenant_user_id = tenant_user_id
    rev.claimed_at = datetime.now(timezone.utc)
    await _append_event(
        db,
        tenant_id=tenant_id,
        review_id=rev.id,
        event_type="claimed",
        actor_kind=ak,
        actor_platform_user_id=plat,
        actor_tenant_user_id=atu,
        old_value=old,
        new_value={"status": REVIEW_STATUS_CLAIMED, "claimed_by_tenant_user_id": tenant_user_id},
    )
    return rev


async def resolve_email_intake_review(
    db: AsyncSession,
    tenant_id: int,
    thread_id: int,
    cu: CurrentUser,
    *,
    reason_code: str | None,
    note: str | None,
) -> EmailIntakeReview:
    rev = await db.scalar(
        select(EmailIntakeReview).where(
            EmailIntakeReview.tenant_id == tenant_id,
            EmailIntakeReview.email_thread_id == thread_id,
        )
    )
    if not rev:
        raise ValueError("no_review")
    if rev.status == REVIEW_STATUS_RESOLVED:
        raise ValueError("already_resolved")
    if rev.status == REVIEW_STATUS_DISMISSED:
        raise ValueError("already_dismissed")

    ak, plat, atu = _actor_payload(cu)
    now = datetime.now(timezone.utc)
    old = {"status": rev.status, "claimed_by": rev.claimed_by_tenant_user_id}
    rev.status = REVIEW_STATUS_RESOLVED
    rev.resolved_at = now
    rev.dismissed_at = None
    rev.claimed_by_tenant_user_id = None
    rev.claimed_at = None
    await _append_event(
        db,
        tenant_id=tenant_id,
        review_id=rev.id,
        event_type="resolved",
        actor_kind=ak,
        actor_platform_user_id=plat,
        actor_tenant_user_id=atu,
        old_value=old,
        new_value={"status": REVIEW_STATUS_RESOLVED, "resolved_at": now.isoformat()},
        reason_code=reason_code,
        payload_note=note,
    )
    return rev


async def dismiss_email_intake_review(
    db: AsyncSession,
    tenant_id: int,
    thread_id: int,
    cu: CurrentUser,
    *,
    reason_code: str | None,
    note: str | None,
) -> EmailIntakeReview:
    rev = await db.scalar(
        select(EmailIntakeReview).where(
            EmailIntakeReview.tenant_id == tenant_id,
            EmailIntakeReview.email_thread_id == thread_id,
        )
    )
    if not rev:
        raise ValueError("no_review")
    if rev.status == REVIEW_STATUS_DISMISSED:
        raise ValueError("already_dismissed")
    if rev.status not in (REVIEW_STATUS_OPEN, REVIEW_STATUS_CLAIMED):
        if rev.status == REVIEW_STATUS_RESOLVED:
            raise ValueError("resolved_use_reopen_first")
        raise ValueError("invalid_state_for_dismiss")

    ak, plat, atu = _actor_payload(cu)
    now = datetime.now(timezone.utc)
    old = {"status": rev.status}
    rev.status = REVIEW_STATUS_DISMISSED
    rev.dismissed_at = now
    rev.resolved_at = None
    rev.claimed_by_tenant_user_id = None
    rev.claimed_at = None
    await _append_event(
        db,
        tenant_id=tenant_id,
        review_id=rev.id,
        event_type="dismissed",
        actor_kind=ak,
        actor_platform_user_id=plat,
        actor_tenant_user_id=atu,
        old_value=old,
        new_value={"status": REVIEW_STATUS_DISMISSED, "dismissed_at": now.isoformat()},
        reason_code=reason_code,
        payload_note=note,
    )
    return rev


async def reopen_email_intake_review(
    db: AsyncSession,
    tenant_id: int,
    thread_id: int,
    cu: CurrentUser,
    *,
    reason_code: str | None,
    note: str | None,
) -> EmailIntakeReview:
    rev = await db.scalar(
        select(EmailIntakeReview).where(
            EmailIntakeReview.tenant_id == tenant_id,
            EmailIntakeReview.email_thread_id == thread_id,
        )
    )
    if not rev:
        raise ValueError("no_review")
    if rev.status not in (REVIEW_STATUS_RESOLVED, REVIEW_STATUS_DISMISSED):
        raise ValueError("not_closed")

    ak, plat, atu = _actor_payload(cu)
    old = {"status": rev.status}
    rev.status = REVIEW_STATUS_OPEN
    rev.resolved_at = None
    rev.dismissed_at = None
    rev.claimed_by_tenant_user_id = None
    rev.claimed_at = None
    await _append_event(
        db,
        tenant_id=tenant_id,
        review_id=rev.id,
        event_type="reopened_manual",
        actor_kind=ak,
        actor_platform_user_id=plat,
        actor_tenant_user_id=atu,
        old_value=old,
        new_value={"status": REVIEW_STATUS_OPEN},
        reason_code=reason_code,
        payload_note=note,
    )
    return rev


async def load_review_summary_for_thread(
    db: AsyncSession,
    tenant_id: int,
    thread_id: int,
) -> EmailIntakeReview | None:
    return await db.scalar(
        select(EmailIntakeReview).where(
            EmailIntakeReview.tenant_id == tenant_id,
            EmailIntakeReview.email_thread_id == thread_id,
        )
    )
