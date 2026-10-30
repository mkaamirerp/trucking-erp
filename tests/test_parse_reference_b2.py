"""Milestone B2 — parse attached revised RC (first parser only, no AI compare)."""

from __future__ import annotations

import hashlib
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.schemas.load_document_parse import LoadDocumentParseResponse, LoadParseExtractedFields, LoadParseDocumentMeta
from app.services.load_document_parse_orchestrator import LoadReparseError, parse_attached_rate_confirmation_reference


@pytest.mark.asyncio
async def test_parse_reference_reads_revision_and_returns_field_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    pdf = b"%PDF-parse-reference-test"
    digest = hashlib.sha256(pdf).hexdigest()
    evidence = MagicMock()
    evidence.accepted_parse_json = {
        "extracted": {"rate": "2100.00", "broker_load_reference": "PO-1"},
        "_revised_pdfs": [{"sha256": digest, "storage_key": "demo/x.pdf", "filename": "rev.pdf"}],
    }
    evidence.file_sha256 = "original-sha"

    db = AsyncMock()

    parsed = LoadDocumentParseResponse(
        document=LoadParseDocumentMeta(filename="rev.pdf"),
        extracted=LoadParseExtractedFields(rate="2000.00", broker_load_reference="PO-1"),
        raw_text="Rate: 2000",
        warnings=[],
        field_confidence={},
        context={"document_type": "rate_confirmation"},
    )

    monkeypatch.setattr(
        "app.services.loads.read_revised_rate_confirmation_pdf_bytes",
        AsyncMock(return_value=("rev.pdf", pdf)),
    )
    monkeypatch.setattr(
        "app.services.load_document_parse_orchestrator.parse_load_workspace_document_orchestrated",
        AsyncMock(return_value=parsed),
    )
    monkeypatch.setattr(
        "app.services.load_document_parse_orchestrator._broker_aliases",
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(
        "app.services.load_workspace_draft_document.assess_same_load",
        lambda *a, **k: {"verdict": "strong", "summary": "", "reasons": []},
    )
    db.scalar = AsyncMock(return_value=evidence)

    result = await parse_attached_rate_confirmation_reference(
        db,
        tenant_id=53,
        load_id=1010,
        revision=1,
        tenant_slug="demo",
    )
    assert result["revision"] == 1
    assert result["pdf_sha256"] == digest
    assert str(result["parse"].extracted.rate) == "2000.00"
    assert any(row.get("field") == "rate" for row in result["field_rows"])


@pytest.mark.asyncio
async def test_parse_reference_rejects_revision_zero() -> None:
    db = AsyncMock()
    with pytest.raises(LoadReparseError) as exc:
        await parse_attached_rate_confirmation_reference(
            db, tenant_id=53, load_id=1, revision=0, tenant_slug="demo"
        )
    assert exc.value.status_code == 422
