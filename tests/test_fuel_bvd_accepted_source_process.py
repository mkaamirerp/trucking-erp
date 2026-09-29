"""Accepted-source Process contract — permanent fuel_bvd and canonical use effective values."""

from __future__ import annotations

import copy
import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.models.fuel import FuelBvd, FuelSourceBatch
from app.services.fuel_bvd_canonical_projection import (
    _build_purchase_transaction,
    project_bvd_rows_to_canonical,
)
from app.services.fuel_bvd_effective import build_effective_bvd_row, build_effective_bvd_rows
from app.services.fuel_bvd_review import (
    commit_accepted_values_onto_permanent_fuel_bvd,
    reconcile_bvd_import_review_rows,
)
from app.services.fuel_bvd_stage import (
    FuelBvdImportStage,
    STAGE_STATUS_ACTIVE,
    process_stage_to_permanent,
)


def _txn_row(
    *,
    row_id: int = 12,
    unit: str = "125",
    final_amt: str = "100.00",
    corrections: dict | None = None,
) -> dict:
    row = {
        "id": row_id,
        "row_type": "TRANSACTION",
        "source_page": 1,
        "source_row_number": 3,
        "auth_code": "AUTH-1",
        "unit_number": unit,
        "transaction_date": "2026-07-01 00:00:00",
        "pre_tax_amt": final_amt,
        "final_amt": final_amt,
        "cur": "CAD",
        "prod": "D",
        "field_corrections": corrections or {},
    }
    return row


def test_effective_unit_before_process() -> None:
    row = _txn_row(
        corrections={"unit_number": {"extracted_value": "125", "reviewed_value": "1025"}},
    )
    assert row["unit_number"] == "125"
    assert build_effective_bvd_row(row)["unit_number"] == "1025"
    assert reconcile_bvd_import_review_rows([row]).transaction_total is not None


def test_latest_review_edit_wins() -> None:
    row = _txn_row(
        corrections={"unit_number": {"extracted_value": "125", "reviewed_value": "1026"}},
    )
    assert build_effective_bvd_row(row)["unit_number"] == "1026"


def test_no_edit_accepted_equals_parser() -> None:
    row = _txn_row(unit="1100", corrections={})
    assert build_effective_bvd_row(row)["unit_number"] == "1100"


def test_provider_raw_uses_accepted_not_parser() -> None:
    raw = _txn_row(unit="125")
    eff = build_effective_bvd_row(
        {
            **raw,
            "field_corrections": {
                "unit_number": {"extracted_value": "125", "reviewed_value": "1025"},
            },
        }
    )
    import_id = uuid.uuid4()
    txn = _build_purchase_transaction(
        tenant_id=53,
        batch_id=1,
        effective=eff,
        raw=raw,
        fuel_bvd_id=99,
        import_id=import_id,
    )
    assert txn.unit_number_snapshot == "1025"
    fields = txn.provider_raw.get("fields") or {}
    assert fields.get("unit_number") == "1025"
    assert fields.get("unit_number") != "125"


def test_control_projection_uses_accepted_money() -> None:
    header = {
        "id": 10,
        "row_type": "HEADER",
        "source_row_number": 1,
        "invoice_number": "T-1",
        "invoice_date": "2026-07-01 00:00:00",
        "start_date": "2026-07-01 00:00:00",
        "end_date": "2026-07-31 23:59:59",
    }
    grand_parser = {
        "id": 11,
        "row_type": "GRAND_TOTAL",
        "source_row_number": 2,
        "row_label": "Grand Total",
        "final_amt": "125.00",
        "cur": "CAD",
    }
    grand_accepted = {
        **grand_parser,
        "final_amt": "1025.00",
        "field_corrections": {
            "final_amt": {"extracted_value": "125.00", "reviewed_value": "1025.00"},
        },
    }
    grand_eff = build_effective_bvd_row(grand_accepted)
    txn_parser = _txn_row(final_amt="1025.00", unit="1100")
    txn_eff = build_effective_bvd_row(txn_parser)
    accepted = [header, grand_eff, txn_eff]
    batch = FuelSourceBatch(id=1, tenant_id=53)
    import_id = uuid.uuid4()
    id_map = {10: 100, 11: 101, 12: 102}
    txns, controls = project_bvd_rows_to_canonical(
        tenant_id=53,
        batch=batch,
        import_id=import_id,
        raw_rows=accepted,
        effective_rows=accepted,
        fuel_bvd_id_by_stage_row_id=id_map,
    )
    assert len(txns) == 1
    assert txns[0].total_amount == Decimal("1025.00")
    invoice_ctrl = next(c for c in controls if c.control_type == "INVOICE_TOTAL")
    assert invoice_ctrl.declared_amount == Decimal("1025.00")


