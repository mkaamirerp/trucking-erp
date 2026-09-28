"""BVD list/history dedupe by full document identity."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from app.models.fuel import FuelBvd
from app.services.fuel_bvd_document_identity import (
    bvd_document_identity_key,
    dedupe_bvd_headers_by_document_identity,
    pick_canonical_bvd_header,
)


def _header(
    *,
    tenant_id: int = 53,
    import_id: uuid.UUID | None = None,
    invoice_number: str = "972201",
    invoice_date: str = "2026-07-29 00:00:00",
    start_date: str = "2026-07-22 00:00:00",
    end_date: str = "2026-07-28 23:59:59",
    review_status: str | None = "PENDING",
    uploaded_at: datetime | None = None,
    row_id: int = 1,
) -> FuelBvd:
    row = FuelBvd()
    row.id = row_id
    row.tenant_id = tenant_id
    row.import_id = import_id or uuid.uuid4()
    row.row_type = "HEADER"
    row.invoice_number = invoice_number
    row.invoice_date = invoice_date
    row.start_date = start_date
    row.end_date = end_date
    row.review_status = review_status
    row.uploaded_at = uploaded_at or datetime(2026, 7, 30, tzinfo=timezone.utc)
    return row


def test_a_same_full_identity_collapses_to_one_card() -> None:
    rows = [
        _header(row_id=10, review_status="IN_REVIEW", import_id=uuid.UUID(int=1)),
        _header(row_id=20, review_status="PENDING", import_id=uuid.UUID(int=2)),
    ]
    out = dedupe_bvd_headers_by_document_identity(53, rows, limit=10)
    assert len(out) == 1


def test_b_different_invoice_date_two_cards() -> None:
    a = _header(invoice_date="2026-07-29 00:00:00", row_id=1)
    b = _header(invoice_date="2027-07-29 00:00:00", row_id=2)
    out = dedupe_bvd_headers_by_document_identity(53, [a, b], limit=10)
    assert len(out) == 2


def test_c_different_period_two_cards() -> None:
    a = _header(start_date="2026-07-22 00:00:00", end_date="2026-07-28 23:59:59", row_id=1)
    b = _header(start_date="2027-07-22 00:00:00", end_date="2027-07-28 23:59:59", row_id=2)
    out = dedupe_bvd_headers_by_document_identity(53, [a, b], limit=10)
    assert len(out) == 2


def test_d_legacy_duplicates_pick_source_reviewed() -> None:
    pending = _header(row_id=1, review_status="PENDING", import_id=uuid.UUID(int=10))
    in_review = _header(row_id=2, review_status="IN_REVIEW", import_id=uuid.UUID(int=11))
    completed = _header(row_id=3, review_status="SOURCE_REVIEWED", import_id=uuid.UUID(int=12))
    best = pick_canonical_bvd_header([pending, in_review, completed])
    assert best.review_status == "SOURCE_REVIEWED"
    assert best.import_id == completed.import_id


def test_f_completed_identity_suppressed_on_open_list_after_dedupe() -> None:
    """Open review list excludes identity when canonical is SOURCE_REVIEWED (not stale IN_REVIEW)."""
    stale = _header(row_id=1, review_status="IN_REVIEW", import_id=uuid.UUID(int=10))
    done = _header(row_id=2, review_status="SOURCE_REVIEWED", import_id=uuid.UUID(int=11))
    chosen = dedupe_bvd_headers_by_document_identity(53, [stale, done], limit=10)
    assert len(chosen) == 1
    assert chosen[0].review_status == "SOURCE_REVIEWED"
    open_rows = [r for r in chosen if (r.review_status or "PENDING") != "SOURCE_REVIEWED"]
    assert open_rows == []


def test_e_tenant_isolation_on_identity_key() -> None:
    h53 = _header(tenant_id=53, row_id=1)
    h99 = _header(tenant_id=99, row_id=2)
    assert bvd_document_identity_key(53, h53) != bvd_document_identity_key(99, h99)
