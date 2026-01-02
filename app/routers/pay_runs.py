from __future__ import annotations

from datetime import datetime, timezone, timedelta
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Optional
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy import and_, delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.dependencies.authz import require_tenant_admin
from app.deps.tenant import require_tenant
from app.deps.tenant_status import require_active_tenant
from app.models.driver import Driver
from app.models.payee import (
    ChargeCategory,
    PayDocument,
    Payee,
    PayeePayoutPreference,
    PayRunOverride,
)
from app.models.payroll import PayEntry, PayPeriod, PayRun, PayRunItem
from app.models.enums import SourceType, PayRunStatus, PayoutStatus, WorkerType, PayeeType
from app.core.storage import resolve_storage_path, DEFAULT_PAY_DOCS_DIR
from app.schemas.pay_documents import PayDocumentSummary
from app.schemas.pay_runs import (
    PayRunCreate,
    PayRunDetail,
    PayRunFinalizeResponse,
    PayRunGenerateResponse,
    PayRunItemOut,
    PayRunPayeeRow,
    PayRunSummary,
)

router = APIRouter(
    prefix="/api/v1/payroll",
    tags=["Payroll Runs"],
    dependencies=[Depends(require_active_tenant)],
)

logger = logging.getLogger(__name__)


def run_error(detail: str, code: str, status_code: int) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"detail": detail, "code": code})


