"""Fuel Segment 1: canonical batch/transaction schema foundation."""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest
from pydantic import ValidationError
from sqlalchemy import Numeric, UniqueConstraint

from app.models.fuel import FuelSourceBatch, FuelTransaction
from app.schemas.fuel import FuelTransactionOut, FuelTransactionSourceHydration
from app.services.fuel_canonical import (
    PROVIDER_EVENT_CREDIT,
    PROVIDER_EVENT_OTHER,
    PROVIDER_EVENT_PURCHASE,
    PROVIDER_EVENT_REFUND,
    PROVIDER_EVENT_REVERSAL,
    PROVIDER_EVENT_UNKNOWN,
    PROVIDER_EVENT_VOID,
    SOURCE_HYDRATION_FORBIDDEN_FIELDS,
    TZ_SOURCE_DATE_ONLY,
    TZ_SOURCE_PROVIDER_LOCAL_NO_ZONE,
    TZ_SOURCE_PROVIDER_SUPPLIED,
    FuelTimestampProvenanceError,
    assert_source_hydration_excludes_derived_fields,
    classify_currency,
    classify_provider_event_type,
    event_type_preserves_sign,
    interpret_provider_timestamp,
)
from app.services.fuel_money import (
    DISCOUNT_RATE_PRECISION,
    MONEY_PRECISION,
    QUANTITY_PRECISION,
    UNIT_PRICE_PRECISION,
    FuelFloatForbidden,
    decimal_json,
    preserve_source_numeric_string,
    quantize_discount_rate,
    quantize_money,
    quantize_quantity,
    quantize_unit_price,
    to_decimal,
)


def _numeric(col_name: str) -> Numeric:
    col = FuelTransaction.__table__.c[col_name]
    assert isinstance(col.type, Numeric)
    return col.type


def test_locked_numeric_precision_and_scale() -> None:
    assert (_numeric("quantity").precision, _numeric("quantity").scale) == QUANTITY_PRECISION
    assert (_numeric("unit_price").precision, _numeric("unit_price").scale) == UNIT_PRICE_PRECISION
    assert (
        _numeric("provider_discount_rate").precision,
        _numeric("provider_discount_rate").scale,
    ) == DISCOUNT_RATE_PRECISION
    money_cols = [
        "provider_discount_amount",
        "tax_amount",
        "hst_amount",
        "gst_amount",
        "pst_amount",
        "qst_amount",
        "missed_discount_amount",
        "out_of_network_fee",
        "pre_tax_amount",
        "billed_amount",
        "retail_amount",
        "total_amount",
        "owner_operator_charge_amount",
    ]
    for name in money_cols:
        assert (_numeric(name).precision, _numeric(name).scale) == MONEY_PRECISION
        assert FuelTransaction.__table__.c[name].nullable is True


def test_three_identities_are_separate_columns() -> None:
    cols = FuelTransaction.__table__.c
    assert "id" in cols
    assert "provider_transaction_identity" in cols
    assert "source_row_order" in cols
    assert "source_row_id" in cols
    assert cols["id"].primary_key is True
    assert cols["provider_transaction_identity"].primary_key is False
    assert cols["provider_transaction_identity"].nullable is True
    assert cols["source_row_order"].nullable is False
    names = {uq.name for uq in FuelTransaction.__table__.constraints if isinstance(uq, UniqueConstraint)}
    assert "uq_fuel_transactions_tenant_id_id" in names
    assert "uq_fuel_transactions_tenant_batch_source_row_order" in names
    unique_provider_txn = [
        ix
        for ix in FuelTransaction.__table__.indexes
        if ix.name == "ix_fuel_transactions_tenant_provider_txn" and ix.unique
    ]
    assert unique_provider_txn == []


def test_batch_file_hash_idempotency_is_tenant_scoped_not_global() -> None:
    hash_indexes = [
        ix for ix in FuelSourceBatch.__table__.indexes if ix.name == "ix_fuel_source_batches_tenant_source_hash"
    ]
    assert len(hash_indexes) == 1
    assert hash_indexes[0].unique is True
    col_names = [c.name for c in hash_indexes[0].columns]
    assert col_names == ["tenant_id", "source_hash"]


