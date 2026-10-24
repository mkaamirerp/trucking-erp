"""Task 14 cp2: load number minter and writer integration."""

from __future__ import annotations

import asyncio
import os
import uuid
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("ALLOW_TENANT_RESOLUTION_SHORTCUTS", "true")

from app.core.db_url import to_async_pg_url
from app.services.load_numbering import (
    format_load_number,
    mint_next_load_number,
    period_key_for_instant,
)
from app.services.load_workspace_draft_mapper import draft_json_to_load_create
REQUIRES_DB = not (os.environ.get("TENANT_DATABASE_URL") or os.environ.get("ALEMBIC_TENANT_DATABASE_URL"))


def _tenant_async_url() -> str:
    raw = os.environ.get("TENANT_DATABASE_URL") or os.environ.get("ALEMBIC_TENANT_DATABASE_URL") or ""
    if not raw:
        raise RuntimeError("TENANT_DATABASE_URL required")
    return to_async_pg_url(raw)


async def _table_exists(session: AsyncSession) -> bool:
    reg = await session.scalar(text("SELECT to_regclass('public.tenant_load_number_periods')"))
    return reg is not None


@pytest.fixture
async def mint_db():
    engine = create_async_engine(_tenant_async_url(), pool_pre_ping=True)
    Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with Session() as session:
        if not await _table_exists(session):
            pytest.skip("tenant_load_number_periods not present (migrate ln01 on this tenant DB)")
        yield session
        await session.rollback()
    await engine.dispose()


class TestLoadNumberFormatUnit:
    def test_format_pads_four_digits(self) -> None:
        local = datetime(2026, 10, 15, 12, 0, tzinfo=ZoneInfo("America/Toronto"))
        assert format_load_number(local, 1) == "Oct-26-0001"
        assert format_load_number(local, 9999) == "Oct-26-9999"

    def test_format_overflow_no_truncate(self) -> None:
        local = datetime(2026, 10, 15, 12, 0, tzinfo=ZoneInfo("America/Toronto"))
        assert format_load_number(local, 10000) == "Oct-26-10000"

    def test_period_key(self) -> None:
        local = datetime(2026, 11, 1, 0, 30, tzinfo=ZoneInfo("America/Toronto"))
        assert period_key_for_instant(local) == "2026-11"


@pytest.mark.skipif(REQUIRES_DB, reason="tenant DB required")
class TestLoadNumberMinterIntegration:
    async def test_concurrent_mints_are_distinct(self, mint_db: AsyncSession) -> None:
        tenant_id = 999_001
        fixed = datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc)
        engine = mint_db.bind
        Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

        async def one() -> str:
            async with Session() as s:
                async with s.begin():
                    return await mint_next_load_number(s, tenant_id, now=fixed)

        a, b = await asyncio.gather(one(), one())
        assert a != b

    async def test_month_rollover(self, mint_db: AsyncSession) -> None:
        tenant_id = 999_002
        oct_end = datetime(2026, 10, 31, 23, 0, tzinfo=timezone.utc)
        nov_start = datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc)
        n1 = await mint_next_load_number(mint_db, tenant_id, now=oct_end)
        n2 = await mint_next_load_number(mint_db, tenant_id, now=nov_start)
        assert n1.startswith("Oct-26-")
        assert n2 == "Nov-26-0001"

    async def test_toronto_timezone_boundary(self, mint_db: AsyncSession) -> None:
        tenant_id = 999_003
        toronto = ZoneInfo("America/Toronto")
        oct_inst = datetime(2026, 11, 1, 3, 30, tzinfo=timezone.utc)  # 2026-10-31 23:30 Toronto
        nov_inst = datetime(2026, 11, 1, 4, 30, tzinfo=timezone.utc)  # 2026-11-01 00:30 Toronto
        oct_num = await mint_next_load_number(mint_db, tenant_id, now=oct_inst)
        nov_num = await mint_next_load_number(mint_db, tenant_id, now=nov_inst)
        assert oct_num.startswith("Oct-26-")
        assert nov_num.startswith("Nov-26-")

    async def test_rollback_does_not_consume(self, mint_db: AsyncSession) -> None:
        tenant_id = 999_004
        fixed = datetime(2026, 10, 10, 15, 0, tzinfo=timezone.utc)
        engine = mint_db.bind
        Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
        async with Session() as s:
            txn = await s.begin()
            rolled = await mint_next_load_number(s, tenant_id, now=fixed)
            await txn.rollback()
        async with Session() as s:
            async with s.begin():
                again = await mint_next_load_number(s, tenant_id, now=fixed)
        assert again == rolled

    async def test_overflow_sequence(self, mint_db: AsyncSession) -> None:
        tenant_id = 999_005
        period = "2026-10"
        await mint_db.execute(
            text(
                """
                INSERT INTO tenant_load_number_periods (tenant_id, period, next_numeric)
                VALUES (:t, :p, 9999)
                ON CONFLICT (tenant_id, period) DO UPDATE SET next_numeric = 9999
                """
            ),
            {"t": tenant_id, "p": period},
        )
        await mint_db.commit()
        fixed = datetime(2026, 10, 5, 12, 0, tzinfo=timezone.utc)
        a = await mint_next_load_number(mint_db, tenant_id, now=fixed)
        b = await mint_next_load_number(mint_db, tenant_id, now=fixed)
        assert a.endswith("-9999")
        assert b.endswith("-10000")


def test_draft_mapper_ignores_load_number() -> None:
    payload = draft_json_to_load_create({"loadNumber": "SHOULD-NOT-APPLY", "stops": []})
    assert payload.load_number is None
