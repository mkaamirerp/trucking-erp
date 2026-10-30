"""Milestone B1 — attach revised RC without mutating load business fields."""

from __future__ import annotations

import hashlib
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.loads import attach_revised_rate_confirmation_pdf


@pytest.mark.asyncio
async def test_attach_skips_duplicate_bytes_without_storage(monkeypatch: pytest.MonkeyPatch) -> None:
    pdf = b"%PDF-duplicate-test"
    digest = hashlib.sha256(pdf).hexdigest()
    evidence = MagicMock()
    evidence.accepted_parse_json = {
        "extracted": {"rate": "1800.00", "broker_load_reference": "PO-1"},
        "_revised_pdfs": [{"sha256": digest, "storage_key": "demo/revised/a.pdf", "filename": "a.pdf"}],
    }
    evidence.file_sha256 = "original-sha"

    load = MagicMock()
    load.status = "ready"

    db = AsyncMock()
    db.scalar = AsyncMock(return_value=evidence)
    db.commit = AsyncMock()

    monkeypatch.setattr("app.services.loads.get_load", AsyncMock(return_value=load))
    save = AsyncMock()
    monkeypatch.setattr("app.core.storage.get_storage", lambda: MagicMock(save_bytes=save))

    result = await attach_revised_rate_confirmation_pdf(
        db,
        tenant_id=53,
        load_id=1010,
        pdf_bytes=pdf,
        filename="same.pdf",
        tenant_slug="demo",
    )
    assert result["stored_new"] is False
    assert result["pdf_reuse_status"] == "existing_latest_revision"
    save.assert_not_called()
    db.commit.assert_not_called()


@pytest.mark.asyncio
async def test_attach_appends_pointer_without_changing_extracted_rate(monkeypatch: pytest.MonkeyPatch) -> None:
    pdf = b"%PDF-new-revision"
    prior_json = {
        "extracted": {"rate": "2100.00", "broker_load_reference": "PO-KEEP"},
        "_revised_pdfs": [],
    }
    evidence = MagicMock()
    evidence.accepted_parse_json = prior_json.copy()
    evidence.file_sha256 = "orig"

    load = MagicMock()
    load.status = "ready"
    load.id = 1010

    db = AsyncMock()
    db.scalar = AsyncMock(return_value=evidence)
    db.commit = AsyncMock()

    stored = MagicMock(
        storage_key="demo/revised/new.pdf",
        sha256=hashlib.sha256(pdf).hexdigest(),
        original_filename="rev.pdf",
    )

    monkeypatch.setattr("app.services.loads.get_load", AsyncMock(return_value=load))
    monkeypatch.setattr(
        "app.core.storage.get_storage",
        lambda: MagicMock(save_bytes=AsyncMock(return_value=stored)),
    )
    monkeypatch.setattr(
        "app.services.load_parser_duplicate_precheck.find_exact_pdf_duplicate_candidates",
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr("app.services.loads._write_load_audit", AsyncMock())

    result = await attach_revised_rate_confirmation_pdf(
        db,
        tenant_id=53,
        load_id=1010,
        pdf_bytes=pdf,
        filename="rev.pdf",
        tenant_slug="demo",
    )
    assert result["stored_new"] is True
    assert evidence.accepted_parse_json["extracted"]["rate"] == "2100.00"
    assert evidence.accepted_parse_json["extracted"]["broker_load_reference"] == "PO-KEEP"
    assert len(evidence.accepted_parse_json["_revised_pdfs"]) == 1
    assert evidence.accepted_parse_json["_revised_pdfs"][0]["uploaded_at"]