def _to_json_amount(value: Decimal) -> float:
    return float(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _compute_totals(items: list[PayRunItem]) -> dict:
    totals = {
        "gross": Decimal("0.00"),
        "by_type": {},
        "count": len(items),
        "net": Decimal("0.00"),
    }
    for item in items:
        amt = (item.amount_signed or Decimal("0")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        totals["net"] += amt
        totals["by_type"][item.source_type] = totals["by_type"].get(item.source_type, Decimal("0.00")) + amt
    totals["gross"] = totals["by_type"].get(SourceType.EARNING.value, Decimal("0.00"))
    for k, v in totals["by_type"].items():
        totals["by_type"][k] = v.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    totals["net"] = totals["net"].quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return totals


async def _get_period(db: AsyncSession, tenant_id: int, period_id: int) -> PayPeriod:
    period = await db.scalar(select(PayPeriod).where(PayPeriod.id == period_id, PayPeriod.tenant_id == tenant_id))
    if not period:
        raise run_error("Pay period not found", "PAYRUN_PERIOD_NOT_FOUND", status.HTTP_404_NOT_FOUND)
    return period


async def _get_run(db: AsyncSession, tenant_id: int, run_id: int) -> PayRun:
    run = await db.scalar(select(PayRun).where(PayRun.id == run_id, PayRun.tenant_id == tenant_id))
    if not run:
        raise run_error("Pay run not found", "PAYRUN_NOT_FOUND", status.HTTP_404_NOT_FOUND)
    return run


@router.get("/pay-runs", response_model=list[PayRunSummary])
async def list_pay_runs(
    tenant_id: int = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
    pay_period_id: Optional[int] = Query(default=None),
    status_filter: Optional[str] = Query(default=None, alias="status"),
    document_type: Optional[str] = Query(default=None),
    payout_status: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    stmt = select(PayRun).where(PayRun.tenant_id == tenant_id)
    if pay_period_id is not None:
        stmt = stmt.where(PayRun.pay_period_id == pay_period_id)
    if status_filter:
        stmt = stmt.where(PayRun.status == status_filter.upper())
    if document_type:
        stmt = stmt.where(PayRun.pay_document_type == document_type)
    if payout_status:
        stmt = stmt.where(PayRun.payout_status == payout_status.upper())
    stmt = stmt.order_by(PayRun.id.desc()).limit(limit).offset(offset)
    res = await db.execute(stmt)
    return list(res.scalars().all())


@router.post(
    "/pay-runs",
    response_model=PayRunDetail,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_tenant_admin)],
)
async def create_pay_run(
    payload: PayRunCreate,
    tenant_id: int = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    period = await _get_period(db, tenant_id, payload.pay_period_id)
    pay_document_type = (payload.pay_document_type or "PAYSTUB").upper()
    worker_type_snapshot = (payload.worker_type_snapshot or "EMPLOYEE_DRIVER").upper()
    pay_date = payload.pay_date or (period.end_date + timedelta(days=1))
    base_currency = payload.base_currency_snapshot or "USD"
    existing = await db.scalar(
        select(PayRun).where(
            PayRun.tenant_id == tenant_id,
            PayRun.pay_period_id == payload.pay_period_id,
            PayRun.pay_document_type == pay_document_type,
            PayRun.worker_type_snapshot == worker_type_snapshot,
        )
    )
    if existing:
        return existing

    run = PayRun(
        tenant_id=tenant_id,
        pay_period_id=payload.pay_period_id,
        pay_document_type=pay_document_type,
        worker_type_snapshot=worker_type_snapshot,
        base_currency_snapshot=base_currency,
        pay_date=pay_date,
        status=PayRunStatus.DRAFT,
        payout_status=PayoutStatus.UNPAID,
    )
    db.add(run)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise run_error("Pay run already exists", "PAYRUN_DUPLICATE", status.HTTP_409_CONFLICT)
    await db.refresh(run)
    return run


@router.post(
    "/pay-runs/{run_id}/generate",
    response_model=PayRunGenerateResponse,
    dependencies=[Depends(require_tenant_admin)],
)
async def generate_pay_run(
    run_id: int,
    tenant_id: int = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    try:
        run = await db.scalar(select(PayRun).where(PayRun.id == run_id, PayRun.tenant_id == tenant_id).with_for_update())
        if not run:
            raise run_error("Pay run not found", "PAYRUN_NOT_FOUND", status.HTTP_404_NOT_FOUND)
        if run.status == PayRunStatus.FINALIZED:
            raise run_error("Cannot regenerate finalized pay run", "PAYRUN_FINALIZED", status.HTTP_409_CONFLICT)

        period = await db.scalar(select(PayPeriod).where(PayPeriod.id == run.pay_period_id, PayPeriod.tenant_id == tenant_id))
        if not period:
            raise run_error("Pay period not found", "PAYRUN_PERIOD_NOT_FOUND", status.HTTP_404_NOT_FOUND)
        if period.status != "CLOSED":
            raise run_error("Pay period must be closed before generation", "PAYRUN_PERIOD_OPEN", status.HTTP_409_CONFLICT)

        # clear existing items
        await db.execute(delete(PayRunItem).where(PayRunItem.pay_run_id == run.id))

        entries = await db.execute(
            select(PayEntry).where(
                PayEntry.tenant_id == tenant_id,
                PayEntry.pay_period_id == run.pay_period_id,
                PayEntry.is_active.is_(True),
                PayEntry.status != "VOID",
            )
        )
        entries_list = list(entries.scalars().all())

        driver_ids = {e.driver_id for e in entries_list}
        driver_map = {}
        if driver_ids:
            drivers_res = await db.execute(
                select(Driver).where(Driver.id.in_(driver_ids), Driver.tenant_id == tenant_id)
            )
            driver_objs = list(drivers_res.scalars().all())
            driver_map = {d.id: d for d in driver_objs}

        items = []
        for e in entries_list:
            driver = driver_map.get(e.driver_id)
            payee_id = driver.payee_id if driver else None
            if not payee_id:
                if not driver:
                    raise run_error(
                        f"Driver {e.driver_id} missing payee",
                        "PAYRUN_DRIVER_NOT_FOUND",
                        status.HTTP_404_NOT_FOUND,
                    )
                display_name = f"{driver.first_name} {driver.last_name}".strip() or f"Driver {driver.id}"
                payee = Payee(
                    tenant_id=tenant_id,
                    payee_type=PayeeType.DRIVER,
                    worker_type=WorkerType.EMPLOYEE_DRIVER,
                    display_name=display_name,
                    is_active=True,
                )
                db.add(payee)
                await db.flush()
                driver.payee_id = payee.id
                payee_id = payee.id
            amt = e.amount
            if amt is None:
                amt = (e.quantity or Decimal("0")) * (e.rate_amount or Decimal("0"))
            amt = (amt or Decimal("0")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            item = PayRunItem(
                tenant_id=tenant_id,
                pay_run_id=run.id,
                payee_id=payee_id,
                source_type=SourceType.EARNING.value,
                description=e.entry_type,
                quantity=e.quantity,
                unit_rate=e.rate_amount,
                amount_signed=amt,
                currency=run.base_currency_snapshot,
            )
            db.add(item)
            items.append(item)
        run.status = PayRunStatus.GENERATED
        await db.commit()
        return PayRunGenerateResponse(pay_run_id=run.id, item_count=len(items))
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("generate_pay_run_failed run_id=%s tenant_id=%s", run_id, tenant_id)
        raise run_error("Generate pay run failed", "PAYRUN_GENERATE_ERROR", status.HTTP_500_INTERNAL_SERVER_ERROR) from exc


@router.post(
    "/pay-runs/{run_id}/finalize",
    response_model=PayRunFinalizeResponse,
    dependencies=[Depends(require_tenant_admin)],
)
async def finalize_pay_run(
    run_id: int,
    tenant_id: int = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    try:
        run = await db.scalar(select(PayRun).where(PayRun.id == run_id, PayRun.tenant_id == tenant_id).with_for_update())
        if not run:
            raise run_error("Pay run not found", "PAYRUN_NOT_FOUND", status.HTTP_404_NOT_FOUND)
        if run.status == PayRunStatus.FINALIZED:
            raise run_error("Pay run already finalized", "PAYRUN_FINALIZED", status.HTTP_409_CONFLICT)

        period = await db.scalar(select(PayPeriod).where(PayPeriod.id == run.pay_period_id, PayPeriod.tenant_id == tenant_id))
        if not period:
            raise run_error("Pay period not found", "PAYRUN_PERIOD_NOT_FOUND", status.HTTP_404_NOT_FOUND)
        if period.status != "CLOSED":
            raise run_error("Pay period must be closed before finalize", "PAYRUN_PERIOD_OPEN", status.HTTP_409_CONFLICT)

        items_res = await db.execute(select(PayRunItem).where(PayRunItem.pay_run_id == run.id))
        items = list(items_res.scalars().all())
        if not items:
            raise run_error("No items to finalize", "PAYRUN_NO_ITEMS", status.HTTP_422_UNPROCESSABLE_ENTITY)

        totals = _compute_totals(items)
        run.status = PayRunStatus.FINALIZED
        run.finalized_at = datetime.now(timezone.utc)
        totals_snapshot = {
            "gross": _to_json_amount(totals["gross"]),
            "net": _to_json_amount(totals["net"]),
            "by_type": {k: _to_json_amount(v) for k, v in totals["by_type"].items()},
            "count": totals["count"],
        }
        run.calculation_snapshot_json = totals_snapshot

        await db.commit()
        return PayRunFinalizeResponse(pay_run_id=run.id, status=run.status, totals_snapshot=totals_snapshot)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("finalize_pay_run_failed run_id=%s tenant_id=%s", run_id, tenant_id)
        raise run_error("Finalize pay run failed", "PAYRUN_FINALIZE_ERROR", status.HTTP_500_INTERNAL_SERVER_ERROR) from exc


@router.get("/pay-runs/{run_id}", response_model=PayRunDetail)
async def get_pay_run(
    run_id: int,
    tenant_id: int = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    run = await _get_run(db, tenant_id, run_id)
    if run.calculation_snapshot_json is None:
        items_res = await db.execute(select(PayRunItem).where(PayRunItem.pay_run_id == run.id))
        items = list(items_res.scalars().all())
        totals = _compute_totals(items)
        run.calculation_snapshot_json = {
            "gross": _to_json_amount(totals["gross"]),
            "net": _to_json_amount(totals["net"]),
            "by_type": {k: _to_json_amount(v) for k, v in totals["by_type"].items()},
            "count": totals["count"],
        }
    return run


@router.get("/pay-runs/{run_id}/payees", response_model=list[PayRunPayeeRow])
async def list_pay_run_payees(
    run_id: int,
    tenant_id: int = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    await _get_run(db, tenant_id, run_id)

    overrides_exists = await db.scalar(
        select(func.count()).select_from(PayRunOverride).where(PayRunOverride.pay_run_id == run_id)
    )

    prefs_res = await db.execute(
        select(PayeePayoutPreference.payee_id).where(
            PayeePayoutPreference.tenant_id == tenant_id,
            PayeePayoutPreference.is_active.is_(True),
        )
    )
    pref_set = {row.payee_id for row in prefs_res}

    rows = await db.execute(
        select(
            PayRunItem.payee_id,
            Payee.display_name,
            func.sum(PayRunItem.amount_signed).label("net_amount"),
        )
        .join(Payee, Payee.id == PayRunItem.payee_id)
        .where(PayRunItem.pay_run_id == run_id, PayRunItem.tenant_id == tenant_id)
        .group_by(PayRunItem.payee_id, Payee.display_name)
    )
    results = []
    for payee_id, display_name, net_amount in rows.all():
        net = net_amount or Decimal("0")
        results.append(
            PayRunPayeeRow(
                payee_id=payee_id,
                display_name=display_name,
                net_amount=net,
                flags={
                    "negative_net": net < 0,
                    "has_overrides": bool(overrides_exists),
                    "missing_payout_preference": payee_id not in pref_set,
                },
            )
        )
    return results


@router.get("/pay-runs/{run_id}/items", response_model=list[PayRunItemOut])
async def list_pay_run_items(
    run_id: int,
    tenant_id: int = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
    payee_id: Optional[int] = Query(default=None),
):
    await _get_run(db, tenant_id, run_id)
    stmt = (
        select(PayRunItem, ChargeCategory.code)
        .select_from(PayRunItem)
        .join(ChargeCategory, ChargeCategory.id == PayRunItem.charge_category_id, isouter=True)
        .where(PayRunItem.pay_run_id == run_id, PayRunItem.tenant_id == tenant_id)
    )
    if payee_id:
        stmt = stmt.where(PayRunItem.payee_id == payee_id)
    res = await db.execute(stmt)
    items_out: list[PayRunItemOut] = []
    for item, code in res.all():
        items_out.append(
            PayRunItemOut(
                id=item.id,
                payee_id=item.payee_id,
                source_type=item.source_type,
                description=item.description,
                amount_signed=item.amount_signed,
                currency=item.currency,
                quantity=item.quantity,
                unit_rate=item.unit_rate,
                charge_category_id=item.charge_category_id,
                charge_category_code=code,
                metadata_json=item.metadata_json,
                created_at=item.created_at,
            )
        )
    return items_out


@router.get("/documents", response_model=list[PayDocumentSummary])
async def list_pay_documents(
    tenant_id: int = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
    pay_period_id: Optional[int] = Query(default=None),
    payee_id: Optional[int] = Query(default=None),
    document_type: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    stmt = (
        select(PayDocument)
        .join(PayRun, PayRun.id == PayDocument.pay_run_id)
        .where(PayRun.tenant_id == tenant_id)
    )
    if pay_period_id is not None:
        stmt = stmt.where(PayRun.pay_period_id == pay_period_id)
    if payee_id is not None:
        stmt = stmt.where(PayDocument.payee_id == payee_id)
    if document_type:
        stmt = stmt.where(PayDocument.document_type == document_type)
    stmt = stmt.order_by(PayDocument.generated_at.desc()).limit(limit).offset(offset)
    res = await db.execute(stmt)
    return list(res.scalars().all())


@router.get("/documents/{document_id}/download")
async def download_pay_document(
    document_id: int,
    tenant_id: int = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    doc = await db.scalar(
        select(PayDocument)
        .join(PayRun, PayRun.id == PayDocument.pay_run_id)
        .where(PayDocument.id == document_id, PayRun.tenant_id == tenant_id)
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    key = doc.file_storage_key
    if key.startswith("http://") or key.startswith("https://"):
        return RedirectResponse(key)

    path = resolve_storage_path(key, default_dir=DEFAULT_PAY_DOCS_DIR)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Document file not found")

    return FileResponse(path, media_type="application/pdf", filename=path.name)
