"""TASK 21 — broker load reference and PDF SHA duplicate rules."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.load_rate_confirmation_duplicate import (
    LOAD_RATE_CONFIRMATION_DUPLICATE,
    LOAD_RATE_CONFIRMATION_DUPLICATE_SOFT,
    advisory_lock_broker_reference_promote,
    assert_promote_rate_confirmation_not_duplicate,
    classify_broker_reference_duplicates,
    normalize_rate_confirmation_reference,
)


def test_normalize_rate_confirmation_reference() -> None:
    assert normalize_rate_confirmation_reference("PO-123") == "po123"
    assert normalize_rate_confirmation_reference("po 123") == "po123"
    assert normalize_rate_confirmation_reference("  PO  123 ") == "po123"
    assert normalize_rate_confirmation_reference(None) is None
    assert normalize_rate_confirmation_reference("   ") is None


def test_classify_hard_when_same_broker() -> None:
    from types import SimpleNamespace

    matches = [SimpleNamespace(broker_id=5, id=10)]
    severity, rows = classify_broker_reference_duplicates(incoming_broker_id=5, matches=matches)
    assert severity == "hard"
    assert rows == matches


def test_classify_soft_when_broker_differs() -> None:
    from types import SimpleNamespace

    matches = [SimpleNamespace(broker_id=9, id=10)]
    severity, rows = classify_broker_reference_duplicates(incoming_broker_id=5, matches=matches)
    assert severity == "soft"
    assert rows == matches


@pytest.mark.asyncio
async def test_promote_hard_duplicate_raises_409() -> None:
    db = AsyncMock(spec=AsyncSession)
    with patch(
        "app.services.load_rate_confirmation_duplicate.evaluate_broker_reference_duplicate",
        new_callable=AsyncMock,
        return_value=("hard", [{"load_id": 42, "load_number": "L-42"}]),
    ):
        with pytest.raises(HTTPException) as exc:
            await assert_promote_rate_confirmation_not_duplicate(
                db,
                tenant_id=1,
                broker_load_reference="ABC",
                broker_id=1,
                acknowledge_soft=False,
            )
    assert exc.value.status_code == 409
    detail = exc.value.detail
    assert isinstance(detail, dict)
    assert detail.get("code") == LOAD_RATE_CONFIRMATION_DUPLICATE


@pytest.mark.asyncio
async def test_promote_soft_requires_acknowledgment() -> None:
    db = AsyncMock(spec=AsyncSession)
    with patch(
        "app.services.load_rate_confirmation_duplicate.evaluate_broker_reference_duplicate",
        new_callable=AsyncMock,
        return_value=("soft", [{"load_id": 99}]),
    ):
        with pytest.raises(HTTPException) as exc:
            await assert_promote_rate_confirmation_not_duplicate(
                db,
                tenant_id=1,
                broker_load_reference="ABC",
                broker_id=None,
                acknowledge_soft=False,
            )
    detail = exc.value.detail
    assert isinstance(detail, dict)
    assert detail.get("code") == LOAD_RATE_CONFIRMATION_DUPLICATE_SOFT


@pytest.mark.asyncio
async def test_advisory_lock_uses_pg_advisory_xact_lock() -> None:
    db = AsyncMock(spec=AsyncSession)
    db.execute = AsyncMock()
    await __import__(
        "app.services.load_rate_confirmation_duplicate", fromlist=["advisory_lock_broker_reference_promote"]
    ).advisory_lock_broker_reference_promote(
        db, tenant_id=1, broker_id=5, broker_load_reference="PO-123"
    )
    db.execute.assert_awaited()