def test_source_truth_columns_separate_from_resolution_columns() -> None:
    cols = FuelTransaction.__table__.c
    for source in (
        "unit_number_snapshot",
        "card_or_account_id",
        "driver_name_snapshot",
        "provider_raw",
        "total_amount",
        "provider_event_type",
        "provider_event_type_raw",
        "currency_raw",
        "currency",
    ):
        assert source in cols
    for resolution in (
        "truck_id",
        "driver_id",
        "owner_operator_payee_id",
        "classification",
        "financial_responsibility",
        "pricing_agreement_ref",
        "settlement_ref",
        "owner_operator_charge_amount",
        "downstream_module",
        "downstream_ack_status",
        "downstream_ack_ref",
        "gate_status",
    ):
        assert cols[resolution].nullable is True
    assert cols["provider_raw"].nullable is False


def test_decimal_helpers_reject_float_and_quantize_half_even() -> None:
    with pytest.raises(FuelFloatForbidden):
        to_decimal(1.23)
    with pytest.raises(FuelFloatForbidden):
        quantize_money(12.50)
    with pytest.raises(FuelFloatForbidden):
        preserve_source_numeric_string(1.10)
    assert quantize_quantity("674.17006") == Decimal("674.1701")
    assert quantize_unit_price("1.6590014") == Decimal("1.659001")
    assert quantize_discount_rate("0.0350004") == Decimal("0.035000")
    assert quantize_money("-145.409") == Decimal("-145.4090")
    assert quantize_money("1.23455") == Decimal("1.2346")
    assert preserve_source_numeric_string("674.17006") == "674.17006"
    assert decimal_json(Decimal("-145.40")) == "-145.40"


