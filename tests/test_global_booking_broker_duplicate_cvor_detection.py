"""CVOR duplicate signal contract: aligns SQL ``shared_cvor:`` with Slice 1 normalization (no DB)."""

from __future__ import annotations

import pytest

from app.utils.broker_identity import normalize_cvor_number_digits


def test_shared_cvor_signal_format_matches_normalizer_output() -> None:
    """Canonical stored form is nine digits; match_signals use ``shared_cvor:<value>``."""
    canon = normalize_cvor_number_digits("123 456 789")
    assert canon == "123456789"
    assert f"shared_cvor:{canon}" == "shared_cvor:123456789"


def test_cvor_normalizer_rejects_non_nine_digit_for_detection_alignment() -> None:
    """Rows that cannot normalize to 9 digits are not valid global CVOR; SQL also excludes them."""
    with pytest.raises(ValueError):
        normalize_cvor_number_digits("12345")
