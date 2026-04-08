"""Global booking broker CVOR normalization and API body validation (no DB)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.platform_global_booking_broker import GlobalBookingBrokerCreateIn, GlobalBookingBrokerProfilePatchIn
from app.utils.broker_identity import normalize_cvor_number_digits


def test_normalize_cvor_empty() -> None:
    assert normalize_cvor_number_digits(None) is None
    assert normalize_cvor_number_digits("") is None
    assert normalize_cvor_number_digits("   ") is None


def test_normalize_cvor_digits_strip() -> None:
    assert normalize_cvor_number_digits("  123-456-789 ") == "123456789"


def test_normalize_cvor_invalid() -> None:
    with pytest.raises(ValueError, match="invalid_cvor_number"):
        normalize_cvor_number_digits("12345")
    with pytest.raises(ValueError, match="invalid_cvor_number"):
        normalize_cvor_number_digits("1234567890")


def test_create_in_accepts_cvor() -> None:
    m = GlobalBookingBrokerCreateIn(
        name="Test",
        cvor_number="123456789",
    )
    assert m.cvor_number == "123456789"


def test_create_in_rejects_bad_cvor() -> None:
    with pytest.raises(ValidationError):
        GlobalBookingBrokerCreateIn(name="Test", cvor_number="12")


def test_profile_patch_clear() -> None:
    m = GlobalBookingBrokerProfilePatchIn.model_validate({"cvor_number": None})
    assert m.cvor_number is None


def test_profile_patch_valid() -> None:
    m = GlobalBookingBrokerProfilePatchIn.model_validate({"cvor_number": "123 456 789"})
    assert m.cvor_number == "123456789"
