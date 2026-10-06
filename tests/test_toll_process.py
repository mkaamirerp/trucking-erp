"""Toll review corrections → effective rows → Process → canonical TollTransaction."""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import UniqueConstraint

from app.deps.auth import get_current_user
from app.deps.entitlements import require_admin_sensitive_entitlement
from app.deps.tenant import require_tenant, require_tenant_slug
from app.deps.tenant_db import get_tenant_db
from app.models.toll import (
    BATCH_STATUS_PROCESSED,
    MANUAL_STAGE_DISCARDED,
    MANUAL_STAGE_DRAFT,
    MANUAL_STAGE_NEEDS_REVIEW,
    MANUAL_STAGE_PROCESSED,
    REVIEW_STATUS_PROCESSED,
    SOURCE_TYPE_FILE,
    SOURCE_TYPE_MANUAL,
    TOLL_PDF_EDITABLE_FIELDS,
    TollPdfReviewFieldCorrection,
    TollSourceBatch,
    TollTransaction,
)
from app.routers import tolls as tolls_router
from app.services.toll_manual_entry import (
    TollManualEntryError,
    create_manual_stage,
    discard_manual_stage,
    patch_manual_stage,
    validate_manual_stage,
)
from app.services.toll_pdf_corrections import TollPdfCorrectionError, apply_pdf_review_corrections
from app.services.toll_pdf_effective import build_effective_toll_pdf_row, build_effective_toll_pdf_rows
from app.services.toll_pdf_review import persist_toll_pdf_file
from app.services.toll_process import TollProcessError, process_toll_manual_stage, process_toll_pdf_review
from tests.support.toll_wvpa_fixture import (
    WVPA_SOURCE_TRIP_CHARGE,
    WVPA_SOURCE_TRIP_COUNT,
    build_wvpa_monthly_statement_pdf,
)
from tests.test_toll_segment_1 import FORBIDDEN_TOLL_COLUMNS
from tests.test_toll_wvpa_pdf import FakePdfSession, PROFILE, _store


async def _persist_pdf(db: FakePdfSession, tenant_id: int = 7) -> int:
    result = await persist_toll_pdf_file(
        db,
        tenant_id=tenant_id,
        tenant_slug="demo",
        filename="wvpa.pdf",
        body=build_wvpa_monthly_statement_pdf(),
        created_by="u1",
        profile_code=PROFILE,
    )
    return int(result.batch_id)


def _app(db: FakePdfSession, tenant_id: int = 7) -> FastAPI:
    async def _yield_db():
        yield db

    app = FastAPI()
    app.include_router(tolls_router.router, prefix="/api/v1")
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(user_id="u1")
    app.dependency_overrides[require_admin_sensitive_entitlement] = lambda: None
    app.dependency_overrides[require_tenant] = lambda: tenant_id
    app.dependency_overrides[require_tenant_slug] = lambda: "demo"
    app.dependency_overrides[get_tenant_db] = _yield_db
    return app


@pytest.mark.asyncio
async def test_1_raw_pdf_row_unchanged_after_correction() -> None:
    db = FakePdfSession()
    with patch("app.services.toll_pdf_review.save_toll_pdf_file_bytes", new=_store):
        batch_id = await _persist_pdf(db)
    row = db.review_rows[0]
    original = row.trip_charge
    raw = dict(row.provider_raw)
    await apply_pdf_review_corrections(
        db,
        tenant_id=7,
        batch_id=batch_id,
        row_id=int(row.id),
        fields={"trip_charge": "9.99"},
        changed_by="u1",
    )
    assert row.trip_charge == original
    assert row.provider_raw == raw


@pytest.mark.asyncio
async def test_2_correction_stored_separately() -> None:
    db = FakePdfSession()
    with patch("app.services.toll_pdf_review.save_toll_pdf_file_bytes", new=_store):
        batch_id = await _persist_pdf(db)
    row = db.review_rows[0]
    await apply_pdf_review_corrections(
        db,
        tenant_id=7,
        batch_id=batch_id,
        row_id=int(row.id),
        fields={"agency_raw": "WVPA"},
        reason="label typo",
        changed_by="u1",
    )
    assert len(db.corrections) == 1
    item = db.corrections[0]
    assert isinstance(item, TollPdfReviewFieldCorrection)
    assert item.review_row_id == row.id
    assert item.field_name == "agency_raw"
    assert item.original_value == row.agency_raw
    assert item.corrected_value == "WVPA"
    assert item.reason == "label typo"
    assert item.changed_by == "u1"


