"""Unit tests for narrow TQL digital-PDF text heuristics."""
from __future__ import annotations

from app.services.email_intake_pdf import (
    extract_tql_rate_con_hints,
    guess_broker_load_reference,
    tql_digital_pdf_high_confidence,
)
from app.services.email_intake_routing import participants_indicate_tql, subject_or_snippet_indicates_tql


def test_tql_high_confidence_requires_keywords_and_length() -> None:
    short = "TQL RATE CONFIRMATION " + "x" * 50
    ok, reason = tql_digital_pdf_high_confidence(short)
    assert ok is False
    assert reason == "extracted_text_too_short"

    good = """
    TOTAL QUALITY LOGISTICS
    RATE CONFIRMATION
    SHIPPER ABC Inc
    PICKUP Chicago IL
    DELIVERY Dallas TX
    CONSIGNEE XYZ
    """ + ("detail line\n" * 30)
    ok2, reason2 = tql_digital_pdf_high_confidence(good)
    assert ok2 is True
    assert reason2 == "tql_digital_pdf_rate_confirmation"

    missing_rc = good.replace("RATE CONFIRMATION", "FREIGHT BILL")
    ok3, _ = tql_digital_pdf_high_confidence(missing_rc)
    assert ok3 is False


def test_guess_broker_load_reference() -> None:
    assert guess_broker_load_reference("Please see Load # ABC12X for details") == "ABC12X"
    assert guess_broker_load_reference("no ref here") is None


def test_extract_tql_rate_con_hints() -> None:
    blob = """
    TOTAL QUALITY LOGISTICS
    RATE CONFIRMATION
    Total Rate: $2,500.50
    Billable Miles: 1245
    Commodity: Paper rolls
    PICKUP Chicago IL
    DELIVERY Dallas TX
    """
    h = extract_tql_rate_con_hints(blob)
    assert h["rate"] == 2500.50
    assert h["miles"] == 1245
    assert "Paper" in str(h.get("commodity", ""))


def test_participants_indicate_tql() -> None:
    assert participants_indicate_tql([{"email": "agent@tql.com"}]) is True
    assert participants_indicate_tql([{"email": "broker@example.com"}]) is False
    assert participants_indicate_tql(None) is False


def test_subject_or_snippet_indicates_tql() -> None:
    assert subject_or_snippet_indicates_tql("Rate con from TQL", None) is True
    assert subject_or_snippet_indicates_tql("Total Quality Logistics update", "") is True
    assert subject_or_snippet_indicates_tql("Random freight", None) is False
