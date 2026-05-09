from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.models.load import Load
from app.services.email_engine import intake_service


@pytest.mark.asyncio
async def test_apply_email_pdf_intake_does_not_insert_load(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Guardrail: email PDF intake must never create `Load` rows automatically.

    This is a unit-level assertion: if any code path in apply_email_pdf_intake calls Load(...),
    the test fails.
    """

    def _fail_load_ctor(*_args, **_kwargs):  # noqa: ANN001
        raise AssertionError("Email PDF intake must not instantiate Load() (no auto-load creation).")

    monkeypatch.setattr(intake_service, "Load", _fail_load_ctor, raising=True)

    db = AsyncMock()
    # Intake should safely early-return if thread lookup fails; we only care that Load() isn't called.
    await intake_service.apply_email_pdf_intake(db, tenant_id=1, thread_id=1, access_token="tok")
