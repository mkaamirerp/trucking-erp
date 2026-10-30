"""Load workspace miles: half-up whole-mile normalization (Create, Save, Re-parse)."""

import pytest
from pydantic import ValidationError

from app.schemas.load import LoadUpdate
from app.services.load_workspace_draft_document import (
    _supported_reparse_differences,
    reparse_values_equivalent,
    values_equivalent,
)
from app.services.load_workspace_draft_mapper import (
    DraftJsonMappingError,
    draft_json_to_load_create,
    normalize_load_miles_value,
)


def test_normalize_load_miles_value_examples() -> None:
    assert normalize_load_miles_value(478.81) == 479
    assert normalize_load_miles_value(478.49) == 478
    assert normalize_load_miles_value("478.50") == 479
    assert normalize_load_miles_value(None) is None
    assert normalize_load_miles_value("") is None


def test_normalize_load_miles_rejects_invalid() -> None:
    with pytest.raises(ValueError):
        normalize_load_miles_value("not-a-number")
    with pytest.raises(ValueError):
        normalize_load_miles_value(-1)


def test_reparse_miles_equivalence_after_rounding() -> None:
    assert reparse_values_equivalent("miles", 479, 478.81)
    assert not reparse_values_equivalent("miles", 478, 478.81)
    assert not reparse_values_equivalent("miles", None, 478.81)
    assert values_equivalent(479, 478.81)


def test_reparse_no_spurious_rate_or_miles_changes() -> None:
    saved = {"extracted": {"rate": "2550.00", "miles": 479}}
    revised = {"extracted": {"rate": "2550.00", "miles": 478.81}}
    rows = _supported_reparse_differences(saved, revised)
    fields = {row["field"] for row in rows}
    assert "rate" not in fields
    assert "miles" not in fields


def test_reparse_miles_difference_when_rounding_changes_value() -> None:
    saved = {"extracted": {"miles": 478}}
    revised = {"extracted": {"miles": 478.81}}
    rows = _supported_reparse_differences(saved, revised)
    miles = next(row for row in rows if row["field"] == "miles")
    assert miles["current_value"] == 478
    assert miles["revised_value"] == 479


def test_create_load_draft_json_rounds_fractional_miles() -> None:
    load_create = draft_json_to_load_create({"miles": "478.81", "rate": "100"})
    assert load_create.miles == 479


def test_create_load_draft_json_rejects_invalid_miles() -> None:
    with pytest.raises(DraftJsonMappingError, match="whole mile"):
        draft_json_to_load_create({"miles": "abc", "rate": "100"})


def test_load_update_coerces_fractional_miles() -> None:
    payload = LoadUpdate(expected_concurrency_version=1, miles=478.81)
    assert payload.miles == 479


def test_load_update_rejects_invalid_miles() -> None:
    with pytest.raises(ValidationError):
        LoadUpdate(expected_concurrency_version=1, miles="nope")
