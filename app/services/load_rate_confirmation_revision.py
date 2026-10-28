"""Accept one revised rate confirmation and keep every earlier PDF.

The load stays the dispatcher-corrected record. This step writes only an accepted
rate (and customer_rate when it still equals that old rate). Stops, broker fields,
the creation snapshot, and the original evidence row are not updated.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.storage import get_storage
from app.models.load import Load
from app.models.load_rate_confirmation_revision import LoadRateConfirmationRevision
from app.schemas.load_document_parse import (
    RateConfirmationRevisionAcceptResponse,
    RateConfirmationRevisionListItem,
    RateConfirmationRevisionListResponse,
)
from app.services.load_approved_commercial_snapshot import _scrub, build_approved_db_fields, money_string
from app.services.load_document_parse_orchestrator import (
    _DIFFERENT_LOAD,
    _NO_BASELINE,
    _NO_REVISED_REF,
    _NO_SAVED_REF,
    _UNREADABLE_PDF,
    _broker_notices,
    _canon,
    _extraction_dict,
    _facility_notices,
    _revised_pdf_unreadable,
    original_evidence_select,
    parse_load_workspace_document_orchestrated,
    verify_revision_changes,
)
from app.services.load_rate_confirmation_duplicate import normalize_rate_confirmation_reference
from app.services.load_workspace_draft_storage import (
    STORAGE_MODULE,
    LoadWorkspaceDraftStorageError,
    Sha256MismatchError,
    read_object_bytes,
)
from app.services.loads import read_load_rate_confirmation_pdf_bytes

_CANCELLED = "Cancelled loads cannot accept a revised rate confirmation."
_LOAD_CHANGED = "load changed since compare"
_ALREADY_APPLIED = "already applied/original"
_RATE_ONLY = "Only the rate can be accepted."
_RATE_UNVERIFIED = "This rate change is not verified against the revised PDF."
_PDF_MISSING = "Rate confirmation PDF file not found"


class RateConfirmationRevisionAcceptError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def _money(value: Any) -> Decimal | None:
    text = _canon(value)
    if text is None:
        return None
    return Decimal(str(text))


def _rate_change(changes: Any) -> tuple[str | None, str | None]:
    if not isinstance(changes, list):
        return None, None
    for item in changes:
        if isinstance(item, dict) and item.get("field") == "rate":
            old = item.get("old")
            new = item.get("new")
            return (None if old is None else str(old), None if new is None else str(new))
    return None, None


async def _lock_load(db: AsyncSession, tenant_id: int, load_id: int) -> Load | None:
    return await db.scalar(
        select(Load)
        .where(Load.tenant_id == int(tenant_id), Load.id == int(load_id))
        .options(selectinload(Load.stops))
        .with_for_update(of=Load)
    )


async def accept_revised_rate_confirmation(
    db: AsyncSession,
    *,
    tenant_id: int,
    tenant_slug: str,
    load_id: int,
    pdf_bytes: bytes,
    filename: str,
    accepted_fields: list[dict[str, Any]],
    accepted_by_platform_user_id: str | None,
) -> RateConfirmationRevisionAcceptResponse:
    """Lock the load, re-parse, and persist one current revision plus the accepted rate."""
    load = await _lock_load(db, tenant_id, load_id)
    if load is None:
        raise RateConfirmationRevisionAcceptError(404, "Load not found")
    if (load.status or "").strip().casefold() == "cancelled":
        raise RateConfirmationRevisionAcceptError(409, _CANCELLED)

    try:
        evidence = await db.scalar(original_evidence_select(tenant_id, load_id))
        revisions = list(
            (
                await db.scalars(
                    select(LoadRateConfirmationRevision)
                    .where(
                        LoadRateConfirmationRevision.tenant_id == int(tenant_id),
                        LoadRateConfirmationRevision.load_id == int(load_id),
                    )
                    .order_by(LoadRateConfirmationRevision.revision_number)
                )
            ).all()
        )
    except ProgrammingError:
        await db.rollback()
        raise RateConfirmationRevisionAcceptError(409, _NO_BASELINE) from None

    accepted = evidence.accepted_parse_json if evidence is not None else None
    original = _extraction_dict(accepted if isinstance(accepted, dict) else None)
    if original is None:
        raise RateConfirmationRevisionAcceptError(409, _NO_BASELINE)

    parsed = await parse_load_workspace_document_orchestrated(
        pdf_bytes,
        filename=filename,
        load_id=load_id,
        tenant_id=tenant_id,
        db=db,
    )
    if _revised_pdf_unreadable(parsed):
        raise RateConfirmationRevisionAcceptError(422, _UNREADABLE_PDF)
    new_extracted = parsed.extracted.model_dump(mode="json")
    saved_ref = normalize_rate_confirmation_reference(load.broker_load_reference)
    new_ref = normalize_rate_confirmation_reference(new_extracted.get("broker_load_reference"))
    if not saved_ref:
        raise RateConfirmationRevisionAcceptError(409, _NO_SAVED_REF)
    if not new_ref:
        raise RateConfirmationRevisionAcceptError(409, _NO_REVISED_REF)
    if saved_ref != new_ref:
        raise RateConfirmationRevisionAcceptError(409, _DIFFERENT_LOAD)
    if len(accepted_fields) != 1 or not isinstance(accepted_fields[0], dict):
        raise RateConfirmationRevisionAcceptError(422, _RATE_ONLY)
    requested = accepted_fields[0]
    if requested.get("field") != "rate" or "new_value" not in requested or "expected_current_value" not in requested:
        raise RateConfirmationRevisionAcceptError(422, _RATE_ONLY)

    await db.refresh(load, attribute_names=["stops"])
    current = build_approved_db_fields(load)
    verified = verify_revision_changes(
        [{"field": "rate", "new_value": requested.get("new_value")}],
        current=current,
        original_extracted=original,
        new_extracted=new_extracted,
    )
    rate_change = next((item for item in verified if item.field == "rate" and item.kind == "changed"), None)
    if rate_change is None:
        raise RateConfirmationRevisionAcceptError(422, _RATE_UNVERIFIED)
    if _canon(load.rate) != _canon(requested.get("expected_current_value")):
        raise RateConfirmationRevisionAcceptError(409, _LOAD_CHANGED)

    digest = hashlib.sha256(pdf_bytes).hexdigest()
    original_sha = (getattr(evidence, "file_sha256", None) or "").strip().lower()
    if original_sha and original_sha == digest:
        raise RateConfirmationRevisionAcceptError(409, _ALREADY_APPLIED)
    if any((row.file_sha256 or "").strip().lower() == digest for row in revisions):
        raise RateConfirmationRevisionAcceptError(409, _ALREADY_APPLIED)

    old_rate = _money(load.rate)
    new_rate = _money(rate_change.new_value)
    if new_rate is None:
        raise RateConfirmationRevisionAcceptError(422, _RATE_UNVERIFIED)
    customer_moved = _canon(load.customer_rate) == _canon(old_rate)
    old_customer = _money(load.customer_rate)
    changes: list[dict[str, str | None]] = [
        {"field": "rate", "old": money_string(old_rate), "new": money_string(new_rate)}
    ]
    if customer_moved:
        changes.append(
            {
                "field": "customer_rate",
                "old": money_string(old_customer),
                "new": money_string(new_rate),
            }
        )
    notices = _broker_notices(current=current, original_extracted=original, new_extracted=new_extracted)
    notices.extend(
        _facility_notices(current=current, original_extracted=original, new_extracted=new_extracted)
    )
    next_number = max((int(row.revision_number) for row in revisions), default=0) + 1
    stored = await get_storage().save_bytes(
        tenant_slug,
        STORAGE_MODULE,
        "load_rc_revision",
        load_id,
        pdf_bytes,
        filename_hint=filename or "revised-rate-confirmation.pdf",
        content_type="application/pdf",
    )
    if (stored.sha256 or "").lower() != digest:
        get_storage().delete(stored.storage_key, module=STORAGE_MODULE, tenant_slug=tenant_slug)
        raise RateConfirmationRevisionAcceptError(
            500,
            "Stored rate confirmation PDF did not match the upload.",
        )

    try:
        for row in revisions:
            if row.is_current:
                row.is_current = False
        actor = (accepted_by_platform_user_id or "").strip() or None
        if actor is not None:
            actor = actor[:36]
        revision = LoadRateConfirmationRevision(
            tenant_id=int(tenant_id),
            load_id=int(load_id),
            revision_number=next_number,
            is_current=True,
            file_sha256=digest,
            storage_key=stored.storage_key,
            filename=(stored.original_filename or filename or "revised-rate-confirmation.pdf")[:512],
            new_parse_json=_scrub(parsed.model_dump(mode="json")),
            accepted_changes_json=changes,
            compare_notices_json=notices,
            accepted_by_platform_user_id=actor,
            accepted_at=datetime.now(timezone.utc),
        )
        db.add(revision)
        load.rate = new_rate
        if customer_moved:
            load.customer_rate = new_rate
        await db.flush()
        await db.commit()
    except Exception:
        await db.rollback()
        get_storage().delete(stored.storage_key, module=STORAGE_MODULE, tenant_slug=tenant_slug)
        raise

    applied = ["rate", "customer_rate"] if customer_moved else ["rate"]
    return RateConfirmationRevisionAcceptResponse(
        revision_number=next_number,
        applied_fields=applied,
        new_rate=money_string(new_rate) or "",
        customer_rate_moved=customer_moved,
    )


async def list_rate_confirmation_revisions(
    db: AsyncSession,
    *,
    tenant_id: int,
    load_id: int,
) -> RateConfirmationRevisionListResponse:
    load = await db.scalar(
        select(Load).where(Load.tenant_id == int(tenant_id), Load.id == int(load_id))
    )
    if load is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Load not found")
    try:
        rows = list(
            (
                await db.scalars(
                    select(LoadRateConfirmationRevision)
                    .where(
                        LoadRateConfirmationRevision.tenant_id == int(tenant_id),
                        LoadRateConfirmationRevision.load_id == int(load_id),
                    )
                    .order_by(LoadRateConfirmationRevision.revision_number)
                )
            ).all()
        )
    except ProgrammingError:
        await db.rollback()
        rows = []
    items: list[RateConfirmationRevisionListItem] = []
    for row in rows:
        old_rate, new_rate = _rate_change(row.accepted_changes_json)
        items.append(
            RateConfirmationRevisionListItem(
                revision_number=int(row.revision_number),
                filename=row.filename,
                accepted_at=row.accepted_at,
                accepted_by=row.accepted_by_platform_user_id,
                is_current=bool(row.is_current),
                old_rate=old_rate,
                new_rate=new_rate,
            )
        )
    return RateConfirmationRevisionListResponse(items=items)


async def read_rate_confirmation_pdf_for_view(
    db: AsyncSession,
    *,
    tenant_id: int,
    load_id: int,
    tenant_slug: str,
    revision: int | None,
) -> tuple[str, bytes]:
    """Current revision PDF, the original when none exists, or ?revision=N (0 = original)."""
    if revision is not None and revision < 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_PDF_MISSING)
    if revision == 0:
        row, body = await read_load_rate_confirmation_pdf_bytes(
            db, tenant_id, load_id, tenant_slug=tenant_slug
        )
        return row.filename or "rate-confirmation.pdf", body

    chosen = None
    try:
        if revision is None:
            chosen = await db.scalar(
                select(LoadRateConfirmationRevision).where(
                    LoadRateConfirmationRevision.tenant_id == int(tenant_id),
                    LoadRateConfirmationRevision.load_id == int(load_id),
                    LoadRateConfirmationRevision.is_current.is_(True),
                )
            )
        else:
            chosen = await db.scalar(
                select(LoadRateConfirmationRevision).where(
                    LoadRateConfirmationRevision.tenant_id == int(tenant_id),
                    LoadRateConfirmationRevision.load_id == int(load_id),
                    LoadRateConfirmationRevision.revision_number == int(revision),
                )
            )
    except ProgrammingError:
        await db.rollback()
        chosen = None
        if revision is not None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_PDF_MISSING) from None

    if chosen is None:
        if revision is None:
            row, body = await read_load_rate_confirmation_pdf_bytes(
                db, tenant_id, load_id, tenant_slug=tenant_slug
            )
            return row.filename or "rate-confirmation.pdf", body
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_PDF_MISSING)

    expected = (chosen.file_sha256 or "").strip().lower()
    if not expected or not (chosen.storage_key or "").strip():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_PDF_MISSING)
    try:
        body = read_object_bytes(
            chosen.storage_key,
            tenant_slug=tenant_slug,
            expected_sha256=expected,
        )
    except (Sha256MismatchError, LoadWorkspaceDraftStorageError) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_PDF_MISSING) from exc
    return chosen.filename or f"rate-confirmation-revision-{chosen.revision_number}.pdf", body
