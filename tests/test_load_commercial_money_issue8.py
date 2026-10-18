"""Issue I8 — Load commercial money Decimal parsing (no DB)."""

from __future__ import annotations

import math
from decimal import Decimal

import pytest

from app.schemas.load import LoadCreate, LoadUpdate
from app.schemas.load_document_parse import LoadParseExtractedFields
from app.utils.load_commercial_money import parse_load_customer_rate, parse_load_rate


def test_parse_rate_preserves_cents_from_string() -> None:
    assert parse_load_rate("1500.50") == Decimal("1500.50")
    assert parse_load_rate("1,800.00") == Decimal("1800.00")


def test_parse_rate_avoids_float_binary_drift() -> None:
    # JSON float 2800.10 is not exact in binary; str path must still quantize correctly.
    assert parse_load_rate(2800.10) == Decimal("2800.10")


def test_load_create_schema_coerces_to_decimal() -> None:
    payload = LoadCreate.model_validate(
        {
            "status": "draft",
            "rate": "99.99",
            "customer_rate": 100,
        }
    )
    assert payload.rate == Decimal("99.99")
    assert payload.customer_rate == Decimal("100.00")


def test_load_update_rejects_negative_rate() -> None:
    with pytest.raises(ValueError):
        LoadUpdate.model_validate({"expected_concurrency_version": 1, "rate": -1})


def test_parse_extracted_fields_coerce_rate() -> None:
    ex = LoadParseExtractedFields.model_validate({"rate": 1800, "customer_rate": "2100.55"})
    assert ex.rate == Decimal("1800.00")
    assert ex.customer_rate == Decimal("2100.55")


@pytest.mark.parametrize(
    "bad",
    [
        Decimal("NaN"),
        Decimal("Infinity"),
        Decimal("-Infinity"),
        float("nan"),
        float("inf"),
        float("-inf"),
        "NaN",
        "Infinity",
    ],
)
def test_parse_rate_rejects_non_finite(bad: object) -> None:
    with pytest.raises(ValueError, match="finite monetary amount"):
        parse_load_rate(bad)


def test_load_create_rejects_nan_rate_via_pydantic() -> None:
    with pytest.raises(ValueError, match="finite monetary amount"):
        LoadCreate.model_validate({"status": "draft", "rate": math.nan})


def test_load_update_rejects_infinite_customer_rate_via_pydantic() -> None:
    with pytest.raises(ValueError, match="finite monetary amount"):
        LoadUpdate.model_validate(
            {"expected_concurrency_version": 1, "customer_rate": Decimal("Infinity")}
        )
