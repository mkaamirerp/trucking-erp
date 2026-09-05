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
from pypdf import PdfWriter

from app.core.config import settings
from app.schemas.load_document_parse import LoadDocumentParseResponse
from app.schemas.load_document_parse_semantic import ParseDocumentSemanticModelOutput
from app.services import load_document_parse_guarded
from app.services.load_document_parse_adapter import map_lab_parse_response_to_document_contract
from app.services.load_document_parse_guarded import parse_pdf_bytes_to_load_document_response
from app.services.load_parser_pdf_safety import UnsafeLoadPdfError

_REPO_ROOT = Path(__file__).resolve().parents[1]
_FIXTURE_DIR = _REPO_ROOT / "docs" / "fixtures" / "load_lab"
_FIXTURE_PDF = _FIXTURE_DIR / "load_lab_fixture_1pickup_3deliveries.pdf"
_GOLDEN_CASES = [
    ("load_lab_fixture_1pickup_3deliveries.pdf", "load_lab_fixture_1pickup_3deliveries.lab_parse_response.json"),
    ("load_lab_fixture_3pickups_1delivery.pdf", "load_lab_fixture_3pickups_1delivery.lab_parse_response.json"),
]


def _lab_golden_to_semantic_openai(golden_payload: dict) -> dict:
    """Test-only: lab goldens are product-shaped; OpenAI now returns semantic extracted."""
    payload = dict(golden_payload)
    ex = dict(payload.get("extracted") or {})
    payload["extracted"] = {
        "broker_company": {
            "name": ex.get("broker_name_snapshot"),
            "main_phone": ex.get("broker_phone_snapshot"),
            "mc_number": ex.get("broker_mc_number_snapshot"),
            "dot_number": ex.get("broker_dot_number_snapshot"),
        },
        "broker_agent": {
            "name": ex.get("broker_contact_name_snapshot"),
            "direct_phone": ex.get("broker_contact_phone_snapshot"),
            "email": ex.get("broker_contact_email_snapshot"),
        },
        "principal_load_identifier": ex.get("broker_load_reference"),
        "freight_mode": ex.get("mode"),
        "equipment": {
            "description": ex.get("equipment_type"),
            "trailer_body_type": ex.get("trailer_type"),
            "trailer_length": ex.get("trailer_size"),
        },
        "commodity": ex.get("commodity"),
        "estimated_weight": ex.get("estimated_weight"),
        "temperature_requirement": ex.get("temperature_requirement"),
        "rate": ex.get("rate"),
        "customer_rate": ex.get("customer_rate"),
        "miles": ex.get("miles"),
        "customs_broker_name": ex.get("customs_broker_name"),
        "references": ex.get("references") or [],
        "stops": ex.get("stops") or [],
    }
    return payload


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
            "extracted": {
                "principal_load_identifier": "DEF-123",
                "references": [],
                "stops": [],
            },
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
    assert calls[0]["input_file_bytes"] == _FIXTURE_PDF.read_bytes()
    assert calls[0]["input_filename"] == "default.pdf"
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
                "principal_load_identifier": "REF-123",
                "broker_company": {"name": "Acme Broker"},
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
    assert calls[0]["input_file_bytes"] == _FIXTURE_PDF.read_bytes()
    assert calls[0]["input_filename"] == "input.pdf"