@pytest.mark.asyncio
async def test_process_writes_accepted_unit_to_fuel_bvd() -> None:
    stage_id = uuid.uuid4()
    stage = FuelBvdImportStage(
        stage_id=stage_id,
        tenant_id=53,
        provider_code="BVD",
        status=STAGE_STATUS_ACTIVE,
        source_file_name="x.pdf",
        source_file_sha256="abc",
        source_storage_ref="k",
        parse_status="SUCCESS",
        uploaded_at=None,
        parser_version="test",
    )
    header = {
        "row_type": "HEADER",
        "id": 10,
        "source_page": 1,
        "source_row_number": 1,
        "invoice_number": "972201",
        "invoice_date": "2026-07-01 00:00:00",
        "start_date": "2026-07-01 00:00:00",
        "end_date": "2026-07-31 23:59:59",
    }
    grand = {
        "row_type": "GRAND_TOTAL",
        "id": 11,
        "source_page": 1,
        "source_row_number": 2,
        "row_label": "Grand Total",
        "final_amt": "1025.00",
        "cur": "CAD",
    }
    txn = _txn_row(
        corrections={"unit_number": {"extracted_value": "125", "reviewed_value": "1025"}},
        final_amt="1025.00",
    )
    txn["pre_tax_amt"] = "1025.00"
    rows = [header, grand, txn]

    fuel_rows_added: list[FuelBvd] = []

    async def _exec(*_a, **_k):
        class _Scalars:
            def all(self):
                return []

        class _Result:
            def scalars(self):
                return _Scalars()

        return _Result()

    db = AsyncMock()
    db.execute = AsyncMock(side_effect=_exec)
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()

    def _add(obj):
        if isinstance(obj, FuelBvd):
            fuel_rows_added.append(obj)
            obj.id = 500 + len(fuel_rows_added)

    db.add = MagicMock(side_effect=_add)

    stored = MagicMock(storage_key="perm/key.pdf")
    real_txn = None
    real_controls = None

    def _project(**kwargs):
        nonlocal real_txn, real_controls
        from app.services.fuel_bvd_canonical_projection import project_bvd_rows_to_canonical as real

        real_txn, real_controls = real(**kwargs)
        return real_txn, real_controls

    with patch("app.services.fuel_bvd_stage._import_already_source_reviewed", AsyncMock(return_value=False)):
        with patch("app.services.fuel_bvd_stage.get_active_stage", AsyncMock(return_value=stage)):
            with patch("app.services.fuel_bvd_stage.list_stage_rows_for_review", AsyncMock(return_value=rows)):
                with patch("app.services.fuel_bvd_stage.get_storage") as gs:
                    gs.return_value.read_bytes.return_value = b"%PDF-1.4"
                    with patch(
                        "app.services.fuel_bvd_stage.save_fuel_bvd_import_bytes",
                        AsyncMock(return_value=stored),
                    ):
                        with patch(
                            "app.services.fuel_bvd_stage.check_bvd_pdf_duplicate_before_import",
                            AsyncMock(return_value=None),
                        ):
                            with patch(
                                "app.services.fuel_bvd_stage.acquire_bvd_import_advisory_lock",
                                AsyncMock(),
                            ):
                                with patch(
                                    "app.services.fuel_bvd_stage.project_bvd_rows_to_canonical",
                                    side_effect=_project,
                                ):
                                    with patch(
                                        "app.services.fuel_bvd_stage.build_fuel_source_batch",
                                        return_value=MagicMock(id=1),
                                    ):
                                        with patch(
                                            "app.services.fuel_classification_persistence.best_effort_backfill_classifications_for_import",
                                            AsyncMock(),
                                        ):
                                            with patch(
                                                "app.services.fuel_bvd_stage.get_bvd_import_review_summary",
                                                AsyncMock(return_value={"review_status": "SOURCE_REVIEWED"}),
                                            ):
                                                with patch(
                                                    "app.services.fuel_bvd_stage._delete_stage_records",
                                                    AsyncMock(),
                                                ):
                                                    await process_stage_to_permanent(
                                                        db,
                                                        tenant_id=53,
                                                        tenant_slug="demo",
                                                        stage_id=stage_id,
                                                        reviewed_by="u",
                                                    )

    purchase = next(r for r in fuel_rows_added if r.row_type == "TRANSACTION")
    assert purchase.unit_number == "1025"
    assert purchase.unit_number != "125"
    assert real_txn is not None
    assert real_txn[0].unit_number_snapshot == "1025"
    assert real_txn[0].total_amount == Decimal("1025.00")


@pytest.mark.asyncio
async def test_commit_accepted_flattens_legacy_permanent_rows() -> None:
    import_id = uuid.uuid4()
    row_dict = _txn_row(
        corrections={"unit_number": {"extracted_value": "125", "reviewed_value": "1025"}},
    )
    orm = FuelBvd(
        id=12,
        tenant_id=53,
        import_id=import_id,
        row_type="TRANSACTION",
        unit_number="125",
    )
    db = AsyncMock()
    db.execute = AsyncMock(
        return_value=MagicMock(scalars=MagicMock(return_value=MagicMock(all=lambda: [orm])))
    )

    await commit_accepted_values_onto_permanent_fuel_bvd(
        db, tenant_id=53, import_id=import_id, rows=[row_dict]
    )
    assert orm.unit_number == "1025"
    db.execute.assert_awaited()
