"""Completed BASIC projection for processed BVD (operational history view)."""

from __future__ import annotations

import json
from pathlib import Path

from app.services.fuel_bvd_completed_basic import build_bvd_completed_basic_projection

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "fuel_bvd_972201_expected.json"


def _golden_rows() -> list[dict]:
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return list(data["rows"])


def _project(rows: list[dict]) -> dict:
    return build_bvd_completed_basic_projection(
        rows,
        import_id="import-972201",
        review_status="SOURCE_REVIEWED",
    )


def test_a_only_hst_visible_when_other_taxes_zero() -> None:
    view = _project(_golden_rows())
    tax_keys = {line["key"] for line in view["taxes"]}
    assert tax_keys == {"hst"}
    assert view["taxes"][0]["amount"] == "393.57"


def test_b_gst_pst_visible_hst_hidden() -> None:
    rows = _golden_rows()
    grand = next(r for r in rows if r.get("row_type") == "GRAND_TOTAL" and r.get("row_label") == "Grand Total")
    grand["hst"] = "0.00"
    grand["gst"] = "72.14"
    grand["pst"] = "31.00"
    view = _project(rows)
    tax_keys = {line["key"] for line in view["taxes"]}
    assert tax_keys == {"gst", "pst"}


def test_c_all_taxes_zero_omits_tax_section() -> None:
    rows = _golden_rows()
    for row in rows:
        if row.get("row_type") == "GRAND_TOTAL" and row.get("row_label") == "Grand Total":
            row["hst"] = "0.00"
            row["gst"] = "0.00"
            row["pst"] = "0.00"
            row["qst"] = "0.00"
    view = _project(rows)
    assert view["taxes"] == []


def test_d_only_fuel_ta_category_when_def_scale_zero() -> None:
    view = _project(_golden_rows())
    cat_keys = {line["key"] for line in view["categories"]}
    assert cat_keys == {"TA"}
    assert view["categories"][0]["label"] == "Fuel / TA"


def test_e_def_appears_when_nonzero() -> None:
    rows = _golden_rows()
    for row in rows:
        if row.get("row_type") == "GRAND_TOTAL" and row.get("product") == "DF":
            row["final_amount"] = "125.50"
    view = _project(rows)
    cat_keys = {line["key"] for line in view["categories"]}
    assert "DF" in cat_keys


def test_completed_basic_is_read_only_when_source_reviewed() -> None:
    view = _project(_golden_rows())
    assert view["read_only"] is True
    assert view["review_status"] == "SOURCE_REVIEWED"


def test_completed_basic_includes_due_date_and_grand_total_discount() -> None:
    view = _project(_golden_rows())
    assert view["card_number"] == "4237111"
    assert view["due_date"] == "2026-07-30 23:59:59"
    assert view["invoice_disc_amt"] == "0.00"
    assert view["total_amount"] == "3,421.01"
    assert view["currency"] == "CN"
