"""Pre-AI duplicate review: exact immutable PDF SHA, digital and scanned paths.

Tests never call real AI or mutate tenant databases.
"""
from __future__ import annotations

import hashlib
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import UploadFile

from app.schemas.load_document_parse import (
    LoadDocumentParseResponse,
    LoadParseDocumentMeta,
    LoadParseExtractedFields,
)
from app.services import load_document_parse_rate_con as parser
from app.services import load_workspace_draft_document as draft_doc
from app.services.load_parser_duplicate_precheck import (
    find_exact_pdf_duplicate_candidates,
    DuplicatePrecheckUnavailable,
)

PDF = (
    Path(__file__).resolve().parents[1]
    / "docs/fixtures/load_lab/load_lab_fixture_1pickup_3deliveries.pdf"
)
EXACT_MATCH = {
    "match_type": "exact_pdf_sha256",
    "load_id": 103,
    "load_number": "103",
    "broker_name": "Test Broker",
    "broker_load_reference": "ABC-99",
    "load_status": "ready",
    "pickup": "Chicago, IL",
    "delivery": "Boston, MA",
    "trip_id": 15,
    "trip_status": "completed",
    "driver_id": 7,
    "truck_id": 104,
    "trailer_id": 5307,
}


def _duplicate(*, filename: str = "same.pdf", pdf_type: str = "digital_text"):
    return LoadDocumentParseResponse(
        document=LoadParseDocumentMeta(filename=filename),
        extracted=LoadParseExtractedFields(),
        raw_text="source text",
        context={
            "semantic_outcome": "blocked_duplicate_review",
            "pdf_type": pdf_type,
            "duplicate_candidates": [EXACT_MATCH],
        },
    )


@pytest.mark.asyncio
async def test_digital_exact_match_blocks_ai_before_exclusion_or_handoff(monkeypatch):
    calls = {"duplicate": 0, "ai": 0}
    async def lookup(db, **kwargs):
        calls["duplicate"] += 1
        assert kwargs["tenant_id"] == 53
        assert kwargs["pdf_bytes"] == PDF.read_bytes()
        return [EXACT_MATCH]
    async def ai(**kwargs):
        calls["ai"] += 1
        raise AssertionError("AI MUST NOT be called before duplicate review")
    monkeypatch.setattr(parser, "find_exact_pdf_duplicate_candidates", lookup)

    out = await parser.parse_pdf_bytes_to_load_document_response(
        AsyncMock(), tenant_id=53, pdf_bytes=PDF.read_bytes(),
        filename="same.pdf", openai_chat_json_schema=ai,
    )
    assert out.context["semantic_outcome"] == "blocked_duplicate_review"
    assert out.context["duplicate_candidates"][0]["broker_name"] == "Test Broker"
    assert out.extracted.broker_name_snapshot is None
    assert calls == {"duplicate": 1, "ai": 0}


@pytest.mark.asyncio
async def test_digital_continue_anyway_skips_review_and_invokes_normal_ai(monkeypatch):
    async def unexpected(*args, **kwargs):
        raise AssertionError("Continue bypass must not re-block exact file")
    ai_calls = []
    async def ai(**kwargs):
        ai_calls.append(kwargs)
        return {
            "document": {"filename": "same.pdf"},
            "extracted": {"broker_load_reference": "ABC-99", "references": [], "stops": []},
            "warnings": [],
            "field_confidence": {},
            "context": {},
        }
    monkeypatch.setattr(parser, "find_exact_pdf_duplicate_candidates", unexpected)
    out = await parser.parse_pdf_bytes_to_load_document_response(
        AsyncMock(), tenant_id=53, pdf_bytes=PDF.read_bytes(),
        filename="same.pdf", openai_chat_json_schema=ai,
        continue_anyway=True,
    )
    assert len(ai_calls) == 1
    assert ai_calls[0]["input_file_bytes"] == PDF.read_bytes()
    assert out.context.get("semantic_outcome") != "blocked_duplicate_review"


@pytest.mark.asyncio
async def test_scanned_checks_after_ocr_but_before_ai(monkeypatch):
    calls = []
    monkeypatch.setattr(parser, "validate_load_parser_pdf", lambda _b: None)
    monkeypatch.setattr(parser, "acquire_load_parser_pdf_pages", lambda _b: {
        "pdf_type": "scanned_image", "page_count": 1,
        "requires_ocr": True, "warnings": [], "pages": [],
    })
    def fake_ocr(_pdf):
        calls.append("ocr")
        return [{"page_number": 1, "text": "OCR CONTENT TEXT"}], []
    async def lookup(_db, **kwargs):
        calls.append("duplicate")
        return [EXACT_MATCH]
    async def bad_ai(**kwargs):
        raise AssertionError("AI called")
    monkeypatch.setattr(parser, "ocr_load_parser_pdf_pages", fake_ocr)
    monkeypatch.setattr(parser, "find_exact_pdf_duplicate_candidates", lookup)
    out = await parser.parse_pdf_bytes_to_load_document_response(
        AsyncMock(), tenant_id=53,
        pdf_bytes=b"%PDF-valid-fixture-mocked", filename="scan.pdf",
        openai_chat_json_schema=bad_ai,
    )
    assert calls == ["ocr", "duplicate"]
    assert out.raw_text == "OCR CONTENT TEXT"
    assert out.context["semantic_outcome"] == "blocked_duplicate_review"


