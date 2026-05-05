"""Tests for stateless semantic parse (B4 schema). No DB, no live OpenAI, no load_lab."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.core.config import settings
from app.schemas.load_document_parse import LoadDocumentParseResponse
from app.services.load_document_parse_semantic import (
    SEMANTIC_PROMPT_VERSION_PARSE_DOCUMENT,
    SEMANTIC_SCHEMA_VERSION_PARSE_DOCUMENT,
    parse_load_workspace_from_pdf_semantic_stateless,
)

_LAB_LEAK = frozenset({"parse_diagnostics", "run_id", "ai_model_output", "semantic_extract_status"})
_FORBIDDEN_CONTEXT = frozenset({"choices", "ai_model_output", "parse_diagnostics", "raw_prompt"})


def _assert_public_dump_clean(out: LoadDocumentParseResponse) -> None:
    dumped = out.model_dump(mode="json")
    for k in _LAB_LEAK:
        assert k not in dumped


def _assert_context_allowlist(out: LoadDocumentParseResponse) -> None:
    for k in _FORBIDDEN_CONTEXT:
        assert k not in (out.context or {})


def _valid_semantic_ai_dict(*, filename: str = "stub.pdf", ref: str = "REF-1") -> dict:
    """B4 model output: no raw_text / context — server attaches those."""
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


def _lab_workspace_dict_for_mapper(*, ref: str = "REF-1", raw_text: str = "text") -> dict:
    """Full workspace contract keys for map_lab_parse_response_to_document_contract."""
    return {
        "document": {"filename": "labish.pdf"},
        "extracted": {
            "broker_load_reference": ref,
            "references": [],
            "stops": [],
        },
        "raw_text": raw_text,
        "warnings": [],
        "field_confidence": {},
        "context": {},
    }


@pytest.fixture
def openai_key_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "openai_api_key", "sk-test-key-for-semantic", raising=False)


@pytest.mark.asyncio
async def test_no_extractable_text_skips_openai_no_call() -> None:
    mock_openai = AsyncMock(return_value=_valid_semantic_ai_dict())
    with patch(
        "app.services.load_document_parse_semantic._extract_text_and_pages_from_pdf_bytes",
        return_value=("", [], []),
    ):
        out = await parse_load_workspace_from_pdf_semantic_stateless(
            b"%PDF-fake",
            filename="emptyish.pdf",
            openai_chat_json_schema=mock_openai,
        )
    mock_openai.assert_not_awaited()
    assert isinstance(out, LoadDocumentParseResponse)
    assert out.raw_text == ""
    assert out.context.get("semantic_outcome") == "skipped_no_text"
    assert any("No extractable text" in w for w in out.warnings)
    assert out.context.get("semantic_model")
    assert out.context.get("semantic_schema_version") == SEMANTIC_SCHEMA_VERSION_PARSE_DOCUMENT
    assert out.context.get("semantic_prompt_version") == SEMANTIC_PROMPT_VERSION_PARSE_DOCUMENT
    _assert_public_dump_clean(out)
    _assert_context_allowlist(out)


@pytest.mark.asyncio
async def test_no_openai_client_supplied_skips_call() -> None:
    with patch(
        "app.services.load_document_parse_semantic._extract_text_and_pages_from_pdf_bytes",
        return_value=("some text from pdf", [], []),
    ):
        out = await parse_load_workspace_from_pdf_semantic_stateless(
            b"%PDF-fake",
            filename="x.pdf",
            openai_chat_json_schema=None,
        )
    assert out.context.get("semantic_outcome") == "skipped_no_client"
    assert "no openai client" in " ".join(out.warnings).lower()
    assert out.context.get("semantic_model")
    _assert_public_dump_clean(out)
    _assert_context_allowlist(out)


@pytest.mark.asyncio
async def test_openai_key_missing_skips_http_injectable_not_called() -> None:
    mock_openai = AsyncMock(return_value=_valid_semantic_ai_dict())
    with patch(
        "app.services.load_document_parse_semantic._extract_text_and_pages_from_pdf_bytes",
        return_value=("pdf body text", [], []),
    ):
        with patch.object(settings, "openai_api_key", ""):
            out = await parse_load_workspace_from_pdf_semantic_stateless(
                b"%PDF-fake",
                filename="n.pdf",
                openai_chat_json_schema=mock_openai,
            )
    mock_openai.assert_not_awaited()
    assert out.context.get("semantic_outcome") == "skipped_missing_key"
    assert "not configured" in " ".join(out.warnings).lower() or "openai api key" in " ".join(
        out.warnings
    ).lower()
    _assert_public_dump_clean(out)
    _assert_context_allowlist(out)


@pytest.mark.asyncio
async def test_fake_openai_success_returns_valid_contract(openai_key_set: None) -> None:
    async def fake_openai(**_kwargs: object) -> dict:
        return _valid_semantic_ai_dict(filename="golden.pdf", ref="GOLD-9")

    with patch(
        "app.services.load_document_parse_semantic._extract_text_and_pages_from_pdf_bytes",
        return_value=("broker ref GOLD-9\nmore", [], []),
    ):
        out = await parse_load_workspace_from_pdf_semantic_stateless(
            b"%PDF-fake",
            filename="golden.pdf",
            openai_chat_json_schema=fake_openai,
        )
    assert out.extracted.broker_load_reference == "GOLD-9"
    assert out.raw_text == "broker ref GOLD-9\nmore"
    assert out.document.filename == "golden.pdf"
    assert out.context.get("semantic_outcome") == "success"
    assert out.context.get("parse_path") == "semantic_stateless"
    assert out.context.get("semantic_model")
    assert out.context.get("semantic_prompt_version") == SEMANTIC_PROMPT_VERSION_PARSE_DOCUMENT
    assert out.context.get("semantic_schema_version") == SEMANTIC_SCHEMA_VERSION_PARSE_DOCUMENT
    _assert_public_dump_clean(out)
    _assert_context_allowlist(out)


@pytest.mark.asyncio
async def test_minimal_ai_output_defaults_extracted(openai_key_set: None) -> None:
    async def fake_openai(**_kwargs: object) -> dict:
        return {"document": {"filename": "ignored.pdf"}, "extracted": {}}

    with patch(
        "app.services.load_document_parse_semantic._extract_text_and_pages_from_pdf_bytes",
        return_value=("body", [], []),
    ):
        out = await parse_load_workspace_from_pdf_semantic_stateless(
            b"%PDF-fake",
            filename="min.pdf",
            openai_chat_json_schema=fake_openai,
        )
    assert out.context.get("semantic_outcome") == "success"
    assert out.extracted.broker_load_reference is None
    assert out.document.filename == "min.pdf"
    _assert_public_dump_clean(out)


@pytest.mark.asyncio
async def test_field_confidence_preserved(openai_key_set: None) -> None:
    async def fake_openai(**_kwargs: object) -> dict:
        d = _valid_semantic_ai_dict(ref="R1")
        d["field_confidence"] = {"broker_load_reference": "high"}
        d["warnings"] = ["unsure about date"]
        return d

    with patch(
        "app.services.load_document_parse_semantic._extract_text_and_pages_from_pdf_bytes",
        return_value=("txt", [], []),
    ):
        out = await parse_load_workspace_from_pdf_semantic_stateless(
            b"%PDF-fake",
            filename="fc.pdf",
            openai_chat_json_schema=fake_openai,
        )
    assert out.field_confidence.get("broker_load_reference") == "high"
    assert any("unsure about date" in w for w in out.warnings)
    _assert_public_dump_clean(out)


@pytest.mark.asyncio
async def test_ai_warnings_precede_pdf_extract_warnings(openai_key_set: None) -> None:
    async def fake_openai(**_kwargs: object) -> dict:
        d = _valid_semantic_ai_dict()
        d["warnings"] = ["ai note"]
        return d

    with patch(
        "app.services.load_document_parse_semantic._extract_text_and_pages_from_pdf_bytes",
        return_value=("txt", [], ["pdf extract hint"]),
    ):
        out = await parse_load_workspace_from_pdf_semantic_stateless(
            b"%PDF-fake",
            filename="ord.pdf",
            openai_chat_json_schema=fake_openai,
        )
    assert out.warnings.index("ai note") < out.warnings.index("pdf extract hint")


@pytest.mark.asyncio
async def test_invalid_payload_validation_failed(openai_key_set: None) -> None:
    async def fake_openai(**_kwargs: object) -> dict:
        return {"document": {"filename": "x.pdf"}, "extracted": "not-an-object"}

    with patch(
        "app.services.load_document_parse_semantic._extract_text_and_pages_from_pdf_bytes",
        return_value=("txt", [], []),
    ):
        out = await parse_load_workspace_from_pdf_semantic_stateless(
            b"%PDF-fake",
            filename="bad.pdf",
            openai_chat_json_schema=fake_openai,
        )
    assert out.context.get("semantic_outcome") == "validation_failed"
    assert out.extracted.broker_load_reference is None
    assert any("validate semantic payload" in w.lower() for w in out.warnings)
    _assert_public_dump_clean(out)


@pytest.mark.asyncio
async def test_context_echo_preserves_only_allowlisted_keys(openai_key_set: None) -> None:
    async def fake_openai(**_kwargs: object) -> dict:
        return _valid_semantic_ai_dict()

    echo = {
        "email_thread_id": 42,
        "load_id": 100,
        "malicious_key": "leak",
    }
    with patch(
        "app.services.load_document_parse_semantic._extract_text_and_pages_from_pdf_bytes",
        return_value=("text", [], []),
    ):
        out = await parse_load_workspace_from_pdf_semantic_stateless(
            b"%PDF-fake",
            filename="c.pdf",
            context_echo=echo,
            openai_chat_json_schema=fake_openai,
        )
    assert out.context.get("email_thread_id") == 42
    assert out.context.get("load_id") == 100
    assert "malicious_key" not in out.context
    _assert_context_allowlist(out)


@pytest.mark.asyncio
async def test_lab_shaped_injectable_strips_leaks_via_mapper(openai_key_set: None) -> None:
    async def fake_openai(**_kwargs: object) -> dict:
        d = _lab_workspace_dict_for_mapper(raw_text="text")
        d["parse_diagnostics"] = {"internal": True}
        d["run_id"] = 123
        d["ai_model_output"] = {"x": 1}
        d["semantic_extract_status"] = "success"
        d["extracted"]["stops"] = [
            {"stop_type": "pickup", "sequence": 1, "city": "Austin"},
        ]
        return d

    with patch(
        "app.services.load_document_parse_semantic._extract_text_and_pages_from_pdf_bytes",
        return_value=("text", [], []),
    ):
        out = await parse_load_workspace_from_pdf_semantic_stateless(
            b"%PDF-fake",
            filename="labish.pdf",
            openai_chat_json_schema=fake_openai,
        )
    _assert_public_dump_clean(out)
    assert out.extracted.stops[0].sequence == 0
    assert out.context.get("semantic_outcome") == "success"
    _assert_context_allowlist(out)


@pytest.mark.asyncio
async def test_injectable_exception_returns_valid_sparse_with_warning(openai_key_set: None) -> None:
    async def boom(**_kwargs: object) -> dict:
        raise RuntimeError("network down")

    with patch(
        "app.services.load_document_parse_semantic._extract_text_and_pages_from_pdf_bytes",
        return_value=("saved text", [], []),
    ):
        out = await parse_load_workspace_from_pdf_semantic_stateless(
            b"%PDF-fake",
            filename="e.pdf",
            openai_chat_json_schema=boom,
        )
    assert out.raw_text == "saved text"
    assert out.context.get("semantic_outcome") == "openai_error"
    assert out.context.get("provider_status") == "error"
    assert any("OpenAI call failed" in w for w in out.warnings)
    _assert_public_dump_clean(out)
    _assert_context_allowlist(out)


@pytest.mark.asyncio
async def test_raw_openai_wire_unsupported(openai_key_set: None) -> None:
    async def fake_wire(**_kwargs: object) -> dict:
        return {"choices": [{"message": {"content": "{}"}}]}

    with patch(
        "app.services.load_document_parse_semantic._extract_text_and_pages_from_pdf_bytes",
        return_value=("t", [], []),
    ):
        out = await parse_load_workspace_from_pdf_semantic_stateless(
            b"%PDF-fake",
            filename="w.pdf",
            openai_chat_json_schema=fake_wire,
        )
    assert out.context.get("semantic_outcome") == "unsupported_openai_wire"
    assert "choices" not in out.context
    _assert_public_dump_clean(out)
    _assert_context_allowlist(out)


@pytest.mark.asyncio
async def test_semantic_extra_root_keys_ignored_no_leak(openai_key_set: None) -> None:
    async def fake(**_kwargs: object) -> dict:
        d = _valid_semantic_ai_dict(ref="X")
        d["evil_root"] = "leak"
        d["parse_path"] = "hijack"
        return d

    with patch(
        "app.services.load_document_parse_semantic._extract_text_and_pages_from_pdf_bytes",
        return_value=("txt", [], []),
    ):
        out = await parse_load_workspace_from_pdf_semantic_stateless(
            b"%PDF-fake",
            filename="strip.pdf",
            openai_chat_json_schema=fake,
        )
    assert out.extracted.broker_load_reference == "X"
    assert out.context.get("parse_path") == "semantic_stateless"
    assert "evil_root" not in out.context
    dumped = set(out.model_dump(mode="json").keys())
    assert "evil_root" not in dumped
    _assert_context_allowlist(out)


def test_module_avoids_db_and_load_lab_imports() -> None:
    import app.services.load_document_parse_semantic as mod

    src = open(mod.__file__, encoding="utf-8").read()
    lower = src.lower()
    assert "sqlalchemy" not in lower
    assert "load_lab_extraction_run" not in lower
    assert "semantic_extract_run" not in lower
