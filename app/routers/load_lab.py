"""Load Lab — isolated PDF extraction testing (tenant API)."""

from __future__ import annotations

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.deps.admin import is_tenant_admin
from app.deps.auth import get_current_user, CurrentUser
from app.deps.tenant import require_tenant
from app.deps.tenant_db import get_tenant_db
from app.schemas.load_lab import (
    LoadLabOpenaiSmokeOut,
    LoadLabRunOut,
    LoadLabRunUploadResponse,
)
from app.models.extraction_field_learning import ORIGIN_LOAD_LAB_RUN
from app.schemas.extraction_field_learning import ExtractionFieldLearningEventOut, ExtractionFieldLearningWriteIn
from app.services import load_lab as load_lab_service
from app.services import load_lab_review as load_lab_review_service
from app.services import extraction_field_learning as extraction_field_learning_service
from app.services import load_lab_semantic

router = APIRouter(prefix="/load-lab", tags=["load-lab"])

_MAX_BYTES = 20 * 1024 * 1024


@router.post("/openai-smoke", response_model=LoadLabOpenaiSmokeOut)
async def openai_smoke(
    _tenant_id: int = Depends(require_tenant),
    user: CurrentUser = Depends(get_current_user),
):
    """Tenant-admin only: verify OpenAI API key reaches the API (GET /v1/models). No PDF parsing."""
    if not is_tenant_admin(user.role):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tenant admin required")
    key = (settings.openai_api_key or "").strip()
    if not key:
        return LoadLabOpenaiSmokeOut(ok=False, http_status=None, detail="OPENAI_API_KEY not configured")
    try:
        async with httpx.AsyncClient(timeout=45.0) as client:
            r = await client.get(
                "https://api.openai.com/v1/models",
                headers={"Authorization": f"Bearer {key}"},
            )
        if r.status_code != 200:
            return LoadLabOpenaiSmokeOut(
                ok=False,
                http_status=r.status_code,
                detail=(r.text or "")[:500] or f"HTTP {r.status_code}",
            )
        data = r.json()
        items = data.get("data") or []
        first = items[0].get("id") if items else None
        return LoadLabOpenaiSmokeOut(ok=True, http_status=r.status_code, sample_model_id=first)
    except httpx.TimeoutException:
        return LoadLabOpenaiSmokeOut(ok=False, http_status=None, detail="OpenAI request timed out")
    except Exception as exc:  # noqa: BLE001
        return LoadLabOpenaiSmokeOut(ok=False, http_status=None, detail=str(exc)[:500])


@router.post("/runs/upload", response_model=LoadLabRunUploadResponse)
async def upload_run(
    request: Request,
    file: UploadFile = File(...),
    force_rerun: bool = Form(False),
    tenant_id: int = Depends(require_tenant),
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    data = await file.read()
    if not data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Empty file")
    if len(data) > _MAX_BYTES:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="File too large")
    mime = (file.content_type or "application/pdf").split(";")[0].strip()[:128]
    run, reused = await load_lab_service.ingest_pdf_and_run_pipeline(
        db,
        tenant_id=tenant_id,
        platform_user_id=user.user_id,
        file_bytes=data,
        filename=file.filename or "upload.pdf",
        mime_type=mime,
        force_rerun=force_rerun,
    )
    return LoadLabRunUploadResponse(run=LoadLabRunOut.model_validate(run), reused_existing_run=reused)


@router.get("/runs", response_model=list[LoadLabRunOut])
async def list_runs(
    tenant_id: int = Depends(require_tenant),
    _user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
    limit: int = Query(30, ge=1, le=100),
):
    runs = await load_lab_service.list_runs(db, tenant_id, limit=limit)
    return [LoadLabRunOut.model_validate(r) for r in runs]


