"""Checkpoint 1: provider-neutral TruckERP operational transaction contract."""

from __future__ import annotations

import inspect
import os
import uuid
from datetime import date, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import select
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
from app.services.fuel_processed_read import get_processed_fuel_batch
from app.services.fuel_canonical import BATCH_STATUS_FINALIZED
from tests.support.integration_isolation import require_integration_tenant_database_url

REPO = Path(__file__).resolve().parents[1]
TENANT_A = 53
TENANT_B = 54
TEST_PROVIDER = "TEST_PROVIDER"


def _tenant_url() -> str | None:
    try:
        return to_async_pg_url(require_integration_tenant_database_url(context="fuel_operational_contract"))
    except Exception:
        return None


REQUIRES_DB = _tenant_url() is None


def _minimal_txn(**overrides) -> FuelTransaction:
    from datetime import datetime

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


def test_operational_mapper_field_contract_is_fixed() -> None:
    assert OPERATIONAL_TRANSACTION_FIELD_NAMES == frozenset(
        FuelProcessedOperationalTransactionOut.model_fields.keys()
    )
    assert "id" in OPERATIONAL_TRANSACTION_FIELD_NAMES
    assert "unit_number_snapshot" in OPERATIONAL_TRANSACTION_FIELD_NAMES
    assert "provider_raw" not in OPERATIONAL_TRANSACTION_FIELD_NAMES


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
@pytest.mark.skipif(REQUIRES_DB, reason="tenant DB required")
async def test_processed_batch_operational_rows_from_fuel_transactions_only() -> None:
    url = _tenant_url()
    assert url
    engine = create_async_engine(url)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)

    async with session_maker() as session:
        bvd_batch_id = await session.scalar(
            select(FuelSourceBatch.id).where(
                FuelSourceBatch.tenant_id == TENANT_A,
                FuelSourceBatch.provider_code == "BVD",
                FuelSourceBatch.status == BATCH_STATUS_FINALIZED,
            ).limit(1)
        )
        nw_batch_id = await session.scalar(
            select(FuelSourceBatch.id).where(
                FuelSourceBatch.tenant_id == TENANT_A,
                FuelSourceBatch.provider_code == "NATIONWIDE",
                FuelSourceBatch.status == BATCH_STATUS_FINALIZED,
            ).limit(1)
        )
        if bvd_batch_id is None or nw_batch_id is None:
            pytest.skip("need finalized BVD and Nationwide batches on tenant A")

        bvd_detail = await get_processed_fuel_batch(session, tenant_id=TENANT_A, batch_id=int(bvd_batch_id))
        nw_detail = await get_processed_fuel_batch(session, tenant_id=TENANT_A, batch_id=int(nw_batch_id))

    bvd_ops = bvd_detail["operational_transactions"]
    nw_ops = nw_detail["operational_transactions"]
    assert len(bvd_ops) > 0
    assert len(nw_ops) > 0

    bvd_sample = bvd_ops[0]
    nw_sample = nw_ops[0]
    if hasattr(bvd_sample, "model_dump"):
        bvd_keys = set(bvd_sample.model_dump(mode="json").keys())
        nw_keys = set(nw_sample.model_dump(mode="json").keys())
    else:
        bvd_keys = set(FuelProcessedOperationalTransactionOut(**bvd_sample).model_dump(mode="json").keys())
        nw_keys = set(FuelProcessedOperationalTransactionOut(**nw_sample).model_dump(mode="json").keys())

    assert bvd_keys == nw_keys == OPERATIONAL_TRANSACTION_FIELD_NAMES
    assert isinstance(bvd_sample, FuelProcessedOperationalTransactionOut) or hasattr(bvd_sample, "id")

    await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.skipif(REQUIRES_DB, reason="tenant DB required")
async def test_nationwide_batch_8_operational_contract() -> None:
    url = _tenant_url()
    assert url
    engine = create_async_engine(url)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)

    async with session_maker() as session:
        batch = await session.scalar(
            select(FuelSourceBatch).where(
                FuelSourceBatch.tenant_id == TENANT_A,
                FuelSourceBatch.id == 8,
                FuelSourceBatch.provider_code == "NATIONWIDE",
            )
        )
        if batch is None:
            pytest.skip("Nationwide batch 8 not on tenant A")

        detail = await get_processed_fuel_batch(session, tenant_id=TENANT_A, batch_id=8)
        ops = detail["operational_transactions"]
        assert len(ops) == len(detail["canonical_transactions"])
        assert len(ops) == 12
        sample = ops[0]
        dumped = (
            sample.model_dump(mode="json")
            if hasattr(sample, "model_dump")
            else FuelProcessedOperationalTransactionOut.model_validate(sample).model_dump(mode="json")
        )
        assert set(dumped.keys()) == OPERATIONAL_TRANSACTION_FIELD_NAMES

    await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.skipif(REQUIRES_DB, reason="tenant DB required")
async def test_operational_batch_tenant_isolation() -> None:
    from fastapi import HTTPException

    url = _tenant_url()
    assert url
    engine = create_async_engine(url)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)

    async with session_maker() as session:
        batch_id = await session.scalar(
            select(FuelSourceBatch.id).where(
                FuelSourceBatch.tenant_id == TENANT_A,
                FuelSourceBatch.status == BATCH_STATUS_FINALIZED,
            ).limit(1)
        )
        if batch_id is None:
            pytest.skip("no finalized batch")

    async with session_maker() as session:
        with pytest.raises(HTTPException) as exc:
            await get_processed_fuel_batch(session, tenant_id=TENANT_B, batch_id=int(batch_id))
        assert exc.value.status_code == 404

    await engine.dispose()
