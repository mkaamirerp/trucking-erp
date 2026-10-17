"""Discard and expiry for load workspace drafts."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.storage import get_storage
from app.models.load_commercial_evidence import LoadCommercialEvidence
from app.models.load_workspace_draft import LoadWorkspaceDraft

# Storage module name — keep in sync with load_workspace_draft_document.LOAD_WORKSPACE_DRAFT_PDF_MODULE
_LOAD_WORKSPACE_DRAFT_PDF_MODULE = "load_workspace_draft"

MUTABLE_BEFORE_DISCARD = frozenset({"draft", "expired"})


async def _fetch_workspace_draft(
    db: AsyncSession, tenant_id: int, draft_id: uuid.UUID
) -> LoadWorkspaceDraft | None:
    return await db.scalar(
        select(LoadWorkspaceDraft).where(
            LoadWorkspaceDraft.tenant_id == tenant_id,
            LoadWorkspaceDraft.id == draft_id,
        )
    )


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


async def apply_expiry_if_overdue(db: AsyncSession, draft: LoadWorkspaceDraft) -> bool:
    """Transition status draft → expired when past expires_at. Returns True if changed."""
    if draft.status != "draft":
        return False
    now = _utc_now()
    if _normalize_utc(draft.expires_at) > now:
        return False
    stmt = (
        update(LoadWorkspaceDraft)
        .where(
            LoadWorkspaceDraft.tenant_id == draft.tenant_id,
            LoadWorkspaceDraft.id == draft.id,
            LoadWorkspaceDraft.status == "draft",
            LoadWorkspaceDraft.expires_at <= now,
        )
        .values(
            status="expired",
            concurrency_version=LoadWorkspaceDraft.concurrency_version + 1,
            updated_at=func.now(),
        )
        .returning(LoadWorkspaceDraft)
    )
    result = await db.execute(stmt)
    row = result.scalar_one_or_none()
    if row is None:
        await db.refresh(draft)
        return draft.status == "expired"
    draft.status = row.status
    draft.concurrency_version = int(row.concurrency_version)
    return True


def raise_not_editable(draft: LoadWorkspaceDraft) -> None:
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={
            "code": "LOAD_WORKSPACE_DRAFT_NOT_EDITABLE",
            "status": draft.status,
        },
    )


async def require_workspace_draft_open_for_mutation(
    db: AsyncSession, draft: LoadWorkspaceDraft
) -> LoadWorkspaceDraft:
    """Apply expiry, then ensure status is still draft (editable / parseable / promotable)."""
    await apply_expiry_if_overdue(db, draft)
    if draft.status != "draft":
        raise_not_editable(draft)
    return draft


async def storage_key_referenced_by_commercial_evidence(
    db: AsyncSession, tenant_id: int, storage_key: str
) -> bool:
    found = await db.scalar(
        select(LoadCommercialEvidence.id).where(
            LoadCommercialEvidence.tenant_id == tenant_id,
            LoadCommercialEvidence.storage_key == storage_key,
        )
    )
    return found is not None


async def delete_ephemeral_workspace_draft_pdf(
    db: AsyncSession,
    tenant_id: int,
    tenant_slug: str,
    draft: LoadWorkspaceDraft,
) -> None:
    """Remove workspace-TTL draft PDF from object storage only when safe for promoted evidence."""
    key = draft.pdf_storage_key
    if not key:
        return
    if draft.pdf_retention_class != "workspace_ttl":
        return
    if await storage_key_referenced_by_commercial_evidence(db, tenant_id, key):
        return
    get_storage().delete(key, module=_LOAD_WORKSPACE_DRAFT_PDF_MODULE, tenant_slug=tenant_slug)


async def discard_workspace_draft(
    db: AsyncSession,
    tenant_id: int,
    tenant_slug: str,
    draft_id: uuid.UUID,
    *,
    discard_reason: str | None,
    updated_by_platform_user_id: str | None,
) -> LoadWorkspaceDraft:
    draft = await db.scalar(
        select(LoadWorkspaceDraft)
        .where(LoadWorkspaceDraft.tenant_id == tenant_id, LoadWorkspaceDraft.id == draft_id)
        .with_for_update()
    )
    if draft is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace draft not found")

    await apply_expiry_if_overdue(db, draft)
    if draft.status not in MUTABLE_BEFORE_DISCARD:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "LOAD_WORKSPACE_DRAFT_NOT_DISCARDABLE",
                "status": draft.status,
            },
        )

    await delete_ephemeral_workspace_draft_pdf(db, tenant_id, tenant_slug, draft)

    now = _utc_now()
    reason = (discard_reason or "").strip() or None
    draft.status = "discarded"
    draft.discarded_at = now
    draft.discard_reason = reason
    draft.concurrency_version = int(draft.concurrency_version) + 1
    draft.updated_by_platform_user_id = updated_by_platform_user_id
    draft.pdf_upload_state = "idle"
    draft.pdf_storage_key = None
    draft.pdf_sha256 = None
    draft.pdf_filename = None
    draft.pdf_size_bytes = None
    draft.pdf_pending_storage_key = None
    draft.accepted_parse_json = None
    draft.accepted_parse_schema_version = None
    draft.accepted_parse_pdf_sha256 = None

    await db.commit()
    await db.refresh(draft)
    return draft


async def get_workspace_draft_with_lifecycle(
    db: AsyncSession, tenant_id: int, draft_id: uuid.UUID
) -> LoadWorkspaceDraft | None:
    draft = await _fetch_workspace_draft(db, tenant_id, draft_id)
    if draft is None:
        return None
    if await apply_expiry_if_overdue(db, draft):
        await db.commit()
        await db.refresh(draft)
    return draft
