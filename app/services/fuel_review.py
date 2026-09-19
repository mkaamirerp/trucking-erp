"""Fuel Segment 8 — source review queue (not reconciliation / finalization).

Admin reviews extracted transactions + controls against the original source.
Corrections are append-only; provider_raw is never mutated. Process promotes
to READY_FOR_RECONCILIATION only — Segment 9 owns financial reconciliation.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping, Sequence

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.fuel import (
    FuelExtractionCorrection,
    FuelSourceBatch,
    FuelSourceControl,
    FuelTransaction,
)
from app.services.audit_events import write_audit_event
from app.services.fuel_money import FuelFloatForbidden
from app.services.fuel_canonical import (
    BATCH_REVIEW_QUEUE_STATUSES,
    BATCH_STATUS_BLOCKED,
    BATCH_STATUS_IN_REVIEW,
    BATCH_STATUS_PARSED,
    BATCH_STATUS_READY_FOR_RECONCILIATION,
    BATCH_STATUS_REVIEW_REQUIRED,
    ENTITY_CONTROL,
    ENTITY_TRANSACTION,
    ROW_REVIEW_CONFIRMED,
    ROW_REVIEW_PENDING,
    assert_not_float,
)

MODULE = "fuel"

# Source-extraction facts only — never truck/driver/payee/pricing/settlement.
TRANSACTION_EDITABLE_FIELDS: frozenset[str] = frozenset(
    {
        "transaction_datetime_source",
        "transaction_timezone_source",
        "transaction_timezone",
        "transaction_utc_offset",
        "transaction_date",
        "provider_event_type_raw",
        "provider_event_type",
        "provider_transaction_identity",
        "unit_number_snapshot",
        "card_or_account_id",
        "driver_name_snapshot",
        "merchant_site",
        "site_number",
        "site_name",
        "city",
        "province_state",
        "country",
        "product",
        "product_code_raw",
        "product_description_raw",
        "quantity",
        "quantity_unit",
        "unit_price",
        "unit_price_basis",
        "currency_raw",
        "currency",
        "processing_network",
        "merchant_network",
        "provider_discount_rate",
        "provider_discount_amount",
        "tax_amount",
        "hst_amount",
        "gst_amount",
        "pst_amount",
        "qst_amount",
        "missed_discount_amount",
        "out_of_network_fee",
        "pre_tax_amount",
        "billed_amount",
        "retail_amount",
        "total_amount",
        "account_reference",
        "requires_review",
        "review_reason",
        "row_role",  # reviewed_row_role only; does not move table rows
    }
)

CONTROL_EDITABLE_FIELDS: frozenset[str] = frozenset(
    {
        "provider_control_identity",
        "control_label_raw",
        "control_type_raw",
        "control_type",
        "control_scope_raw",
        "control_scope",
        "scope_card_or_account_id",
        "scope_unit_number_snapshot",
        "scope_product_raw",
        "invoice_number",
        "currency_raw",
        "currency",
        "quantity",
        "declared_amount",
        "tax_amount",
        "hst_amount",
        "gst_amount",
        "pst_amount",
        "qst_amount",
        "discount_amount",
        "pre_tax_amount",
        "account_reference",
        "requires_review",
        "review_reason",
        "row_role",
    }
)

FORBIDDEN_AUTHORITY_FIELDS: frozenset[str] = frozenset(
    {
        "truck_id",
        "driver_id",
        "owner_operator_payee_id",
        "classification",
        "financial_responsibility",
        "pricing_agreement_ref",
        "settlement_ref",
        "owner_operator_charge_amount",
        "oo_pricing_mode",
        "oo_pricing_rule_id",
        "oo_pricing_rule_version",
        "oo_charge_unit_price",
        "oo_benefit_per_unit",
        "oo_pricing_status",
        "oo_pricing_reason",
        "oo_pricing_inputs_json",
        "downstream_module",
        "downstream_ack_status",
        "downstream_ack_ref",
        "gate_status",
        "provider_raw",
        "tenant_id",
        "batch_id",
        "id",
        "source_vendor",
        "source_row_order",
        "source_row_id",
        "parsed_row_role",
    }
)

MONEY_FIELDS: frozenset[str] = frozenset(
    {
        "quantity",
        "unit_price",
        "provider_discount_rate",
        "provider_discount_amount",
        "tax_amount",
        "hst_amount",
        "gst_amount",
        "pst_amount",
        "qst_amount",
        "missed_discount_amount",
        "out_of_network_fee",
        "pre_tax_amount",
        "billed_amount",
        "retail_amount",
        "total_amount",
        "declared_amount",
        "discount_amount",
    }
)

DATE_FIELDS: frozenset[str] = frozenset({"transaction_date"})
BOOL_FIELDS: frozenset[str] = frozenset({"requires_review"})


class FuelReviewConflict(Exception):
    """Stale review_version / concurrent mutation."""

    def __init__(self, message: str = "Review state is stale; reload and retry.") -> None:
        super().__init__(message)
        self.message = message


class FuelReviewError(Exception):
    def __init__(self, code: str, message: str, *, http_status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _actor_id(actor: Any) -> str:
    uid = getattr(actor, "user_id", None)
    if uid is None:
        uid = getattr(actor, "member_id", None)
    return str(uid) if uid is not None else "unknown"


def serialize_review_value(value: Any) -> Any:
    """JSON-safe value preserving Decimal as string and null vs zero."""
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, float) and not isinstance(value, bool):
        raise FuelReviewError("FLOAT_FORBIDDEN", "Fuel review values must not use float")
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, date) and not isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, (int, str)):
        return value
    if isinstance(value, Mapping):
        return {str(k): serialize_review_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [serialize_review_value(v) for v in value]
    return str(value)


def deserialize_field_value(field: str, raw: Any) -> Any:
    if raw is None:
        return None
    try:
        assert_not_float(raw, field=field)
    except FuelFloatForbidden as exc:
        raise FuelReviewError("FLOAT_FORBIDDEN", str(exc)) from exc
    if field in BOOL_FIELDS:
        if isinstance(raw, bool):
            return raw
        if isinstance(raw, str) and raw.strip().lower() in {"true", "false"}:
            return raw.strip().lower() == "true"
        raise FuelReviewError("INVALID_BOOL", f"{field} must be a boolean")
    if field in DATE_FIELDS:
        if isinstance(raw, date) and not isinstance(raw, datetime):
            return raw
        if isinstance(raw, str):
            return date.fromisoformat(raw.strip()[:10])
        raise FuelReviewError("INVALID_DATE", f"{field} must be an ISO date string")
    if field in MONEY_FIELDS:
        if isinstance(raw, Decimal):
            return raw
        if isinstance(raw, int) and not isinstance(raw, bool):
            return Decimal(raw)
        if isinstance(raw, str):
            s = raw.strip()
            if s == "":
                return None
            try:
                return Decimal(s)
            except InvalidOperation as exc:
                raise FuelReviewError("INVALID_DECIMAL", f"{field} must be a decimal string") from exc
        raise FuelReviewError("INVALID_DECIMAL", f"{field} must be a decimal string")
    if field == "row_role":
        token = str(raw).strip().upper()
        if token not in {"TRANSACTION", "CONTROL", "UNKNOWN"}:
            raise FuelReviewError("INVALID_ROW_ROLE", "row_role must be TRANSACTION|CONTROL|UNKNOWN")
        return token
    return raw


def editable_fields_for(entity_type: str) -> frozenset[str]:
    if entity_type == ENTITY_TRANSACTION:
        return TRANSACTION_EDITABLE_FIELDS
    if entity_type == ENTITY_CONTROL:
        return CONTROL_EDITABLE_FIELDS
    raise FuelReviewError("INVALID_ENTITY_TYPE", f"Unknown entity_type: {entity_type}")


def assert_field_editable(entity_type: str, field: str) -> None:
    if field in FORBIDDEN_AUTHORITY_FIELDS or field == "provider_raw":
        raise FuelReviewError(
            "FORBIDDEN_AUTHORITY_FIELD",
            f"Field {field} cannot be changed in source review",
            http_status=403,
        )
    allowed = editable_fields_for(entity_type)
    if field not in allowed:
        raise FuelReviewError(
            "FIELD_NOT_EDITABLE",
            f"Field {field} is not editable in source review",
            http_status=400,
        )


async def get_batch(
    db: AsyncSession, *, tenant_id: int, batch_id: int
) -> FuelSourceBatch | None:
    result = await db.execute(
        select(FuelSourceBatch).where(
            FuelSourceBatch.tenant_id == tenant_id,
            FuelSourceBatch.id == batch_id,
        )
    )
    return result.scalar_one_or_none()


def _require_batch_version(batch: FuelSourceBatch, expected_version: int | None) -> None:
    if expected_version is None:
        return
    if int(batch.review_version) != int(expected_version):
        raise FuelReviewConflict(
            f"Stale review_version: expected {expected_version}, current {batch.review_version}"
        )


def bump_review_version(batch: FuelSourceBatch) -> None:
    batch.review_version = int(batch.review_version or 1) + 1


async def list_review_queue(
    db: AsyncSession,
    *,
    tenant_id: int,
    statuses: Sequence[str] | None = None,
) -> list[dict[str, Any]]:
    status_filter = list(statuses) if statuses else sorted(BATCH_REVIEW_QUEUE_STATUSES)
    result = await db.execute(
        select(FuelSourceBatch)
        .where(
            FuelSourceBatch.tenant_id == tenant_id,
            FuelSourceBatch.status.in_(status_filter),
        )
        .order_by(FuelSourceBatch.imported_at.desc(), FuelSourceBatch.id.desc())
    )
    batches = list(result.scalars().all())
    out: list[dict[str, Any]] = []
    for batch in batches:
        out.append(await queue_item_for_batch(db, tenant_id=tenant_id, batch=batch))
    return out


async def queue_item_for_batch(
    db: AsyncSession, *, tenant_id: int, batch: FuelSourceBatch
) -> dict[str, Any]:
    txn_count = await db.scalar(
        select(func.count())
        .select_from(FuelTransaction)
        .where(FuelTransaction.tenant_id == tenant_id, FuelTransaction.batch_id == batch.id)
    )
    ctrl_count = await db.scalar(
        select(func.count())
        .select_from(FuelSourceControl)
        .where(FuelSourceControl.tenant_id == tenant_id, FuelSourceControl.batch_id == batch.id)
    )
    pending_txn = await db.scalar(
        select(func.count())
        .select_from(FuelTransaction)
        .where(
            FuelTransaction.tenant_id == tenant_id,
            FuelTransaction.batch_id == batch.id,
            FuelTransaction.review_status == ROW_REVIEW_PENDING,
        )
    )
    pending_ctrl = await db.scalar(
        select(func.count())
        .select_from(FuelSourceControl)
        .where(
            FuelSourceControl.tenant_id == tenant_id,
            FuelSourceControl.batch_id == batch.id,
            FuelSourceControl.review_status == ROW_REVIEW_PENDING,
        )
    )
    problem_txn = await db.scalar(
        select(func.count())
        .select_from(FuelTransaction)
        .where(
            FuelTransaction.tenant_id == tenant_id,
            FuelTransaction.batch_id == batch.id,
            or_(
                FuelTransaction.requires_review.is_(True),
                FuelTransaction.review_reason.isnot(None),
            ),
        )
    )
    problem_ctrl = await db.scalar(
        select(func.count())
        .select_from(FuelSourceControl)
        .where(
            FuelSourceControl.tenant_id == tenant_id,
            FuelSourceControl.batch_id == batch.id,
            or_(
                FuelSourceControl.requires_review.is_(True),
                FuelSourceControl.review_reason.isnot(None),
            ),
        )
    )
    currencies = await _batch_currencies(db, tenant_id=tenant_id, batch_id=batch.id)
    pending = int(pending_txn or 0) + int(pending_ctrl or 0)
    problems = int(problem_txn or 0) + int(problem_ctrl or 0)
    layout_problems = _layout_problem_codes(batch)
    return {
        "batch_id": batch.id,
        "tenant_id": batch.tenant_id,
        "provider_code": batch.provider_code,
        "source_type": batch.source_type,
        "invoice_number": batch.invoice_number,
        "invoice_date": batch.invoice_date,
        "statement_start": batch.statement_start,
        "statement_end": batch.statement_end,
        "account_reference": batch.account_reference,
        "remote_filename": batch.remote_filename,
        "source_storage_ref": batch.source_storage_ref,
        "parser_rule_version": batch.parser_rule_version,
        "provider_profile_code": batch.provider_profile_code,
        "layout_status": batch.layout_status,
        "status": batch.status,
        "review_version": batch.review_version,
        "currencies": currencies,
        "transaction_count": int(txn_count or 0),
        "control_count": int(ctrl_count or 0),
        "pending_review_count": pending,
        "problem_count": problems + len(layout_problems),
        "layout_problems": layout_problems,
        "problem_summary": batch.problem_summary_json or {},
        "reviewed_by": batch.reviewed_by,
        "reviewed_at": batch.reviewed_at,
        "review_started_by": batch.review_started_by,
        "review_started_at": batch.review_started_at,
        "imported_at": batch.imported_at,
    }


async def _batch_currencies(db: AsyncSession, *, tenant_id: int, batch_id: int) -> list[str]:
    txn_ccy = await db.execute(
        select(FuelTransaction.currency)
        .where(
            FuelTransaction.tenant_id == tenant_id,
            FuelTransaction.batch_id == batch_id,
            FuelTransaction.currency.isnot(None),
        )
        .distinct()
    )
    ctrl_ccy = await db.execute(
        select(FuelSourceControl.currency)
        .where(
            FuelSourceControl.tenant_id == tenant_id,
            FuelSourceControl.batch_id == batch_id,
            FuelSourceControl.currency.isnot(None),
        )
        .distinct()
    )
    values = {str(r[0]) for r in txn_ccy.all() if r[0]} | {str(r[0]) for r in ctrl_ccy.all() if r[0]}
    return sorted(values)


def _layout_problem_codes(batch: FuelSourceBatch) -> list[str]:
    codes: list[str] = []
    layout = (batch.layout_status or "").strip().upper()
    if layout in {
        "PROVIDER_LAYOUT_UNRECOGNIZED",
        "PROVIDER_LAYOUT_AMBIGUOUS",
        "REVIEW",
    }:
        codes.append(layout)
    summary = batch.problem_summary_json or {}
    for key in ("layout_status", "reasons", "warnings"):
        val = summary.get(key)
        if isinstance(val, str) and val.strip():
            codes.append(val.strip())
        elif isinstance(val, list):
            codes.extend(str(x) for x in val if x)
    # de-dupe preserve order
    seen: set[str] = set()
    out: list[str] = []
    for c in codes:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out


async def start_batch_review(
    db: AsyncSession,
    *,
    tenant_id: int,
    batch: FuelSourceBatch,
    actor: Any,
    expected_version: int | None = None,
) -> FuelSourceBatch:
    if batch.tenant_id != tenant_id:
        raise FuelReviewError("TENANT_MISMATCH", "Batch not in tenant", http_status=404)
    _require_batch_version(batch, expected_version)
    if batch.status in {BATCH_STATUS_READY_FOR_RECONCILIATION, BATCH_STATUS_FINALIZED}:
        raise FuelReviewError(
            "BATCH_NOT_REVIEWABLE",
            f"Batch status {batch.status} is not open for review start",
        )
    now = _utcnow()
    if batch.status in {BATCH_STATUS_REVIEW_REQUIRED, BATCH_STATUS_PARSED, BATCH_STATUS_BLOCKED}:
        batch.status = BATCH_STATUS_IN_REVIEW
    if batch.review_started_at is None:
        batch.review_started_at = now
        batch.review_started_by = _actor_id(actor)
    batch.updated_by = _actor_id(actor)
    bump_review_version(batch)
    await write_audit_event(
        db,
        tenant_id=tenant_id,
        module=MODULE,
        entity_type="fuel_source_batch",
        entity_id=batch.id,
        action="fuel.review.started",
        source="ui",
        actor_type="user",
        actor_user_id=int(getattr(actor, "user_id", 0) or 0) or None,
        actor_label=getattr(actor, "email", None),
        context_json={
            "status": batch.status,
            "review_version": batch.review_version,
            "provider_code": batch.provider_code,
            "provider_profile_code": batch.provider_profile_code,
        },
        visibility="finance_sensitive",
    )
    await db.flush()
    return batch


async def load_workspace(
    db: AsyncSession, *, tenant_id: int, batch_id: int
) -> dict[str, Any]:
    batch = await get_batch(db, tenant_id=tenant_id, batch_id=batch_id)
    if batch is None:
        raise FuelReviewError("BATCH_NOT_FOUND", "Fuel source batch not found", http_status=404)
    txns = (
        await db.execute(
            select(FuelTransaction)
            .where(FuelTransaction.tenant_id == tenant_id, FuelTransaction.batch_id == batch_id)
            .order_by(FuelTransaction.source_row_order.asc(), FuelTransaction.id.asc())
        )
    ).scalars().all()
    ctrls = (
        await db.execute(
            select(FuelSourceControl)
            .where(FuelSourceControl.tenant_id == tenant_id, FuelSourceControl.batch_id == batch_id)
            .order_by(
                FuelSourceControl.source_row_order.asc().nulls_last(),
                FuelSourceControl.id.asc(),
            )
        )
    ).scalars().all()
    corrections = (
        await db.execute(
            select(FuelExtractionCorrection)
            .where(
                FuelExtractionCorrection.tenant_id == tenant_id,
                FuelExtractionCorrection.batch_id == batch_id,
            )
            .order_by(FuelExtractionCorrection.id.asc())
        )
    ).scalars().all()
    rows = [_row_view(ENTITY_TRANSACTION, t) for t in txns] + [
        _row_view(ENTITY_CONTROL, c) for c in ctrls
    ]
    rows.sort(key=lambda r: (r["source_row_order"] is None, r["source_row_order"] or 0, r["entity_type"], r["entity_id"]))
    pending = [r for r in rows if r["review_status"] == ROW_REVIEW_PENDING]
    current = pending[0] if pending else None
    return {
        "batch": await queue_item_for_batch(db, tenant_id=tenant_id, batch=batch),
        "rows": rows,
        "current_row": current,
        "progress": {
            "total_rows": len(rows),
            "confirmed_rows": sum(1 for r in rows if r["review_status"] == ROW_REVIEW_CONFIRMED),
            "pending_rows": len(pending),
        },
        "corrections": [_correction_out(c) for c in corrections],
        "document": {
            "source_storage_ref": batch.source_storage_ref,
            "remote_filename": batch.remote_filename,
            "source_type": batch.source_type,
            "immutable": True,
            "note": "Original provider document is immutable evidence; corrections do not rewrite it.",
        },
        "process_boundary": {
            "action": "READY_FOR_RECONCILIATION",
            "reconciliation_implemented": False,
            "finalization_implemented": False,
            "message": "Process marks the batch ready for Segment 9 reconciliation; it does not reconcile or post.",
        },
    }


def _row_view(entity_type: str, row: FuelTransaction | FuelSourceControl) -> dict[str, Any]:
    parsed_role = getattr(row, "parsed_row_role", None) or (
        "TRANSACTION" if entity_type == ENTITY_TRANSACTION else "CONTROL"
    )
    reviewed_role = getattr(row, "reviewed_row_role", None)
    effective_role = reviewed_role or parsed_role
    warnings: list[str] = []
    if getattr(row, "requires_review", False):
        warnings.append("REQUIRES_REVIEW")
    if getattr(row, "review_reason", None):
        warnings.append(str(row.review_reason))
    fields = _entity_fields(entity_type, row)
    return {
        "entity_type": entity_type,
        "entity_id": row.id,
        "source_row_order": getattr(row, "source_row_order", None),
        "review_status": row.review_status,
        "reviewed_by": row.reviewed_by,
        "reviewed_at": row.reviewed_at,
        "parsed_row_role": parsed_role,
        "reviewed_row_role": reviewed_role,
        "effective_row_role": effective_role,
        "requires_review": bool(getattr(row, "requires_review", False)),
        "review_reason": getattr(row, "review_reason", None),
        "warnings": warnings,
        "provider_raw": dict(getattr(row, "provider_raw", None) or {}),
        "fields": fields,
        "editable_fields": sorted(editable_fields_for(entity_type)),
    }


def _entity_fields(entity_type: str, row: Any) -> dict[str, Any]:
    allowed = editable_fields_for(entity_type) - {"row_role"}
    out: dict[str, Any] = {}
    for name in sorted(allowed):
        if hasattr(row, name):
            out[name] = serialize_review_value(getattr(row, name))
    out["row_role"] = serialize_review_value(
        getattr(row, "reviewed_row_role", None) or getattr(row, "parsed_row_role", None)
    )
    # Include a few display-only source keys
    for extra in ("source_vendor", "provider_event_type", "control_type", "control_scope"):
        if hasattr(row, extra) and extra not in out:
            out[extra] = serialize_review_value(getattr(row, extra))
    return out


def _correction_out(c: FuelExtractionCorrection) -> dict[str, Any]:
    return {
        "id": c.id,
        "batch_id": c.batch_id,
        "entity_type": c.entity_type,
        "entity_id": c.entity_id,
        "field_name": c.field_name,
        "parsed_value": c.parsed_value,
        "reviewed_value": c.reviewed_value,
        "reason": c.reason,
        "reviewed_by": c.reviewed_by,
        "reviewed_at": c.reviewed_at,
    }


async def _load_entity(
    db: AsyncSession,
    *,
    tenant_id: int,
    batch_id: int,
    entity_type: str,
    entity_id: int,
) -> FuelTransaction | FuelSourceControl:
    if entity_type == ENTITY_TRANSACTION:
        result = await db.execute(
            select(FuelTransaction).where(
                FuelTransaction.tenant_id == tenant_id,
                FuelTransaction.batch_id == batch_id,
                FuelTransaction.id == entity_id,
            )
        )
        row = result.scalar_one_or_none()
    elif entity_type == ENTITY_CONTROL:
        result = await db.execute(
            select(FuelSourceControl).where(
                FuelSourceControl.tenant_id == tenant_id,
                FuelSourceControl.batch_id == batch_id,
                FuelSourceControl.id == entity_id,
            )
        )
        row = result.scalar_one_or_none()
    else:
        raise FuelReviewError("INVALID_ENTITY_TYPE", f"Unknown entity_type: {entity_type}")
    if row is None:
        raise FuelReviewError("ENTITY_NOT_FOUND", "Review entity not found", http_status=404)
    return row


async def confirm_row(
    db: AsyncSession,
    *,
    tenant_id: int,
    batch: FuelSourceBatch,
    entity_type: str,
    entity_id: int,
    actor: Any,
    expected_version: int | None = None,
    corrections: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Save/Next: optionally apply corrections, mark row CONFIRMED, return next pending."""
    if batch.tenant_id != tenant_id:
        raise FuelReviewError("TENANT_MISMATCH", "Batch not in tenant", http_status=404)
    _require_batch_version(batch, expected_version)
    row = await _load_entity(
        db, tenant_id=tenant_id, batch_id=batch.id, entity_type=entity_type, entity_id=entity_id
    )
    actor_s = _actor_id(actor)
    now = _utcnow()
    applied: list[FuelExtractionCorrection] = []
    for item in corrections or []:
        field = str(item.get("field") or item.get("field_name") or "").strip()
        reason = str(item.get("reason") or "").strip()
        if not field:
            raise FuelReviewError("FIELD_REQUIRED", "Correction field is required")
        assert_field_editable(entity_type, field)
        if not reason:
            raise FuelReviewError("REASON_REQUIRED", "Correction reason is required when a value changes")
        new_raw = item.get("reviewed_value", item.get("value"))
        new_val = deserialize_field_value(field, new_raw)
        old_val = _read_field(row, field)
        if _values_equal(field, old_val, new_val):
            continue
        corr = FuelExtractionCorrection(
            tenant_id=tenant_id,
            batch_id=batch.id,
            entity_type=entity_type,
            entity_id=entity_id,
            field_name=field,
            parsed_value=serialize_review_value(old_val),
            reviewed_value=serialize_review_value(new_val),
            reason=reason,
            reviewed_by=actor_s,
            reviewed_at=now,
        )
        db.add(corr)
        applied.append(corr)
        _write_field(row, field, new_val)
        await write_audit_event(
            db,
            tenant_id=tenant_id,
            module=MODULE,
            entity_type=f"fuel_{entity_type.lower()}",
            entity_id=entity_id,
            action="fuel.review.field_corrected",
            source="ui",
            actor_type="user",
            actor_user_id=int(getattr(actor, "user_id", 0) or 0) or None,
            changed_fields={
                field: {
                    "before": serialize_review_value(old_val),
                    "after": serialize_review_value(new_val),
                }
            },
            reason_note=reason,
            context_json={"batch_id": batch.id, "entity_type": entity_type},
            visibility="finance_sensitive",
        )
        if field == "row_role":
            await write_audit_event(
                db,
                tenant_id=tenant_id,
                module=MODULE,
                entity_type=f"fuel_{entity_type.lower()}",
                entity_id=entity_id,
                action="fuel.review.row_role_corrected",
                source="ui",
                actor_type="user",
                actor_user_id=int(getattr(actor, "user_id", 0) or 0) or None,
                context_json={
                    "batch_id": batch.id,
                    "parsed_row_role": getattr(row, "parsed_row_role", None),
                    "reviewed_row_role": getattr(row, "reviewed_row_role", None),
                },
                reason_note=reason,
                visibility="finance_sensitive",
            )

    # provider_raw must remain untouched
    row.review_status = ROW_REVIEW_CONFIRMED
    row.reviewed_by = actor_s
    row.reviewed_at = now
    if batch.status in {BATCH_STATUS_REVIEW_REQUIRED, BATCH_STATUS_PARSED, BATCH_STATUS_BLOCKED}:
        batch.status = BATCH_STATUS_IN_REVIEW
    if batch.review_started_at is None:
        batch.review_started_at = now
        batch.review_started_by = actor_s
    batch.updated_by = actor_s
    bump_review_version(batch)

    await write_audit_event(
        db,
        tenant_id=tenant_id,
        module=MODULE,
        entity_type=f"fuel_{entity_type.lower()}",
        entity_id=entity_id,
        action="fuel.review.row_confirmed",
        source="ui",
        actor_type="user",
        actor_user_id=int(getattr(actor, "user_id", 0) or 0) or None,
        context_json={
            "batch_id": batch.id,
            "corrections_applied": len(applied),
            "review_version": batch.review_version,
        },
        visibility="finance_sensitive",
    )
    await db.flush()

    workspace = await load_workspace(db, tenant_id=tenant_id, batch_id=batch.id)
    return {
        "batch_id": batch.id,
        "review_version": batch.review_version,
        "confirmed": {
            "entity_type": entity_type,
            "entity_id": entity_id,
            "review_status": ROW_REVIEW_CONFIRMED,
            "corrections_applied": len(applied),
        },
        "next_row": workspace["current_row"],
        "progress": workspace["progress"],
        "batch_status": batch.status,
    }


