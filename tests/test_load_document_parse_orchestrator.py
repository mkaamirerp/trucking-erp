"""Orchestrator for parse-document: legacy vs semantic flag (Track B1). No DB, no live OpenAI."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core.config import settings
from app.schemas.load_document_parse import LoadDocumentParseResponse
from app.services.load_document_parse import parse_load_workspace_from_pdf_bytes
from app.services.load_document_parse_orchestrator import parse_load_workspace_document_orchestrated
from app.services.load_document_parse_semantic import parse_load_workspace_from_pdf_semantic_stateless

_REPO_ROOT = Path(__file__).resolve().parents[1]
_FIXTURE_PDF = _REPO_ROOT / "docs" / "fixtures" / "load_lab" / "load_lab_fixture_1pickup_3deliveries.pdf"

_LAB_LEAK = frozenset({"parse_diagnostics", "ai_model_output", "run_id", "semantic_extract_status"})


def _assert_public_response_clean(out: LoadDocumentParseResponse) -> None:
    dumped = out.model_dump(mode="json")
    for k in _LAB_LEAK:
        assert k not in dumped
    for k in _LAB_LEAK:
        assert k not in (out.context or {})


@pytest.fixture
def openai_key_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "openai_api_key", "sk-test-key-for-semantic", raising=False)


def _valid_semantic_ai_dict(*, filename: str = "stub.pdf", ref: str = "REF-ORCH") -> dict:
    """B4 injectable return shape (no raw_text / context)."""
    return {
        "document": {"filename": filename},
        "extracted": {
            "broker_load_reference": ref,
            "references": [],
            "stops": [],
        },
        "warnings": [],
        "field_confidence": {},
    }


@pytest.mark.asyncio
async def test_orchestrator_flag_off_matches_legacy_extracted_and_adds_parse_path_legacy() -> None:
    pdf_bytes = _FIXTURE_PDF.read_bytes()
    fn = "golden.pdf"
    legacy_raw = parse_load_workspace_from_pdf_bytes(
        pdf_bytes,
        filename=fn,
        email_thread_id=9,
        load_id=101,
    )
    expected = LoadDocumentParseResponse.model_validate(legacy_raw)

    out = await parse_load_workspace_document_orchestrated(
        pdf_bytes,
        filename=fn,
        email_thread_id=9,
        load_id=101,
        semantic_enabled=False,
    )

    assert out.extracted == expected.extracted
    assert out.document == expected.document
    assert out.raw_text == expected.raw_text
    assert out.warnings == expected.warnings
    assert out.field_confidence == expected.field_confidence
    assert out.context.get("parse_path") == "legacy"
    base_ctx = {k: v for k, v in out.context.items() if k != "parse_path"}
    assert base_ctx == (expected.context or {})
    _assert_public_response_clean(out)


@pytest.mark.asyncio
async def test_orchestrator_flag_on_fake_semantic_success(openai_key_set: None) -> None:
    async def fake_openai(**_kwargs: object) -> dict:
        return _valid_semantic_ai_dict(filename="ok.pdf", ref="SEM-OK")

    pdf_bytes = _FIXTURE_PDF.read_bytes()
    out = await parse_load_workspace_document_orchestrated(
        pdf_bytes,
        filename="ok.pdf",
        semantic_enabled=True,
        openai_chat_json_schema=fake_openai,
    )
    assert out.extracted.broker_load_reference == "SEM-OK"
    assert out.context.get("parse_path") == "semantic"
    assert out.context.get("semantic_outcome") == "success"
    _assert_public_response_clean(out)


@pytest.mark.asyncio
async def test_orchestrator_flag_on_no_client_is_semantic_skipped_not_legacy_regex() -> None:
    pdf_bytes = _FIXTURE_PDF.read_bytes()
    fn = "x.pdf"
    legacy = LoadDocumentParseResponse.model_validate(
        parse_load_workspace_from_pdf_bytes(pdf_bytes, filename=fn)
    )

    direct = await parse_load_workspace_from_pdf_semantic_stateless(
        pdf_bytes,
        filename=fn,
        openai_chat_json_schema=None,
    )
    out = await parse_load_workspace_document_orchestrated(
        pdf_bytes,
        filename=fn,
        semantic_enabled=True,
        openai_chat_json_schema=None,
    )

    assert out.context.get("parse_path") == "semantic"
    assert out.context.get("semantic_outcome") == "skipped_no_client"
    want_ctx = {**dict(direct.context), "parse_path": "semantic"}
    assert dict(out.context) == want_ctx
    assert out.model_dump(mode="json") == direct.model_copy(update={"context": want_ctx}).model_dump(mode="json")
    assert legacy.extracted.broker_load_reference or len(legacy.extracted.stops) > 0
    assert out.extracted.broker_load_reference is None and len(out.extracted.stops) == 0
    _assert_public_response_clean(out)


@pytest.mark.asyncio
async def test_orchestrator_flag_on_injectable_exception_is_semantic_error_not_legacy(
    openai_key_set: None,
) -> None:
    async def boom(**_kwargs: object) -> dict:
        raise RuntimeError("network down")

    pdf_bytes = _FIXTURE_PDF.read_bytes()
    fn = "e.pdf"
    legacy = LoadDocumentParseResponse.model_validate(
        parse_load_workspace_from_pdf_bytes(pdf_bytes, filename=fn)
    )

    direct = await parse_load_workspace_from_pdf_semantic_stateless(
        pdf_bytes,
        filename=fn,
        openai_chat_json_schema=boom,
    )
    out = await parse_load_workspace_document_orchestrated(
        pdf_bytes,
        filename=fn,
        semantic_enabled=True,
        openai_chat_json_schema=boom,
    )

    assert out.context.get("parse_path") == "semantic"
    assert out.context.get("semantic_outcome") == "openai_error"
    assert any("OpenAI call failed" in w for w in out.warnings)
    assert out.raw_text == legacy.raw_text
    want_ctx = {**dict(direct.context), "parse_path": "semantic"}
    assert dict(out.context) == want_ctx
    assert out.model_dump(mode="json") == direct.model_copy(update={"context": want_ctx}).model_dump(mode="json")
    assert legacy.extracted.broker_load_reference or len(legacy.extracted.stops) > 0
    assert out.extracted.broker_load_reference is None and len(out.extracted.stops) == 0
    _assert_public_response_clean(out)


@pytest.mark.asyncio
async def test_orchestrator_semantic_path_normalizes_parse_path_and_matches_direct_semantic(
    openai_key_set: None,
) -> None:
    async def fake_openai(**_kwargs: object) -> dict:
        return _valid_semantic_ai_dict(ref="ALIGN-1")

    pdf_bytes = _FIXTURE_PDF.read_bytes()
    direct = await parse_load_workspace_from_pdf_semantic_stateless(
        pdf_bytes,
        filename="x.pdf",
        openai_chat_json_schema=fake_openai,
    )
    orch = await parse_load_workspace_document_orchestrated(
        pdf_bytes,
        filename="x.pdf",
        semantic_enabled=True,
        openai_chat_json_schema=fake_openai,
    )

    assert orch.context.get("parse_path") == "semantic"
    assert direct.context.get("parse_path") == "semantic_stateless"
    dctx = dict(direct.context)
    dctx["parse_path"] = "semantic"
    assert dict(orch.context) == dctx
    assert orch.extracted == direct.extracted
    _assert_public_response_clean(orch)
