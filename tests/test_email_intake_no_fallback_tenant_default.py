from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.services.email_engine import intake_service
from app.services.broker_intake_resolve import BrokerIntakeResolveResult


@pytest.mark.asyncio
async def test_email_intake_never_emits_fallback_tenant_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Guardrail: email intake must not emit `fallback_tenant_default` match_method.

    We patch the intake review upsert to inspect the written detail payload when a parse-review is recorded.
    """
    captured: list[dict] = []

    async def fake_upsert(*_args, **kwargs):  # noqa: ANN001
        captured.append(kwargs)

    monkeypatch.setattr(intake_service, "upsert_intake_review_from_intake_source", fake_upsert, raising=True)

    async def fake_sync(*_args, **_kwargs):  # noqa: ANN001
        return None

    monkeypatch.setattr(intake_service, "sync_email_intake_review_for_thread", fake_sync, raising=True)

    # Make the resolver return a non-match (no broker, no method).
    async def fake_resolve(*_args, **_kwargs):  # noqa: ANN001
        return BrokerIntakeResolveResult(broker_id=None, broker_label=None, match_method=None)

    monkeypatch.setattr(intake_service, "resolve_booking_broker_for_email_intake", fake_resolve, raising=True)

    # Avoid exercising real DB queries in helper functions.
    monkeypatch.setattr(intake_service, "fetch_latest_inbound_from_header", AsyncMock(return_value=None), raising=True)
    monkeypatch.setattr(
        intake_service,
        "_supplemental_mc_dot_hints_from_pdf_attachments",
        AsyncMock(return_value=(None, None)),
        raising=True,
    )

    # Force the PDF row path and parse success without touching DB/storage.
    monkeypatch.setattr(intake_service, "_latest_pdf_attachment_rows", AsyncMock(return_value=[(AsyncMock(), AsyncMock())]))
    monkeypatch.setattr(intake_service, "_fetch_email_pdf_attachment_bytes", AsyncMock(return_value=b"%PDF-1.4 test"))
    fake_parse = AsyncMock()
    fake_parse.model_dump = lambda **_kwargs: {"extracted": {}, "raw_text": ""}  # noqa: E731
    monkeypatch.setattr(
        intake_service,
        "parse_pdf_bytes_to_load_document_response",
        AsyncMock(return_value=fake_parse),
        raising=True,
    )

    # Thread is active, unlinked, and not new_load.
    fake_thread = AsyncMock()
    fake_thread.status = "active"
    fake_thread.linked_load_id = None
    fake_thread.intake_bucket = "background"
    fake_thread.provider = "gmail"
    fake_thread.subject = "Rate Confirmation"
    fake_thread.snippet = "See attached"

    # db.scalar(select(EmailThread...)) returns thread.
    db = AsyncMock()
    db.scalar = AsyncMock(return_value=fake_thread)

    await intake_service.apply_email_pdf_intake(db, tenant_id=1, thread_id=1, access_token="tok")

    # If we wrote a parse-review or low-confidence review, ensure match_method isn't fallback_tenant_default.
    for call in captured:
        detail = call.get("detail_extensions") or {}
        broker_res = (detail.get("broker_resolution") or {}) if isinstance(detail, dict) else {}
        assert broker_res.get("match_method") != "fallback_tenant_default"