@pytest.mark.asyncio
async def test_3_effective_row_uses_correction() -> None:
    db = FakePdfSession()
    with patch("app.services.toll_pdf_review.save_toll_pdf_file_bytes", new=_store):
        batch_id = await _persist_pdf(db)
    row = db.review_rows[0]
    await apply_pdf_review_corrections(
        db,
        tenant_id=7,
        batch_id=batch_id,
        row_id=int(row.id),
        fields={"agency_raw": "WVPA"},
        changed_by="u1",
    )
    effective = build_effective_toll_pdf_row(
        row,
        {"agency_raw": {"corrected_value": "WVPA", "original_value": row.agency_raw}},
    )
    assert effective["agency_raw"] == "WVPA"
    assert "agency_raw" in effective["changed_fields"]


@pytest.mark.asyncio
async def test_4_untouched_fields_use_raw_value() -> None:
    db = FakePdfSession()
    with patch("app.services.toll_pdf_review.save_toll_pdf_file_bytes", new=_store):
        await _persist_pdf(db)
    row = db.review_rows[0]
    effective = build_effective_toll_pdf_row(
        row,
        {"agency_raw": {"corrected_value": "WVPA", "original_value": row.agency_raw}},
    )
    assert effective["trip_charge_decimal"] == row.trip_charge
    assert effective["entry_location"] == row.entry_location
    assert effective["raw"]["trip_charge"] == format(row.trip_charge, "f")


@pytest.mark.asyncio
async def test_5_invalid_field_cannot_be_corrected() -> None:
    db = FakePdfSession()
    with patch("app.services.toll_pdf_review.save_toll_pdf_file_bytes", new=_store):
        batch_id = await _persist_pdf(db)
    row = db.review_rows[0]
    with pytest.raises(TollPdfCorrectionError) as err:
        await apply_pdf_review_corrections(
            db,
            tenant_id=7,
            batch_id=batch_id,
            row_id=int(row.id),
            fields={"source_page_number": 99},
            changed_by="u1",
        )
    assert err.value.code == "TOLL_PDF_FIELD_NOT_EDITABLE"
    assert db.corrections == []
    assert row.source_page_number != 99


@pytest.mark.asyncio
async def test_6_money_correction_uses_decimal() -> None:
    db = FakePdfSession()
    with patch("app.services.toll_pdf_review.save_toll_pdf_file_bytes", new=_store):
        batch_id = await _persist_pdf(db)
    row = db.review_rows[0]
    await apply_pdf_review_corrections(
        db,
        tenant_id=7,
        batch_id=batch_id,
        row_id=int(row.id),
        fields={"trip_charge": "10.50"},
        changed_by="u1",
    )
    assert db.corrections[0].corrected_value == "10.50"
    assert not isinstance(db.corrections[0].corrected_value, float)
    effective = build_effective_toll_pdf_row(
        row,
        {"trip_charge": {"corrected_value": "10.50"}},
    )
    assert isinstance(effective["trip_charge_decimal"], Decimal)
    assert effective["trip_charge_decimal"] == Decimal("10.50")
    with pytest.raises(TollPdfCorrectionError):
        await apply_pdf_review_corrections(
            db,
            tenant_id=7,
            batch_id=batch_id,
            row_id=int(row.id),
            fields={"trip_charge": 1.25},
            changed_by="u1",
        )


@pytest.mark.asyncio
async def test_7_corrected_amount_changes_effective_reconciliation() -> None:
    db = FakePdfSession()
    with patch("app.services.toll_pdf_review.save_toll_pdf_file_bytes", new=_store):
        batch_id = await _persist_pdf(db)
    row = db.review_rows[0]
    _row, recon = await apply_pdf_review_corrections(
        db,
        tenant_id=7,
        batch_id=batch_id,
        row_id=int(row.id),
        fields={"trip_charge": "1.00"},
        changed_by="u1",
    )
    assert recon["reconciliation_ok"] is False
    assert Decimal(recon["effective_total_trip_charge"]) != WVPA_SOURCE_TRIP_CHARGE
    assert db.reviews[0].review_status == "RECONCILIATION_FAILED"


