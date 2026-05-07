"""Orchestrator for parse-document: guarded product parser only. No live OpenAI."""

from __future__ import annotations

import inspect
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from app.schemas.load_document_parse import LoadDocumentParseResponse
from app.services import load_document_parse_orchestrator
from app.services.load_document_parse_orchestrator import parse_load_workspace_document_orchestrated

_REPO_ROOT = Path(__file__).resolve().parents[1]
_FIXTURE_PDF = _REPO_ROOT / "docs" / "fixtures" / "load_lab" / "load_lab_fixture_1pickup_3deliveries.pdf"

_LAB_LEAK = frozenset({"parse_diagnostics", "ai_model_output", "run_id", "semantic_extract_status"})


def _assert_public_response_clean(out: LoadDocumentParseResponse) -> None:
    dumped = out.model_dump(mode="json")
    for k in _LAB_LEAK:
        assert k not in dumped
    for k in _LAB_LEAK:
        assert k not in (out.context or {})


@pytest.mark.asyncio
async def test_orchestrator_calls_guarded_product_parser(monkeypatch: pytest.MonkeyPatch) -> None:
    pdf_bytes = _FIXTURE_PDF.read_bytes()
    calls: list[dict] = []

    async def fake_guarded(db, **kwargs):  # noqa: ANN001
        calls.append({"db": db, **kwargs})
        return LoadDocumentParseResponse.model_validate(
            {
                "document": {"filename": kwargs["filename"]},
                "extracted": {"broker_load_reference": "GUARDED-1"},
                "raw_text": "guarded raw",
                "warnings": [],
                "field_confidence": {},
                "context": {"parse_path": "guarded_truckerjson"},
            }
        )

    monkeypatch.setattr(
        load_document_parse_orchestrator,
        "parse_pdf_bytes_to_load_document_response",
        fake_guarded,
    )
    db = AsyncMock()

    out = await parse_load_workspace_document_orchestrated(
        pdf_bytes,
        filename="guarded.pdf",
        tenant_id=12,
        db=db,
        openai_chat_json_schema=None,
    )

    assert out.extracted.broker_load_reference == "GUARDED-1"
    assert out.context.get("parse_path") == "guarded_truckerjson"
    assert len(calls) == 1
    assert calls[0]["db"] is db
    assert calls[0]["tenant_id"] == 12
    assert calls[0]["pdf_bytes"] == pdf_bytes
    assert calls[0]["filename"] == "guarded.pdf"
    assert calls[0]["openai_chat_json_schema"] is None
    _assert_public_response_clean(out)


@pytest.mark.asyncio
async def test_orchestrator_without_client_returns_guarded_sparse_response() -> None:
    pdf_bytes = _FIXTURE_PDF.read_bytes()
    out = await parse_load_workspace_document_orchestrated(
        pdf_bytes,
        filename="sparse.pdf",
        tenant_id=1,
        db=AsyncMock(),
        openai_chat_json_schema=None,
    )

    assert out.context.get("parse_path") == "guarded_truckerjson"
    assert "[guarded] OpenAI client not supplied; guarded extraction skipped." in out.warnings
    assert out.extracted.broker_load_reference is None
    _assert_public_response_clean(out)


@pytest.mark.asyncio
async def test_orchestrator_requires_tenant_and_db() -> None:
    with pytest.raises(RuntimeError, match="tenant_id and db"):
        await parse_load_workspace_document_orchestrated(
            _FIXTURE_PDF.read_bytes(),
            filename="missing.pdf",
            tenant_id=None,
            db=None,
        )


def test_orchestrator_does_not_import_or_call_old_b4_semantic_parser() -> None:
    src = inspect.getsource(load_document_parse_orchestrator)
    assert "parse_load_workspace_from_pdf_semantic_stateless" not in src
    assert "parse_load_workspace_from_pdf_bytes" not in src
    assert "semantic_enabled" not in src
