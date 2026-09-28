"""BVD effective reviewed values — reconciliation authority and correction validation."""

from __future__ import annotations

import copy
import json
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.services.fuel_bvd_correction_validate import (
    BvdCorrectionValidationError,
    validate_reviewed_bvd_field,
)
from app.services.fuel_bvd_effective import build_effective_bvd_row, build_effective_bvd_rows
from app.services.fuel_bvd_review import (
    reconcile_bvd_import_review_rows,
    save_bvd_import_review,
    process_bvd_import_review,
)
from app.services.fuel_bvd_source_reconciliation import reconcile_bvd_source_rows

REPO = Path(__file__).resolve().parents[1]
GOLDEN = REPO / "tests" / "fixtures" / "fuel_bvd_972201_expected.json"


def _golden_rows() -> list[dict]:
    payload = json.loads(GOLDEN.read_text(encoding="utf-8"))
    return [{"id": i + 1, "import_id": "test-import", **row} for i, row in enumerate(payload["rows"])]


def _find(rows: list[dict], **kwargs: object) -> dict:
    for row in rows:
        if all(row.get(k) == v for k, v in kwargs.items()):
            return row
    raise AssertionError(f"row not found: {kwargs}")


def _with_correction(rows: list[dict], auth_code: str, field: str, reviewed: str) -> list[dict]:
    out = copy.deepcopy(rows)
    txn = _find(out, auth_code=auth_code)
    orig = txn[field]
    txn["field_corrections"] = {
        field: {"extracted_value": orig, "reviewed_value": reviewed},
    }
    return out


def test_effective_row_overlays_all_correctable_fields() -> None:
    row = {
        "id": 1,
        "row_type": "TRANSACTION",
        "unit_number": "1100",
        "final_amt": "1,610.96",
        "field_corrections": {
            "unit_number": {"extracted_value": "1100", "reviewed_value": "110A"},
            "final_amt": {"extracted_value": "1,610.96", "reviewed_value": "1,610.86"},
        },
    }
    eff = build_effective_bvd_row(row)
    assert eff["unit_number"] == "110A"
    assert eff["final_amt"] == "1,610.86"
    assert row["final_amt"] == "1,610.96"
    assert eff["field_corrections"] == row["field_corrections"]


def test_reconciliation_uses_effective_final_amt_not_raw() -> None:
    rows = _with_correction(_golden_rows(), "A204040667-TA", "final_amt", "1,610.86")
    raw_result = reconcile_bvd_source_rows(rows)
    effective_result = reconcile_bvd_import_review_rows(rows)
    assert raw_result.transaction_total == "3421.01"
    assert effective_result.transaction_total == "3420.91"
    assert effective_result.passed is False
    assert effective_result.difference == "0.10"


def test_parser_mistake_corrected_to_provider_truth_passes() -> None:
    rows = copy.deepcopy(_golden_rows())
    txn = _find(rows, auth_code="A204040667-TA")
    txn["unit_number"] = "0125"
    txn["field_corrections"] = {
        "unit_number": {"extracted_value": "0125", "reviewed_value": "1100"},
    }
    result = reconcile_bvd_import_review_rows(rows)
    assert result.passed is True


def test_effective_unit_number_changes_unit_grouping() -> None:
    rows = copy.deepcopy(_golden_rows())
    txn = _find(rows, auth_code="A208448597-TA")
    txn["unit_number"] = "1100"
    txn["field_corrections"] = {
        "unit_number": {"extracted_value": "1100", "reviewed_value": "1104"},
    }
    result = reconcile_bvd_import_review_rows(rows)
    assert "1104" in result.units
    assert result.units["1104"]["final_amt"] == "1810.05"


def test_effective_prod_changes_product_grouping() -> None:
    rows = copy.deepcopy(_golden_rows())
    txn = _find(rows, auth_code="A204040667-TA")
    txn["prod"] = "XX"
    txn["field_corrections"] = {"prod": {"extracted_value": "XX", "reviewed_value": "TA"}}
    result = reconcile_bvd_import_review_rows(rows)
    assert "TA" in result.products
    assert result.products["TA"]["final_amt"] == "3421.01"


