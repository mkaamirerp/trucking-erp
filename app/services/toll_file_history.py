"""Toll FILE history/search (admin audit). Raw CSV rows only; no canonical mapping."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.toll import SOURCE_TYPE_FILE, TollFileSourceRow, TollSourceBatch
from app.services.toll_csv_intake import TollCsvIntakeError

FILE_HISTORY_LIMIT = 100


def batch_matches_search(batch: TollSourceBatch, q: str | None) -> bool:
    needle = (q or "").strip().lower()
    if not needle:
        return True
    filename = (batch.source_filename or "").lower()
    source_hash = (batch.source_hash or "").lower()
    return needle in filename or needle in source_hash


def headers_from_source_rows(rows: list[TollFileSourceRow]) -> list[str]:
    headers: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for key in row.cells.keys():
            if key not in seen:
                seen.add(key)
                headers.append(str(key))
    return headers


def _cell_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def source_row_to_dict(row: TollFileSourceRow) -> dict[str, Any]:
    cells = row.cells or {}
    values = row.values or []
    return {
        "source_row_order": row.source_row_order,
        "cells": {str(key): _cell_text(value) for key, value in cells.items()},
        "values": [_cell_text(value) for value in values],
    }


def batch_to_list_item(batch: TollSourceBatch, row_count: int) -> dict[str, Any]:
    imported = getattr(batch, "imported_at", None)
    return {
        "batch_id": int(batch.id) if batch.id is not None else 0,
        "source_type": batch.source_type,
        "file_format": batch.file_format,
        "filename": batch.source_filename,
        "source_hash": batch.source_hash,
        "source_storage_ref": batch.source_storage_ref,
        "status": batch.status,
        "row_count": row_count,
        "imported_at": imported.isoformat() if imported is not None else None,
    }


async def list_toll_file_batches(
    db: AsyncSession,
    *,
    tenant_id: int,
    q: str | None = None,
    limit: int = FILE_HISTORY_LIMIT,
) -> list[dict[str, Any]]:
    result = await db.execute(
        select(TollSourceBatch)
        .where(
            TollSourceBatch.tenant_id == tenant_id,
            TollSourceBatch.source_type == SOURCE_TYPE_FILE,
        )
        .order_by(TollSourceBatch.id.desc())
    )
    batches = [batch for batch in result.scalars().all() if batch_matches_search(batch, q)]
    batches.sort(key=lambda batch: int(batch.id or 0), reverse=True)
    batches = batches[: max(0, min(limit, FILE_HISTORY_LIMIT))]
    items: list[dict[str, Any]] = []
    for batch in batches:
        row_result = await db.execute(
            select(TollFileSourceRow).where(
                TollFileSourceRow.tenant_id == tenant_id,
                TollFileSourceRow.batch_id == batch.id,
            )
        )
        items.append(batch_to_list_item(batch, len(list(row_result.scalars().all()))))
    return items


async def get_toll_file_batch(
    db: AsyncSession,
    *,
    tenant_id: int,
    batch_id: int,
) -> dict[str, Any]:
    batch = await db.scalar(
        select(TollSourceBatch).where(
            TollSourceBatch.tenant_id == tenant_id,
            TollSourceBatch.id == batch_id,
            TollSourceBatch.source_type == SOURCE_TYPE_FILE,
        )
    )
    if batch is None:
        raise TollCsvIntakeError("TOLL_FILE_NOT_FOUND", "Toll FILE batch not found", http_status=404)
    row_result = await db.execute(
        select(TollFileSourceRow)
        .where(
            TollFileSourceRow.tenant_id == tenant_id,
            TollFileSourceRow.batch_id == batch_id,
        )
        .order_by(TollFileSourceRow.source_row_order)
    )
    rows = list(row_result.scalars().all())
    item = batch_to_list_item(batch, len(rows))
    item["headers"] = headers_from_source_rows(rows)
    item["rows"] = [source_row_to_dict(row) for row in rows]
    return item
