"""Per-currency discount/total rollups on processed Fuel summaries (provider-neutral)."""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.services.fuel_processed_read import (
    _currency_financial_summaries_from_transactions,
    _discount_rollup_by_currency,
    _money_amounts_by_currency,
    _summary_from_batch,
)


def _txn(currency: str, total: str, discount: str | None) -> MagicMock:
    row = MagicMock()
    row.currency = currency
    row.currency_raw = None
    row.total_amount = Decimal(total)
    row.provider_discount_amount = Decimal(discount) if discount is not None else None
    row.card_or_account_id = "CARD1"
    return row


def _batch() -> SimpleNamespace:
    return SimpleNamespace(
        id=1,
        provider_code="GENERIC",
        source_import_ref="x",
        source_storage_ref="y",
        account_reference="acct",
        invoice_number="INV-1",
        statement_start=None,
        statement_end=None,
        due_date=None,
        finalized_at=None,
        status="FINALIZED",
    )


def test_money_never_sums_different_currencies() -> None:
    rows = [
        _txn("USD", "100.00", "5.00"),
        _txn("USD", "50.00", "2.50"),
        _txn("CAD", "200.00", "0"),
        _txn("EUR", "8421.55", "125.20"),
    ]
    assert _money_amounts_by_currency(rows) == {
        "USD": Decimal("150.00"),
        "CAD": Decimal("200.00"),
        "EUR": Decimal("8421.55"),
    }
    assert _discount_rollup_by_currency(rows) == {
        "USD": Decimal("7.50"),
        "CAD": Decimal("0"),
        "EUR": Decimal("125.20"),
    }


def test_one_currency_eur_summary() -> None:
    lines = _currency_financial_summaries_from_transactions([_txn("EUR", "8421.55", "125.20")])
    assert len(lines) == 1
    assert lines[0]["currency"] == "EUR"
    assert Decimal(lines[0]["total_amount"]) == Decimal("8421.55")
    assert Decimal(lines[0]["discount_amount"]) == Decimal("125.20")


def test_two_currencies_mixed_summary() -> None:
    lines = _currency_financial_summaries_from_transactions(
        [
            _txn("USD", "5197.67", "204.72"),
            _txn("CAD", "1263.85", "0"),
        ]
    )
    assert [line["currency"] for line in lines] == ["CAD", "USD"]
    assert Decimal(lines[0]["discount_amount"]) == Decimal("0")
    assert Decimal(lines[1]["discount_amount"]) == Decimal("204.72")


def test_three_currencies_sorted_by_iso_code() -> None:
    lines = _currency_financial_summaries_from_transactions(
        [
            _txn("NZD", "10", "1"),
            _txn("AUD", "20", "2"),
            _txn("MXN", "30", "3"),
        ]
    )
    assert [line["currency"] for line in lines] == ["AUD", "MXN", "NZD"]
    assert len(lines) == 3


def test_known_zero_discount_not_null() -> None:
    lines = _currency_financial_summaries_from_transactions([_txn("USD", "100", "0")])
    assert lines[0]["discount_amount"] == "0"


def test_missing_discount_stays_unknown_not_zero() -> None:
    lines = _currency_financial_summaries_from_transactions(
        [
            _txn("USD", "100", None),
            _txn("USD", "50", "5"),
        ]
    )
    assert len(lines) == 1
    assert lines[0]["discount_amount"] is None


def test_missing_discount_all_lines_unknown() -> None:
    lines = _currency_financial_summaries_from_transactions([_txn("GBP", "99", None)])
    assert lines[0]["discount_amount"] is None


def test_grouping_uses_canonical_currency_column_not_raw_alias_rules() -> None:
    row = MagicMock()
    row.currency = "EUR"
    row.currency_raw = "CN"
    row.total_amount = Decimal("100")
    row.provider_discount_amount = Decimal("1")
    row.card_or_account_id = "C1"
    lines = _currency_financial_summaries_from_transactions([row])
    assert lines == [
        {
            "currency": "EUR",
            "total_amount": "100",
            "discount_amount": "1",
        }
    ]


def test_legacy_raw_token_compat_when_canonical_currency_missing() -> None:
    row = MagicMock()
    row.currency = None
    row.currency_raw = "US"
    row.total_amount = Decimal("50")
    row.provider_discount_amount = None
    row.card_or_account_id = "C1"
    lines = _currency_financial_summaries_from_transactions([row])
    assert lines[0]["currency"] == "USD"
    assert lines[0]["discount_amount"] is None


def test_summary_from_batch_includes_dynamic_financial_lines() -> None:
    summary = _summary_from_batch(
        _batch(),
        transactions=[
            _txn("USD", "5197.67", "145.12"),
            _txn("CAD", "1263.85", "0"),
        ],
        controls=[],
    )
    lines = summary["currency_financial_summaries"]
    assert len(lines) == 2
    assert lines[0]["currency"] == "CAD"
    assert Decimal(lines[0]["total_amount"]) == Decimal("1263.85")
    assert Decimal(lines[0]["discount_amount"]) == Decimal("0")
    assert lines[1]["currency"] == "USD"
    assert Decimal(lines[1]["discount_amount"]) == Decimal("145.12")
