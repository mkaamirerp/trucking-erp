"""Fuel / Fuel-Card API.

Segment 0A: provider catalog + tenant connections.
Segment 8: source review queue (not reconciliation / finalization).
Segment 9: deterministic reconciliation engine (not financial responsibility).
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.storage import PROJECT_ROOT
from app.deps.auth import CurrentUser
from app.deps.entitlements import require_entitlement
from app.deps.fuel_rbac import (
    FUEL_PROVIDERS_MANAGE,
    FUEL_PROVIDERS_SYNC,
    FUEL_PROVIDERS_TEST_CONNECTION,
    FUEL_PROVIDERS_VIEW,
    FUEL_RECONCILIATION_RUN,
    FUEL_RECONCILIATION_VIEW,
    FUEL_REVIEW_MANAGE,
    FUEL_REVIEW_VIEW,
    require_fuel_capability,
)
from app.deps.tenant import require_tenant
from app.deps.tenant_db import get_tenant_db
from app.schemas.fuel import (
    FuelAdapterActionOut,
    FuelProviderCatalogOut,
    FuelProviderConnectionOut,
    FuelProviderConnectionUpdate,
    FuelProviderConnectionWrite,
    FuelReconciliationOut,
    FuelReconciliationRunIn,
    FuelReviewConfirmIn,
    FuelReviewConfirmOut,
    FuelReviewProcessIn,
    FuelReviewProcessOut,
    FuelReviewQueueItemOut,
    FuelReviewStartIn,
    FuelReviewWorkspaceOut,
)
from app.services.fuel_provider_catalog import get_provider_catalog_entry, list_provider_catalog
from app.services import fuel_provider_connections as connections_service
from app.services import fuel_reconciliation as reconciliation_service
from app.services import fuel_review as review_service

router = APIRouter(
    prefix="/fuel",
    tags=["Fuel"],
    dependencies=[Depends(require_entitlement("admin_sensitive"))],
)


@router.get("/providers", response_model=list[FuelProviderCatalogOut])
async def list_fuel_providers(
    _user: CurrentUser = Depends(require_fuel_capability(FUEL_PROVIDERS_VIEW)),
    _tenant_id: int = Depends(require_tenant),
):
    return list_provider_catalog()


@router.get("/providers/{provider_code}", response_model=FuelProviderCatalogOut)
async def get_fuel_provider(
    provider_code: str,
    _user: CurrentUser = Depends(require_fuel_capability(FUEL_PROVIDERS_VIEW)),
    _tenant_id: int = Depends(require_tenant),
):
    entry = get_provider_catalog_entry(provider_code)
    if entry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown fuel provider")
    return entry


@router.get("/provider-connections", response_model=list[FuelProviderConnectionOut])
async def list_fuel_provider_connections(
    user: CurrentUser = Depends(require_fuel_capability(FUEL_PROVIDERS_VIEW)),
    tenant_id: int = Depends(require_tenant),
    db: AsyncSession = Depends(get_tenant_db),
):
    _ = user
    rows = await connections_service.list_connections(db, tenant_id=tenant_id)
    return [connections_service.connection_to_out(row) for row in rows]


@router.post(
    "/provider-connections",
    response_model=FuelProviderConnectionOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_fuel_provider_connection(
    payload: FuelProviderConnectionWrite,
    user: CurrentUser = Depends(require_fuel_capability(FUEL_PROVIDERS_MANAGE)),
    tenant_id: int = Depends(require_tenant),
    db: AsyncSession = Depends(get_tenant_db),
    platform_db: AsyncSession = Depends(get_db),
):
    row = await connections_service.create_connection(
        db, platform_db, tenant_id=tenant_id, payload=payload, actor=user
    )
    return connections_service.connection_to_out(row)


@router.get("/provider-connections/{connection_id}", response_model=FuelProviderConnectionOut)
async def get_fuel_provider_connection(
    connection_id: int,
    user: CurrentUser = Depends(require_fuel_capability(FUEL_PROVIDERS_VIEW)),
    tenant_id: int = Depends(require_tenant),
    db: AsyncSession = Depends(get_tenant_db),
):
    _ = user
    row = await connections_service.get_connection(db, tenant_id=tenant_id, connection_id=connection_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fuel provider connection not found")
    return connections_service.connection_to_out(row)


@router.put("/provider-connections/{connection_id}", response_model=FuelProviderConnectionOut)
async def update_fuel_provider_connection(
    connection_id: int,
    payload: FuelProviderConnectionUpdate,
    user: CurrentUser = Depends(require_fuel_capability(FUEL_PROVIDERS_MANAGE)),
    tenant_id: int = Depends(require_tenant),
    db: AsyncSession = Depends(get_tenant_db),
    platform_db: AsyncSession = Depends(get_db),
):
    row = await connections_service.get_connection(db, tenant_id=tenant_id, connection_id=connection_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fuel provider connection not found")
    row = await connections_service.update_connection(
        db, platform_db, tenant_id=tenant_id, row=row, payload=payload, actor=user
    )
    return connections_service.connection_to_out(row)


@router.post(
    "/provider-connections/{connection_id}/test",
    response_model=FuelAdapterActionOut,
)
async def test_fuel_provider_connection(
    connection_id: int,
    user: CurrentUser = Depends(require_fuel_capability(FUEL_PROVIDERS_TEST_CONNECTION)),
    tenant_id: int = Depends(require_tenant),
    db: AsyncSession = Depends(get_tenant_db),
):
    row = await connections_service.get_connection(db, tenant_id=tenant_id, connection_id=connection_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fuel provider connection not found")
    return await connections_service.run_test_connection(db, tenant_id=tenant_id, row=row, actor=user)


@router.post(
    "/provider-connections/{connection_id}/sync",
    response_model=FuelAdapterActionOut,
)
async def sync_fuel_provider_connection(
    connection_id: int,
    user: CurrentUser = Depends(require_fuel_capability(FUEL_PROVIDERS_SYNC)),
    tenant_id: int = Depends(require_tenant),
    db: AsyncSession = Depends(get_tenant_db),
):
    row = await connections_service.get_connection(db, tenant_id=tenant_id, connection_id=connection_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fuel provider connection not found")
    return await connections_service.run_sync(db, tenant_id=tenant_id, row=row, actor=user)


# --- Segment 8: source review ---


@router.get("/review/queue", response_model=list[FuelReviewQueueItemOut])
async def list_fuel_review_queue(
    user: CurrentUser = Depends(require_fuel_capability(FUEL_REVIEW_VIEW)),
    tenant_id: int = Depends(require_tenant),
    db: AsyncSession = Depends(get_tenant_db),
    status_filter: list[str] | None = Query(default=None, alias="status"),
):
    _ = user
    return await review_service.list_review_queue(db, tenant_id=tenant_id, statuses=status_filter)


@router.get("/review/batches/{batch_id}", response_model=FuelReviewWorkspaceOut)
async def get_fuel_review_workspace(
    batch_id: int,
    user: CurrentUser = Depends(require_fuel_capability(FUEL_REVIEW_VIEW)),
    tenant_id: int = Depends(require_tenant),
    db: AsyncSession = Depends(get_tenant_db),
):
    _ = user
    try:
        return await review_service.load_workspace(db, tenant_id=tenant_id, batch_id=batch_id)
    except Exception as exc:
        review_service.raise_http(exc)
        raise


@router.get("/review/batches/{batch_id}/document")
async def get_fuel_review_document(
    batch_id: int,
    user: CurrentUser = Depends(require_fuel_capability(FUEL_REVIEW_VIEW)),
    tenant_id: int = Depends(require_tenant),
    db: AsyncSession = Depends(get_tenant_db),
):
    """Stream original source document when resolvable locally. Never mutates it."""
    _ = user
    batch = await review_service.get_batch(db, tenant_id=tenant_id, batch_id=batch_id)
    if batch is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fuel source batch not found")
    ref = (batch.source_storage_ref or "").strip()
    if not ref:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No source document reference")
    path = Path(ref)
    if not path.is_absolute():
        path = (PROJECT_ROOT / ref).resolve()
    try:
        path.relative_to(PROJECT_ROOT.resolve())
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Source document path is not available",
        ) from exc
    if not path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source document file not found")
    media = "application/pdf" if path.suffix.lower() == ".pdf" else "application/octet-stream"
    return FileResponse(
        path,
        media_type=media,
        filename=batch.remote_filename or path.name,
        headers={"Content-Disposition": f'inline; filename="{batch.remote_filename or path.name}"'},
    )


@router.post("/review/batches/{batch_id}/start", response_model=FuelReviewQueueItemOut)
async def start_fuel_batch_review(
    batch_id: int,
    payload: FuelReviewStartIn,
    user: CurrentUser = Depends(require_fuel_capability(FUEL_REVIEW_MANAGE)),
    tenant_id: int = Depends(require_tenant),
    db: AsyncSession = Depends(get_tenant_db),
):
    batch = await review_service.get_batch(db, tenant_id=tenant_id, batch_id=batch_id)
    if batch is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fuel source batch not found")
    try:
        batch = await review_service.start_batch_review(
            db,
            tenant_id=tenant_id,
            batch=batch,
            actor=user,
            expected_version=payload.expected_version,
        )
        await db.commit()
        return await review_service.queue_item_for_batch(db, tenant_id=tenant_id, batch=batch)
    except Exception as exc:
        await db.rollback()
        review_service.raise_http(exc)
        raise


@router.post(
    "/review/batches/{batch_id}/rows/{entity_type}/{entity_id}/confirm",
    response_model=FuelReviewConfirmOut,
)
async def confirm_fuel_review_row(
    batch_id: int,
    entity_type: str,
    entity_id: int,
    payload: FuelReviewConfirmIn,
    user: CurrentUser = Depends(require_fuel_capability(FUEL_REVIEW_MANAGE)),
    tenant_id: int = Depends(require_tenant),
    db: AsyncSession = Depends(get_tenant_db),
):
    batch = await review_service.get_batch(db, tenant_id=tenant_id, batch_id=batch_id)
    if batch is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fuel source batch not found")
    try:
        out = await review_service.confirm_row(
            db,
            tenant_id=tenant_id,
            batch=batch,
            entity_type=entity_type.strip().upper(),
            entity_id=entity_id,
            actor=user,
            expected_version=payload.expected_version,
            corrections=[c.model_dump() for c in payload.corrections],
        )
        await db.commit()
        return out
    except Exception as exc:
        await db.rollback()
        review_service.raise_http(exc)
        raise


@router.post("/review/batches/{batch_id}/process", response_model=FuelReviewProcessOut)
async def process_fuel_batch_review(
    batch_id: int,
    payload: FuelReviewProcessIn,
    user: CurrentUser = Depends(require_fuel_capability(FUEL_REVIEW_MANAGE)),
    tenant_id: int = Depends(require_tenant),
    db: AsyncSession = Depends(get_tenant_db),
):
    batch = await review_service.get_batch(db, tenant_id=tenant_id, batch_id=batch_id)
    if batch is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fuel source batch not found")
    try:
        out = await review_service.process_batch(
            db,
            tenant_id=tenant_id,
            batch=batch,
            actor=user,
            expected_version=payload.expected_version,
        )
        await db.commit()
        return out
    except Exception as exc:
        await db.rollback()
        review_service.raise_http(exc)
        raise


@router.get(
    "/reconciliation/batches/{batch_id}",
    response_model=FuelReconciliationOut,
)
async def get_fuel_batch_reconciliation(
    batch_id: int,
    user: CurrentUser = Depends(require_fuel_capability(FUEL_RECONCILIATION_VIEW)),
    tenant_id: int = Depends(require_tenant),
    db: AsyncSession = Depends(get_tenant_db),
):
    """Return last reconciliation report from batch.problem_summary_json."""
    _ = user
    batch = await reconciliation_service.get_batch(db, tenant_id=tenant_id, batch_id=batch_id)
    if batch is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fuel source batch not found")
    summary = batch.problem_summary_json or {}
    report = summary.get("reconciliation")
    if not isinstance(report, dict):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No reconciliation report for this batch",
        )
    out = dict(report)
    out.setdefault("status", batch.status)
    out.setdefault("batch_id", batch.id)
    out.setdefault("tenant_id", tenant_id)
    out.setdefault("provider_code", batch.provider_code)
    out.setdefault("ai_authority", False)
    out.setdefault("finalization_implemented", False)
    out.setdefault("financial_responsibility_implemented", False)
    return out


@router.post(
    "/reconciliation/batches/{batch_id}/run",
    response_model=FuelReconciliationOut,
)
async def run_fuel_batch_reconciliation(
    batch_id: int,
    payload: FuelReconciliationRunIn | None = None,
    user: CurrentUser = Depends(require_fuel_capability(FUEL_RECONCILIATION_RUN)),
    tenant_id: int = Depends(require_tenant),
    db: AsyncSession = Depends(get_tenant_db),
):
    """Deterministic Segment 9 reconciliation. Does not finalize or post."""
    _ = payload
    batch = await reconciliation_service.get_batch(db, tenant_id=tenant_id, batch_id=batch_id)
    if batch is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fuel source batch not found")
    try:
        out = await reconciliation_service.reconcile_batch(
            db,
            tenant_id=tenant_id,
            batch=batch,
            actor=user,
        )
        await db.commit()
        return out
    except Exception as exc:
        await db.rollback()
        reconciliation_service.raise_http(exc)
        raise
