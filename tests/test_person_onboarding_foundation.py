"""Unit tests for people-level onboarding constants and approval setup_status derivation."""

from __future__ import annotations

import pytest

from app.constants.person_onboarding import (
    PERSON_SETUP_UI_COMBINED,
    PERSON_SETUP_UI_SEGMENTED,
    SETUP_STATUS_PENDING_DOWNSTREAM,
    normalize_person_setup_ui_mode,
    validate_person_setup_ui_mode_for_write,
)
from app.services.person_application_onboarding import setup_status_after_approval


def test_normalize_person_setup_ui_mode_defaults_invalid() -> None:
    assert normalize_person_setup_ui_mode(None) == PERSON_SETUP_UI_COMBINED
    assert normalize_person_setup_ui_mode("") == PERSON_SETUP_UI_COMBINED
    assert normalize_person_setup_ui_mode("  COMBINED  ") == PERSON_SETUP_UI_COMBINED
    assert normalize_person_setup_ui_mode("Segmented") == PERSON_SETUP_UI_SEGMENTED
    assert normalize_person_setup_ui_mode("bogus") == PERSON_SETUP_UI_COMBINED


def test_validate_person_setup_ui_mode_for_write_strict() -> None:
    assert validate_person_setup_ui_mode_for_write("combined") == "combined"
    assert validate_person_setup_ui_mode_for_write("  SEGMENTED  ") == "segmented"
    with pytest.raises(ValueError, match="invalid_person_setup_ui_mode"):
        validate_person_setup_ui_mode_for_write("bogus")
    with pytest.raises(ValueError, match="invalid_person_setup_ui_mode"):
        validate_person_setup_ui_mode_for_write("")


def test_setup_status_after_approval_foundation_slice() -> None:
    """Approval promotes the row but does not imply full onboarding; both modes → pending_downstream."""
    assert setup_status_after_approval(PERSON_SETUP_UI_COMBINED) == SETUP_STATUS_PENDING_DOWNSTREAM
    assert setup_status_after_approval(PERSON_SETUP_UI_SEGMENTED) == SETUP_STATUS_PENDING_DOWNSTREAM
