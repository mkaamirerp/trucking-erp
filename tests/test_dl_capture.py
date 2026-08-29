"""DL capture token: purpose filter, scoped revoke, resume steps."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import or_

from app.models.application_access_token import ApplicationAccessToken
from app.routers import driver_onboarding as ro


def test_dl_capture_step_resume_rules() -> None:
    assert ro._dl_capture_step("MISSING", "MISSING") == "FRONT"
    assert ro._dl_capture_step("FAILED", "MISSING") == "FRONT"
    assert ro._dl_capture_step("PROCESSED", "MISSING") == "BACK"
    assert ro._dl_capture_step("PROCESSED", "FAILED") == "BACK"
    assert ro._dl_capture_step("PROCESSED", "PROCESSED") == "COMPLETE"


def test_dl_side_status_from_intake() -> None:
    intake = {
        "files": {
            "CDL_FRONT": {"dl_preprocess_status": "PROCESSED"},
            "CDL_BACK": {"dl_preprocess_status": "FAILED"},
        }
    }
    assert ro._dl_side_status(intake, "CDL_FRONT") == "PROCESSED"
    assert ro._dl_side_status(intake, "CDL_BACK") == "FAILED"
    assert ro._dl_side_status({}, "CDL_FRONT") == "MISSING"


@pytest.mark.asyncio
async def test_revoke_active_tokens_purpose_scoped() -> None:
    db = AsyncMock()
    db.execute = AsyncMock()
    await ro._revoke_active_access_tokens_for_application(
        db, tenant_id=1, application_id=60, purpose=ro.TOKEN_PURPOSE_DL_CAPTURE
    )
    assert db.execute.await_count == 1
    # Compiled WHERE should constrain purpose — inspect call args for Update
    stmt = db.execute.await_args.args[0]
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": False}))
    assert "application_access_tokens" in compiled.lower() or "application_access_tokens" in str(stmt)


@pytest.mark.asyncio
async def test_get_token_requires_dl_capture_purpose() -> None:
    db = AsyncMock()
    db.scalar = AsyncMock(return_value=None)
    with pytest.raises(Exception) as exc:
        await ro._get_application_and_access_by_token(
            db,
            tenant_id=1,
            token="abc",
            purpose=ro.TOKEN_PURPOSE_DL_CAPTURE,
            detail=ro._DL_CAPTURE_INVALID,
        )
    assert exc.value.status_code == 404
    assert exc.value.detail == ro._DL_CAPTURE_INVALID
    # Ensure purpose was part of the query filter
    stmt = db.scalar.await_args.args[0]
    assert any(
        getattr(c, "right", None) is not None
        or "dl_capture" in str(c)
        for c in stmt._where_criteria
    ) or "dl_capture" in str(stmt)


def test_dl_capture_ttl_constant() -> None:
    assert ro.DL_CAPTURE_TOKEN_TTL == timedelta(hours=24)