def test_effective_hst_changes_tax_reconciliation() -> None:
    rows = copy.deepcopy(_golden_rows())
    txn = _find(rows, auth_code="A204040667-TA")
    txn["hst"] = "0.00"
    txn["field_corrections"] = {"hst": {"extracted_value": "0.00", "reviewed_value": "185.34"}}
    result = reconcile_bvd_import_review_rows(rows)
    assert result.products["TA"]["hst"] != "0.00"


def test_latest_correction_wins_in_effective_row() -> None:
    row = {
        "id": 1,
        "row_type": "TRANSACTION",
        "unit_number": "0125",
        "field_corrections": {
            "unit_number": {"extracted_value": "0125", "reviewed_value": "1025"},
        },
    }
    assert build_effective_bvd_row(row)["unit_number"] == "1025"


def test_validate_rejects_invalid_money() -> None:
    with pytest.raises(BvdCorrectionValidationError):
        validate_reviewed_bvd_field("final_amt", "abc", row_type="TRANSACTION")


def test_validate_accepts_valid_money() -> None:
    validate_reviewed_bvd_field("final_amt", "1,025.00", row_type="TRANSACTION")


@pytest.mark.asyncio
async def test_save_review_rejects_invalid_correction(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.services.fuel_bvd_stage.get_active_stage",
        AsyncMock(return_value=None),
    )
    db = AsyncMock()
    import_id = uuid.uuid4()
    row = MagicMock()
    row.id = 242
    row.row_type = "TRANSACTION"
    row.final_amt = "1,610.96"

    lock_open = MagicMock()
    lock_open.scalar_one_or_none.return_value = None
    row_fetch = MagicMock()
    row_fetch.scalars.return_value.all.return_value = [row]
    execute_calls = 0

    async def _execute(stmt, *a, **k):
        nonlocal execute_calls
        execute_calls += 1
        if execute_calls == 1:
            return lock_open
        return row_fetch

    db.execute = _execute

    with pytest.raises(HTTPException) as exc:
        await save_bvd_import_review(
            db,
            tenant_id=53,
            import_id=import_id,
            reviewed_by="tester",
            corrections=[
                {"fuel_bvd_id": 242, "field_name": "final_amt", "reviewed_value": "not-money"},
            ],
        )
    assert exc.value.status_code == 400
    assert exc.value.detail["code"] == "BVD_CORRECTION_INVALID"


@pytest.mark.asyncio
async def test_process_blocked_on_effective_reconciliation_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services import fuel_bvd_review as mod

    import_id = uuid.uuid4()
    rows = _with_correction(_golden_rows(), "A204040667-TA", "final_amt", "1,610.86")

    async def _list_rows(*_a, **_k):
        return rows

    async def _summary(*_a, **_k):
        return {
            "import_id": str(import_id),
            "invoice_number": "972201",
            "row_count": len(rows),
            "transaction_count": 2,
            "correction_count": 1,
            "review_status": "IN_REVIEW",
        }

    monkeypatch.setattr(mod, "list_bvd_import_rows_for_review", _list_rows)
    monkeypatch.setattr(mod, "get_bvd_import_review_summary", _summary)
    monkeypatch.setattr(
        "app.services.fuel_bvd_stage.get_active_stage",
        AsyncMock(return_value=None),
    )

    db = AsyncMock()
    with pytest.raises(HTTPException) as exc:
        await process_bvd_import_review(db, tenant_id=53, import_id=import_id, reviewed_by="tester")
    assert exc.value.status_code == 400
    assert exc.value.detail["code"] == "BVD_SOURCE_RECONCILIATION_FAILED"
    db.execute.assert_not_called()


