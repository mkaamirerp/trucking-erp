"""Checkpoint 1: provider-neutral TruckERP operational transaction contract."""

from __future__ import annotations

import inspect
import os
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from fastapi import HTTPException
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("ALLOW_TENANT_RESOLUTION_SHORTCUTS", "true")

from app.core.db_url import to_async_pg_url
from app.models.fuel import FuelSourceBatch, FuelTransaction
from app.schemas.fuel import (
    OPERATIONAL_TRANSACTION_FIELD_NAMES,
    FuelProcessedOperationalTransactionOut,
    fuel_transaction_to_operational_out,
)
from app.services.fuel_canonical import BATCH_STATUS_FINALIZED
from app.services.fuel_processed_read import get_processed_fuel_batch
from app.services.fuel_source_duplicate_gate import sha256_hex
from tests.support.integration_isolation import require_integration_tenant_database_url

TENANT_A = 53
TENANT_B = 54
TEST_PROVIDER = "TEST_PROVIDER"


def _tenant_url() -> str:
    return to_async_pg_url(require_integration_tenant_database_url(context="fuel_operational_contract"))


def _minimal_txn(**overrides) -> FuelTransaction:
    base = {
        "id": 1,
        "tenant_id": TENANT_A,
        "batch_id": 10,
        "source_row_order": 1,
        "source_vendor": "BVD",
        "provider_event_type": "PURCHASE",
        "transaction_datetime_source": "2025-01-15",
        "transaction_timezone_source": "UNKNOWN",
        "provider_raw": {},
    }
    base.update(overrides)
    return FuelTransaction(**base)


def _operational_payload(row: object) -> dict:
    if hasattr(row, "model_dump"):
        return row.model_dump(mode="json")
    return FuelProcessedOperationalTransactionOut.model_validate(row).model_dump(mode="json")


async def _insert_finalized_batch(
    session,
    *,
    tenant_id: int,
    provider_code: str,
    token: str,
) -> FuelSourceBatch:
    now = datetime.now(timezone.utc)
    ref = f"cp1-operational-{provider_code.lower()}-{token}"
    batch = FuelSourceBatch(
        tenant_id=tenant_id,
        provider_code=provider_code,
        source_type="PDF",
        status=BATCH_STATUS_FINALIZED,
        finalized_at=now,
        invoice_number=f"CP1-{token[:8]}",
        source_import_ref=ref,
        source_hash=sha256_hex(ref.encode("utf-8")),
    )
    session.add(batch)
    await session.flush()
    return batch


async def _insert_canonical_txn(
    session,
    batch: FuelSourceBatch,
    *,
    source_row_order: int,
    source_vendor: str,
    sparse: bool,
) -> FuelTransaction:
    common = {
        "tenant_id": batch.tenant_id,
        "batch_id": batch.id,
        "source_row_order": source_row_order,
        "source_vendor": source_vendor,
        "provider_event_type": "PURCHASE",
        "transaction_datetime_source": "2025-06-01",
        "transaction_timezone_source": "DATE_ONLY",
        "provider_raw": {},
    }
    if sparse:
        txn = FuelTransaction(**common)
    else:
        txn = FuelTransaction(
            **common,
            transaction_date=date(2025, 6, 1),
            unit_number_snapshot="UNIT-42",
            card_or_account_id="CARD-9",
            product_code_raw="DF",
            quantity=Decimal("50.0000"),
            quantity_unit="L",
            total_amount=Decimal("125.50"),
            currency="USD",
            classification="FUEL",
        )
    session.add(txn)
    await session.flush()
    return txn


async def _purge_batch(session, *, tenant_id: int, batch_id: int) -> None:
    await session.execute(
        delete(FuelTransaction).where(
            FuelTransaction.tenant_id == tenant_id,
            FuelTransaction.batch_id == batch_id,
        )
    )
    await session.execute(
        delete(FuelSourceBatch).where(
            FuelSourceBatch.tenant_id == tenant_id,
            FuelSourceBatch.id == batch_id,
        )
    )


