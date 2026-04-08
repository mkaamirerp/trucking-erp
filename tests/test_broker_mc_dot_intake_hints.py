"""Broker MC/DOT normalization and supplemental text hints for global Tier D."""

from __future__ import annotations

from app.services.email_intake_pdf import extract_broker_mc_dot_hints
from app.utils.broker_identity import normalize_dot_number_digits, normalize_mc_number_digits


def test_normalize_mc_strips_to_digits_min_length() -> None:
    assert normalize_mc_number_digits("MC-123456") == "123456"
    assert normalize_mc_number_digits("mc 00123456") == "00123456"
    assert normalize_mc_number_digits("12") is None
    assert normalize_mc_number_digits("") is None


def test_normalize_dot_strips_to_digits_min_length() -> None:
    assert normalize_dot_number_digits("USDOT 9876543") == "9876543"
    assert normalize_dot_number_digits("dot#123456") == "123456"
    assert normalize_dot_number_digits("12") is None


def test_extract_hints_from_block() -> None:
    text = "Carrier MC: 123456 — DOT 987654"
    mc, dot = extract_broker_mc_dot_hints(text)
    assert mc == "123456"
    assert dot == "987654"
