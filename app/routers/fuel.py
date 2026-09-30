"""Fuel / Fuel-Card API.

Segment 0A: provider catalog + tenant connections.
Segment 8: source review queue (not reconciliation / finalization).
Segment 9: deterministic reconciliation engine (not financial responsibility).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.storage import PROJECT_ROOT, serve_file
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
from app.deps.tenant import require_tenant, require_tenant_slug
from app.deps.tenant_db import get_tenant_db
from app.schemas.fuel import (
    FuelAdapterActionOut,
    FuelProviderCatalogOut,
    FuelProviderConnectionOut,
    FuelProviderConnectionUpdate,
    FuelProviderConnectionWrite,
    FuelBvdImportOut,
    FuelBvdImportListItemOut,
    FuelBvdCompletedBasicOut,
    FuelDashboardStatsOut,
    FuelBvdReviewSaveIn,
    FuelBvdReviewSummaryOut,
    FuelBvdRowOut,
    FuelBvdSourceReconciliationOut,
    FuelCanonicalTransactionOut,
    FuelChargeCategoryOut,
    FuelClassificationAuditEventOut,
    FuelClassificationSummaryOut,
    FuelReasonGroupClassificationIn,
    FuelTransactionClassificationIn,
    FuelUnresolvedReasonGroupOut,
    fuel_transaction_to_canonical_out,
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
from app.services import fuel_bvd_import as bvd_import_service
from app.services import fuel_bvd_review as bvd_review_service
from app.services import fuel_reconciliation as reconciliation_service
from app.services import fuel_review as review_service
from app.services import fuel_dashboard_stats as dashboard_stats_service
from app.services.fuel_bvd_import import FuelBvdImportError

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


# --- Fuel home dashboard (authoritative counts) ---


@router.get("/dashboard/stats", response_model=FuelDashboardStatsOut)
async def get_fuel_dashboard_stats(
    user: CurrentUser = Depends(require_fuel_capability(FUEL_REVIEW_VIEW)),
    tenant_id: int = Depends(require_tenant),
    db: AsyncSession = Depends(get_tenant_db),
):
    _ = user
    stats = await dashboard_stats_service.get_fuel_dashboard_stats(db, tenant_id=tenant_id)
    return FuelDashboardStatsOut(**stats)


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


# --- BVD Implementation 1 (extraction fidelity; not Segment 10) ---


@router.post("/bvd/imports", response_model=FuelBvdImportOut)
async def upload_bvd_import(
    file: UploadFile = File(...),
    user: CurrentUser = Depends(require_fuel_capability(FUEL_REVIEW_MANAGE)),
    tenant_id: int = Depends(require_tenant),
    tenant_slug: str = Depends(require_tenant_slug),
    db: AsyncSession = Depends(get_tenant_db),
):
    body = await file.read()
    filename = file.filename or "bvd.pdf"
    uploaded_by = str(user.user_id) if user.user_id is not None else user.email
    try:
        import_id, row_count, parse_status = await bvd_import_service.import_bvd_digital_pdf(
            db,
            tenant_id=tenant_id,
            tenant_slug=tenant_slug,
            pdf_bytes=body,
            filename=filename,
            uploaded_by=uploaded_by,
        )
    except FuelBvdImportError as exc:
        detail: dict[str, Any] = {"code": exc.code, "message": exc.message, **exc.detail}
        if "detail" not in detail and exc.message:
            detail["detail"] = exc.message
        raise HTTPException(status_code=exc.http_status, detail=detail) from exc
    return FuelBvdImportOut(
        import_id=str(import_id),
        row_count=row_count,
        parse_status=parse_status,
    )


@router.get("/bvd/imports", response_model=list[FuelBvdImportListItemOut])
async def list_bvd_imports(
    user: CurrentUser = Depends(require_fuel_capability(FUEL_REVIEW_VIEW)),
    tenant_id: int = Depends(require_tenant),
    db: AsyncSession = Depends(get_tenant_db),
    review_status: str | None = Query(None),
    exclude_review_status: str | None = Query(None),
):
    _ = user
    items = await bvd_import_service.list_bvd_import_headers(
        db,
        tenant_id=tenant_id,
        review_status=review_status,
        exclude_review_status=exclude_review_status,
    )
    return [FuelBvdImportListItemOut(**item) for item in items]


@router.get("/bvd/history", response_model=list[FuelBvdCompletedBasicOut])
async def list_bvd_completed_history(
    user: CurrentUser = Depends(require_fuel_capability(FUEL_REVIEW_VIEW)),
    tenant_id: int = Depends(require_tenant),
    db: AsyncSession = Depends(get_tenant_db),
):
    _ = user
    items = await bvd_import_service.list_bvd_completed_history(db, tenant_id=tenant_id)
    return [FuelBvdCompletedBasicOut(**item) for item in items]


@router.get("/bvd/imports/{import_id}/completed-basic", response_model=FuelBvdCompletedBasicOut)
async def get_bvd_completed_basic(
    import_id: UUID,
    user: CurrentUser = Depends(require_fuel_capability(FUEL_REVIEW_VIEW)),
    tenant_id: int = Depends(require_tenant),
    db: AsyncSession = Depends(get_tenant_db),
):
    _ = user
    try:
        payload = await bvd_import_service.get_bvd_completed_basic_projection(
            db, tenant_id=tenant_id, import_id=import_id
        )
    except bvd_import_service.FuelBvdImportNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="BVD import not found") from None
    return FuelBvdCompletedBasicOut(**payload)


@router.get("/bvd/imports/{import_id}/rows", response_model=list[FuelBvdRowOut])
async def list_bvd_import_rows(
    import_id: UUID,
    user: CurrentUser = Depends(require_fuel_capability(FUEL_REVIEW_VIEW)),
    tenant_id: int = Depends(require_tenant),
    db: AsyncSession = Depends(get_tenant_db),
):
    _ = user
    rows = await bvd_review_service.list_bvd_import_rows_for_review(
        db, tenant_id=tenant_id, import_id=import_id
    )
    if not rows:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="BVD import not found")
    return [FuelBvdRowOut(**r) for r in rows]


@router.get(
    "/bvd/imports/{import_id}/source-reconciliation",
    response_model=FuelBvdSourceReconciliationOut,
)
async def get_bvd_import_source_reconciliation(
    import_id: UUID,
    user: CurrentUser = Depends(require_fuel_capability(FUEL_REVIEW_VIEW)),
    tenant_id: int = Depends(require_tenant),
    db: AsyncSession = Depends(get_tenant_db),
):
    _ = user
    report = await bvd_review_service.get_bvd_source_reconciliation_report(
        db, tenant_id=tenant_id, import_id=import_id
    )
    return FuelBvdSourceReconciliationOut(**report)


@router.get("/bvd/imports/{import_id}/summary", response_model=FuelBvdReviewSummaryOut)
async def get_bvd_import_summary(
    import_id: UUID,
    user: CurrentUser = Depends(require_fuel_capability(FUEL_REVIEW_VIEW)),
    tenant_id: int = Depends(require_tenant),
    db: AsyncSession = Depends(get_tenant_db),
):
    summary = await bvd_review_service.get_bvd_import_review_summary(
        db, tenant_id=tenant_id, import_id=import_id
    )
    return FuelBvdReviewSummaryOut(**summary)


@router.post("/bvd/imports/{import_id}/save-review")
async def save_bvd_import_review(
    import_id: UUID,
    body: FuelBvdReviewSaveIn,
    user: CurrentUser = Depends(require_fuel_capability(FUEL_REVIEW_MANAGE)),
    tenant_id: int = Depends(require_tenant),
    db: AsyncSession = Depends(get_tenant_db),
):
    reviewed_by = str(user.user_id) if user.user_id is not None else user.email
    written = await bvd_review_service.save_bvd_import_review(
        db,
        tenant_id=tenant_id,
        import_id=import_id,
        reviewed_by=reviewed_by,
        corrections=[c.model_dump() for c in body.corrections],
    )
    return {"saved_corrections": written}


@router.post("/bvd/imports/{import_id}/process", response_model=FuelBvdReviewSummaryOut)
async def process_bvd_import_review(
    import_id: UUID,
    user: CurrentUser = Depends(require_fuel_capability(FUEL_REVIEW_MANAGE)),
    tenant_id: int = Depends(require_tenant),
    tenant_slug: str = Depends(require_tenant_slug),
    db: AsyncSession = Depends(get_tenant_db),
):
    reviewed_by = str(user.user_id) if user.user_id is not None else user.email
    try:
        summary = await bvd_review_service.process_bvd_import_review(
            db,
            tenant_id=tenant_id,
            import_id=import_id,
            reviewed_by=reviewed_by,
            tenant_slug=tenant_slug,
        )
    except FuelBvdImportError as exc:
        detail: dict[str, Any] = {"code": exc.code, "message": exc.message, **exc.detail}
        raise HTTPException(status_code=exc.http_status, detail=detail) from exc
    return FuelBvdReviewSummaryOut(**summary)


@router.post("/bvd/imports/{import_id}/discard")
async def discard_bvd_import_stage(
    import_id: UUID,
    user: CurrentUser = Depends(require_fuel_capability(FUEL_REVIEW_MANAGE)),
    tenant_id: int = Depends(require_tenant),
    tenant_slug: str = Depends(require_tenant_slug),
    db: AsyncSession = Depends(get_tenant_db),
):
    _ = user
    from app.services.fuel_bvd_stage import discard_bvd_import_stage

    discarded = await discard_bvd_import_stage(
        db,
        tenant_id=tenant_id,
        tenant_slug=tenant_slug,
        stage_id=import_id,
    )
    if not discarded:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="BVD stage not found")
    return {"discarded": True}


@router.get("/charge-categories", response_model=list[FuelChargeCategoryOut])
async def list_fuel_charge_categories(
    _user: CurrentUser = Depends(require_fuel_capability(FUEL_REVIEW_VIEW)),
    _tenant_id: int = Depends(require_tenant),
    db: AsyncSession = Depends(get_tenant_db),
):
    from app.models.fuel import FuelChargeCategory
    from app.services.fuel_charge_categories import CANONICAL_CATEGORY_CODES, CATEGORY_UNMAPPED
    from sqlalchemy import select

    rows = (
        await db.execute(
            select(FuelChargeCategory)
            .where(FuelChargeCategory.active.is_(True))
            .order_by(FuelChargeCategory.code.asc())
        )
    ).scalars().all()
    return [
        FuelChargeCategoryOut(
            code=r.code,
            display_name=r.display_name,
            description=r.description,
            active=r.active,
        )
        for r in rows
        if r.code in CANONICAL_CATEGORY_CODES and r.code != CATEGORY_UNMAPPED
    ]


@router.get(
    "/bvd/imports/{import_id}/canonical-transactions",
    response_model=list[FuelCanonicalTransactionOut],
)
async def list_bvd_import_canonical_transactions(
    import_id: UUID,
    _user: CurrentUser = Depends(require_fuel_capability(FUEL_REVIEW_VIEW)),
    tenant_id: int = Depends(require_tenant),
    db: AsyncSession = Depends(get_tenant_db),
):
    from app.services.fuel_classification_persistence import list_canonical_transactions_for_import

    txns = await list_canonical_transactions_for_import(
        db, tenant_id=tenant_id, import_id=str(import_id)
    )
    if not txns:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Canonical transactions not found for import",
        )
    return [fuel_transaction_to_canonical_out(t) for t in txns]


@router.post("/bvd/imports/{import_id}/classify-canonical")
async def classify_bvd_import_canonical_transactions(
    import_id: UUID,
    user: CurrentUser = Depends(require_fuel_capability(FUEL_REVIEW_MANAGE)),
    tenant_id: int = Depends(require_tenant),
    db: AsyncSession = Depends(get_tenant_db),
):
    from app.services.fuel_classification_persistence import (
        FuelClassificationError,
        backfill_classifications_for_import,
        raise_http_from_classification_error,
    )

    try:
        updated = await backfill_classifications_for_import(
            db, tenant_id=tenant_id, import_id=str(import_id)
        )
        await db.commit()
    except FuelClassificationError as exc:
        raise_http_from_classification_error(exc)
    return {"import_id": str(import_id), "transactions_reclassified": updated}


@router.patch(
    "/transactions/{transaction_id}/classification",
    response_model=FuelCanonicalTransactionOut,
)
async def set_fuel_transaction_classification(
    transaction_id: int,
    payload: FuelTransactionClassificationIn,
    user: CurrentUser = Depends(require_fuel_capability(FUEL_REVIEW_MANAGE)),
    tenant_id: int = Depends(require_tenant),
    db: AsyncSession = Depends(get_tenant_db),
):
    from app.services.fuel_classification_persistence import (
        FuelClassificationError,
        raise_http_from_classification_error,
        set_transaction_classification_manual,
    )

    actor = str(user.user_id) if user.user_id is not None else user.email
    try:
        txn = await set_transaction_classification_manual(
            db,
            tenant_id=tenant_id,
            transaction_id=transaction_id,
            canonical_category=payload.canonical_category,
            remember_mapping=payload.remember_mapping,
            apply_matching_in_import=payload.apply_matching_in_import,
            actor_user_id=actor,
        )
        await db.commit()
    except FuelClassificationError as exc:
        raise_http_from_classification_error(exc)
    return fuel_transaction_to_canonical_out(txn)


@router.get(
    "/bvd/imports/{import_id}/classification-summary",
    response_model=FuelClassificationSummaryOut,
)
async def get_bvd_import_classification_summary(
    import_id: UUID,
    _user: CurrentUser = Depends(require_fuel_capability(FUEL_REVIEW_VIEW)),
    tenant_id: int = Depends(require_tenant),
    db: AsyncSession = Depends(get_tenant_db),
):
    from app.services.fuel_classification_workflow import get_classification_summary_for_import
    from app.services.fuel_classification_persistence import (
        FuelClassificationError,
        raise_http_from_classification_error,
    )

    try:
        summary = await get_classification_summary_for_import(
            db, tenant_id=tenant_id, import_id=str(import_id)
        )
    except FuelClassificationError as exc:
        raise_http_from_classification_error(exc)
    return FuelClassificationSummaryOut(**summary)


@router.get(
    "/bvd/imports/{import_id}/classification-unresolved-groups",
    response_model=list[FuelUnresolvedReasonGroupOut],
)
async def list_bvd_import_unresolved_classification_groups(
    import_id: UUID,
    _user: CurrentUser = Depends(require_fuel_capability(FUEL_REVIEW_VIEW)),
    tenant_id: int = Depends(require_tenant),
    db: AsyncSession = Depends(get_tenant_db),
):
    from app.services.fuel_classification_workflow import get_unresolved_groups_for_import
    from app.services.fuel_classification_persistence import (
        FuelClassificationError,
        raise_http_from_classification_error,
    )

    try:
        groups = await get_unresolved_groups_for_import(
            db, tenant_id=tenant_id, import_id=str(import_id)
        )
    except FuelClassificationError as exc:
        raise_http_from_classification_error(exc)
    return [FuelUnresolvedReasonGroupOut(**g) for g in groups]


@router.post(
    "/bvd/imports/{import_id}/classification-reason-group",
    response_model=list[FuelCanonicalTransactionOut],
)
async def classify_bvd_import_reason_group(
    import_id: UUID,
    payload: FuelReasonGroupClassificationIn,
    user: CurrentUser = Depends(require_fuel_capability(FUEL_REVIEW_MANAGE)),
    tenant_id: int = Depends(require_tenant),
    db: AsyncSession = Depends(get_tenant_db),
):
    from app.services.fuel_classification_workflow import classify_reason_group_in_import
    from app.services.fuel_classification_persistence import (
        FuelClassificationError,
        raise_http_from_classification_error,
    )

    actor = str(user.user_id) if user.user_id is not None else user.email
    try:
        txns = await classify_reason_group_in_import(
            db,
            tenant_id=tenant_id,
            import_id=str(import_id),
            provider_section_raw=payload.provider_section_raw,
            provider_reason_raw=payload.provider_reason_raw,
            canonical_category=payload.canonical_category,
            remember_mapping=payload.remember_mapping,
            actor_user_id=actor,
        )
        await db.commit()
    except FuelClassificationError as exc:
        raise_http_from_classification_error(exc)
    return [fuel_transaction_to_canonical_out(t) for t in txns]


@router.get(
    "/bvd/imports/{import_id}/classification-audit",
    response_model=list[FuelClassificationAuditEventOut],
)
async def list_bvd_import_classification_audit(
    import_id: UUID,
    _user: CurrentUser = Depends(require_fuel_capability(FUEL_REVIEW_VIEW)),
    tenant_id: int = Depends(require_tenant),
    db: AsyncSession = Depends(get_tenant_db),
):
    from app.services.fuel_classification_workflow import list_classification_audit_for_import

    events = await list_classification_audit_for_import(
        db, tenant_id=tenant_id, import_id=str(import_id)
    )
    return [FuelClassificationAuditEventOut(**e) for e in events]


@router.get("/bvd/imports/{import_id}/document")
async def get_bvd_import_document(
    import_id: UUID,
    user: CurrentUser = Depends(require_fuel_capability(FUEL_REVIEW_VIEW)),
    tenant_id: int = Depends(require_tenant),
    tenant_slug: str = Depends(require_tenant_slug),
    db: AsyncSession = Depends(get_tenant_db),
):
    _ = user
    ref = await bvd_import_service.get_bvd_import_storage_ref(
        db, tenant_id=tenant_id, import_id=import_id
    )
    if ref is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="BVD import not found")
    storage_key, filename, storage_module = ref
    module = storage_module or bvd_import_service.FUEL_BVD_STORAGE_MODULE
    return serve_file(
        storage_key,
        module,
        tenant_slug=tenant_slug,
        filename=filename or "bvd.pdf",
        content_type="application/pdf",
    )
