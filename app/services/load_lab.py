"""Load Lab — persist PDF extraction runs (tenant DB).

Locked pipeline direction (current implementation):
- Upload PDF → compute hash/metadata → extract text locally → readability gate
- Persist normalized package + warnings + versions + run state
- For digital + text-usable PDFs: automatically run semantic mapping (OpenAI) to persist `parse_response`
- No OCR execution (OCR is a future branch; status is marked `ocr_required`)
- No promote / operational load writes
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import delete
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.storage import resolve_storage_path
from app.models.load_lab import LoadLabExtractionRun
from app.services.load_document_parse import _extract_text_and_pages_from_pdf_bytes
from app.services import load_lab_semantic as load_lab_semantic_service
from app.services.load_lab_diagnostics import build_parse_diagnostics

# Version pins for reproducibility (bump when behavior changes).
PARSER_VERSION = "pdf_text_extract_pypdf_v1"
SCHEMA_VERSION = "normalized_package_v1"
PROMPT_VERSION = "n/a"
MODEL_NAME = "n/a"
NORMALIZER_VERSION = "normalized_package_v1"
OCR_ENGINE_VERSION: str | None = None

SOURCE_ROUTE_UPLOAD = "POST /api/v1/load-lab/runs/upload"

_MAX_RAW_TEXT_STORED = 350_000

# Reuse only “stable” runs for same bytes + same version pins.
REUSE_STATUSES = frozenset({"text_extracted", "ocr_required"})


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _truncate_raw_text(raw: str) -> tuple[str, bool]:
    # PostgreSQL text/jsonb cannot store NUL bytes (\u0000). Some PDFs yield them during extraction.
    # Strip them deterministically so uploads never 500 at persistence time.
    if "\x00" in raw:
        raw = raw.replace("\x00", "")
    if len(raw) <= _MAX_RAW_TEXT_STORED:
        return raw, False
    return raw[:_MAX_RAW_TEXT_STORED], True


def _build_normalized_package(
    *,
    filename: str,
    mime_type: str,
    file_size_bytes: int,
    extraction_method: str,
    raw_text: str,
    page_texts: list[str] | None,
    parse_warnings: list[str],
) -> dict[str, Any]:
    body, truncated = _truncate_raw_text(raw_text)
    pkg: dict[str, Any] = {
        "file_metadata": {"filename": filename, "mime_type": mime_type, "size_bytes": file_size_bytes},
        "extraction_method": extraction_method,
        "page_texts": [{"page": i + 1, "text": _truncate_raw_text((t or ""))[0]} for i, t in enumerate(page_texts or [])],
        "raw_full_text": body,
        "lines_blocks": [],
        "table_hints": [],
        "warnings": list(parse_warnings),
    }
    if truncated:
        pkg["warnings"] = list(pkg["warnings"]) + [
            f"raw_full_text truncated to {_MAX_RAW_TEXT_STORED} characters for storage",
        ]
    return pkg


def _lab_pdf_storage_key(*, tenant_id: int, file_sha256: str, filename: str) -> str:
    safe_name = "".join(c if c.isalnum() or c in ("-", "_", ".", " ") else "_" for c in (filename or "upload.pdf"))
    safe_name = safe_name.strip()[:160] or "upload.pdf"
    return f"load_lab_uploads/tenant_{tenant_id}/{file_sha256}/{safe_name}"


def _persist_uploaded_pdf_bytes(
    *,
    tenant_id: int,
    file_sha256: str,
    filename: str,
    file_bytes: bytes,
) -> str | None:
    """
    Persist uploaded bytes to local storage so runs can be re-processed later.

    Production policy: this host uses local storage volume mounted at /app/storage_persistent via settings.local_storage_dir.
    For non-local providers, we currently skip persistence (no list/delete semantics in this service).
    """
    if (settings.storage_provider or "local").lower() != "local":
        return None
    key = _lab_pdf_storage_key(tenant_id=tenant_id, file_sha256=file_sha256, filename=filename)
    dest = resolve_storage_path(key)
    Path(dest).parent.mkdir(parents=True, exist_ok=True)
    Path(dest).write_bytes(file_bytes)
    return key


async def _find_reusable_run(
    db: AsyncSession,
    tenant_id: int,
    file_sha256: str,
) -> LoadLabExtractionRun | None:
    stmt = (
        select(LoadLabExtractionRun)
        .where(
            LoadLabExtractionRun.tenant_id == tenant_id,
            LoadLabExtractionRun.file_sha256 == file_sha256,
            LoadLabExtractionRun.parser_version == PARSER_VERSION,
            LoadLabExtractionRun.schema_version == SCHEMA_VERSION,
            LoadLabExtractionRun.prompt_version == PROMPT_VERSION,
            LoadLabExtractionRun.normalizer_version == NORMALIZER_VERSION,
            LoadLabExtractionRun.model_name == MODEL_NAME,
            LoadLabExtractionRun.status.in_(REUSE_STATUSES),
        )
        .order_by(LoadLabExtractionRun.id.desc())
        .limit(1)
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def _find_latest_run_by_hash(
    db: AsyncSession,
    tenant_id: int,
    file_sha256: str,
) -> LoadLabExtractionRun | None:
    stmt = (
        select(LoadLabExtractionRun)
        .where(LoadLabExtractionRun.tenant_id == tenant_id, LoadLabExtractionRun.file_sha256 == file_sha256)
        .order_by(LoadLabExtractionRun.id.desc())
        .limit(1)
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def get_run(db: AsyncSession, tenant_id: int, run_id: int) -> LoadLabExtractionRun | None:
    stmt = select(LoadLabExtractionRun).where(
        LoadLabExtractionRun.tenant_id == tenant_id,
        LoadLabExtractionRun.id == run_id,
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def list_runs(db: AsyncSession, tenant_id: int, *, limit: int = 30) -> list[LoadLabExtractionRun]:
    stmt = (
        select(LoadLabExtractionRun)
        .where(LoadLabExtractionRun.tenant_id == tenant_id)
        .order_by(LoadLabExtractionRun.id.desc())
        .limit(min(max(limit, 1), 100))
    )
    return list((await db.execute(stmt)).scalars().all())


async def ingest_pdf_and_run_pipeline(
    db: AsyncSession,
    *,
    tenant_id: int,
    platform_user_id: str | None,
    file_bytes: bytes,
    filename: str,
    mime_type: str,
    force_rerun: bool,
) -> tuple[LoadLabExtractionRun, bool]:
    """Create or reuse a run and execute the locked digital pipeline (no OCR).

    Returns (run, reused). For digital PDFs, this persists a workspace-shaped `parse_response`
    via OpenAI semantic mapping when possible.
    """
    sha = hashlib.sha256(file_bytes).hexdigest()

    if not force_rerun:
        reused = await _find_reusable_run(db, tenant_id, sha)
        if reused is not None:
            return reused, True

    prior = await _find_latest_run_by_hash(db, tenant_id, sha)
    dedupe_id: int | None = prior.id if prior is not None else None

    run = LoadLabExtractionRun(
        tenant_id=tenant_id,
        source_route=SOURCE_ROUTE_UPLOAD,
        created_by_platform_user_id=platform_user_id,
        file_sha256=sha,
        filename=(filename or "upload.pdf")[:512],
        mime_type=(mime_type or "application/pdf")[:128],
        file_size_bytes=len(file_bytes),
        status="uploaded",
        parser_version=PARSER_VERSION,
        schema_version=SCHEMA_VERSION,
        prompt_version=PROMPT_VERSION,
        model_name=MODEL_NAME,
        ocr_engine_version=OCR_ENGINE_VERSION,
        normalizer_version=NORMALIZER_VERSION,
    )
    if dedupe_id is not None:
        run.dedupe_prior_run_id = dedupe_id
    db.add(run)
    await db.flush()

    run.status = "deduped"
    run.updated_at = _utcnow()

    if not file_bytes.startswith(b"%PDF-"):
        run.status = "failed"
        run.pipeline_error = "Expected a PDF file (magic bytes %PDF-)."
        run.warnings = []
        await db.commit()
        await db.refresh(run)
        return run, False

    # Persist raw PDF bytes (local storage only) for later evaluation/reprocessing.
    try:
        storage_key = _persist_uploaded_pdf_bytes(
            tenant_id=tenant_id,
            file_sha256=sha,
            filename=run.filename,
            file_bytes=file_bytes,
        )
        if storage_key and isinstance(run.normalized_package, dict):
            meta = run.normalized_package.get("file_metadata")
            if isinstance(meta, dict):
                meta["storage_key"] = storage_key
    except Exception:
        # Never fail the extraction pipeline if persistence fails; it is a convenience for eval/replay.
        pass

    raw_text, page_texts, warnings = _extract_text_and_pages_from_pdf_bytes(file_bytes)
    extraction_method = "pypdf_text_v1"
    run.normalized_package = _build_normalized_package(
        filename=run.filename,
        mime_type=run.mime_type,
        file_size_bytes=run.file_size_bytes,
        extraction_method=extraction_method,
        raw_text=raw_text,
        page_texts=page_texts,
        parse_warnings=warnings,
    )

    if not raw_text.strip():
        run.extraction_path = "ocr_required"
        run.status = "ocr_required"
        run.pipeline_error = "No extractable text; OCR is required (OCR not executed in v1)."
        run.warnings = warnings
        run.updated_at = _utcnow()
        await db.commit()
        await db.refresh(run)
        return run, False

    run.extraction_path = "digital"
    run.status = "text_extracted"
    run.updated_at = _utcnow()

    await db.commit()
    await db.refresh(run)

    # Locked: digital + text-usable PDFs should automatically produce candidate JSON
    # matching the workspace parse contract, so the frontend can hydrate the canonical form.
    #
    # NOTE: OCR branch is intentionally not executed here yet; those runs remain `ocr_required`.
    run2 = await load_lab_semantic_service.semantic_extract_run(
        db,
        tenant_id=tenant_id,
        run_id=run.id,
        force=force_rerun,
    )
    return (run2 or run), False


async def clear_runs_for_tenant(db: AsyncSession, *, tenant_id: int) -> int:
    """Delete all Load Lab runs for this tenant. Best-effort removes local stored PDFs too."""
    # Best-effort local file cleanup (only for our local storage layout).
    if (settings.storage_provider or "local").lower() == "local":
        try:
            base = resolve_storage_path(f"load_lab_uploads/tenant_{tenant_id}/.keep")
            tenant_dir = Path(base).parent
            if tenant_dir.is_dir():
                for p in tenant_dir.rglob("*"):
                    if p.is_file():
                        p.unlink()
                # Remove empty dirs bottom-up
                for p in sorted(tenant_dir.rglob("*"), reverse=True):
                    if p.is_dir():
                        try:
                            p.rmdir()
                        except OSError:
                            pass
        except Exception:
            pass

    res = await db.execute(delete(LoadLabExtractionRun).where(LoadLabExtractionRun.tenant_id == tenant_id))
    await db.commit()
    return int(getattr(res, "rowcount", 0) or 0)
