"""Unit tests for email intake PDF helpers."""
from __future__ import annotations

from app.services.email_intake_pdf import (
    extract_tql_rate_con_hints,
    guess_broker_load_reference,
)
from app.services.email_engine.message_classifier import (
    participants_indicate_booking_broker_touchpoints,
    subject_or_snippet_indicates_booking_broker_touchpoints,
)


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


def test_participants_indicate_booking_broker_touchpoints() -> None:
    assert participants_indicate_booking_broker_touchpoints([{"email": "agent@tql.com"}]) is True
    assert participants_indicate_booking_broker_touchpoints([{"email": "broker@example.com"}]) is False
    assert participants_indicate_booking_broker_touchpoints(None) is False


def test_subject_or_snippet_indicates_booking_broker_touchpoints() -> None:
    assert subject_or_snippet_indicates_booking_broker_touchpoints("Rate con from TQL", None) is True
    assert subject_or_snippet_indicates_booking_broker_touchpoints("Total Quality Logistics update", "") is True
    assert subject_or_snippet_indicates_booking_broker_touchpoints("Random freight", None) is False
