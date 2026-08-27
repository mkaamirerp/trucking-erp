"""Production Rate Confirmation parse-document entrypoint tests (v2 path).

Legacy PRODUCT_PARSE_DIAGNOSTICS / apply_guarded_load_document_repairs coverage removed
with the dead semantic diagnostics/repair modules.
"""

from __future__ import annotations

import inspect
import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from app.core.config import settings
from app.schemas.load_document_parse import LoadDocumentParseResponse, ParseDocumentSemanticModelOutput
from app.services import load_document_parse_guarded
from app.services.load_document_parse_adapter import map_lab_parse_response_to_document_contract
from app.services.load_document_parse_guarded import parse_pdf_bytes_to_load_document_response

_REPO_ROOT = Path(__file__).resolve().parents[1]
_FIXTURE_DIR = _REPO_ROOT / "docs" / "fixtures" / "load_lab"
_FIXTURE_PDF = _FIXTURE_DIR / "load_lab_fixture_1pickup_3deliveries.pdf"
_GOLDEN_CASES = [
    ("load_lab_fixture_1pickup_3deliveries.pdf", "load_lab_fixture_1pickup_3deliveries.lab_parse_response.json"),
    ("load_lab_fixture_3pickups_1delivery.pdf", "load_lab_fixture_3pickups_1delivery.lab_parse_response.json"),
]


@pytest.mark.asyncio
async def test_returns_sparse_shape_when_no_openai_client_or_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "openai_api_key", "", raising=False)

    out = await parse_pdf_bytes_to_load_document_response(
        AsyncMock(),
        tenant_id=1,
        pdf_bytes=_FIXTURE_PDF.read_bytes(),
        filename="fixture.pdf",
    )

    assert isinstance(out, LoadDocumentParseResponse)
    assert out.document.filename == "fixture.pdf"
    assert out.context["parse_path"] == "load_rate_con_v2"
    assert "[rate_con_v2] OpenAI client not supplied; extraction skipped." in out.warnings
    assert out.raw_text


@pytest.mark.asyncio
async def test_no_injected_client_uses_default_product_openai_when_key_exists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services import load_document_parse_rate_con

    calls: list[dict] = []

    async def fake_default_openai(**kwargs):
        calls.append(kwargs)
        return {
            "document": {"filename": "default.pdf"},
            "extracted": {"broker_load_reference": "DEF-123", "references": [], "stops": []},
            "raw_text": "default raw",
            "warnings": [],
            "field_confidence": {},
            "context": {},
        }

    monkeypatch.setattr(settings, "openai_api_key", "sk-test-key", raising=False)
    monkeypatch.setattr(
        load_document_parse_rate_con,
        "parse_document_openai_chat_json_schema",
        fake_default_openai,
    )

    out = await parse_pdf_bytes_to_load_document_response(
        AsyncMock(),
        tenant_id=1,
        pdf_bytes=_FIXTURE_PDF.read_bytes(),
        filename="default.pdf",
    )

    assert out.extracted.broker_load_reference == "DEF-123"
    assert out.context["parse_path"] == "load_rate_con_v2"
    assert calls
    assert calls[0]["api_key"] == "sk-test-key"
    assert calls[0]["schema_name"] == "load_document_parse_guarded_truckerjson_v1"
    assert "PRODUCT_PARSE_DIAGNOSTICS" not in calls[0]["user_text"]
    assert "tenant_identity_exclusion" in calls[0]["user_text"]


@pytest.mark.asyncio
async def test_uses_injected_openai_callable_and_returns_mapped_fields() -> None:
    calls: list[dict] = []

    async def fake_openai(**kwargs):
        calls.append(kwargs)
        return {
            "document": {"filename": "ai.pdf"},
            "extracted": {
                "broker_load_reference": "REF-123",
                "broker_name_snapshot": "Acme Broker",
                "references": [],
                "stops": [],
            },
            "raw_text": "ai raw",
            "warnings": ["ai warning"],
            "field_confidence": {"broker_load_reference": "high"},
            "context": {"semantic_outcome": "success"},
        }

    out = await parse_pdf_bytes_to_load_document_response(
        AsyncMock(),
        tenant_id=42,
        pdf_bytes=_FIXTURE_PDF.read_bytes(),
        filename="input.pdf",
        openai_chat_json_schema=fake_openai,
        forensic_enabled=True,
    )

    assert out.extracted.broker_load_reference == "REF-123"
    assert out.extracted.broker_name_snapshot == "Acme Broker"
    assert out.field_confidence["broker_load_reference"] == "high"
    assert out.context["parse_path"] == "load_rate_con_v2"
    assert calls
    assert calls[0]["model"]
    assert "PRODUCT_PARSE_DIAGNOSTICS" not in calls[0]["user_text"]
    assert "broker_party" not in calls[0]["user_text"]
    assert "role_hint" not in calls[0]["user_text"]
    assert "tenant_identity_exclusion" in calls[0]["user_text"]
    assert "field_rules" in calls[0]["user_text"]
    assert "document.pages" in calls[0]["user_text"] or '"pages"' in calls[0]["user_text"]
    assert calls[0]["schema"]["type"] == "object"
    assert calls[0]["schema_name"] == "load_document_parse_guarded_truckerjson_v1"