def test_operational_mapper_field_contract_is_fixed() -> None:
    assert OPERATIONAL_TRANSACTION_FIELD_NAMES == frozenset(
        FuelProcessedOperationalTransactionOut.model_fields.keys()
    )
    assert "id" in OPERATIONAL_TRANSACTION_FIELD_NAMES
    assert "unit_number_snapshot" in OPERATIONAL_TRANSACTION_FIELD_NAMES
    assert "provider_raw" in OPERATIONAL_TRANSACTION_FIELD_NAMES


def test_operational_mapper_has_no_provider_branches() -> None:
    from app.schemas import fuel as fuel_schemas

    source = inspect.getsource(fuel_schemas.fuel_transaction_to_operational_out)
    normalized = source.replace(" ", "").lower()
    assert "ifprovider" not in normalized
    assert "bvd" not in normalized
    assert "nationwide" not in normalized
    assert "fuel_bvd" not in normalized
    assert "fuel_nationwide" not in normalized


def test_operational_processed_read_has_no_native_table_imports() -> None:
    import app.services.fuel_processed_read as mod

    source = inspect.getsource(mod)
    assert "fuel_bvd" not in source.lower()
    assert "fuel_nationwide" not in source.lower()
    assert "getFuelBvd" not in source


def test_bvd_and_nationwide_and_test_provider_same_json_keys() -> None:
    bvd = fuel_transaction_to_operational_out(
        _minimal_txn(id=1, source_vendor="BVD", product_code_raw="DF", total_amount=Decimal("1.00"))
    )
    nw = fuel_transaction_to_operational_out(
        _minimal_txn(
            id=2,
            source_vendor="NATIONWIDE",
            product="TA",
            unit_number_snapshot="U-9",
            total_amount=None,
        )
    )
    testp = fuel_transaction_to_operational_out(
        _minimal_txn(id=3, source_vendor=TEST_PROVIDER, total_amount=Decimal("10"))
    )
    keys_bvd = set(bvd.model_dump(mode="json").keys())
    keys_nw = set(nw.model_dump(mode="json").keys())
    keys_test = set(testp.model_dump(mode="json").keys())
    assert keys_bvd == OPERATIONAL_TRANSACTION_FIELD_NAMES
    assert keys_nw == keys_bvd
    assert keys_test == keys_bvd


def test_missing_fields_serialize_as_null() -> None:
    row = fuel_transaction_to_operational_out(_minimal_txn(driver_id=None, truck_id=None, product=None))
    payload = row.model_dump(mode="json")
    assert payload["driver_id"] is None
    assert payload["truck_id"] is None
    assert payload["product"] is None
    assert payload["owner_operator_payee_id"] is None
    assert payload["settlement_deduction_candidate"] is None


def test_test_provider_operational_row() -> None:
    row = fuel_transaction_to_operational_out(
        _minimal_txn(
            source_vendor=TEST_PROVIDER,
            classification="FUEL",
            currency="USD",
            total_amount=Decimal("42.50"),
        )
    )
    payload = row.model_dump(mode="json")
    assert payload["source_vendor"] == TEST_PROVIDER
    assert set(payload.keys()) == OPERATIONAL_TRANSACTION_FIELD_NAMES