@pytest.mark.asyncio
async def test_digital_pdf_does_not_invoke_ocr(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services import load_document_parse_rate_con

    def boom(_pdf_bytes: bytes):
        raise AssertionError("OCR must not run on a digital PDF")

    monkeypatch.setattr(load_document_parse_rate_con, "ocr_load_parser_pdf_pages", boom)

    async def fake_openai(**kwargs):
        assert kwargs["input_file_bytes"] == _FIXTURE_PDF.read_bytes()
        return {
            "document": {"filename": "digital.pdf"},
            "extracted": {"principal_load_identifier": "D-1", "references": [], "stops": []},
            "warnings": [],
            "field_confidence": {},
            "context": {},
        }

    out = await parse_pdf_bytes_to_load_document_response(
        AsyncMock(),
        tenant_id=1,
        pdf_bytes=_FIXTURE_PDF.read_bytes(),
        filename="digital.pdf",
        openai_chat_json_schema=fake_openai,
    )
    assert out.extracted.broker_load_reference == "D-1"
    assert out.context.get("requires_ocr") is False


def _blank_pdf_bytes() -> bytes:
    from io import BytesIO

    buf = BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    writer.add_blank_page(width=612, height=792)
    writer.write(buf)
    return buf.getvalue()


@pytest.mark.asyncio
async def test_scanned_image_sends_ocr_text_not_pdf(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services import load_document_parse_rate_con

    scanned = _blank_pdf_bytes()
    calls: list[dict] = []

    def fake_ocr(_pdf_bytes: bytes):
        return (
            [
                {"page_number": 1, "text": "AGRICULTURE OCR PAGE 1 LOAD 123"},
                {"page_number": 2, "text": "AGRICULTURE OCR PAGE 2 STOP A"},
            ],
            [],
        )

    monkeypatch.setattr(load_document_parse_rate_con, "ocr_load_parser_pdf_pages", fake_ocr)

    async def fake_openai(**kwargs):
        calls.append(kwargs)
        return {
            "document": {"filename": "scanned.pdf"},
            "extracted": {"principal_load_identifier": "OCR-1", "references": [], "stops": []},
            "warnings": [],
            "field_confidence": {},
            "context": {},
        }

    out = await parse_pdf_bytes_to_load_document_response(
        AsyncMock(),
        tenant_id=1,
        pdf_bytes=scanned,
        filename="scanned.pdf",
        openai_chat_json_schema=fake_openai,
    )

    assert calls
    assert calls[0]["input_file_bytes"] is None
    assert "AGRICULTURE OCR PAGE 1" in calls[0]["user_text"]
    assert "field_rules" in calls[0]["user_text"]
    assert "tenant_identity_exclusion" in calls[0]["user_text"]
    assert calls[0]["schema_name"] == "load_document_parse_guarded_truckerjson_v1"
    assert out.extracted.broker_load_reference == "OCR-1"
    assert out.context["requires_ocr"] is True
    assert out.context["semantic_input"] == "ocr_text"


@pytest.mark.asyncio
async def test_mixed_pdf_still_blocks_without_ocr_or_openai(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services import load_document_parse_rate_con

    def boom(_pdf_bytes: bytes):
        raise AssertionError("OCR must not run on mixed PDFs")

    monkeypatch.setattr(load_document_parse_rate_con, "ocr_load_parser_pdf_pages", boom)
    monkeypatch.setattr(
        load_document_parse_rate_con,
        "acquire_load_parser_pdf_pages",
        lambda _b: {
            "pdf_type": "mixed",
            "page_count": 2,
            "requires_ocr": True,
            "pages": [
                {
                    "page_number": 1,
                    "source": "embedded_text",
                    "usable_embedded_text": True,
                    "requires_ocr": False,
                    "text": "Load confirmation page one with enough alphanumeric content here.",
                },
                {
                    "page_number": 2,
                    "source": "ocr_required",
                    "usable_embedded_text": False,
                    "requires_ocr": True,
                    "text": "",
                },
            ],
            "warnings": [],
        },
    )
    openai = AsyncMock()
    out = await parse_pdf_bytes_to_load_document_response(
        AsyncMock(),
        tenant_id=1,
        pdf_bytes=_FIXTURE_PDF.read_bytes(),
        filename="mixed.pdf",
        openai_chat_json_schema=openai,
    )
    openai.assert_not_awaited()
    assert out.context["semantic_outcome"] == "blocked_ocr_required"
    assert out.context["pdf_type"] == "mixed"


@pytest.mark.asyncio
async def test_agriculture_pdf_ocr_path_uses_text_not_file(monkeypatch: pytest.MonkeyPatch) -> None:
    """Agriculture.pdf is scanned_image. OCR is mocked; OpenAI is injected (no live call)."""
    from app.services import load_document_parse_rate_con

    agriculture = Path("/tmp/Agriculture.pdf")
    if not agriculture.is_file():
        pytest.skip("Agriculture.pdf not present")

    calls: list[dict] = []

    def fake_ocr(pdf_bytes: bytes):
        assert pdf_bytes == agriculture.read_bytes()
        return (
            [
                {"page_number": 1, "text": "AG PAGE 1"},
                {"page_number": 2, "text": "AG PAGE 2"},
                {"page_number": 3, "text": "AG PAGE 3"},
                {"page_number": 4, "text": "AG PAGE 4"},
            ],
            [],
        )

    monkeypatch.setattr(load_document_parse_rate_con, "ocr_load_parser_pdf_pages", fake_ocr)

    async def fake_openai(**kwargs):
        calls.append(kwargs)
        return {
            "document": {"filename": "Agriculture.pdf"},
            "extracted": {"principal_load_identifier": "AG-12345", "references": [], "stops": []},
            "warnings": [],
            "field_confidence": {},
            "context": {},
        }

    out = await parse_pdf_bytes_to_load_document_response(
        AsyncMock(),
        tenant_id=1,
        pdf_bytes=agriculture.read_bytes(),
        filename="Agriculture.pdf",
        openai_chat_json_schema=fake_openai,
    )

    assert calls[0]["input_file_bytes"] is None
    assert "AG PAGE 1" in calls[0]["user_text"]
    assert "field_rules" in calls[0]["user_text"]
    assert out.extracted.broker_load_reference == "AG-12345"


@pytest.mark.asyncio
async def test_unsafe_pdf_is_rejected_before_openai(tmp_path: Path) -> None:
    unsafe_path = tmp_path / "javascript.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    writer.add_js("app.alert('unsafe')")
    writer.write(unsafe_path)
    openai = AsyncMock()

    with pytest.raises(UnsafeLoadPdfError, match="active content"):
        await parse_pdf_bytes_to_load_document_response(
            AsyncMock(),
            tenant_id=1,
            pdf_bytes=unsafe_path.read_bytes(),
            filename="javascript.pdf",
            openai_chat_json_schema=openai,
        )

    openai.assert_not_awaited()


@pytest.mark.asyncio
async def test_strips_parse_diagnostics_from_injected_payload() -> None:
    async def fake_openai(**_kwargs):
        return {
            "document": {"filename": "diag.pdf"},
            "extracted": {"principal_load_identifier": "DIAG-1", "references": [], "stops": []},
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
        return _lab_golden_to_semantic_openai(golden_payload)

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
