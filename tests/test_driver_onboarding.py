from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.deps.auth import CurrentUser
from app.routers.driver_onboarding import approve_submission, create_submission
from app.schemas.driver_onboarding import DriverOnboardingSubmissionCreate


def test_legacy_create_submission_returns_410() -> None:
    """Legacy create_submission is quarantined; no new entity creation."""
    async def run() -> None:
        current_user = CurrentUser(
            user=SimpleNamespace(id="user-1", email="u@example.com", first_name="U", last_name="One"),
            tenant=SimpleNamespace(id=1, slug="test", name="Test Tenant"),
            role="ADMIN",
            member_id=1,
        )
        payload = DriverOnboardingSubmissionCreate(
            first_name="Ada",
            last_name="Lovelace",
            email="ada@example.com",
            phone="+14165551212",
            submit=False,
        )
        db = MagicMock()
        with pytest.raises(HTTPException) as exc_info:
            await create_submission(payload, tenant_id=1, current_user=current_user, db=db)
        assert exc_info.value.status_code == 410

    asyncio.run(run())


def test_legacy_approve_submission_returns_410() -> None:
    """Legacy approve_submission is quarantined; PersonApplication is canonical."""
    async def run() -> None:
        current_user = CurrentUser(
            user=SimpleNamespace(id="user-1", email="u@example.com", first_name="U", last_name="One"),
            tenant=SimpleNamespace(id=1, slug="test", name="Test Tenant"),
            role="ADMIN",
            member_id=1,
        )
        db = MagicMock()
        with pytest.raises(HTTPException) as exc_info:
            await approve_submission(submission_id=999, tenant_id=1, current_user=current_user, db=db)
        assert exc_info.value.status_code == 410

    asyncio.run(run())
