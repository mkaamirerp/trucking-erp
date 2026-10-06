"""Toll WVPA PDF intake + review staging. No TollTransaction writes."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.storage import StoredFile
from app.deps.auth import get_current_user
from app.deps.entitlements import require_admin_sensitive_entitlement
from app.deps.tenant import require_tenant, require_tenant_slug
from app.deps.tenant_db import get_tenant_db
from app.models.base import Base
from app.models.toll import (
    FILE_FORMAT_PDF,
    PDF_PROFILE_EZPASS_WVPA_MONTHLY,
    REVIEW_STATUS_NEEDS_REVIEW,
    REVIEW_STATUS_RECONCILIATION_FAILED,
    SOURCE_TYPE_FILE,
    TollFileSourceRow,
    TollManualEntryStage,
    TollPdfReviewFieldCorrection,
    TollPdfReviewRow,
    TollPdfStatementReview,
    TollSourceBatch,
    TollTransaction,
)
from app.routers import tolls as tolls_router
from app.services.toll_csv_intake import persist_toll_csv_file
from app.services.toll_file_history import list_toll_file_batches
from app.services.toll_pdf_review import (
    get_toll_pdf_review,
    list_toll_pdf_reviews,
    persist_toll_pdf_file,
)
from app.services.toll_wvpa_pdf import (
    TollPdfIntakeError,
    parse_wvpa_monthly_statement_pdf,
    parse_wvpa_trip_charge,
)
from tests.support.toll_wvpa_fixture import (
    WVPA_ACCOUNT,
    WVPA_AGENCIES,
    WVPA_GROUP_A,
    WVPA_GROUP_B,
    WVPA_GROUP_ZERO,
    WVPA_PLATE_B,
    WVPA_SOURCE_TRIP_CHARGE,
    WVPA_SOURCE_TRIP_COUNT,
    build_non_wvpa_pdf,
    build_wvpa_monthly_statement_pdf,
)
from tests.test_toll_segment_1 import FORBIDDEN_TOLL_COLUMNS
from tests.test_toll_segment_2 import GENERIC_CSV, FakeTollSession, _fake_store

PROFILE = PDF_PROFILE_EZPASS_WVPA_MONTHLY


async def _persist_pdf(db: FakePdfSession | FakeTollSession, **kwargs: Any):
    kwargs.setdefault("profile_code", PROFILE)
    return await persist_toll_pdf_file(db, **kwargs)


def _eq_filters_qualified(stmt: Any) -> dict[str, Any]:
    out: dict[str, Any] = {}
    where = getattr(stmt, "whereclause", None)
    if where is None:
        return out
    clauses = list(getattr(where, "clauses", [where]))
    for clause in clauses:
        left = getattr(clause, "left", None)
        right = getattr(clause, "right", None)
        if left is None:
            continue
        name = getattr(left, "key", None)
        table = getattr(getattr(left, "table", None), "name", None)
        value = getattr(right, "value", right)
        if hasattr(value, "value"):
            value = value.value
        if name:
            out[name] = value
        if table and name:
            out[f"{table}.{name}"] = value
    return out


class FakePdfSession(FakeTollSession):
    def __init__(self) -> None:
        super().__init__()
        self.reviews: list[TollPdfStatementReview] = []
        self.review_rows: list[TollPdfReviewRow] = []
        self.corrections: list[TollPdfReviewFieldCorrection] = []
        self.stages: list[TollManualEntryStage] = []
        self.raise_on_commit = False
        self.fail_after_n_transactions: int | None = None
        self._committed_batches: list[TollSourceBatch] = []
        self._committed_rows: list[TollFileSourceRow] = []
        self._committed_reviews: list[TollPdfStatementReview] = []
        self._committed_review_rows: list[TollPdfReviewRow] = []
        self._committed_corrections: list[TollPdfReviewFieldCorrection] = []
        self._committed_stages: list[TollManualEntryStage] = []
        self._committed_transactions: list[TollTransaction] = []

    def _capture_committed(self) -> None:
        self._committed_batches = list(self.batches)
        self._committed_rows = list(self.rows)
        self._committed_reviews = list(self.reviews)
        self._committed_review_rows = list(self.review_rows)
        self._committed_corrections = list(self.corrections)
        self._committed_stages = list(self.stages)
        self._committed_transactions = list(self.transactions)

    def _restore_committed(self) -> None:
        self.batches = list(self._committed_batches)
        self.rows = list(self._committed_rows)
        self.reviews = list(self._committed_reviews)
        self.review_rows = list(self._committed_review_rows)
        self.corrections = list(self._committed_corrections)
        self.stages = list(self._committed_stages)
        self.transactions = list(self._committed_transactions)

    async def flush(self) -> None:
        if self.raise_on_flush:
            raise RuntimeError("flush failed")
        added_tx = 0
        for obj in self._pending:
            if getattr(obj, "id", None) is None:
                obj.id = self._next_id
                self._next_id += 1
            if isinstance(obj, TollSourceBatch):
                if obj not in self.batches:
                    self.batches.append(obj)
            elif isinstance(obj, TollFileSourceRow):
                if obj not in self.rows:
                    self.rows.append(obj)
            elif isinstance(obj, TollPdfStatementReview):
                if obj not in self.reviews:
                    self.reviews.append(obj)
            elif isinstance(obj, TollPdfReviewRow):
                if obj not in self.review_rows:
                    self.review_rows.append(obj)
            elif isinstance(obj, TollPdfReviewFieldCorrection):
                if obj not in self.corrections:
                    self.corrections.append(obj)
            elif isinstance(obj, TollManualEntryStage):
                if obj not in self.stages:
                    self.stages.append(obj)
            elif isinstance(obj, TollTransaction):
                if obj not in self.transactions:
                    self.transactions.append(obj)
                added_tx += 1
                if (
                    self.fail_after_n_transactions is not None
                    and added_tx >= self.fail_after_n_transactions
                ):
                    self._pending.clear()
                    raise RuntimeError("flush failed mid-write")
        self._pending.clear()

    async def commit(self) -> None:
        await self.flush()
        if self.raise_on_commit:
            raise RuntimeError("commit failed")
        self.committed = True
        self._capture_committed()
        if self.expire_ids_on_commit:
            for batch in self.batches:
                batch.id = None
            for row in self.rows:
                row.id = None

    async def rollback(self) -> None:
        self.rolled_back = True
        self._pending.clear()
        self._restore_committed()

    async def execute(self, stmt: Any):
        from tests.test_toll_segment_2 import FakeResult, _like_needles, _stmt_limit_offset

        self.execute_calls += 1
        filters = _eq_filters_qualified(stmt)
        tenant_id = filters.get("tenant_id")
        source_hash = filters.get("source_hash")
        batch_id = filters.get("batch_id") or filters.get("toll_source_batches.id")
        row_id = filters.get("toll_pdf_review_rows.id")
        object_id = filters.get("toll_source_batches.id") or (
            filters.get("id") if row_id is None else None
        )
        source_type = filters.get("source_type")
        file_format = filters.get("file_format")
        needles = _like_needles(stmt)
        limit, offset = _stmt_limit_offset(stmt)
        descs = list(getattr(stmt, "column_descriptions", []) or [])
        names = [d.get("name") for d in descs]
        entities = [d.get("entity") for d in descs]
        compiled = str(stmt).lower()
        if TollPdfReviewRow in entities and TollPdfStatementReview in entities and TollSourceBatch in entities:
            triples = []
            for batch in self.batches:
                if tenant_id is not None and batch.tenant_id != tenant_id:
                    continue
                if object_id is not None and batch.id != object_id:
                    continue
                if batch_id is not None and batch.id != batch_id and object_id is None:
                    continue
                review = next(
                    (item for item in self.reviews if item.batch_id == batch.id and item.tenant_id == batch.tenant_id),
                    None,
                )
                if review is None:
                    continue
                for row in self.review_rows:
                    if row.tenant_id != batch.tenant_id or row.batch_id != batch.id:
                        continue
                    if row_id is not None and row.id != row_id:
                        continue
                    triples.append((batch, review, row))
            return FakePairResult(triples)
        if "TollPdfReviewFieldCorrection" in names or any(
            getattr(entity, "__name__", "") == "TollPdfReviewFieldCorrection" for entity in entities
        ):
            items = [
                item
                for item in self.corrections
                if tenant_id is None or item.tenant_id == tenant_id
            ]
            items.sort(key=lambda item: int(item.id or 0))
            return FakeResult(items)
        if TollPdfReviewRow in entities or names == ["TollPdfReviewRow"]:
            rows = [
                row
                for row in self.review_rows
                if (tenant_id is None or row.tenant_id == tenant_id)
                and (batch_id is None or row.batch_id == batch_id)
                and (row_id is None or row.id == row_id)
            ]
            rows.sort(key=lambda row: row.source_row_order)
            start = offset or 0
            end = start + limit if limit is not None else None
            return FakeResult(rows[start:end])
        if TollPdfStatementReview in entities and TollSourceBatch in entities:
            pairs = []
            for batch in self.batches:
                if tenant_id is not None and batch.tenant_id != tenant_id:
                    continue
                if source_type is not None and batch.source_type != source_type:
                    continue
                if file_format is not None and batch.file_format != file_format:
                    continue
                if object_id is not None and batch.id != object_id:
                    continue
                if batch_id is not None and batch.id != batch_id and object_id is None:
                    continue
                review = next(
                    (item for item in self.reviews if item.batch_id == batch.id and item.tenant_id == batch.tenant_id),
                    None,
                )
                if review is None:
                    continue
                if needles:
                    blob = " ".join(
                        [
                            batch.source_filename or "",
                            batch.source_hash or "",
                            review.account_number or "",
                        ]
                    ).lower()
                    if not any(needle in blob for needle in needles):
                        continue
                pairs.append((batch, review))
            pairs.sort(key=lambda item: int(item[0].id or 0), reverse=True)
            if limit is not None:
                pairs = pairs[:limit]
            return FakePairResult(pairs)
        if TollManualEntryStage in entities or names == ["TollManualEntryStage"]:
            stage_id = filters.get("id") or filters.get("toll_manual_entry_stages.id")
            rows = [
                stage
                for stage in self.stages
                if (tenant_id is None or stage.tenant_id == tenant_id)
                and (stage_id is None or stage.id == stage_id)
            ]
            if stage_id is None:
                rows = [stage for stage in rows if stage.status != "DISCARDED"]
            rows.sort(key=lambda stage: int(stage.id or 0), reverse=True)
            if limit is not None:
                rows = rows[:limit]
            return FakeResult(rows)
        if "toll_transaction" in compiled:
            txs = [
                tx
                for tx in self.transactions
                if (tenant_id is None or tx.tenant_id == tenant_id)
                and (batch_id is None or tx.batch_id == batch_id)
                and (filters.get("manual_stage_id") is None or tx.manual_stage_id == filters.get("manual_stage_id"))
                and (filters.get("pdf_review_row_id") is None or tx.pdf_review_row_id == filters.get("pdf_review_row_id"))
            ]
            if "count(" in compiled:
                return FakeResult([len(txs)])
            if "sum(" in compiled:
                total = sum((tx.amount for tx in txs), Decimal("0"))
                return FakeResult([total])
            return FakeResult(txs)
        source_import_ref = filters.get("source_import_ref")
        batches = [
            batch
            for batch in self.batches
            if batch.id is not None
            and (tenant_id is None or batch.tenant_id == tenant_id)
            and (source_hash is None or batch.source_hash == source_hash)
            and (source_type is None or batch.source_type == source_type)
            and (file_format is None or batch.file_format == file_format)
            and (source_import_ref is None or batch.source_import_ref == source_import_ref)
        ]
        if names == ["id"]:
            return FakeResult([int(batch.id) for batch in batches])
        return FakeResult(batches)

    async def scalar(self, stmt: Any):
        compiled = str(stmt).lower()
        filters = _eq_filters_qualified(stmt)
        tenant_id = filters.get("tenant_id")
        batch_id = filters.get("batch_id")
        txs = [
            tx
            for tx in self.transactions
            if (tenant_id is None or tx.tenant_id == tenant_id)
            and (batch_id is None or tx.batch_id == batch_id)
            and (filters.get("manual_stage_id") is None or tx.manual_stage_id == filters.get("manual_stage_id"))
        ]
        if "count(" in compiled:
            return len(txs)
        if "sum(" in compiled:
            return sum((tx.amount for tx in txs), Decimal("0"))
        result = await self.execute(stmt)
        if hasattr(result, "first") and not hasattr(result, "scalars"):
            row = result.first()
            return row
        items = result.scalars().all()
        return items[0] if items else None


class FakePairResult:
    def __init__(self, pairs: list[tuple[Any, Any]]) -> None:
        self._pairs = pairs

    def all(self) -> list[tuple[Any, Any]]:
        return list(self._pairs)

    def first(self) -> tuple[Any, Any] | None:
        return self._pairs[0] if self._pairs else None

    def scalars(self):
        return self


async def _store(tenant_slug: str, intake_token: str, body: bytes, *, filename_hint: str) -> StoredFile:
    return StoredFile(
        storage_key=f"{tenant_slug}/toll/pdf/{intake_token}/{filename_hint}",
        original_filename=filename_hint,
        content_type="application/pdf",
        file_size_bytes=len(body),
        sha256="x",
    )


def test_wvpa_profile_parses_fixture_controls() -> None:
    parsed = parse_wvpa_monthly_statement_pdf(build_wvpa_monthly_statement_pdf())
    assert parsed.profile_code == PDF_PROFILE_EZPASS_WVPA_MONTHLY
    assert parsed.source_page_count == 7
    assert parsed.source_total_trip_count == WVPA_SOURCE_TRIP_COUNT
    assert parsed.source_total_trip_charge == WVPA_SOURCE_TRIP_CHARGE
    assert parsed.parsed_trip_count == 74
    assert parsed.parsed_total_trip_charge == Decimal("854.47")
    assert parsed.reconciliation_ok is True
    assert parsed.trip_count_matches is True
    assert parsed.trip_total_matches is True
    assert parsed.period_start == date(2023, 3, 1)
    assert parsed.period_end == date(2023, 3, 31)
    assert parsed.account_number == WVPA_ACCOUNT
    assert parsed.statement_date == date(2023, 4, 5)
    assert parsed.start_balance == Decimal("100.00")
    assert parsed.end_balance == Decimal("50.00")
    assert parsed.total_payment_amount == Decimal("200.00")
    assert parsed.total_payment_count == 1


def test_multiple_agencies_and_post_date_separate_from_event() -> None:
    parsed = parse_wvpa_monthly_statement_pdf(build_wvpa_monthly_statement_pdf())
    assert {row.agency_raw for row in parsed.rows} == set(WVPA_AGENCIES)
    first = parsed.rows[0]
    assert first.post_date == date(2023, 3, 1)
    assert first.entry_date == date(2023, 2, 13)
    assert first.exit_date == date(2023, 2, 13)
    assert first.post_date != first.entry_date


def test_transponder_grouping_plate_and_zero_group() -> None:
    parsed = parse_wvpa_monthly_statement_pdf(build_wvpa_monthly_statement_pdf())
    group_a = [row for row in parsed.rows if row.source_group_transponder == WVPA_GROUP_A]
    group_b = [row for row in parsed.rows if row.source_group_transponder == WVPA_GROUP_B]
    assert len(group_a) == 40
    assert len(group_b) == 34
    assert all(row.plate_number is None for row in group_a)
    assert all(row.plate_number == WVPA_PLATE_B for row in group_b)
    assert all(row.transponder_number == row.source_group_transponder for row in parsed.rows)
    assert parsed.source_metadata["zero_transaction_groups"] == [
        {"transponder": WVPA_GROUP_ZERO, "plate": None}
    ]
    assert not any(row.transponder_number == WVPA_GROUP_ZERO for row in parsed.rows)


def test_entry_exit_nullable_and_page_numbers() -> None:
    parsed = parse_wvpa_monthly_statement_pdf(build_wvpa_monthly_statement_pdf())
    singles = [row for row in parsed.rows if row.exit_date is None]
    assert singles
    assert all(row.exit_location is None and row.exit_time is None for row in singles)
    assert all(row.entry_location for row in singles)
    assert {row.source_page_number for row in parsed.rows} <= {1, 2, 3, 4, 5, 6, 7}
    assert min(row.source_page_number or 0 for row in parsed.rows) >= 1


def test_parentheses_are_positive_wvpa_charges() -> None:
    assert parse_wvpa_trip_charge("(7.35)") == Decimal("7.35")
    assert parse_wvpa_trip_charge("($7.35)") == Decimal("7.35")
    parsed = parse_wvpa_monthly_statement_pdf(build_wvpa_monthly_statement_pdf())
    assert all(row.trip_charge > 0 for row in parsed.rows)
    assert all(row.trip_charge_raw.startswith("(") for row in parsed.rows)
    assert "trip_charge_raw" in parsed.rows[0].provider_raw


def test_non_wvpa_pdf_fails_closed() -> None:
    with pytest.raises(TollPdfIntakeError) as err:
        parse_wvpa_monthly_statement_pdf(build_non_wvpa_pdf())
    assert err.value.code == "TOLL_PDF_PROFILE_MISMATCH"


def test_reconciliation_can_fail_without_forcing_totals() -> None:
    parsed = parse_wvpa_monthly_statement_pdf(build_wvpa_monthly_statement_pdf(reconciled=False))
    assert parsed.source_total_trip_count == 74
    assert parsed.parsed_trip_count == 73
    assert parsed.reconciliation_ok is False
    assert parsed.trip_count_matches is False


@pytest.mark.asyncio
async def test_persist_pdf_review_and_no_canonical_transactions() -> None:
    db = FakePdfSession()
    pdf = build_wvpa_monthly_statement_pdf()
    result = await _persist_pdf(
        db,
        tenant_id=7,
        tenant_slug="demo",
        filename="wvpa.pdf",
        body=pdf,
        store_bytes=_store,
    )
    assert db.committed is True
    assert result.batch_id == db.batches[0].id
    assert db.batches[0].source_type == SOURCE_TYPE_FILE
    assert db.batches[0].file_format == FILE_FORMAT_PDF
    assert db.batches[0].source_storage_ref.startswith("demo/toll/pdf/")
    assert db.reviews[0].profile_code == PDF_PROFILE_EZPASS_WVPA_MONTHLY
    assert db.reviews[0].review_status == REVIEW_STATUS_NEEDS_REVIEW
    assert db.reviews[0].reconciliation_ok is True
    assert db.reviews[0].parsed_trip_count == 74
    assert db.reviews[0].parsed_total_trip_charge == Decimal("854.47")
    assert len(db.review_rows) == 74
    assert db.transactions == []
    assert "source_storage_ref" not in result.as_api_dict()
    assert result.as_api_dict()["profile_code"] == PDF_PROFILE_EZPASS_WVPA_MONTHLY


@pytest.mark.asyncio
async def test_failed_reconciliation_keeps_review_problem_state() -> None:
    db = FakePdfSession()
    result = await _persist_pdf(
        db,
        tenant_id=1,
        tenant_slug="demo",
        filename="wvpa.pdf",
        body=build_wvpa_monthly_statement_pdf(reconciled=False),
        store_bytes=_store,
    )
    assert result.reconciliation_ok is False
    assert result.review_status == REVIEW_STATUS_RECONCILIATION_FAILED
    assert db.reviews[0].review_status == REVIEW_STATUS_RECONCILIATION_FAILED
    assert db.batches[0].source_storage_ref
    assert len(db.review_rows) == 73
    assert db.transactions == []


@pytest.mark.asyncio
async def test_duplicate_pdf_is_advisory_and_tenant_scoped() -> None:
    db = FakePdfSession()
    pdf = build_wvpa_monthly_statement_pdf()
    first = await _persist_pdf(
        db, tenant_id=53, tenant_slug="alpha", filename="a.pdf", body=pdf, store_bytes=_store
    )
    second = await _persist_pdf(
        db, tenant_id=53, tenant_slug="alpha", filename="b.pdf", body=pdf, store_bytes=_store
    )
    other = await _persist_pdf(
        db, tenant_id=54, tenant_slug="beta", filename="a.pdf", body=pdf, store_bytes=_store
    )
    assert first.duplicate_match_count == 0
    assert second.duplicate_match_count == 1
    assert second.duplicate_batch_ids == (first.batch_id,)
    assert other.duplicate_match_count == 0
    assert first.batch_id != second.batch_id
    assert db.batches[0].source_hash == db.batches[1].source_hash


@pytest.mark.asyncio
async def test_csv_history_excludes_pdf_batches() -> None:
    db = FakePdfSession()
    await _persist_pdf(
        db,
        tenant_id=9,
        tenant_slug="demo",
        filename="wvpa.pdf",
        body=build_wvpa_monthly_statement_pdf(),
        store_bytes=_store,
    )
    await persist_toll_csv_file(
        db,
        tenant_id=9,
        tenant_slug="demo",
        filename="tolls.csv",
        body=GENERIC_CSV,
        store_bytes=_fake_store,
    )
    csv_items = await list_toll_file_batches(db, tenant_id=9)
    pdf_items = await list_toll_pdf_reviews(db, tenant_id=9)
    assert [item["filename"] for item in csv_items] == ["tolls.csv"]
    assert [item["filename"] for item in pdf_items] == ["wvpa.pdf"]


@pytest.mark.asyncio
async def test_pdf_detail_is_paginated_and_hides_storage_ref() -> None:
    db = FakePdfSession()
    result = await _persist_pdf(
        db,
        tenant_id=3,
        tenant_slug="demo",
        filename="wvpa.pdf",
        body=build_wvpa_monthly_statement_pdf(),
        store_bytes=_store,
    )
    page = await get_toll_pdf_review(db, tenant_id=3, batch_id=result.batch_id, row_offset=10, row_limit=5)
    assert page["total_row_count"] == 74
    assert page["row_offset"] == 10
    assert page["row_limit"] == 5
    assert len(page["rows"]) == 5
    assert [row["source_row_order"] for row in page["rows"]] == [11, 12, 13, 14, 15]
    assert "source_storage_ref" not in page
    assert page["rows"][0]["provider_raw"]["line"]
    missing = None
    try:
        await get_toll_pdf_review(db, tenant_id=99, batch_id=result.batch_id)
    except Exception as exc:
        missing = exc
    assert missing is not None
    assert getattr(missing, "code", "") == "TOLL_PDF_NOT_FOUND"


def test_review_models_have_no_unit_or_payroll_columns() -> None:
    review_cols = set(TollPdfStatementReview.__table__.c.keys())
    row_cols = set(TollPdfReviewRow.__table__.c.keys())
    forbidden = FORBIDDEN_TOLL_COLUMNS | {
        "truck_id",
        "unit_id",
        "unit_number",
        "driver_id",
        "owner_operator_id",
    }
    assert forbidden & review_cols == set()
    assert forbidden & row_cols == set()
    assert "toll_pdf_statement_review" in Base.metadata.tables
    assert "toll_pdf_review_rows" in Base.metadata.tables


def test_pdf_routes_registered() -> None:
    paths = {getattr(route, "path", None) for route in tolls_router.router.routes}
    assert "/tolls/files/pdf" in paths
    assert "/tolls/pdf-reviews" in paths
    assert "/tolls/pdf-reviews/{batch_id}" in paths
    assert "/tolls/manual-entry/stages" in paths
    assert "/tolls/manual-entry/stages/{stage_id}" in paths
    assert "/tolls/manual-entry/stages/{stage_id}/validate" in paths
    assert "/tolls/manual-entry/stages/{stage_id}/discard" in paths


@pytest.mark.asyncio
async def test_pdf_profile_code_must_be_explicit() -> None:
    db = FakePdfSession()
    with pytest.raises(TollPdfIntakeError) as err:
        await persist_toll_pdf_file(
            db,
            tenant_id=1,
            tenant_slug="demo",
            filename="wvpa.pdf",
            body=build_wvpa_monthly_statement_pdf(),
            store_bytes=_store,
            profile_code="",
        )
    assert err.value.code == "TOLL_PDF_PROFILE_REQUIRED"
    assert db.batches == []
    assert db.transactions == []


@pytest.mark.asyncio
async def test_unsupported_pdf_profile_fails_closed() -> None:
    db = FakePdfSession()
    with pytest.raises(TollPdfIntakeError) as err:
        await persist_toll_pdf_file(
            db,
            tenant_id=1,
            tenant_slug="demo",
            filename="wvpa.pdf",
            body=build_wvpa_monthly_statement_pdf(),
            store_bytes=_store,
            profile_code="SUNPASS_MONTHLY_STATEMENT_PDF",
        )
    assert err.value.code == "TOLL_PDF_PROFILE_NOT_IMPLEMENTED"
    assert db.batches == []
    assert db.transactions == []


@pytest.mark.asyncio
async def test_matching_ezpass_wvpa_profile_succeeds() -> None:
    db = FakePdfSession()
    result = await _persist_pdf(
        db,
        tenant_id=1,
        tenant_slug="demo",
        filename="wvpa.pdf",
        body=build_wvpa_monthly_statement_pdf(),
        store_bytes=_store,
        profile_code=PROFILE,
    )
    assert result.profile_code == PROFILE
    assert result.status == "PARSED"
    assert result.review_status == REVIEW_STATUS_NEEDS_REVIEW
    assert db.transactions == []


@pytest.mark.asyncio
async def test_nonmatching_document_fails_profile_structure() -> None:
    db = FakePdfSession()
    with pytest.raises(TollPdfIntakeError) as err:
        await persist_toll_pdf_file(
            db,
            tenant_id=1,
            tenant_slug="demo",
            filename="other.pdf",
            body=build_non_wvpa_pdf(),
            store_bytes=_store,
            profile_code=PROFILE,
        )
    assert err.value.code == "TOLL_PDF_PROFILE_MISMATCH"
    assert db.batches == []
    assert db.transactions == []


def test_pdf_http_requires_explicit_profile_and_rejects_unsupported() -> None:
    db = FakePdfSession()

    async def _yield_db():
        yield db

    app = FastAPI()
    app.include_router(tolls_router.router, prefix="/api/v1")
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(user_id="u1")
    app.dependency_overrides[require_admin_sensitive_entitlement] = lambda: None
    app.dependency_overrides[require_tenant] = lambda: 1
    app.dependency_overrides[require_tenant_slug] = lambda: "demo"
    app.dependency_overrides[get_tenant_db] = _yield_db
    pdf = build_wvpa_monthly_statement_pdf()
    with patch("app.services.toll_pdf_review.save_toll_pdf_file_bytes", new=_store):
        client = TestClient(app)
        missing = client.post(
            "/api/v1/tolls/files/pdf",
            files={"file": ("wvpa.pdf", pdf, "application/pdf")},
        )
        assert missing.status_code == 400
        assert missing.json()["detail"]["code"] == "TOLL_PDF_PROFILE_REQUIRED"
        unsupported = client.post(
            "/api/v1/tolls/files/pdf",
            files={"file": ("wvpa.pdf", pdf, "application/pdf")},
            data={"profile_code": "PREPASS_API"},
        )
        assert unsupported.status_code == 400
        assert unsupported.json()["detail"]["code"] == "TOLL_PDF_PROFILE_NOT_IMPLEMENTED"
        mismatch = client.post(
            "/api/v1/tolls/files/pdf",
            files={"file": ("other.pdf", build_non_wvpa_pdf(), "application/pdf")},
            data={"profile_code": PROFILE},
        )
        assert mismatch.status_code == 400
        assert mismatch.json()["detail"]["code"] == "TOLL_PDF_PROFILE_MISMATCH"
    assert db.transactions == []


@pytest.mark.asyncio
async def test_pdf_http_upload_list_detail_and_tenant_isolation() -> None:
    db = FakePdfSession()

    async def _yield_db():
        yield db

    def _app(tenant_id: int, slug: str) -> FastAPI:
        app = FastAPI()
        app.include_router(tolls_router.router, prefix="/api/v1")
        app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(user_id="u1")
        app.dependency_overrides[require_admin_sensitive_entitlement] = lambda: None
        app.dependency_overrides[require_tenant] = lambda: tenant_id
        app.dependency_overrides[require_tenant_slug] = lambda: slug
        app.dependency_overrides[get_tenant_db] = _yield_db
        return app

    pdf = build_wvpa_monthly_statement_pdf()
    with patch("app.services.toll_pdf_review.save_toll_pdf_file_bytes", new=_store):
        client = TestClient(_app(53, "alpha"))
        created = client.post(
            "/api/v1/tolls/files/pdf",
            files={"file": ("wvpa.pdf", pdf, "application/pdf")},
            data={"profile_code": PROFILE},
        )
        assert created.status_code == 201, created.text
        body = created.json()
        assert body["source_type"] == "FILE"
        assert body["file_format"] == "PDF"
        assert body["profile_code"] == PDF_PROFILE_EZPASS_WVPA_MONTHLY
        assert body["parsed_trip_count"] == 74
        assert body["parsed_total_trip_charge"] == "854.47"
        assert body["reconciliation_ok"] is True
        assert "source_storage_ref" not in body
        batch_id = body["batch_id"]

        listed = client.get("/api/v1/tolls/pdf-reviews", params={"q": "wvpa"})
        assert listed.status_code == 200
        assert listed.json()[0]["batch_id"] == batch_id
        assert "source_storage_ref" not in listed.json()[0]

        detail = client.get(f"/api/v1/tolls/pdf-reviews/{batch_id}", params={"row_limit": 10})
        assert detail.status_code == 200
        payload = detail.json()
        assert payload["total_row_count"] == 74
        assert len(payload["rows"]) == 10
        assert payload["rows"][0]["agency_raw"] in WVPA_AGENCIES
        assert payload["rows"][0]["source_page_number"] >= 1
        assert "source_storage_ref" not in payload
        assert db.transactions == []

        other = TestClient(_app(54, "beta"))
        missing = other.get(f"/api/v1/tolls/pdf-reviews/{batch_id}")
        assert missing.status_code == 404
        empty = other.get("/api/v1/tolls/pdf-reviews")
        assert empty.json() == []