@pytest.mark.asyncio
async def test_processed_batch_operational_contract_bvd_and_nationwide() -> None:
    """Hermetic: creates finalized canonical batches on tenant_pytest; no demo data."""
    token = uuid.uuid4().hex
    engine = create_async_engine(_tenant_url())
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    bvd_batch_id: int | None = None
    nw_batch_id: int | None = None

    try:
        async with session_maker() as session:
            bvd_batch = await _insert_finalized_batch(
                session, tenant_id=TENANT_A, provider_code="BVD", token=f"bvd-{token}"
            )
            nw_batch = await _insert_finalized_batch(
                session, tenant_id=TENANT_A, provider_code="NATIONWIDE", token=f"nw-{token}"
            )
            await _insert_canonical_txn(
                session, bvd_batch, source_row_order=1, source_vendor="BVD", sparse=False
            )
            await _insert_canonical_txn(
                session, bvd_batch, source_row_order=2, source_vendor="BVD", sparse=True
            )
            await _insert_canonical_txn(
                session, nw_batch, source_row_order=1, source_vendor="NATIONWIDE", sparse=True
            )
            await _insert_canonical_txn(
                session, nw_batch, source_row_order=2, source_vendor="NATIONWIDE", sparse=False
            )
            await _insert_canonical_txn(
                session, nw_batch, source_row_order=3, source_vendor="NATIONWIDE", sparse=True
            )
            bvd_batch_id = int(bvd_batch.id)
            nw_batch_id = int(nw_batch.id)
            await session.commit()

        async with session_maker() as session:
            bvd_detail = await get_processed_fuel_batch(
                session, tenant_id=TENANT_A, batch_id=bvd_batch_id
            )
            nw_detail = await get_processed_fuel_batch(
                session, tenant_id=TENANT_A, batch_id=nw_batch_id
            )

        assert len(bvd_detail["operational_transactions"]) == 2
        assert len(nw_detail["operational_transactions"]) == 3
        assert len(bvd_detail["operational_transactions"]) == len(bvd_detail["canonical_transactions"])
        assert len(nw_detail["operational_transactions"]) == len(nw_detail["canonical_transactions"])

        bvd_keys = set(_operational_payload(bvd_detail["operational_transactions"][0]).keys())
        nw_keys = set(_operational_payload(nw_detail["operational_transactions"][0]).keys())
        assert bvd_keys == nw_keys == OPERATIONAL_TRANSACTION_FIELD_NAMES

        def _by_row_order(ops: list, order: int) -> dict:
            for row in ops:
                payload = _operational_payload(row)
                if payload["source_row_order"] == order:
                    return payload
            raise AssertionError(f"missing source_row_order={order}")

        bvd_rich = _by_row_order(bvd_detail["operational_transactions"], 1)
        bvd_sparse = _by_row_order(bvd_detail["operational_transactions"], 2)
        nw_sparse = _by_row_order(nw_detail["operational_transactions"], 1)
        nw_rich = _by_row_order(nw_detail["operational_transactions"], 2)

        assert bvd_rich["source_vendor"] == "BVD"
        assert nw_rich["source_vendor"] == "NATIONWIDE"
        assert bvd_rich["product_code_raw"] == "DF"
        assert bvd_rich["total_amount"] == "125.5000"
        assert bvd_sparse["product_code_raw"] is None
        assert bvd_sparse["driver_id"] is None
        assert nw_sparse["total_amount"] is None
        assert nw_rich["product_code_raw"] == "DF"
        assert nw_rich["total_amount"] == "125.5000"
    finally:
        async with session_maker() as session:
            if bvd_batch_id is not None:
                await _purge_batch(session, tenant_id=TENANT_A, batch_id=bvd_batch_id)
            if nw_batch_id is not None:
                await _purge_batch(session, tenant_id=TENANT_A, batch_id=nw_batch_id)
            await session.commit()
        await engine.dispose()


@pytest.mark.asyncio
async def test_processed_batch_operational_tenant_isolation() -> None:
    token = uuid.uuid4().hex
    engine = create_async_engine(_tenant_url())
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    batch_id: int | None = None

    try:
        async with session_maker() as session:
            batch = await _insert_finalized_batch(
                session, tenant_id=TENANT_A, provider_code="BVD", token=f"iso-{token}"
            )
            await _insert_canonical_txn(
                session, batch, source_row_order=1, source_vendor="BVD", sparse=False
            )
            batch_id = int(batch.id)
            await session.commit()

        async with session_maker() as session:
            with pytest.raises(HTTPException) as exc:
                await get_processed_fuel_batch(session, tenant_id=TENANT_B, batch_id=batch_id)
            assert exc.value.status_code == 404
    finally:
        async with session_maker() as session:
            if batch_id is not None:
                await _purge_batch(session, tenant_id=TENANT_A, batch_id=batch_id)
            await session.commit()
        await engine.dispose()