@router.delete("/runs", response_model=dict)
async def clear_runs(
    tenant_id: int = Depends(require_tenant),
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    """Tenant-admin only: delete all Load Lab runs for this tenant (and local stored PDFs)."""
    if not is_tenant_admin(user.role):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tenant admin required")
    deleted = await load_lab_service.clear_runs_for_tenant(db, tenant_id=tenant_id)
    return {"deleted": deleted}


@router.get("/runs/{run_id}", response_model=LoadLabRunOut)
async def get_run(
    run_id: int,
    tenant_id: int = Depends(require_tenant),
    _user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    run = await load_lab_service.get_run(db, tenant_id, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    return LoadLabRunOut.model_validate(run)


@router.post("/runs/{run_id}/semantic-extract", response_model=LoadLabRunOut)
async def semantic_extract(
    run_id: int,
    tenant_id: int = Depends(require_tenant),
    _user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
    force: bool = Query(False, description="Re-run OpenAI even if a successful candidate is already stored."),
    mode: str = Query(
        "guarded",
        description="Extraction mode: guarded (default), pure_ai (schema-only, no diagnostics hints, no post-AI repairs), ai_validate_only (diagnostics hints allowed, but no post-AI repairs).",
    ),
    response_contract: str = Query(
        "truckerjson",
        description=(
            "truckerjson: legacy full parse schema (default). "
            "critical_v1_1: dispatch-critical contract v1.1 (Pydantic schema + field instructions + guardrails)."
        ),
    ),
):
    """Run OpenAI structured extraction on normalized text for this run (Load Lab only; no load writes)."""
    run = await load_lab_semantic.semantic_extract_run(
        db,
        tenant_id=tenant_id,
        run_id=run_id,
        force=force,
        mode=mode,
        response_contract=response_contract,
    )
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    return LoadLabRunOut.model_validate(run)


@router.get("/runs/{run_id}/field-learning-events", response_model=list[ExtractionFieldLearningEventOut])
async def list_field_learning_events(
    run_id: int,
    tenant_id: int = Depends(require_tenant),
    _user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
    limit: int = Query(200, ge=1, le=500),
    response_contract: str | None = Query(
        None,
        description="Filter to one snapshot contract (e.g. truckerjson, critical_v1_1). Omit to return all runs (truckerjson and critical may both be present after re-semantic).",
    ),
    dedupe: bool = Query(
        False,
        description="Keep only the latest row per field_path (highest id) after the optional response_contract filter; requires response_contract.",
    ),
):
    """Field learning for this Load Lab run (`origin_type=load_lab_run`, `origin_id=run_id`)."""
    if dedupe and not (response_contract and str(response_contract).strip()):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="dedupe=true requires response_contract=... (e.g. truckerjson or critical_v1_1) so results are not mixed.",
        )
    run = await load_lab_service.get_run(db, tenant_id, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    evs = await extraction_field_learning_service.list_extraction_field_learning_by_origin(
        db,
        tenant_id=tenant_id,
        origin_type=ORIGIN_LOAD_LAB_RUN,
        origin_id=run_id,
        limit=limit,
        response_contract=response_contract.strip() if response_contract and str(response_contract).strip() else None,
        dedupe_latest_per_field_path=dedupe,
    )
    return [ExtractionFieldLearningEventOut.model_validate(e) for e in evs]


@router.post("/runs/{run_id}/field-learning-events", response_model=ExtractionFieldLearningEventOut)
async def create_field_learning_event(
    run_id: int,
    body: ExtractionFieldLearningWriteIn,
    tenant_id: int = Depends(require_tenant),
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    """Record an operator correction (shared tenant spine; `origin` = this Load Lab run)."""
    run = await load_lab_service.get_run(db, tenant_id, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    pr = run.parse_response if isinstance(run.parse_response, dict) else None
    c0 = (pr or {}).get("context")
    contract = (
        c0.get("load_lab_response_contract") if isinstance(c0, dict) and isinstance(c0.get("load_lab_response_contract"), str) else None
    )
    pv = extraction_field_learning_service.parser_version_for_load_lab_run(run)
    ev = await extraction_field_learning_service.record_extraction_field_learning_operator_event(
        db,
        tenant_id=tenant_id,
        origin_type=ORIGIN_LOAD_LAB_RUN,
        origin_id=run_id,
        platform_user_id=user.user_id,
        field_path=body.field_path,
        final_value_json=body.final_value_json,
        proposed_value_json=body.proposed_value_json,
        previous_value_json=body.previous_value_json,
        source_text=body.source_text,
        source_page=body.source_page,
        source_label=body.source_label,
        source_section=body.source_section,
        correction_type=body.correction_type,
        response_contract=contract,
        parser_version=pv,
    )
    await db.commit()
    await db.refresh(ev)
    return ExtractionFieldLearningEventOut.model_validate(ev)


@router.post("/runs/{run_id}/lab-review", response_model=LoadLabRunOut)
async def recompute_lab_review(
    run_id: int,
    tenant_id: int = Depends(require_tenant),
    _user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    """Recompute v3 confidence + contradiction flags from current candidate JSON (no OpenAI; lab only)."""
    run = await load_lab_review_service.recompute_lab_review_for_run(db, tenant_id=tenant_id, run_id=run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    return LoadLabRunOut.model_validate(run)
