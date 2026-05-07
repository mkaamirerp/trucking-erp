from __future__ import annotations

import inspect
import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from app.core.config import settings
from app.schemas.load_document_parse import LoadDocumentParseResponse
from app.services import load_document_parse_guarded
from app.services.load_document_parse_adapter import map_lab_parse_response_to_document_contract
from app.services.load_document_parse_guardrails import apply_guarded_load_document_repairs
from app.services.load_document_parse_guarded import parse_pdf_bytes_to_load_document_response
from app.services.load_document_parse_diagnostics import build_load_document_parse_diagnostics
from app.services.load_document_parse_reference import rank_reference_candidates

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
    assert out.context["parse_path"] == "guarded_truckerjson"
    assert "[guarded] OpenAI client not supplied; guarded extraction skipped." in out.warnings
    assert out.raw_text


@pytest.mark.asyncio
async def test_no_injected_client_uses_default_product_openai_when_key_exists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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
        load_document_parse_guarded,
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
    assert out.context["parse_path"] == "guarded_truckerjson"
    assert calls
    assert calls[0]["api_key"] == "sk-test-key"
    assert calls[0]["schema_name"] == "load_document_parse_guarded_truckerjson_v1"


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
    assert out.context["parse_path"] == "guarded_truckerjson"
    assert calls
    assert calls[0]["model"]
    assert "guarded, conservative extraction" in calls[0]["system"]
    assert "Filename for document.filename: input.pdf" in calls[0]["user_text"]
    assert "PRODUCT_PARSE_DIAGNOSTICS" in calls[0]["user_text"]
    assert "reference_candidates" in calls[0]["user_text"]
    assert "--- BEGIN EXTRACTED PDF TEXT ---" in calls[0]["user_text"]
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
    assert out.context["parse_path"] == "guarded_truckerjson"


def test_module_does_not_import_load_lab_semantic() -> None:
    src = inspect.getsource(load_document_parse_guarded)
    assert "app.services.load_lab_semantic" not in src
    assert "load_lab_semantic" not in src


def test_diagnostics_contacts_split_carrier_vs_broker_party() -> None:
    text = """
BROKER AGREEMENT
CONTACT INFORMATION
Jane Agent 800-111-2222 jane@acmebroker.com

Carrier Contact
Dispatcher 513-688-6962 carrierops@carrier.com
""".strip()
    diag = build_load_document_parse_diagnostics(
        raw_full_text=text,
        page_texts=[text],
        filename="t.pdf",
        extraction_method="test",
    )
    bp = diag["contacts"]["broker_party"]
    cp = diag["contacts"]["carrier_party"]
    assert "jane@acmebroker.com" in bp["emails"]
    assert "carrierops@carrier.com" in cp["emails"]
    assert cp["phones"]


def test_guardrails_clear_broker_contact_name_when_carrier_section_name_matches() -> None:
    text = """
CONTACT INFORMATION
Jane Broker jane@shipco.com 800-111-2222

Carrier Contact
Name
Dispatcher
Imran Khan

LOAD INFORMATION
Mode
""".strip()
    diag = build_load_document_parse_diagnostics(
        raw_full_text=text,
        page_texts=[text],
        filename="carriername.pdf",
        extraction_method="test",
    )
    assert "imran khan" in {n.casefold() for n in (diag["contacts"]["carrier_party"].get("person_names") or [])}

    base = LoadDocumentParseResponse.model_validate(
        {
            "document": {"filename": "carriername.pdf"},
            "extracted": {
                "broker_contact_name_snapshot": "Imran Khan",
                "broker_contact_email_snapshot": "jane@shipco.com",
                "broker_contact_phone_snapshot": "800-111-2222",
                "references": [],
                "stops": [],
            },
            "raw_text": text,
            "warnings": [],
            "field_confidence": {},
            "context": {"parse_path": "guarded_truckerjson"},
        }
    )
    out = apply_guarded_load_document_repairs(base, diagnostics=diag)
    assert out.extracted.broker_contact_email_snapshot == "jane@shipco.com"
    assert out.extracted.broker_contact_phone_snapshot == "800-111-2222"
    assert out.extracted.broker_contact_name_snapshot is None
    assert any("broker_party name candidates" in w or "carrier/driver-party name" in w for w in out.warnings)


def test_guardrails_clear_broker_contact_when_carrier_party_matches() -> None:
    base = LoadDocumentParseResponse.model_validate(
        {
            "document": {"filename": "x.pdf"},
            "extracted": {
                "broker_contact_name_snapshot": "Wrong Dispatch",
                "broker_contact_phone_snapshot": "513-688-6962",
                "broker_contact_email_snapshot": "mike@carrier.com",
                "references": [],
                "stops": [],
            },
            "raw_text": "x",
            "warnings": [],
            "field_confidence": {},
            "context": {"parse_path": "guarded_truckerjson"},
        }
    )
    diagnostics = {
        "contact_candidates": [
            {"kind": "email", "value": "mike@carrier.com", "role": "carrier_party"},
            {"kind": "phone", "value": "(513) 688-6962", "role": "carrier_party"},
            {"kind": "name", "value": "Wrong Dispatch", "role": "carrier_party"},
        ],
    }
    out = apply_guarded_load_document_repairs(base, diagnostics=diagnostics)
    assert out.extracted.broker_contact_email_snapshot is None
    assert out.extracted.broker_contact_phone_snapshot is None
    assert out.extracted.broker_contact_name_snapshot is None
    assert any("Cleared broker_contact_email_snapshot" in w for w in out.warnings)
    assert any("Cleared broker_contact_phone_snapshot" in w for w in out.warnings)