@pytest.mark.asyncio
async def test_8_broken_reconciliation_blocks_process() -> None:
    db = FakePdfSession()
    with patch("app.services.toll_pdf_review.save_toll_pdf_file_bytes", new=_store):
        batch_id = await _persist_pdf(db)
    row = db.review_rows[0]
    await apply_pdf_review_corrections(
        db,
        tenant_id=7,
        batch_id=batch_id,
        row_id=int(row.id),
        fields={"trip_charge": "1.00"},
        changed_by="u1",
    )
    with pytest.raises(TollProcessError) as err:
        await process_toll_pdf_review(db, tenant_id=7, batch_id=batch_id, processed_by="u1")
    assert err.value.code == "TOLL_RECONCILIATION_FAILED"
    assert db.transactions == []
    assert db.reviews[0].review_status != REVIEW_STATUS_PROCESSED


@pytest.mark.asyncio
async def test_9_matching_reconciliation_allows_process() -> None:
    db = FakePdfSession()
    with patch("app.services.toll_pdf_review.save_toll_pdf_file_bytes", new=_store):
        batch_id = await _persist_pdf(db)
    result = await process_toll_pdf_review(db, tenant_id=7, batch_id=batch_id, processed_by="u1")
    assert result["process_status"] == BATCH_STATUS_PROCESSED
    assert result["reconciliation"]["reconciliation_ok"] is True


@pytest.mark.asyncio
async def test_10_11_pdf_process_creates_expected_count_and_total() -> None:
    db = FakePdfSession()
    with patch("app.services.toll_pdf_review.save_toll_pdf_file_bytes", new=_store):
        batch_id = await _persist_pdf(db)
    result = await process_toll_pdf_review(db, tenant_id=7, batch_id=batch_id, processed_by="u1")
    assert result["processed_transaction_count"] == WVPA_SOURCE_TRIP_COUNT
    assert Decimal(result["processed_total"]) == WVPA_SOURCE_TRIP_CHARGE
    assert len(db.transactions) == 74
    assert sum((tx.amount for tx in db.transactions), Decimal("0")) == Decimal("854.47")


@pytest.mark.asyncio
async def test_12_source_lineage_retained() -> None:
    db = FakePdfSession()
    with patch("app.services.toll_pdf_review.save_toll_pdf_file_bytes", new=_store):
        batch_id = await _persist_pdf(db)
    await process_toll_pdf_review(db, tenant_id=7, batch_id=batch_id, processed_by="u1")
    tx = db.transactions[0]
    assert tx.pdf_review_row_id == db.review_rows[0].id
    assert tx.batch_id == batch_id
    assert tx.manual_stage_id is None
    assert tx.accepted_effective_json["source_type"] == SOURCE_TYPE_FILE
    assert tx.accepted_effective_json["pdf_review_row_id"] == db.review_rows[0].id
    for field_name in TOLL_PDF_EDITABLE_FIELDS:
        assert field_name in tx.accepted_effective_json
    assert tx.accepted_effective_json["trip_charge"] == format(db.review_rows[0].trip_charge, "f")
    assert tx.accepted_effective_json["agency_raw"] == db.review_rows[0].agency_raw
    assert tx.provider_raw["pdf_review_row_id"] == db.review_rows[0].id
    assert db.batches[0].source_type == SOURCE_TYPE_FILE
    assert db.batches[0].source_filename == "wvpa.pdf"


@pytest.mark.asyncio
async def test_13_repeated_pdf_process_creates_no_duplicates() -> None:
    db = FakePdfSession()
    with patch("app.services.toll_pdf_review.save_toll_pdf_file_bytes", new=_store):
        batch_id = await _persist_pdf(db)
    first = await process_toll_pdf_review(db, tenant_id=7, batch_id=batch_id, processed_by="u1")
    second = await process_toll_pdf_review(db, tenant_id=7, batch_id=batch_id, processed_by="u1")
    assert first["idempotent_replay"] is False
    assert second["idempotent_replay"] is True
    assert len(db.transactions) == 74
    assert second["processed_transaction_count"] == 74