def test_build_effective_bvd_rows_list() -> None:
    rows = _with_correction(_golden_rows(), "A204040667-TA", "final_amt", "1,610.86")
    effective = build_effective_bvd_rows(rows)
    txn = _find(effective, auth_code="A204040667-TA")
    assert txn["final_amt"] == "1,610.86"


def _df_to_s_scale_fixture() -> list[dict]:
    """Provider product line S; parser mis-read prod as DF on one scale txn."""
    return [
        {
            "id": 1,
            "row_type": "HEADER",
            "invoice_number": "TEST-SCALE",
            "card_number": "111",
        },
        {
            "id": 2,
            "row_type": "TRANSACTION",
            "auth_code": "SCALE-1",
            "unit_number": "1100",
            "prod": "DF",
            "qty": "1.00",
            "pre_tax_amt": "88.50",
            "hst": "11.50",
            "gst": "0.00",
            "pst": "0.00",
            "qst": "0.00",
            "disc_amt": "0.00",
            "final_amt": "100.00",
            "cur": "CN",
        },
        {
            "id": 3,
            "row_type": "GRAND_TOTAL",
            "row_label": "Grand Total",
            "final_amount": "100.00",
            "final_amt": "100.00",
            "qty": "1.00",
            "pre_tax_amt": "88.50",
            "hst": "11.50",
            "gst": "0.00",
            "pst": "0.00",
            "qst": "0.00",
            "disc_amt": "0.00",
            "cur": "CN",
        },
        {
            "id": 4,
            "row_type": "GRAND_TOTAL",
            "row_label": "S",
            "product": "S",
            "final_amount": "100.00",
            "qty": "1.00",
            "pre_tax_amt": "88.50",
            "hst": "11.50",
            "gst": "0.00",
            "pst": "0.00",
            "qst": "0.00",
            "disc_amt": "0.00",
            "cur": "CN",
        },
        {
            "id": 5,
            "row_type": "GRAND_TOTAL",
            "row_label": "DF",
            "product": "DF",
            "final_amount": "0.00",
            "qty": "0.00",
            "pre_tax_amt": "0.00",
            "hst": "0.00",
            "gst": "0.00",
            "pst": "0.00",
            "qst": "0.00",
            "disc_amt": "0.00",
            "cur": "CN",
        },
    ]


def test_prod_df_parser_mistake_fails_until_reviewed_as_s() -> None:
    rows = _df_to_s_scale_fixture()
    before = reconcile_bvd_import_review_rows(rows)
    assert before.passed is False
    assert "DF" in before.products
    assert before.products["DF"]["final_amt"] != "0.00"

    txn = _find(rows, auth_code="SCALE-1")
    assert txn["prod"] == "DF"
    txn["field_corrections"] = {"prod": {"extracted_value": "DF", "reviewed_value": "S"}}
    after = reconcile_bvd_import_review_rows(rows)
    assert after.passed is True
    assert txn["prod"] == "DF"
    assert build_effective_bvd_row(txn)["prod"] == "S"
    assert "S" in after.products
    assert after.products["S"]["final_amt"] == "100.00"
    assert "DF" not in after.products or after.products["DF"]["final_amt"] in ("0", "0.00")


@pytest.mark.asyncio
async def test_save_review_rejected_when_source_reviewed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.services.fuel_bvd_stage.get_active_stage",
        AsyncMock(return_value=None),
    )
    db = AsyncMock()
    import_id = uuid.uuid4()

    lock_result = MagicMock()
    lock_result.scalar_one_or_none.return_value = 99

    db.execute = AsyncMock(return_value=lock_result)

    with pytest.raises(HTTPException) as exc:
        await save_bvd_import_review(
            db,
            tenant_id=53,
            import_id=import_id,
            reviewed_by="tester",
            corrections=[{"fuel_bvd_id": 1, "field_name": "prod", "reviewed_value": "S"}],
        )
    assert exc.value.status_code == 400
    assert exc.value.detail["code"] == "BVD_REVIEW_LOCKED"
    db.add.assert_not_called()