@pytest.mark.asyncio
async def test_strips_parse_diagnostics_from_injected_payload() -> None:
    async def fake_openai(**_kwargs):
        return {
            "document": {"filename": "diag.pdf"},
            "extracted": {"broker_load_reference": "DIAG-1", "references": [], "stops": []},
            "raw_text": "raw",
            "warnings": [],
            "field_confidence": {},
            "context": {"parse_diagnostics": {"leak": True}},
            "parse_diagnostics": {"root": "diagnostic"},
            "unknown_root_key": "ignored",
        }

    out = await parse_pdf_bytes_to_load_document_response(
        AsyncMock(),
        tenant_id=1,
        pdf_bytes=_FIXTURE_PDF.read_bytes(),
        filename="diag.pdf",
        openai_chat_json_schema=fake_openai,
    )

    dumped = out.model_dump(mode="json")
    assert "parse_diagnostics" not in dumped
    assert "parse_diagnostics" not in out.context
    assert "unknown_root_key" not in dumped
    assert out.context["parse_path"] == "load_rate_con_v2"


def test_guarded_module_is_thin_reexport_only() -> None:
    src = inspect.getsource(load_document_parse_guarded)
    assert "parse_pdf_bytes_to_load_document_response" in src
    assert "load_document_parse_rate_con" in src
    assert "build_load_document_parse_diagnostics" not in src
    assert "apply_guarded_load_document_repairs" not in src or "removed" in src.casefold()
    assert "app.services.load_lab_semantic" not in src


def test_v2_system_prompt_is_exclusion_and_field_rules_based() -> None:
    from app.services.load_parser_openai_handoff_v2 import build_v2_openai_system_prompt

    system = build_v2_openai_system_prompt().casefold()
    assert "tenant_identity_exclusion" in system
    assert "field_rules" in system
    assert "product_parse_diagnostics" not in system
    assert "broker_party" not in system


def test_semantic_model_json_schema_includes_document_type_enum() -> None:
    schema = ParseDocumentSemanticModelOutput.model_json_schema()
    props = schema["properties"]
    assert "document_type" in props
    assert "classification_reasoning" in props
    enum = props["document_type"].get("anyOf") or props["document_type"].get("enum")
    if isinstance(enum, list) and enum and isinstance(enum[0], dict):
        inner = next((x for x in enum if x.get("type") == "string" and "enum" in x), None)
        assert inner is not None
        assert "rate_confirmation" in inner["enum"]
    else:
        assert "enum" in props["document_type"]
        assert "rate_confirmation" in props["document_type"]["enum"]


def test_v2_user_message_has_no_product_parse_diagnostics() -> None:
    from app.services.load_parser_openai_handoff_v2 import (
        build_load_rate_con_openai_handoff_v2_payload,
        build_v2_openai_user_message,
    )

    handoff = build_load_rate_con_openai_handoff_v2_payload(
        tenant_identity_exclusion={
            "names": [],
            "mc_numbers": [],
            "usdot_numbers": [],
            "phones": [],
            "emails": [],
            "email_domains": [],
            "addresses": [],
        },
        pages=["STOP DETAIL\nPU 05/29/25\n09:00"],
        filename="rc.pdf",
    )
    text = build_v2_openai_user_message(handoff)
    assert "PRODUCT_PARSE_DIAGNOSTICS" not in text
    assert "tenant_identity_exclusion" in text
    assert "field_rules" in text
    assert "STOP DETAIL" in text


@pytest.mark.asyncio
async def test_maps_document_type_and_reasoning_into_context() -> None:
    async def fake_openai(**_kwargs):
        return {
            "document": {"filename": "c.pdf"},
            "document_type": "rate_confirmation",
            "classification_reasoning": "Broker→carrier load confirmation with two stops.",
            "extracted": {"references": [], "stops": []},
            "warnings": [],
            "field_confidence": {},
            "context": {},
        }

    out = await parse_pdf_bytes_to_load_document_response(
        AsyncMock(),
        tenant_id=1,
        pdf_bytes=_FIXTURE_PDF.read_bytes(),
        filename="c.pdf",
        openai_chat_json_schema=fake_openai,
    )
    assert out.context.get("document_type") == "rate_confirmation"
    assert "Broker→carrier" in str(out.context.get("classification_reasoning") or "")
    assert out.context.get("parse_path") == "load_rate_con_v2"


@pytest.mark.asyncio
@pytest.mark.parametrize("pdf_name,json_name", _GOLDEN_CASES)
async def test_product_parser_maps_saved_lab_golden_without_exposing_diagnostics(
    pdf_name: str,
    json_name: str,
) -> None:
    golden_payload = json.loads((_FIXTURE_DIR / json_name).read_text(encoding="utf-8"))

    async def fake_openai(**_kwargs):
        return golden_payload

    product = await parse_pdf_bytes_to_load_document_response(
        AsyncMock(),
        tenant_id=1,
        pdf_bytes=(_FIXTURE_DIR / pdf_name).read_bytes(),
        filename=pdf_name,
        openai_chat_json_schema=fake_openai,
    )
    mapped_lab = map_lab_parse_response_to_document_contract(golden_payload)

    dumped = product.model_dump(mode="json")
    assert "parse_diagnostics" not in dumped
    assert "parse_diagnostics" not in product.context
    assert product.context["parse_path"] == "load_rate_con_v2"
    assert product.extracted.broker_load_reference == mapped_lab.extracted.broker_load_reference
    assert len(product.extracted.stops) == len(mapped_lab.extracted.stops)


def test_dead_semantic_modules_are_gone() -> None:
    import importlib

    for mod in (
        "app.services.load_document_parse_diagnostics",
        "app.services.load_document_parse_guardrails",
        "app.services.load_document_parse_reference",
        "app.services.load_document_parse_contact_candidates",
    ):
        with pytest.raises(ModuleNotFoundError):
            importlib.import_module(mod)