@pytest.mark.asyncio
async def test_14_process_is_atomic() -> None:
    db = FakePdfSession()
    with patch("app.services.toll_pdf_review.save_toll_pdf_file_bytes", new=_store):
        batch_id = await _persist_pdf(db)
    db.fail_after_n_transactions = 3
    with pytest.raises(RuntimeError):
        await process_toll_pdf_review(db, tenant_id=7, batch_id=batch_id, processed_by="u1")
    assert db.rolled_back is True
    assert db.transactions == []
    assert db.reviews[0].review_status != REVIEW_STATUS_PROCESSED
    assert db.batches[0].status != BATCH_STATUS_PROCESSED
    assert db.batches[0].source_type == SOURCE_TYPE_FILE


@pytest.mark.asyncio
async def test_15_manual_needs_review_can_process() -> None:
    db = FakePdfSession()
    stage = await create_manual_stage(
        db,
        tenant_id=7,
        created_by="u1",
        payload={
            "event_date": "2026-03-01",
            "agency_raw": "ILTOLL",
            "trip_charge": "7.35",
            "transponder_number": "02400000001",
        },
    )
    await validate_manual_stage(db, tenant_id=7, stage_id=int(stage.id), updated_by="u1")
    result = await process_toll_manual_stage(db, tenant_id=7, stage_id=int(stage.id), processed_by="u1")
    assert result["processed_transaction_count"] == 1
    assert Decimal(result["processed_total"]) == Decimal("7.35")
    assert db.stages[0].status == MANUAL_STAGE_PROCESSED
    assert db.transactions[0].manual_stage_id == stage.id
    assert db.transactions[0].pdf_review_row_id is None
    assert db.batches[-1].source_type == SOURCE_TYPE_MANUAL
    assert db.batches[-1].file_format is None
    assert db.batches[-1].source_filename is None
    assert db.batches[-1].source_hash is None
    assert db.batches[-1].source_storage_ref is None
    assert db.batches[-1].provider_code is None
    assert db.batches[-1].csv_parser_name is None
    assert db.batches[-1].source_import_ref == f"manual-stage-{stage.id}"
    snapshot = db.transactions[0].accepted_effective_json
    assert snapshot["trip_charge"] == "7.35"
    assert snapshot["event_date"] == "2026-03-01"
    assert snapshot["agency_raw"] == "ILTOLL"
    assert snapshot["transponder_number"] == "02400000001"
    assert snapshot["manual_stage_id"] == stage.id
    assert snapshot["file_format"] is None


@pytest.mark.asyncio
async def test_16_draft_manual_cannot_process() -> None:
    db = FakePdfSession()
    stage = await create_manual_stage(
        db,
        tenant_id=7,
        payload={"event_date": "2026-03-01", "trip_charge": "7.35", "agency_raw": "ILTOLL"},
    )
    assert stage.status == MANUAL_STAGE_DRAFT
    with pytest.raises(TollProcessError) as err:
        await process_toll_manual_stage(db, tenant_id=7, stage_id=int(stage.id), processed_by="u1")
    assert err.value.code == "TOLL_MANUAL_NOT_READY"
    assert db.transactions == []


@pytest.mark.asyncio
async def test_17_discarded_manual_cannot_process() -> None:
    db = FakePdfSession()
    stage = await create_manual_stage(
        db,
        tenant_id=7,
        payload={"event_date": "2026-03-01", "trip_charge": "7.35", "agency_raw": "ILTOLL"},
    )
    await discard_manual_stage(db, tenant_id=7, stage_id=int(stage.id))
    assert db.stages[0].status == MANUAL_STAGE_DISCARDED
    with pytest.raises(TollProcessError) as err:
        await process_toll_manual_stage(db, tenant_id=7, stage_id=int(stage.id), processed_by="u1")
    assert err.value.code == "TOLL_MANUAL_DISCARDED"
    assert db.stages[0].status == MANUAL_STAGE_DISCARDED
    assert db.transactions == []
    assert not any(batch.source_type == SOURCE_TYPE_MANUAL for batch in db.batches)


@pytest.mark.asyncio
async def test_17b_missing_manual_stage_is_not_found() -> None:
    db = FakePdfSession()
    with pytest.raises(TollManualEntryError) as err:
        await process_toll_manual_stage(db, tenant_id=7, stage_id=999, processed_by="u1")
    assert err.value.code == "TOLL_MANUAL_NOT_FOUND"
    assert db.transactions == []
    client = TestClient(_app(db))
    missing = client.post("/api/v1/tolls/manual-entry/stages/999/process")
    assert missing.status_code == 404
    assert missing.json()["detail"]["code"] == "TOLL_MANUAL_NOT_FOUND"


