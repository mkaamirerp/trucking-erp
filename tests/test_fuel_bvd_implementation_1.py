"""BVD Implementation 1 — source fidelity (fuel_bvd only)."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
import pytest

from app.models.fuel import FuelBvd, FuelSourceControl, FuelTransaction
from app.services.fuel_bvd_extraction import (
    ROW_GRAND_TOTAL,
    ROW_HEADER,
    ROW_LEGEND,
    ROW_PAGE1_SUMMARY,
    ROW_TRANSACTION,
    ROW_TRANSACTION_SUBTOTAL,
    extract_bvd_rows_from_digital_pdf,
)
from app.services.fuel_bvd_import import (
    BVD_SOURCE_FIELD_NAMES,
    fuel_bvd_row_to_dict,
    import_bvd_digital_pdf,
)

REPO = Path(__file__).resolve().parents[1]
BVD_PDF = REPO / "docs" / "fixtures" / "fuel" / "BVD_invoice_972201.pdf"
GOLDEN = REPO / "tests" / "fixtures" / "fuel_bvd_972201_expected.json"


def _golden_rows() -> list[dict]:
    payload = json.loads(GOLDEN.read_text(encoding="utf-8"))
    return payload["rows"]


def _extracted_db_shaped_rows() -> list[dict]:
    pdf_bytes = BVD_PDF.read_bytes()
    extracted, _warnings, _pv = extract_bvd_rows_from_digital_pdf(pdf_bytes)
    out: list[dict] = []
    for i, row in enumerate(extracted, start=1):
        item = {"source_row_number": i, "row_type": row.row_type, "source_page": row.source_page}
        for name in BVD_SOURCE_FIELD_NAMES:
            val = row.fields.get(name)
            if val is not None:
                item[name] = val
        out.append(item)
    return out


def test_bvd_fixture_matches_db_shaped_golden() -> None:
    assert BVD_PDF.is_file()
    assert GOLDEN.is_file()
    assert _extracted_db_shaped_rows() == _golden_rows()


def test_bvd_source_fidelity_not_segment6_normalized() -> None:
    """Pre Tax AMT must keep PDF comma formatting (not 1425.63 canonical)."""
    txns = [r for r in _extracted_db_shaped_rows() if r["row_type"] == ROW_TRANSACTION]
    assert txns[0]["pre_tax_amt"] == "1,425.63"
    assert txns[0]["disc_rate"] == "0.0000"
    assert txns[1]["pre_tax_amt"] == "1,601.81"
    assert txns[1]["transaction_date"] == "2026-07-27 13:38:39"
    assert txns[1]["unit_number"] == "1104"


def test_bvd_locked_milestone_field_samples() -> None:
    header = next(r for r in _extracted_db_shaped_rows() if r["row_type"] == ROW_HEADER)
    assert header["invoice_number"] == "972201"
    assert header["card_number"] == "4237111"
    assert header["hst_number"] == "849416516RT0001"
    assert header["qst_number"] == "1221749509TQ0001"

    t1 = next(r for r in _extracted_db_shaped_rows() if r.get("auth_code") == "A204040667-TA")
    assert t1["driver_name"] == "JASPREET CHOKAR"
    assert t1["unit_number"] == "1100"
    assert t1["qty"] == "719.50"
    assert t1["retail"] == "2.2390"
    assert t1["billed"] == "2.2390"
    assert t1["hst"] == "185.33"
    assert t1["final_amt"] == "1,610.96"
    assert t1["cur"] == "CN"

    t2 = next(r for r in _extracted_db_shaped_rows() if r.get("auth_code") == "A208448597-TA")
    assert t2["hst"] == "208.24"
    assert t2["final_amt"] == "1,810.05"


def test_bvd_row_structure_coverage() -> None:
    rows = _extracted_db_shaped_rows()
    types = {r["row_type"] for r in rows}
    assert ROW_TRANSACTION_SUBTOTAL in types
    assert ROW_PAGE1_SUMMARY in types
    assert ROW_GRAND_TOTAL in types
    assert ROW_LEGEND in types
    assert any(r.get("row_label") == "Manual" for r in rows)
    assert any(r.get("row_label") == "Express" for r in rows)
    assert any(r.get("row_label") == "Grand Total" for r in rows)
    legend_tf = next(r for r in rows if r.get("legend_code") == "TF")
    assert legend_tf["legend_product_name"] == "Trailer"
    assert [r["source_row_number"] for r in rows] == list(range(1, len(rows) + 1))


def test_fuel_bvd_row_to_dict_reads_orm_text() -> None:
    row = FuelBvd(
        tenant_id=1,
        import_id=uuid.uuid4(),
        row_type=ROW_TRANSACTION,
        pre_tax_amt="1,425.63",
        disc_rate="0.0000",
    )
    data = fuel_bvd_row_to_dict(row)
    assert data["pre_tax_amt"] == "1,425.63"
    assert data["disc_rate"] == "0.0000"


@pytest.mark.asyncio
async def test_import_persists_fuel_bvd_only(monkeypatch: pytest.MonkeyPatch) -> None:
    added: list[FuelBvd] = []

    class _Session:
        def add(self, obj: FuelBvd) -> None:
            added.append(obj)

        async def commit(self) -> None:
            for i, row in enumerate(added, start=1):
                row.id = i

    async def _fake_save(**_kwargs):
        return "tenant/demo/fuel_bvd/import/x/file.pdf", "abc123"

    monkeypatch.setattr(
        "app.services.fuel_bvd_import.save_bvd_pdf_to_storage",
        _fake_save,
    )

    import_id, count, status = await import_bvd_digital_pdf(
        _Session(),
        tenant_id=53,
        tenant_slug="demo",
        pdf_bytes=BVD_PDF.read_bytes(),
        filename="BVD_invoice_972201.pdf",
        uploaded_by="tester",
    )
    assert status == "SUCCESS"
    assert count == 24
    assert len(added) == 24
    assert all(isinstance(r, FuelBvd) for r in added)
    assert all(r.import_id == import_id for r in added)
    assert added[0].row_type == ROW_HEADER
    assert added[1].pre_tax_amt == "1,425.63"

    # Regression: import module must not touch canonical fuel tables.
    assert FuelTransaction.__tablename__ == "fuel_transactions"
    assert FuelSourceControl.__tablename__ == "fuel_source_controls"
    import app.services.fuel_bvd_import as mod

    assert "fuel_reconciliation" not in mod.__dict__
    assert "fuel_ingestion" not in mod.__dict__


def test_bvd_api_routes_registered() -> None:
    from app.routers.fuel import router

    paths = {getattr(r, "path", None) for r in router.routes}
    assert "/fuel/bvd/imports" in paths
    assert "/fuel/bvd/imports/{import_id}/rows" in paths
    assert "/fuel/bvd/imports/{import_id}/document" in paths
