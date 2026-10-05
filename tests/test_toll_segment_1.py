"""Toll Segment 1: canonical batch/transaction schema foundation."""

from __future__ import annotations

from sqlalchemy import CheckConstraint, ForeignKeyConstraint, Numeric, UniqueConstraint

from app.models.toll import (
    FILE_FORMAT_CSV,
    FILE_FORMAT_PDF,
    READ_TYPE_DEVICE,
    READ_TYPE_PLATE,
    SOURCE_TYPE_API,
    SOURCE_TYPE_FILE,
    SOURCE_TYPE_MANUAL,
    TOLL_AMOUNT_PRECISION,
    TRANSACTION_TYPE_NORMAL,
    TRANSACTION_TYPE_VIOLATION,
    TollSourceBatch,
    TollTransaction,
)

FORBIDDEN_TOLL_COLUMNS = frozenset(
    {
        "owner_operator_payee_id",
        "driver_id",
        "responsible_payee_id",
        "financial_responsibility",
        "settlement_deduction_candidate",
        "settlement_deduction_basis_amount",
        "settlement_ref",
        "owner_operator_charge_amount",
        "downstream_module",
        "downstream_ack_status",
        "downstream_ack_ref",
        "pricing_agreement_ref",
        "quantity",
        "unit_price",
        "gst_amount",
        "hst_amount",
        "pst_amount",
        "qst_amount",
        "identifier",
    }
)


def _constraint_names(table) -> set[str]:
    return {c.name for c in table.constraints if getattr(c, "name", None)}


def _unique_names(table) -> set[str]:
    return {uq.name for uq in table.constraints if isinstance(uq, UniqueConstraint) and uq.name}


def _fk_names(table) -> set[str]:
    return {
        fk.name
        for fk in table.constraints
        if isinstance(fk, ForeignKeyConstraint) and fk.name
    }


def _check_sql(table, name: str) -> str:
    matches = [
        c
        for c in table.constraints
        if isinstance(c, CheckConstraint) and c.name == name
    ]
    assert len(matches) == 1, name
    return str(matches[0].sqltext)


def test_three_identities_are_separate_columns() -> None:
    cols = TollTransaction.__table__.c
    assert "id" in cols
    assert "provider_transaction_id" in cols
    assert "source_row_order" in cols
    assert "source_row_id" in cols
    assert cols["id"].primary_key is True
    assert cols["provider_transaction_id"].primary_key is False
    assert cols["provider_transaction_id"].nullable is True
    assert cols["source_row_order"].nullable is False
    names = _unique_names(TollTransaction.__table__)
    assert "uq_toll_transactions_tenant_id_id" in names
    assert "uq_toll_transactions_tenant_batch_source_row_order" in names
    unique_provider_txn = [
        ix
        for ix in TollTransaction.__table__.indexes
        if ix.name == "ix_toll_transactions_tenant_provider_txn" and ix.unique
    ]
    assert unique_provider_txn == []


def test_date_unit_and_date_device_are_not_unique() -> None:
    unique_col_sets = [
        tuple(sorted(col.name for col in uq.columns))
        for uq in TollTransaction.__table__.constraints
        if isinstance(uq, UniqueConstraint)
    ]
    forbidden = {
        ("transaction_date", "truck_id"),
        ("tenant_id", "transaction_date", "truck_id"),
        ("tenant_id", "transaction_datetime", "truck_id"),
        ("tenant_id", "transaction_date", "unit_number_snapshot"),
        ("tenant_id", "transaction_datetime", "unit_number_snapshot"),
        ("tenant_id", "transaction_date", "device_number"),
        ("device_number", "transaction_date"),
        ("device_number", "transaction_datetime"),
    }
    for cols in unique_col_sets:
        assert cols not in forbidden
        assert "transaction_date" not in cols or "truck_id" not in cols
        assert "transaction_datetime" not in cols or "truck_id" not in cols
        assert "device_number" not in cols


def test_pull_indexes_cover_tenant_unit_and_datetime() -> None:
    named = {ix.name: ix for ix in TollTransaction.__table__.indexes}
    truck_ix = named["ix_toll_transactions_tenant_truck_datetime"]
    unit_ix = named["ix_toll_transactions_tenant_unit_datetime"]
    date_ix = named["ix_toll_transactions_tenant_date"]
    assert [c.name for c in truck_ix.columns] == ["tenant_id", "truck_id", "transaction_datetime"]
    assert truck_ix.unique is False
    assert [c.name for c in unit_ix.columns] == [
        "tenant_id",
        "unit_number_snapshot",
        "transaction_datetime",
    ]
    assert unit_ix.unique is False
    assert [c.name for c in date_ix.columns] == ["tenant_id", "transaction_date"]
    assert date_ix.unique is False