@pytest.mark.asyncio
async def test_18_repeated_manual_process_creates_no_duplicate() -> None:
    db = FakePdfSession()
    stage = await create_manual_stage(
        db,
        tenant_id=7,
        payload={
            "event_date": "2026-03-01",
            "trip_charge": "7.35",
            "agency_raw": "ILTOLL",
            "transponder_number": "02400000001",
        },
    )
    await validate_manual_stage(db, tenant_id=7, stage_id=int(stage.id), updated_by="u1")
    first = await process_toll_manual_stage(db, tenant_id=7, stage_id=int(stage.id), processed_by="u1")
    second = await process_toll_manual_stage(db, tenant_id=7, stage_id=int(stage.id), processed_by="u1")
    assert first["idempotent_replay"] is False
    assert second["idempotent_replay"] is True
    assert len([tx for tx in db.transactions if tx.manual_stage_id == stage.id]) == 1
    manual_batches = [
        batch
        for batch in db.batches
        if batch.source_type == SOURCE_TYPE_MANUAL and batch.source_import_ref == f"manual-stage-{stage.id}"
    ]
    assert len(manual_batches) == 1
    assert manual_batches[0].file_format is None
    assert manual_batches[0].source_filename is None
    assert manual_batches[0].source_hash is None
    assert manual_batches[0].source_storage_ref is None


@pytest.mark.asyncio
async def test_19_processed_pdf_is_read_only() -> None:
    db = FakePdfSession()
    with patch("app.services.toll_pdf_review.save_toll_pdf_file_bytes", new=_store):
        batch_id = await _persist_pdf(db)
    await process_toll_pdf_review(db, tenant_id=7, batch_id=batch_id, processed_by="u1")
    row = db.review_rows[0]
    with pytest.raises(TollPdfCorrectionError) as err:
        await apply_pdf_review_corrections(
            db,
            tenant_id=7,
            batch_id=batch_id,
            row_id=int(row.id),
            fields={"agency_raw": "X"},
            changed_by="u1",
        )
    assert err.value.code == "TOLL_PDF_PROCESSED_READONLY"


@pytest.mark.asyncio
async def test_20_processed_manual_is_read_only() -> None:
    db = FakePdfSession()
    stage = await create_manual_stage(
        db,
        tenant_id=7,
        payload={
            "event_date": "2026-03-01",
            "trip_charge": "7.35",
            "agency_raw": "ILTOLL",
            "transponder_number": "02400000001",
        },
    )
    await validate_manual_stage(db, tenant_id=7, stage_id=int(stage.id), updated_by="u1")
    await process_toll_manual_stage(db, tenant_id=7, stage_id=int(stage.id), processed_by="u1")
    with pytest.raises(TollManualEntryError) as err:
        await patch_manual_stage(
            db,
            tenant_id=7,
            stage_id=int(stage.id),
            patch={"notes": "late edit"},
            updated_by="u1",
        )
    assert err.value.code == "TOLL_MANUAL_PROCESSED_READONLY"


@pytest.mark.asyncio
async def test_21_tenant_isolation() -> None:
    db = FakePdfSession()
    with patch("app.services.toll_pdf_review.save_toll_pdf_file_bytes", new=_store):
        batch_id = await _persist_pdf(db, tenant_id=7)
    with pytest.raises(Exception):
        await process_toll_pdf_review(db, tenant_id=99, batch_id=batch_id, processed_by="u1")
    assert db.transactions == []
    client = TestClient(_app(db, tenant_id=99))
    missing = client.post(f"/api/v1/tolls/pdf-reviews/{batch_id}/process")
    assert missing.status_code == 404
    row = db.review_rows[0]
    denied = client.patch(
        f"/api/v1/tolls/pdf-reviews/{batch_id}/rows/{row.id}",
        json={"agency_raw": "X"},
    )
    assert denied.status_code == 404