def _read_field(row: Any, field: str) -> Any:
    if field == "row_role":
        return getattr(row, "reviewed_row_role", None) or getattr(row, "parsed_row_role", None)
    return getattr(row, field)


def _write_field(row: Any, field: str, value: Any) -> None:
    if field == "row_role":
        # Preserve original classification; only set reviewed override.
        if getattr(row, "parsed_row_role", None) is None:
            row.parsed_row_role = (
                "TRANSACTION" if isinstance(row, FuelTransaction) else "CONTROL"
            )
        row.reviewed_row_role = value
        return
    setattr(row, field, value)


def _values_equal(field: str, a: Any, b: Any) -> bool:
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    if field in MONEY_FIELDS:
        try:
            return Decimal(str(a)) == Decimal(str(b))
        except InvalidOperation:
            return False
    return a == b


async def process_batch(
    db: AsyncSession,
    *,
    tenant_id: int,
    batch: FuelSourceBatch,
    actor: Any,
    expected_version: int | None = None,
) -> dict[str, Any]:
    """Mark batch READY_FOR_RECONCILIATION when all rows are confirmed.

    Does NOT run Segment 9 reconciliation or finalization.
    """
    if batch.tenant_id != tenant_id:
        raise FuelReviewError("TENANT_MISMATCH", "Batch not in tenant", http_status=404)
    _require_batch_version(batch, expected_version)

    pending_txn = await db.scalar(
        select(func.count())
        .select_from(FuelTransaction)
        .where(
            FuelTransaction.tenant_id == tenant_id,
            FuelTransaction.batch_id == batch.id,
            FuelTransaction.review_status == ROW_REVIEW_PENDING,
        )
    )
    pending_ctrl = await db.scalar(
        select(func.count())
        .select_from(FuelSourceControl)
        .where(
            FuelSourceControl.tenant_id == tenant_id,
            FuelSourceControl.batch_id == batch.id,
            FuelSourceControl.review_status == ROW_REVIEW_PENDING,
        )
    )
    pending = int(pending_txn or 0) + int(pending_ctrl or 0)
    if pending > 0:
        raise FuelReviewError(
            "ROWS_UNRESOLVED",
            f"Cannot process: {pending} row(s) still pending source review",
            http_status=409,
        )

    now = _utcnow()
    batch.status = BATCH_STATUS_READY_FOR_RECONCILIATION
    batch.reviewed_by = _actor_id(actor)
    batch.reviewed_at = now
    batch.updated_by = _actor_id(actor)
    bump_review_version(batch)

    await write_audit_event(
        db,
        tenant_id=tenant_id,
        module=MODULE,
        entity_type="fuel_source_batch",
        entity_id=batch.id,
        action="fuel.review.ready_for_reconciliation",
        source="ui",
        actor_type="user",
        actor_user_id=int(getattr(actor, "user_id", 0) or 0) or None,
        context_json={
            "status": batch.status,
            "review_version": batch.review_version,
            "reviewed_by": batch.reviewed_by,
            "reconciliation_implemented": False,
        },
        visibility="finance_sensitive",
    )
    await db.flush()
    return {
        "batch_id": batch.id,
        "status": batch.status,
        "review_version": batch.review_version,
        "reviewed_by": batch.reviewed_by,
        "reviewed_at": batch.reviewed_at,
        "reconciliation_implemented": False,
        "finalization_implemented": False,
        "message": "Batch is READY_FOR_RECONCILIATION. Segment 9 reconciliation is not run here.",
    }


def raise_http(exc: Exception) -> None:
    if isinstance(exc, FuelReviewConflict):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "REVIEW_VERSION_CONFLICT", "detail": exc.message},
        ) from exc
    if isinstance(exc, FuelReviewError):
        raise HTTPException(
            status_code=exc.http_status,
            detail={"code": exc.code, "detail": exc.message},
        ) from exc
    raise exc
