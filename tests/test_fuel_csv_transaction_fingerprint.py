"""CSV normalized transaction fingerprint (duplicate gate hook)."""

from __future__ import annotations

from app.services.fuel_source_duplicate_gate import (
    FUEL_DUPLICATE_EXACT,
    FUEL_DUPLICATE_TRANSACTIONS,
    FUEL_TRANSACTION_OVERLAP,
    evaluate_csv_duplicate_layers,
    fuel_csv_transaction_fingerprint,
)


def _txn(**kwargs: str) -> dict:
    base = {
        "transaction_date": "2026-07-23 02:17:56",
        "auth_code": "A204040667-TA",
        "unit_number": "1100",
        "prod": "TA",
        "qty": "719.50",
        "final_amt": "1,610.96",
        "cur": "CN",
    }
    base.update(kwargs)
    return base


def test_fingerprint_stable_across_row_order() -> None:
    a = fuel_csv_transaction_fingerprint([_txn(), _txn(auth_code="B", unit_number="1104")])
    b = fuel_csv_transaction_fingerprint([_txn(auth_code="B", unit_number="1104"), _txn()])
    assert a == b


def test_fingerprint_ignores_whitespace_and_commas_in_amounts() -> None:
    t1 = [_txn(final_amt="1,610.96")]
    t2 = [_txn(final_amt="1610.96")]
    assert fuel_csv_transaction_fingerprint(t1) == fuel_csv_transaction_fingerprint(t2)


def test_fingerprint_changes_when_new_transaction() -> None:
    base = fuel_csv_transaction_fingerprint([_txn()])
    extended = fuel_csv_transaction_fingerprint([_txn(), _txn(auth_code="NEW-TXN")])
    assert base != extended


def test_csv_exact_duplicate_by_raw_sha() -> None:
    conflict = evaluate_csv_duplicate_layers(
        raw_sha256="abc",
        existing_raw_sha={"abc"},
        document_identity_key=None,
        existing_document_keys=set(),
        transaction_fingerprint="fp1",
        existing_fingerprints=set(),
        overlapping_auth_codes=set(),
    )
    assert conflict is not None
    assert conflict.code == FUEL_DUPLICATE_EXACT


def test_csv_duplicate_by_transaction_fingerprint() -> None:
    conflict = evaluate_csv_duplicate_layers(
        raw_sha256="newraw",
        existing_raw_sha=set(),
        document_identity_key=None,
        existing_document_keys=set(),
        transaction_fingerprint="fp1",
        existing_fingerprints={"fp1"},
        overlapping_auth_codes=set(),
    )
    assert conflict is not None
    assert conflict.code == FUEL_DUPLICATE_TRANSACTIONS


def test_csv_overlap_not_silent() -> None:
    conflict = evaluate_csv_duplicate_layers(
        raw_sha256="newraw",
        existing_raw_sha=set(),
        document_identity_key=None,
        existing_document_keys=set(),
        transaction_fingerprint="fp-new",
        existing_fingerprints={"fp-old"},
        overlapping_auth_codes={"A204040667-TA"},
    )
    assert conflict is not None
    assert conflict.code == FUEL_TRANSACTION_OVERLAP
