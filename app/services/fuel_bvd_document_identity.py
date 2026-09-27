"""BVD provider document identity for list/history dedupe (not invoice-number-only)."""

from __future__ import annotations

import uuid
from typing import Any

from app.models.fuel import FuelBvd
from app.services.fuel_source_duplicate_gate import BVD_PROVIDER_CODE, BvdDocumentIdentity, _norm_text

# Same precedence as duplicate-gate legacy representative selection.
_STATUS_RANK: dict[str | None, int] = {
    "SOURCE_REVIEWED": 0,
    "IN_REVIEW": 1,
    "PENDING": 2,
    None: 3,
}


def document_identity_from_header(header: FuelBvd) -> BvdDocumentIdentity:
    return BvdDocumentIdentity(
        provider=BVD_PROVIDER_CODE,
        invoice_number=_norm_text(header.invoice_number),
        invoice_date=_norm_text(header.invoice_date),
        start_date=_norm_text(header.start_date),
        end_date=_norm_text(header.end_date),
    )


def bvd_document_identity_key(tenant_id: int, header: FuelBvd) -> str:
    """Canonical dedupe key: tenant + BVD + invoice_number + dates."""
    ident = document_identity_from_header(header)
    if not ident.invoice_number:
        return f"{tenant_id}:{BVD_PROVIDER_CODE}:import:{header.import_id}"
    return (
        f"{tenant_id}:{ident.provider}:{ident.invoice_number}:"
        f"{ident.invoice_date}:{ident.start_date}:{ident.end_date}"
    )


def _header_sort_key(row: FuelBvd) -> tuple[int, float, int]:
    status = row.review_status or "PENDING"
    rank = _STATUS_RANK.get(status, _STATUS_RANK.get("PENDING", 99))
    ts = row.uploaded_at.timestamp() if row.uploaded_at else 0.0
    return (rank, -ts, -int(row.id or 0))


def pick_canonical_bvd_header(candidates: list[FuelBvd]) -> FuelBvd:
    """Among legacy duplicates with the same document identity, pick one representative."""
    if not candidates:
        raise ValueError("candidates must not be empty")
    return sorted(candidates, key=_header_sort_key)[0]


def dedupe_bvd_headers_by_document_identity(
    tenant_id: int,
    headers: list[FuelBvd],
    *,
    limit: int,
) -> list[FuelBvd]:
    """Group by full document identity; keep canonical header per group; newest groups first."""
    groups: dict[str, list[FuelBvd]] = {}
    for row in headers:
        key = bvd_document_identity_key(tenant_id, row)
        groups.setdefault(key, []).append(row)

    canonical = [pick_canonical_bvd_header(group) for group in groups.values()]
    canonical.sort(key=lambda r: -(r.id or 0))
    return canonical[:limit]


def header_row_to_list_item(row: FuelBvd) -> dict[str, Any]:
    return {
        "import_id": str(row.import_id),
        "invoice_number": row.invoice_number or "—",
        "review_status": row.review_status or "PENDING",
        "uploaded_at": row.uploaded_at.isoformat() if row.uploaded_at else None,
        "source_file_name": row.source_file_name,
    }