@pytest.mark.asyncio
async def test_no_existing_match_continues_normal_parser(monkeypatch):
    hits = []
    async def lookup(_db, **kwargs):
        hits.append(kwargs)
        return []
    async def ai(**kwargs):
        return {
            "document": {"filename": "unique.pdf"},
            "extracted": {"broker_load_reference": "NEW", "references": [], "stops": []},
            "warnings": [], "field_confidence": {}, "context": {},
        }
    monkeypatch.setattr(parser, "find_exact_pdf_duplicate_candidates", lookup)
    out = await parser.parse_pdf_bytes_to_load_document_response(
        AsyncMock(), tenant_id=53, pdf_bytes=PDF.read_bytes(),
        filename="unique.pdf", openai_chat_json_schema=ai,
    )
    assert len(hits) == 1
    assert out.context.get("semantic_outcome") != "blocked_duplicate_review"


@pytest.mark.asyncio
async def test_unavailable_precheck_fails_closed_before_ai(monkeypatch):
    async def unavailable(*args, **kwargs):
        raise DuplicatePrecheckUnavailable("db offline")
    async def ai(**kwargs):
        raise AssertionError("AI should not run on unchecked document")
    monkeypatch.setattr(parser, "find_exact_pdf_duplicate_candidates", unavailable)
    with pytest.raises(DuplicatePrecheckUnavailable):
        await parser.parse_pdf_bytes_to_load_document_response(
            AsyncMock(), tenant_id=53, pdf_bytes=PDF.read_bytes(),
            filename="same.pdf", openai_chat_json_schema=ai,
        )


@pytest.mark.asyncio
async def test_draft_review_does_not_upload_replace_or_commit(monkeypatch):
    draft_id = uuid.uuid4()
    current = SimpleNamespace(
        id=draft_id, tenant_id=53, status="draft", concurrency_version=4,
        pdf_sha256="previous-sha", accepted_parse_json={"existing": "keep"},
    )
    db = AsyncMock()
    db.scalar.return_value = current
    async def open_mutation(*args):
        return None
    async def blocked(*args, **kwargs):
        assert kwargs["continue_anyway"] is False
        return _duplicate()
    monkeypatch.setattr(draft_doc, "require_workspace_draft_open_for_mutation", open_mutation)
    monkeypatch.setattr(draft_doc, "parse_load_workspace_document_orchestrated", blocked)
    def must_not_save(*args, **kwargs):
        raise AssertionError("Storage must not be used during duplicate review")
    monkeypatch.setattr(draft_doc, "get_storage", must_not_save)

    file = UploadFile(filename="same.pdf", file=PDF.open("rb"))
    try:
        unchanged, parse = await draft_doc.parse_and_attach_workspace_draft_pdf(
            db, 53, "demo", draft_id, file,
            updated_by_platform_user_id="user-1",
            expected_concurrency_version=4,
        )
    finally:
        await file.close()

    assert unchanged is current
    assert parse.context["semantic_outcome"] == "blocked_duplicate_review"
    assert current.accepted_parse_json == {"existing": "keep"}
    assert current.pdf_sha256 == "previous-sha"
    assert current.concurrency_version == 4
    db.commit.assert_not_awaited()
    db.execute.assert_not_awaited()


def test_existing_evidence_index_and_tenant_scoped_sha_in_query_source():
    import inspect
    src = inspect.getsource(find_exact_pdf_duplicate_candidates)
    assert "file_sha256 == digest" in src
    assert "Load.tenant_id == tenant_id" in src
    assert "LoadCommercialEvidence.tenant_id == tenant_id" in src
    assert "load_id == Load.id" in src
    assert "sha256(pdf_bytes).hexdigest()" in src


def test_browser_duplicate_modal_has_cancel_continue_and_no_hydration_on_review():
    root = Path(__file__).resolve().parents[1]
    page = (root / "apps/web/src/pages/LoadWorkspacePage.tsx").read_text()
    assert "duplicateLoadCandidatesFromParse(res)" in page
    assert "return; // No accepted parse, stored PDF replacement or form hydration." in page
    assert "Continue anyway — parse PDF" in page
    assert "setDuplicateReview(null)" in page
