"""Regression: digital PDF OpenAI handoff must not duplicate extracted page text."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from app.schemas.load_document_parse_semantic import ParseDocumentSemanticModelOutput
from app.services.load_document_parse_guarded import parse_pdf_bytes_to_load_document_response
from app.services.load_parser_openai_handoff_v2 import (
    build_load_rate_con_openai_handoff_v2_payload,
    build_v2_openai_system_prompt,
    build_v2_openai_user_message,
)

_REPO_ROOT = Path(__file__).resolve().parents[1]
_FIXTURE_PDF = (
    _REPO_ROOT / "docs" / "fixtures" / "load_lab" / "load_lab_fixture_1pickup_3deliveries.pdf"
)
_TQL_PDF = _REPO_ROOT / "TQLRC.pdf"
_TQL_SHA256 = "05849ad1a1256eff16b7cc117d0b694c55e1b599d9ad6e0da3ba36a2ee8c8b89"


def _sample_exclusion() -> dict:
    return {
        "names": [],
        "mc_numbers": [],
        "usdot_numbers": [],
        "phones": [],
        "emails": [],
        "email_domains": [],
        "addresses": [],
    }


def test_digital_handoff_omits_page_text_but_keeps_metadata() -> None:
    pages = [
        {"page_number": 1, "text": "JD FACTORS DECOY TEXT MUST NOT REACH AI"},
        {"page_number": 2, "text": "CHARLOTTE PICKUP LINE"},
    ]
    handoff = build_load_rate_con_openai_handoff_v2_payload(
        tenant_identity_exclusion=_sample_exclusion(),
        pages=pages,
        filename="TQLRC.pdf",
        include_page_text_in_ai_handoff=False,
        page_count=2,
    )
    assert handoff["document"]["page_count"] == 2
    assert handoff["document"]["pages"] == []
    assert "field_rules" in handoff
    assert "tenant_identity_exclusion" in handoff

    user_msg = build_v2_openai_user_message(handoff, pdf_bytes_attached=True)
    assert "JD FACTORS DECOY" not in user_msg
    assert "CHARLOTTE PICKUP" not in user_msg
    assert "field_rules" in user_msg
    assert "tenant_identity_exclusion" in user_msg
    assert "attached original PDF" in user_msg

    system = build_v2_openai_system_prompt(pdf_bytes_attached=True)
    assert "attached" in system.casefold()
    assert "duplicated flattened text" in system.casefold()


def test_scanned_handoff_still_includes_ocr_page_text() -> None:
    ocr_text = "OCR PAGE 1 RATE CONFIRMATION"
    handoff = build_load_rate_con_openai_handoff_v2_payload(
        tenant_identity_exclusion=_sample_exclusion(),
        pages=[{"page_number": 1, "text": ocr_text}],
        filename="scan.pdf",
        extraction_method="product_pdf_ocr",
        acquisition_method="scanned_image_ocr",
        include_page_text_in_ai_handoff=True,
    )
    assert handoff["document"]["pages"][0]["text"] == ocr_text
    user_msg = build_v2_openai_user_message(handoff, pdf_bytes_attached=False)
    assert ocr_text in user_msg


@pytest.mark.asyncio
async def test_digital_parse_path_openai_kwargs() -> None:
    pdf_bytes = _FIXTURE_PDF.read_bytes()
    calls: list[dict] = []

    async def fake_openai(**kwargs):
        calls.append(kwargs)
        return {
            "document": {"filename": "input.pdf"},
            "extracted": {"principal_load_identifier": "X", "references": [], "stops": []},
            "warnings": [],
            "field_confidence": {},
            "context": {},
        }

    out = await parse_pdf_bytes_to_load_document_response(
        AsyncMock(),
        tenant_id=1,
        pdf_bytes=pdf_bytes,
        filename="input.pdf",
        openai_chat_json_schema=fake_openai,
    )

    assert calls
    call = calls[0]
    assert call["input_file_bytes"] == pdf_bytes
    assert call["schema"]["type"] == "object"
    assert call["schema_name"] == "load_document_parse_guarded_truckerjson_v1"
    assert "tenant_identity_exclusion" in call["user_text"]
    assert "field_rules" in call["user_text"]
    assert "attached original PDF" in call["user_text"]

    handoff_blob = call["user_text"].split("\n\n")[-1]
    handoff = json.loads(handoff_blob)
    assert handoff["document"]["pages"] == []
    assert out.raw_text
    assert len(out.raw_text) > 20


@pytest.mark.skipif(not _TQL_PDF.is_file(), reason="TQLRC.pdf fixture not on disk")
def test_tql_pdf_sha_and_no_jd_in_digital_user_message() -> None:
    import hashlib

    pdf_bytes = _TQL_PDF.read_bytes()
    assert hashlib.sha256(pdf_bytes).hexdigest() == _TQL_SHA256

    from app.services.load_parser_pdf_acquisition import acquire_load_parser_pdf_pages

    acquisition = acquire_load_parser_pdf_pages(pdf_bytes)
    page_objs = list(acquisition.get("pages") or [])
    handoff_pages = [
        {"page_number": int(p.get("page_number") or i + 1), "text": str(p.get("text") or "")}
        for i, p in enumerate(page_objs)
        if isinstance(p, dict) and not p.get("requires_ocr")
    ]
    assert any("JD FACTORS" in p["text"] for p in handoff_pages)

    handoff = build_load_rate_con_openai_handoff_v2_payload(
        tenant_identity_exclusion=_sample_exclusion(),
        pages=handoff_pages,
        filename="TQLRC.pdf",
        include_page_text_in_ai_handoff=False,
        page_count=len(handoff_pages),
    )
    user_msg = build_v2_openai_user_message(handoff, pdf_bytes_attached=True)
    assert "JD FACTORS" not in user_msg
    assert "Matheson" not in user_msg

    schema = ParseDocumentSemanticModelOutput.model_json_schema()
    assert schema["type"] == "object"


def test_digital_openai_multimodal_user_content_attaches_pdf_bytes() -> None:
    from app.document_platform.capabilities.openai.chat_json_schema import _build_user_content

    pdf_bytes = b"%PDF-1.4 minimal\n"
    handoff = build_load_rate_con_openai_handoff_v2_payload(
        tenant_identity_exclusion=_sample_exclusion(),
        pages=[{"page_number": 1, "text": "LOCAL ONLY"}],
        filename="rate.pdf",
        include_page_text_in_ai_handoff=False,
        page_count=1,
    )
    user_text = build_v2_openai_user_message(handoff, pdf_bytes_attached=True)
    content = _build_user_content(
        user_text=user_text,
        input_file_bytes=pdf_bytes,
        input_filename="rate.pdf",
    )
    assert isinstance(content, list)
    assert content[0]["type"] == "file"
    assert content[0]["file"]["filename"] == "rate.pdf"
    assert content[0]["file"]["file_data"].startswith("data:application/pdf;base64,")
    assert content[1]["type"] == "text"
    assert "LOCAL ONLY" not in content[1]["text"]