def test_batch_source_types_are_api_file_manual_not_pdf_csv() -> None:
    sql = _check_sql(TollSourceBatch.__table__, "ck_toll_source_batches_source_type")
    for code in (SOURCE_TYPE_API, SOURCE_TYPE_FILE, SOURCE_TYPE_MANUAL):
        assert f"'{code}'" in sql
    assert "'PDF'" not in sql
    assert "'CSV'" not in sql
    format_sql = _check_sql(TollSourceBatch.__table__, "ck_toll_source_batches_file_format")
    assert f"'{FILE_FORMAT_PDF}'" in format_sql
    assert f"'{FILE_FORMAT_CSV}'" in format_sql
    file_only = _check_sql(TollSourceBatch.__table__, "ck_toll_source_batches_file_format_file_only")
    assert "FILE" in file_only
    assert TollSourceBatch.__table__.c["file_format"].nullable is True
    assert TollSourceBatch.__table__.c["provider_code"].nullable is True
    assert TollSourceBatch.__table__.c["provider_connection_id"].nullable is True
    assert TollSourceBatch.__table__.c["account_reference"].nullable is True


def test_batch_file_hash_is_indexed_not_unique() -> None:
    hash_indexes = [
        ix
        for ix in TollSourceBatch.__table__.indexes
        if ix.name == "ix_toll_source_batches_tenant_source_hash"
    ]
    assert len(hash_indexes) == 1
    assert hash_indexes[0].unique is False
    assert [c.name for c in hash_indexes[0].columns] == ["tenant_id", "source_hash"]
    unique_col_sets = [
        tuple(sorted(col.name for col in uq.columns))
        for uq in TollSourceBatch.__table__.constraints
        if isinstance(uq, UniqueConstraint)
    ]
    assert ("source_hash", "tenant_id") not in unique_col_sets
    assert ("source_hash",) not in unique_col_sets


def test_source_import_ref_is_indexed_not_unique() -> None:
    ref_indexes = [
        ix
        for ix in TollSourceBatch.__table__.indexes
        if ix.name == "ix_toll_source_batches_tenant_source_import_ref"
    ]
    assert len(ref_indexes) == 1
    assert ref_indexes[0].unique is False
    assert [c.name for c in ref_indexes[0].columns] == ["tenant_id", "source_import_ref"]
    unique_col_sets = [
        tuple(sorted(col.name for col in uq.columns))
        for uq in TollSourceBatch.__table__.constraints
        if isinstance(uq, UniqueConstraint)
    ]
    for cols in unique_col_sets:
        assert "source_import_ref" not in cols
    leftover_unique_names = {
        ix.name
        for ix in TollSourceBatch.__table__.indexes
        if ix.unique and "source_import_ref" in ix.name
    }
    assert leftover_unique_names == set()


def test_amount_is_numeric_not_float_and_has_locked_scale() -> None:
    col = TollTransaction.__table__.c["amount"]
    assert isinstance(col.type, Numeric)
    assert (col.type.precision, col.type.scale) == TOLL_AMOUNT_PRECISION
    assert col.nullable is False
    assert "quantity" not in TollTransaction.__table__.c
    assert "unit_price" not in TollTransaction.__table__.c


def test_transaction_type_and_read_type_are_locked() -> None:
    type_sql = _check_sql(TollTransaction.__table__, "ck_toll_transactions_transaction_type")
    assert f"'{TRANSACTION_TYPE_NORMAL}'" in type_sql
    assert f"'{TRANSACTION_TYPE_VIOLATION}'" in type_sql
    assert "REFUND" not in type_sql
    assert "REVERSAL" not in type_sql
    read_sql = _check_sql(TollTransaction.__table__, "ck_toll_transactions_read_type")
    assert f"'{READ_TYPE_DEVICE}'" in read_sql
    assert f"'{READ_TYPE_PLATE}'" in read_sql
    assert TollTransaction.__table__.c["read_type"].nullable is True
    assert TollTransaction.__table__.c["device_number"].nullable is True
    assert TollTransaction.__table__.c["plate_number"].nullable is True
    assert TollTransaction.__table__.c["plate_state"].nullable is True


def test_identifier_is_not_stored() -> None:
    assert "identifier" not in TollTransaction.__table__.c


def test_vehicle_fk_is_tenant_safe_and_nullable() -> None:
    assert TollTransaction.__table__.c["truck_id"].nullable is True
    assert TollTransaction.__table__.c["unit_number_snapshot"].nullable is True
    assert "fk_toll_transactions_truck_tenant" in _fk_names(TollTransaction.__table__)
    assert "fk_toll_transactions_batch_tenant" in _fk_names(TollTransaction.__table__)
    truck_fk = next(
        fk
        for fk in TollTransaction.__table__.constraints
        if isinstance(fk, ForeignKeyConstraint) and fk.name == "fk_toll_transactions_truck_tenant"
    )
    assert tuple(truck_fk.column_keys) == ("tenant_id", "truck_id")
    referred = {el.target_fullname for el in truck_fk.elements}
    assert referred == {"trucks.tenant_id", "trucks.id"}


def test_provider_raw_is_required_json_object() -> None:
    assert "ck_toll_transactions_provider_raw_object" in _constraint_names(TollTransaction.__table__)
    assert TollTransaction.__table__.c["provider_raw"].nullable is False


def test_no_payroll_settlement_or_oo_columns() -> None:
    cols = set(TollTransaction.__table__.c.keys()) | set(TollSourceBatch.__table__.c.keys())
    present = FORBIDDEN_TOLL_COLUMNS & cols
    assert present == set()


def test_no_provider_connection_fk_in_segment_1() -> None:
    batch_fks = _fk_names(TollSourceBatch.__table__)
    assert batch_fks == set()