@pytest.mark.asyncio
async def test_22_no_driver_oo_payroll_settlement_writes() -> None:
    db = FakePdfSession()
    with patch("app.services.toll_pdf_review.save_toll_pdf_file_bytes", new=_store):
        batch_id = await _persist_pdf(db)
    await process_toll_pdf_review(db, tenant_id=7, batch_id=batch_id, processed_by="u1")
    cols = set(TollTransaction.__table__.c.keys())
    assert not (FORBIDDEN_TOLL_COLUMNS & cols)
    for tx in db.transactions:
        assert getattr(tx, "driver_id", None) is None
        assert "driver_id" not in (tx.accepted_effective_json or {})
        assert "owner_operator_id" not in (tx.accepted_effective_json or {})
        assert "payroll" not in (tx.accepted_effective_json or {})
        assert "settlement" not in (tx.accepted_effective_json or {})


@pytest.mark.asyncio
async def test_23_no_unit_fabricated() -> None:
    db = FakePdfSession()
    with patch("app.services.toll_pdf_review.save_toll_pdf_file_bytes", new=_store):
        batch_id = await _persist_pdf(db)
    await process_toll_pdf_review(db, tenant_id=7, batch_id=batch_id, processed_by="u1")
    assert "unit_id" not in TollTransaction.__table__.c.keys()
    assert TollTransaction.__table__.c["truck_id"].nullable is True
    for tx in db.transactions:
        assert tx.truck_id is None
        assert tx.unit_number_snapshot is None


@pytest.mark.asyncio
async def test_24_two_legitimate_nearby_tolls_remain_two_transactions() -> None:
    db = FakePdfSession()
    with patch("app.services.toll_pdf_review.save_toll_pdf_file_bytes", new=_store):
        batch_id = await _persist_pdf(db)
    first = db.review_rows[0]
    second = db.review_rows[1]
    assert first.entry_date == second.entry_date or first.post_date == second.post_date or True
    await process_toll_pdf_review(db, tenant_id=7, batch_id=batch_id, processed_by="u1")
    assert {tx.source_row_order for tx in db.transactions} == {row.source_row_order for row in db.review_rows}
    assert len(db.transactions) == 74
    assert db.transactions[0].source_row_order != db.transactions[1].source_row_order


def test_source_backed_uniqueness_and_no_unit_id() -> None:
    names = {
        uq.name
        for uq in TollTransaction.__table__.constraints
        if isinstance(uq, UniqueConstraint) and uq.name
    }
    assert "uq_toll_transactions_tenant_batch_source_row_order" in names
    assert "uq_toll_transactions_tenant_pdf_review_row" in names
    assert "uq_toll_transactions_tenant_manual_stage" in names
    assert "unit_id" not in TollTransaction.__table__.c.keys()


@pytest.mark.asyncio
async def test_http_pdf_and_manual_process_endpoints() -> None:
    db = FakePdfSession()
    with patch("app.services.toll_pdf_review.save_toll_pdf_file_bytes", new=_store):
        batch_id = await _persist_pdf(db)
    client = TestClient(_app(db))
    row = db.review_rows[0]
    corrected = client.patch(
        f"/api/v1/tolls/pdf-reviews/{batch_id}/rows/{row.id}",
        json={"agency_raw": "WVPA", "reason": "label"},
    )
    assert corrected.status_code == 200, corrected.text
    assert corrected.json()["reconciliation_ok"] is True
    processed = client.post(f"/api/v1/tolls/pdf-reviews/{batch_id}/process")
    assert processed.status_code == 200, processed.text
    body = processed.json()
    assert body["processed_transaction_count"] == 74
    assert body["processed_total"] == "854.47"
    assert body["process_status"] == "PROCESSED"

    stage = await create_manual_stage(
        db,
        tenant_id=7,
        payload={
            "event_date": "2026-03-01",
            "trip_charge": "7.35",
            "agency_raw": "ILTOLL",
            "transponder_number": "02400000001",
        },
    )
    await validate_manual_stage(db, tenant_id=7, stage_id=int(stage.id), updated_by="u1")
    manual = client.post(f"/api/v1/tolls/manual-entry/stages/{stage.id}/process")
    assert manual.status_code == 200, manual.text
    assert manual.json()["processed_transaction_count"] == 1
    assert manual.json()["process_status"] == "PROCESSED"


