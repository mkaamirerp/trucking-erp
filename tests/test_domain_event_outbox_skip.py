"""Outbox sweeper must not re-query tenants whose table/catalog is missing."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.exc import ProgrammingError

from app.services.domain_event_delivery import DomainEventDispatcher, _is_unsweepable_tenant_error


class _MissingTableSession:
    def __init__(self) -> None:
        self.rollback = AsyncMock()
        self._scalar_calls = 0

    async def scalar(self, _stmt):
        self._scalar_calls += 1
        return None

    async def scalars(self, _stmt):
        raise AssertionError("must not SELECT domain_event_outbox when to_regclass is NULL")


class _PresentEmptySession:
    async def scalar(self, _stmt):
        return "domain_event_outbox"

    async def scalars(self, _stmt):
        result = MagicMock()
        result.__iter__ = lambda self: iter(())
        return result


async def _agen(value):
    yield value


@pytest.mark.asyncio
async def test_missing_outbox_table_skips_and_disposes_engine() -> None:
    dispatcher = DomainEventDispatcher()
    session = _MissingTableSession()
    with (
        patch(
            "app.services.domain_event_delivery.open_tenant_session_by_id",
            return_value=_agen(session),
        ),
        patch(
            "app.services.domain_event_delivery.dispose_cached_engine_for_tenant_id",
            new_callable=AsyncMock,
        ) as dispose,
    ):
        await dispatcher.process_pending_for_tenant(65)
        await dispatcher.process_pending_for_tenant(65)

    assert 65 in dispatcher._skip_tenant_ids
    assert session._scalar_calls == 1
    dispose.assert_awaited_once_with(65)


@pytest.mark.asyncio
async def test_skip_cache_does_not_open_session() -> None:
    dispatcher = DomainEventDispatcher()
    dispatcher._skip_tenant_ids.add(77)
    opened = {"n": 0}

    async def _should_not_open(_tid):
        opened["n"] += 1
        yield None

    with patch(
        "app.services.domain_event_delivery.open_tenant_session_by_id",
        side_effect=_should_not_open,
    ):
        await dispatcher.process_pending_for_tenant(77)
    assert opened["n"] == 0


@pytest.mark.asyncio
async def test_present_table_empty_outbox_does_not_skip() -> None:
    dispatcher = DomainEventDispatcher()
    session = _PresentEmptySession()
    with (
        patch(
            "app.services.domain_event_delivery.open_tenant_session_by_id",
            return_value=_agen(session),
        ),
        patch(
            "app.services.domain_event_delivery.dispose_cached_engine_for_tenant_id",
            new_callable=AsyncMock,
        ) as dispose,
    ):
        await dispatcher.process_pending_for_tenant(53)
    assert 53 not in dispatcher._skip_tenant_ids
    dispose.assert_not_awaited()


@pytest.mark.asyncio
async def test_missing_database_is_skipped_and_engine_disposed() -> None:
    dispatcher = DomainEventDispatcher()

    async def _boom(_tid):
        raise Exception('database "tenant_idar_sub_1f6e4fe4" does not exist')
        yield  # pragma: no cover — make this an async generator

    with patch(
        "app.services.domain_event_delivery.open_tenant_session_by_id",
        side_effect=_boom,
    ), patch(
        "app.services.domain_event_delivery.dispose_cached_engine_for_tenant_id",
        new_callable=AsyncMock,
    ) as dispose:
        await dispatcher.process_pending_for_tenant(99)
    assert 99 in dispatcher._skip_tenant_ids
    dispose.assert_awaited_once_with(99)


def test_unsweepable_error_detects_missing_catalog() -> None:
    assert _is_unsweepable_tenant_error(Exception('database "x" does not exist'))
    assert not _is_unsweepable_tenant_error(RuntimeError("disk full"))


@pytest.mark.asyncio
async def test_legacy_programmingerror_missing_table_still_skips() -> None:
    dispatcher = DomainEventDispatcher()

    class _ErrSession:
        rollback = AsyncMock()

        async def scalar(self, _stmt):
            orig = ProgrammingError("SELECT", {}, Exception("undefined"))
            orig.args = ('relation "domain_event_outbox" does not exist',)
            raise orig

    with (
        patch(
            "app.services.domain_event_delivery.open_tenant_session_by_id",
            return_value=_agen(_ErrSession()),
        ),
        patch(
            "app.services.domain_event_delivery.dispose_cached_engine_for_tenant_id",
            new_callable=AsyncMock,
        ) as dispose,
    ):
        await dispatcher.process_pending_for_tenant(70)
    assert 70 in dispatcher._skip_tenant_ids
    dispose.assert_awaited_once_with(70)