def test_reference_ranking_prefers_load_number() -> None:
    diagnostics = {
        "reference_candidates": [
            {"kind": "po_number", "value": "PO-777", "line": 2},
            {"kind": "load_number", "value": "LOAD-123", "line": 5},
            {"kind": "load_number", "value": "INFORMATION", "line": 1},
            {"kind": "confirmation_number", "value": "Load", "line": 1},
        ]
    }

    ranking = rank_reference_candidates(diagnostics)

    assert ranking["primary"]["kind"] == "load_number"
    assert ranking["primary"]["value"] == "LOAD-123"


def test_guardrails_fill_missing_broker_reference_and_clear_decimal_reference() -> None:
    base = LoadDocumentParseResponse.model_validate(
        {
            "document": {"filename": "x.pdf"},
            "extracted": {"broker_load_reference": "12.34", "references": [], "stops": []},
            "raw_text": "Load # LOAD-123",
            "warnings": [],
            "field_confidence": {},
            "context": {"parse_path": "guarded_truckerjson"},
        }
    )
    diagnostics = {
        "reference_candidates": [{"kind": "load_number", "value": "LOAD-123", "line": 1}],
    }

    out = apply_guarded_load_document_repairs(base, diagnostics=diagnostics)

    assert out.extracted.broker_load_reference is None
    assert any("decimal-like broker_load_reference" in w for w in out.warnings)
    assert any(r.value == "LOAD-123" for r in out.extracted.references)


def test_guardrails_fill_missing_stop_facilities_and_move_customer_rate() -> None:
    base = LoadDocumentParseResponse.model_validate(
        {
            "document": {"filename": "x.pdf"},
            "extracted": {
                "customer_rate": 1200,
                "references": [],
                "stops": [
                    {"stop_type": "pickup", "sequence": 0, "city": "Miami", "reference_number": "P1"},
                    {"stop_type": "delivery", "sequence": 1, "city": "Atlanta", "reference_number": "D1"},
                ],
            },
            "raw_text": "x",
            "warnings": [],
            "field_confidence": {},
            "context": {"parse_path": "guarded_truckerjson"},
        }
    )
    diagnostics = {
        "route_stop_hints": [
            {
                "sequence": 0,
                "facility_name": "Pickup A",
                "street": "10 Harbor Way",
                "appointment_date": "2025-12-01",
                "appointment_time_text": "07:00",
            },
            {
                "sequence": 1,
                "facility_name": "Single Drop",
                "street": "500 Peachtree",
                "appointment_date": "2025-12-03",
                "appointment_time_text": "10:00-16:00",
            },
        ],
    }

    out = apply_guarded_load_document_repairs(base, diagnostics=diagnostics)

    assert out.extracted.rate == 1200
    assert out.extracted.customer_rate is None
    assert out.extracted.stops[0].facility_name == "Pickup A"
    assert out.extracted.stops[0].street == "10 Harbor Way"
    assert out.extracted.stops[1].facility_name == "Single Drop"


def test_guardrails_fill_missing_rate_from_financial_hint() -> None:
    base = LoadDocumentParseResponse.model_validate(
        {
            "document": {"filename": "x.pdf"},
            "extracted": {"references": [], "stops": []},
            "raw_text": "Rate: $1,200.00 USD",
            "warnings": [],
            "field_confidence": {},
            "context": {"parse_path": "guarded_truckerjson"},
        }
    )

    out = apply_guarded_load_document_repairs(
        base,
        diagnostics={"financial_hints": {"linehaul_rate": 1200.0}},
    )

    assert out.extracted.rate == 1200


def test_guardrails_repair_numeric_trailer_type_from_equipment_hint() -> None:
    base = LoadDocumentParseResponse.model_validate(
        {
            "document": {"filename": "x.pdf"},
            "extracted": {"trailer_type": "53", "references": [], "stops": []},
            "raw_text": "Trailer: 53 dry van",
            "warnings": [],
            "field_confidence": {},
            "context": {"parse_path": "guarded_truckerjson"},
        }
    )

    out = apply_guarded_load_document_repairs(
        base,
        diagnostics={"equipment_hints": {"trailer_type": "Van", "trailer_size": "53"}},
    )

    assert out.extracted.trailer_type == "Van"
    assert out.extracted.trailer_size == "53"


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
    assert product.context["parse_path"] == "guarded_truckerjson"
    assert product.extracted.broker_load_reference == mapped_lab.extracted.broker_load_reference
    assert len(product.extracted.stops) == len(mapped_lab.extracted.stops)
