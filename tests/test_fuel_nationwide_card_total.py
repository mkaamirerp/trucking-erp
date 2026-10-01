"""Nationwide CARD_TOTAL — explicit parsed fields for review (not UI heuristics)."""

from __future__ import annotations

from app.services.fuel_nationwide_card_total import (
    apply_card_total_review_fields,
    parse_nationwide_card_total_line,
)

_FIXTURE_LINES = [
    (
        "XXXXX87195 Total GST $145.4 QST $0 674.17 $1,263.85 $0.00 $0.00",
        "XXXXX87195",
        "CAD",
        "1263.85",
        "145.40",
    ),
    ("XXXXX07588 Total 154.27 $722.75 $34.56 $0.00", "XXXXX07588", "USD", "722.75", None),
    ("XXXXX87115 Total 309.32 $1,456.27 $169.19 $0.00", "XXXXX87115", "USD", "1456.27", None),
    ("XXXXX87195 Total 317.06 $1,584.46 $15.79 $0.00", "XXXXX87195", "USD", "1584.46", None),
    ("XXXXX97103 Total 306.36 $1,434.21 $227.30 $0.00", "XXXXX97103", "USD", "1434.21", None),
]


def test_parse_nationwide_card_total_fixture_lines() -> None:
    for line, card, currency, declared, gst in _FIXTURE_LINES:
        parsed = parse_nationwide_card_total_line(line)
        assert parsed["Card Number"] == card
        assert parsed["Currency"] == currency
        assert parsed["declared_amount"] == declared
        if gst:
            assert parsed.get("GST") == gst
        else:
            assert "GST" not in parsed or parsed.get("GST") is None


def test_review_projection_fills_explicit_card_total_fields_without_frontend_scraping() -> None:
    row = {
        "control_type": "CARD_TOTAL",
        "row_label": "CARD_TOTAL",
        "card_number": "XXXXX07588",
        "control_line_raw": "XXXXX07588 Total 154.27 $722.75 $34.56 $0.00",
        "currency": None,
        "declared_amount": None,
        "gst": None,
    }
    apply_card_total_review_fields(row)
    assert row["currency"] == "USD"
    assert row["declared_amount"] == "722.75"
    assert row["gst"] is None


def test_review_projection_does_not_overwrite_existing_explicit_values() -> None:
    row = {
        "control_type": "CARD_TOTAL",
        "control_line_raw": "XXXXX07588 Total 154.27 $999.99 $34.56 $0.00",
        "currency": "USD",
        "declared_amount": "722.75",
    }
    apply_card_total_review_fields(row)
    assert row["declared_amount"] == "722.75"