def test_credit_refund_reversal_void_keep_negative_source_amounts() -> None:
    credit = FuelTransactionOut(
        id=1,
        tenant_id=53,
        batch_id=9,
        provider_transaction_identity="AUTH-1",
        source_row_order=2,
        source_vendor="BVD",
        provider_event_type=PROVIDER_EVENT_CREDIT,
        transaction_datetime_source="2026-06-09",
        transaction_timezone_source=TZ_SOURCE_DATE_ONLY,
        total_amount=Decimal("-45.6700"),
        provider_raw={"Final AMT": "-45.67"},
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    dumped = credit.model_dump(mode="json")
    assert dumped["provider_event_type"] == PROVIDER_EVENT_CREDIT
    assert dumped["total_amount"] == "-45.6700"
    assert dumped["total_amount"].startswith("-")
    assert dumped["id"] != dumped["provider_transaction_identity"]
    for event in (PROVIDER_EVENT_REFUND, PROVIDER_EVENT_REVERSAL, PROVIDER_EVENT_VOID):
        row = credit.model_copy(update={"provider_event_type": event, "id": 3})
        assert row.provider_event_type != PROVIDER_EVENT_PURCHASE
        assert row.total_amount < 0


def test_schema_rejects_float_total_amount() -> None:
    with pytest.raises(Exception):
        FuelTransactionOut(
            id=1,
            tenant_id=53,
            batch_id=9,
            source_row_order=1,
            source_vendor="BVD",
            provider_event_type=PROVIDER_EVENT_PURCHASE,
            transaction_datetime_source="2026-06-09",
            transaction_timezone_source=TZ_SOURCE_DATE_ONLY,
            total_amount=45.67,  # type: ignore[arg-type]
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )


def test_date_only_and_local_time_do_not_invent_timezone() -> None:
    date_only = interpret_provider_timestamp(
        source_text="2026-06-08",
        timezone_source=TZ_SOURCE_DATE_ONLY,
        parsed_date=date(2026, 6, 8),
    )
    assert date_only["transaction_datetime"] is None
    assert date_only["transaction_timezone"] is None
    assert date_only["transaction_datetime_source"] == "2026-06-08"
    naive = datetime(2026, 6, 9, 14, 32)
    with pytest.raises(FuelTimestampProvenanceError):
        interpret_provider_timestamp(
            source_text="Jun 09 2026 14:32",
            timezone_source=TZ_SOURCE_PROVIDER_LOCAL_NO_ZONE,
            parsed_datetime=naive,
        )
    local = interpret_provider_timestamp(
        source_text="Jun 09 2026 14:32",
        timezone_source=TZ_SOURCE_PROVIDER_LOCAL_NO_ZONE,
        parsed_date=date(2026, 6, 9),
    )
    assert local["transaction_datetime"] is None
    supplied = interpret_provider_timestamp(
        source_text="2026-06-09T14:32:00-04:00",
        timezone_source=TZ_SOURCE_PROVIDER_SUPPLIED,
        utc_offset="-04:00",
        parsed_datetime=datetime(2026, 6, 9, 18, 32, tzinfo=timezone.utc),
    )
    assert supplied["transaction_datetime"] is not None
    assert supplied["transaction_datetime"].tzinfo is not None
    utc_next_day = datetime(2026, 6, 10, 3, 30, tzinfo=timezone.utc)
    local_late = interpret_provider_timestamp(
        source_text="2026-06-09T23:30:00-04:00",
        timezone_source=TZ_SOURCE_PROVIDER_SUPPLIED,
        utc_offset="-04:00",
        parsed_date=date(2026, 6, 9),
        parsed_datetime=utc_next_day,
    )
    assert local_late["transaction_date"] == date(2026, 6, 9)
    assert local_late["transaction_datetime"].date() == date(2026, 6, 10)
    missing_local_date = interpret_provider_timestamp(
        source_text="2026-06-09T23:30:00-04:00",
        timezone_source=TZ_SOURCE_PROVIDER_SUPPLIED,
        utc_offset="-04:00",
        parsed_datetime=utc_next_day,
    )
    assert missing_local_date["transaction_date"] is None


def test_provider_raw_is_json_object() -> None:
    raw_ck = [c.name for c in FuelTransaction.__table__.constraints if getattr(c, "name", None)]
    assert "ck_fuel_transactions_provider_raw_object" in raw_ck
    batch_ck = [c.name for c in FuelSourceBatch.__table__.constraints if getattr(c, "name", None)]
    assert "ck_fuel_source_batches_control_totals_object" not in batch_ck
    assert "provider_control_totals_json" not in FuelSourceBatch.__table__.c


def test_resolution_fields_are_not_required_to_construct_source_row() -> None:
    row = SimpleNamespace(
        id=11,
        tenant_id=53,
        batch_id=4,
        provider_transaction_identity=None,
        source_row_order=1,
        source_row_id="line-1",
        source_vendor="NATIONWIDE",
        account_reference=None,
        provider_event_type=PROVIDER_EVENT_PURCHASE,
        provider_event_type_raw="PURCHASE",
        transaction_datetime_source="2026-06-08",
        transaction_timezone_source=TZ_SOURCE_DATE_ONLY,
        transaction_timezone=None,
        transaction_utc_offset=None,
        transaction_date=date(2026, 6, 8),
        transaction_datetime=None,
        unit_number_snapshot="794",
        card_or_account_id="XXXXX07588",
        driver_name_snapshot=None,
        quantity=Decimal("154.2700"),
        unit_price=Decimal("4.685000"),
        provider_discount_rate=None,
        provider_discount_amount=Decimal("34.5600"),
        tax_amount=None,
        hst_amount=None,
        gst_amount=None,
        pst_amount=None,
        qst_amount=None,
        missed_discount_amount=None,
        out_of_network_fee=None,
        pre_tax_amount=None,
        billed_amount=None,
        retail_amount=None,
        total_amount=Decimal("722.7500"),
        owner_operator_charge_amount=None,
        quantity_unit="GAL",
        unit_price_basis="FINAL_GALLON_PRICE",
        currency_raw="USD",
        currency="USD",
        processing_network=None,
        merchant_network="TA-Petro",
        provider_raw={"Volume": "154.27", "Total": "722.75"},
        truck_id=None,
        driver_id=None,
        owner_operator_payee_id=None,
        classification=None,
        financial_responsibility=None,
        pricing_agreement_ref=None,
        settlement_ref=None,
        downstream_module=None,
        downstream_ack_status=None,
        downstream_ack_ref=None,
        gate_status=None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    out = FuelTransactionOut.model_validate(row)
    dumped = out.model_dump(mode="json")
    assert dumped["driver_name_snapshot"] is None
    assert dumped["truck_id"] is None
    assert dumped["driver_id"] is None
    assert dumped["total_amount"] == "722.7500"
    assert dumped["provider_raw"]["Volume"] == "154.27"
    assert dumped["provider_transaction_identity"] is None
    assert dumped["source_row_id"] == "line-1"
    assert dumped["id"] == 11
    assert dumped["owner_operator_charge_amount"] is None


def test_provider_event_type_raw_is_not_canonical_and_unknown_is_never_purchase() -> None:
    event_ck = [
        c
        for c in FuelTransaction.__table__.constraints
        if getattr(c, "name", None) == "ck_fuel_transactions_provider_event_type"
    ]
    assert len(event_ck) == 1
    sql = str(event_ck[0].sqltext)
    for code in (
        PROVIDER_EVENT_PURCHASE,
        PROVIDER_EVENT_CREDIT,
        PROVIDER_EVENT_REFUND,
        PROVIDER_EVENT_REVERSAL,
        PROVIDER_EVENT_VOID,
        PROVIDER_EVENT_OTHER,
        PROVIDER_EVENT_UNKNOWN,
    ):
        assert code in sql

    raw, canonical = classify_provider_event_type("PURCHASE")
    assert raw == "PURCHASE"
    assert canonical == PROVIDER_EVENT_PURCHASE
    raw, canonical = classify_provider_event_type("Cr")
    assert raw == "Cr"
    assert canonical == PROVIDER_EVENT_UNKNOWN
    assert canonical != PROVIDER_EVENT_PURCHASE
    raw, canonical = classify_provider_event_type("ADJ-99")
    assert raw == "ADJ-99"
    assert canonical == PROVIDER_EVENT_UNKNOWN
    raw, canonical = classify_provider_event_type(None)
    assert raw is None
    assert canonical == PROVIDER_EVENT_UNKNOWN
    raw, canonical = classify_provider_event_type("OTHER")
    assert raw == "OTHER"
    assert canonical == PROVIDER_EVENT_OTHER
    event_type_preserves_sign(PROVIDER_EVENT_CREDIT, Decimal("-12.3400"))
    with pytest.raises(ValueError, match="positive purchase"):
        event_type_preserves_sign(PROVIDER_EVENT_CREDIT, Decimal("12.3400"))
    event_type_preserves_sign(PROVIDER_EVENT_UNKNOWN, Decimal("12.3400"))


def test_currency_raw_is_preserved_when_canonical_iso_is_mapped() -> None:
    raw, canonical = classify_currency("CN")
    assert raw == "CN"
    assert canonical == "CAD"
    raw, canonical = classify_currency("cn")
    assert raw == "cn"
    assert canonical == "CAD"
    raw, canonical = classify_currency("USD")
    assert raw == "USD"
    assert canonical == "USD"
    raw, canonical = classify_currency("ZZ")
    assert raw == "ZZ"
    assert canonical is None
    cols = FuelTransaction.__table__.c
    assert cols["currency_raw"].nullable is True
    assert cols["currency"].nullable is True


def test_owner_operator_charge_is_derived_and_forbidden_in_source_hydration() -> None:
    assert "owner_operator_charge_amount" in SOURCE_HYDRATION_FORBIDDEN_FIELDS
    assert "owner_operator_charge_amount" not in FuelTransactionSourceHydration.model_fields
    assert "currency" not in FuelTransactionSourceHydration.model_fields
    assert "provider_event_type" not in FuelTransactionSourceHydration.model_fields
    source = FuelTransactionSourceHydration(
        source_row_order=1,
        source_vendor="BVD",
        provider_event_type_raw="SALE",
        transaction_datetime_source="2026-07-23 02:17:56",
        transaction_timezone_source=TZ_SOURCE_PROVIDER_LOCAL_NO_ZONE,
        transaction_date=date(2026, 7, 23),
        currency_raw="CN",
        total_amount=Decimal("1610.9600"),
        provider_raw={"CUR": "CN", "Final AMT": "1610.96"},
    )
    dumped = source.model_dump()
    assert "owner_operator_charge_amount" not in dumped
    raw_event, canonical_event = classify_provider_event_type(source.provider_event_type_raw)
    assert raw_event == "SALE"
    assert canonical_event == PROVIDER_EVENT_UNKNOWN
    raw_ccy, canonical_ccy = classify_currency(source.currency_raw)
    assert raw_ccy == "CN"
    assert canonical_ccy == "CAD"
    with pytest.raises(ValidationError):
        FuelTransactionSourceHydration(
            source_row_order=1,
            source_vendor="BVD",
            transaction_datetime_source="2026-07-23",
            transaction_timezone_source=TZ_SOURCE_DATE_ONLY,
            owner_operator_charge_amount=Decimal("12.0000"),
        )
    with pytest.raises(ValueError, match="derived/resolution"):
        assert_source_hydration_excludes_derived_fields(
            {"total_amount": Decimal("10.0000"), "owner_operator_charge_amount": Decimal("9.0000")}
        )
    assert FuelTransaction.__table__.c["owner_operator_charge_amount"].nullable is True