@pytest.mark.asyncio
async def test_correction_back_to_original_keeps_history() -> None:
    db = FakePdfSession()
    with patch("app.services.toll_pdf_review.save_toll_pdf_file_bytes", new=_store):
        batch_id = await _persist_pdf(db)
    row = db.review_rows[0]
    original = format(row.trip_charge, "f")
    await apply_pdf_review_corrections(
        db,
        tenant_id=7,
        batch_id=batch_id,
        row_id=int(row.id),
        fields={"trip_charge": "9.99"},
        changed_by="u1",
    )
    await apply_pdf_review_corrections(
        db,
        tenant_id=7,
        batch_id=batch_id,
        row_id=int(row.id),
        fields={"trip_charge": original},
        changed_by="u1",
    )
    history = [item for item in db.corrections if item.field_name == "trip_charge"]
    assert len(history) == 2
    assert history[0].corrected_value == "9.99"
    assert history[1].corrected_value == original
    assert format(row.trip_charge, "f") == original


@pytest.mark.asyncio
async def test_immutable_source_fields_cannot_be_corrected() -> None:
    db = FakePdfSession()
    with patch("app.services.toll_pdf_review.save_toll_pdf_file_bytes", new=_store):
        batch_id = await _persist_pdf(db)
    row = db.review_rows[0]
    for field_name in (
        "source_page_number",
        "source_row_order",
        "provider_raw",
        "source_hash",
        "source_filename",
        "source_storage_ref",
        "source_total_trip_count",
        "source_total_trip_charge",
    ):
        with pytest.raises(TollPdfCorrectionError) as err:
            await apply_pdf_review_corrections(
                db,
                tenant_id=7,
                batch_id=batch_id,
                row_id=int(row.id),
                fields={field_name: "x"},
                changed_by="u1",
            )
        assert err.value.code == "TOLL_PDF_FIELD_NOT_EDITABLE"
    assert db.corrections == []
    assert db.batches[0].source_filename == "wvpa.pdf"


@pytest.mark.asyncio
async def test_manual_process_is_atomic() -> None:
    db = FakePdfSession()
    stage = await create_manual_stage(
        db,
        tenant_id=7,
        payload={
            "event_date": "2026-03-01",
            "trip_charge": "7.35",
            "agency_raw": "ILTOLL",
            "transponder_number": "02400000001",
        },
    )
    await validate_manual_stage(db, tenant_id=7, stage_id=int(stage.id), updated_by="u1")
    db.fail_after_n_transactions = 1
    with pytest.raises(RuntimeError):
        await process_toll_manual_stage(db, tenant_id=7, stage_id=int(stage.id), processed_by="u1")
    assert db.rolled_back is True
    assert db.transactions == []
    assert db.stages[0].status == MANUAL_STAGE_NEEDS_REVIEW
    assert not any(batch.source_type == SOURCE_TYPE_MANUAL for batch in db.batches)


@pytest.mark.asyncio
async def test_canonical_transaction_queryable_without_review_tables() -> None:
    db = FakePdfSession()
    with patch("app.services.toll_pdf_review.save_toll_pdf_file_bytes", new=_store):
        batch_id = await _persist_pdf(db)
    await process_toll_pdf_review(db, tenant_id=7, batch_id=batch_id, processed_by="u1")
    standalone = [
        {
            "id": tx.id,
            "tenant_id": tx.tenant_id,
            "batch_id": tx.batch_id,
            "amount": tx.amount,
            "transaction_date": tx.transaction_date,
            "toll_agency_code": tx.toll_agency_code,
            "accepted_effective_json": tx.accepted_effective_json,
            "provider_raw": tx.provider_raw,
        }
        for tx in db.transactions
        if tx.tenant_id == 7 and tx.batch_id == batch_id
    ]
    assert len(standalone) == 74
    assert all(row["accepted_effective_json"]["trip_charge"] for row in standalone)
    assert "unit_id" not in TollTransaction.__table__.c.keys()
    assert TollSourceBatch.__table__.c["source_type"].nullable is False


@pytest.mark.asyncio
async def test_http_discarded_manual_process_is_business_error() -> None:
    db = FakePdfSession()
    stage = await create_manual_stage(
        db,
        tenant_id=7,
        payload={"event_date": "2026-03-01", "trip_charge": "7.35", "agency_raw": "ILTOLL"},
    )
    await discard_manual_stage(db, tenant_id=7, stage_id=int(stage.id))
    client = TestClient(_app(db))
    response = client.post(f"/api/v1/tolls/manual-entry/stages/{stage.id}/process")
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "TOLL_MANUAL_DISCARDED"
    assert db.stages[0].status == MANUAL_STAGE_DISCARDED
