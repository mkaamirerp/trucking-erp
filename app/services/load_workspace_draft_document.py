"""Persist rate-confirmation PDF + accepted parse on a load workspace draft."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from fastapi import HTTPException, UploadFile, status
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.concurrency.draft_conflicts import workspace_draft_version_conflict_exception
from app.core.storage import get_storage
from app.models.load_workspace_draft import LoadWorkspaceDraft
from app.schemas.load_document_parse import (
    LoadDocumentParseResponse,
    strip_nul_bytes_from_json_tree,
)
from app.services.load_document_parse_orchestrator import parse_load_workspace_document_orchestrated
from app.services.load_parser_pdf_safety import UnsafeLoadPdfError, validate_load_parser_pdf
from app.services.load_workspace_draft_lifecycle import require_workspace_draft_open_for_mutation

LOAD_WORKSPACE_DRAFT_PDF_MODULE = "load_workspace_draft"
WORKSPACE_DRAFT_ACCEPTED_PARSE_SCHEMA_VERSION = "load_document_parse_response_v1"
MAX_PDF_BYTES = 20 * 1024 * 1024
EDITABLE_STATUS = "draft"


async def _read_bounded_pdf(file: UploadFile) -> tuple[bytes, str]:
    chunks: list[bytes] = []
    total = 0
    while True:
        piece = await file.read(1024 * 1024)
        if not piece:
            break
        total += len(piece)
        if total > MAX_PDF_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="PDF too large",
            )
        chunks.append(piece)
    data = b"".join(chunks)
    if not data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Empty file")
    filename = (file.filename or "upload.pdf")[:512]
    return data, filename


def accepted_parse_from_response(parse: LoadDocumentParseResponse) -> dict:
    return strip_nul_bytes_from_json_tree(parse.model_dump(mode="json"))


async def parse_and_attach_workspace_draft_pdf(
    db: AsyncSession,
    tenant_id: int,
    tenant_slug: str,
    draft_id: uuid.UUID,
    file: UploadFile,
    *,
    updated_by_platform_user_id: str | None,
    expected_concurrency_version: int | None = None,
) -> tuple[LoadWorkspaceDraft, LoadDocumentParseResponse]:
    current = await db.scalar(
        select(LoadWorkspaceDraft).where(
            LoadWorkspaceDraft.tenant_id == tenant_id,
            LoadWorkspaceDraft.id == draft_id,
        )
    )
    if current is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace draft not found")
    await require_workspace_draft_open_for_mutation(db, current)
    server_version = int(current.concurrency_version)
    if expected_concurrency_version is not None and expected_concurrency_version != server_version:
        raise workspace_draft_version_conflict_exception(
            draft_id=draft_id,
            client_version=expected_concurrency_version,
            server_version=server_version,
        )

    pdf_bytes, filename = await _read_bounded_pdf(file)
    try:
        validate_load_parser_pdf(pdf_bytes)
    except UnsafeLoadPdfError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    parse = await parse_load_workspace_document_orchestrated(
        pdf_bytes,
        filename=filename,
        tenant_id=tenant_id,
        db=db,
    )
    ctx = dict(parse.context or {})
    ctx["workspace_draft_id"] = str(draft_id)
    parse = parse.model_copy(update={"context": ctx})

    stored = await get_storage().save_bytes(
        tenant_slug,
        LOAD_WORKSPACE_DRAFT_PDF_MODULE,
        "workspace_draft",
        str(draft_id),
        pdf_bytes,
        filename_hint=filename,
        content_type="application/pdf",
    )

    previous_key = current.pdf_storage_key
    now = datetime.now(timezone.utc)
    accepted = accepted_parse_from_response(parse)

    stmt = (
        update(LoadWorkspaceDraft)
        .where(
            LoadWorkspaceDraft.tenant_id == tenant_id,
            LoadWorkspaceDraft.id == draft_id,
            LoadWorkspaceDraft.status == EDITABLE_STATUS,
            LoadWorkspaceDraft.concurrency_version == server_version,
        )
        .values(
            pdf_storage_key=stored.storage_key,
            pdf_sha256=stored.sha256,
            pdf_filename=stored.original_filename,
            pdf_size_bytes=stored.file_size_bytes,
            pdf_upload_state="ready",
            pdf_retention_class="workspace_ttl",
            accepted_parse_json=accepted,
            accepted_parse_schema_version=WORKSPACE_DRAFT_ACCEPTED_PARSE_SCHEMA_VERSION,
            accepted_parse_pdf_sha256=stored.sha256,
            concurrency_version=LoadWorkspaceDraft.concurrency_version + 1,
            updated_by_platform_user_id=updated_by_platform_user_id,
            updated_at=func.now(),
        )
        .returning(LoadWorkspaceDraft)
    )
    result = await db.execute(stmt)
    updated = result.scalar_one_or_none()
    if updated is None:
        await db.rollback()
        get_storage().delete(
            stored.storage_key,
            module=LOAD_WORKSPACE_DRAFT_PDF_MODULE,
            tenant_slug=tenant_slug,
        )
        raise workspace_draft_version_conflict_exception(
            draft_id=draft_id,
            client_version=expected_concurrency_version or server_version,
            server_version=server_version,
        )

    try:
        await db.commit()
        await db.refresh(updated)
    except Exception:
        await db.rollback()
        get_storage().delete(
            stored.storage_key,
            module=LOAD_WORKSPACE_DRAFT_PDF_MODULE,
            tenant_slug=tenant_slug,
        )
        raise

    if previous_key and previous_key != stored.storage_key:
        get_storage().delete(
            previous_key,
            module=LOAD_WORKSPACE_DRAFT_PDF_MODULE,
            tenant_slug=tenant_slug,
        )

    return updated, parse


async def get_workspace_draft_pdf_row(
    db: AsyncSession, tenant_id: int, draft_id: uuid.UUID
) -> LoadWorkspaceDraft:
    row = await db.scalar(
        select(LoadWorkspaceDraft).where(
            LoadWorkspaceDraft.tenant_id == tenant_id,
            LoadWorkspaceDraft.id == draft_id,
        )
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace draft not found")
    if row.pdf_upload_state != "ready" or not row.pdf_storage_key:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No rate confirmation PDF on this draft")
    return row
