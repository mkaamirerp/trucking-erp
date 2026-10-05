"""Toll FILE history/search (admin audit). Raw CSV rows only; no canonical mapping."""

from __future__ import annotations

from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.toll import SOURCE_TYPE_FILE, TollFileSourceRow, TollSourceBatch

FILE_HISTORY_LIMIT = 100
FILE_DETAIL_DEFAULT_LIMIT = 100
FILE_DETAIL_MAX_LIMIT = 500


class TollFileHistoryError(Exception):
    def __init__(self, code: str, message: str, http_status: int = 404) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status


def _ilike_contains(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def ordered_column_keys(batch: TollSourceBatch) -> list[str]:
    """Authoritative CSV working headers. Never JSONB object-key order."""
    raw = getattr(batch, "csv_column_keys", None) or []
    return [str(key) for key in raw]


def ordered_raw_header_names(batch: TollSourceBatch) -> list[str]:
    raw = getattr(batch, "csv_raw_header_names", None) or []
    return [str(name) for name in raw]


def _cell_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def source_row_to_dict(row: TollFileSourceRow) -> dict[str, Any]:
    cells = row.cells or {}
    values = row.values or []
    return {
        "source_row_order": row.source_row_order,
        "source_line_number": getattr(row, "source_line_number", None),
        "cells": {str(key): _cell_text(value) for key, value in cells.items()},
        "values": [_cell_text(value) for value in values],
    }


def batch_to_list_item(batch: TollSourceBatch) -> dict[str, Any]:
    imported = getattr(batch, "imported_at", None)
    parsed_count = getattr(batch, "csv_parsed_row_count", None)
    return {
        "batch_id": int(batch.id) if batch.id is not None else 0,
        "source_type": batch.source_type,
        "file_format": batch.file_format,
        "filename": batch.source_filename,
        "source_hash": batch.source_hash,
        "status": batch.status,
        "row_count": int(parsed_count) if parsed_count is not None else 0,
        "imported_at": imported.isoformat() if imported is not None else None,
        "csv_column_keys": ordered_column_keys(batch),
        "csv_raw_header_names": ordered_raw_header_names(batch),
    }


def _clamp_detail_page(row_offset: int, row_limit: int) -> tuple[int, int]:
    offset = max(0, row_offset)
    if row_limit <= 0:
        limit = FILE_DETAIL_DEFAULT_LIMIT
    else:
        limit = min(row_limit, FILE_DETAIL_MAX_LIMIT)
    return offset, limit


async def list_toll_file_batches(
    db: AsyncSession,
    *,
    tenant_id: int,
    q: str | None = None,
    limit: int = FILE_HISTORY_LIMIT,
) -> list[dict[str, Any]]:
    capped = max(0, min(limit, FILE_HISTORY_LIMIT))
    stmt = (
        select(TollSourceBatch)
        .where(
            TollSourceBatch.tenant_id == tenant_id,
            TollSourceBatch.source_type == SOURCE_TYPE_FILE,
        )
        .order_by(TollSourceBatch.id.desc())
        .limit(capped)
    )
    needle = (q or "").strip()
    if needle:
        pattern = _ilike_contains(needle)
        stmt = stmt.where(
            or_(
                TollSourceBatch.source_filename.ilike(pattern, escape="\\"),
                TollSourceBatch.source_hash.ilike(pattern, escape="\\"),
            )
        )
    result = await db.execute(stmt)
    return [batch_to_list_item(batch) for batch in result.scalars().all()]


async def get_toll_file_batch(
    db: AsyncSession,
    *,
    tenant_id: int,
    batch_id: int,
    row_offset: int = 0,
    row_limit: int = FILE_DETAIL_DEFAULT_LIMIT,
) -> dict[str, Any]:
    batch = await db.scalar(
        select(TollSourceBatch).where(
            TollSourceBatch.tenant_id == tenant_id,
            TollSourceBatch.id == batch_id,
            TollSourceBatch.source_type == SOURCE_TYPE_FILE,
        )
    )
    if batch is None:
        raise TollFileHistoryError("TOLL_FILE_NOT_FOUND", "Toll FILE batch not found", http_status=404)
    offset, limit = _clamp_detail_page(row_offset, row_limit)
    row_result = await db.execute(
        select(TollFileSourceRow)
        .where(
            TollFileSourceRow.tenant_id == tenant_id,
            TollFileSourceRow.batch_id == batch_id,
        )
        .order_by(TollFileSourceRow.source_row_order)
        .offset(offset)
        .limit(limit)
    )
    rows = list(row_result.scalars().all())
    item = batch_to_list_item(batch)
    keys = item["csv_column_keys"]
    item["headers"] = keys
    item["total_row_count"] = item["row_count"]
    item["row_offset"] = offset
    item["row_limit"] = limit
    item["rows"] = [source_row_to_dict(row) for row in rows]
    return item
