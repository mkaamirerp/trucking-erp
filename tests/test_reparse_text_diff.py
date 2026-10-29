"""Re-parse text-diff path: one AI call, validated rows only."""

from __future__ import annotations

import json

import pytest

from app.services.load_document_parse_orchestrator import _REPARSE_TEXT_DIFF_INSTRUCTIONS
from app.services.load_workspace_draft_document import (
    build_reparse_proposal_document,
    extract_reparse_pdf_plain_text,
    reparse_text_document_block_reason,
    validate_ai_reparse_changes,
)


def test_validate_keeps_only_matching_ai_rows() -> None:
    saved = {"extracted": {"rate": "1800", "miles": 721}}
    pdf_text = "Linehaul 2000.00 miles 721 broker Armstrong"
    proposed = [
        {"field": "rate", "current_value": "1800", "revised_value": "2000"},
        {"field": "rate", "current_value": "999", "revised_value": "2000"},
        {"field": "customer_rate", "current_value": "1800", "revised_value": "2000"},
    ]
    rows = validate_ai_reparse_changes(saved, pdf_text, proposed)
    assert len(rows) == 1
    assert rows[0]["field"] == "rate"
    assert rows[0]["revised_value"] == "2000"


def test_validate_empty_ai_means_no_rows() -> None:
    saved = {"extracted": {"rate": "1800"}}
    revised = {"extracted": {"rate": "2000"}}
    pdf_text = "rate 2000"
    assert validate_ai_reparse_changes(saved, pdf_text, []) == []


def test_validate_drops_when_revised_not_in_pdf_text() -> None:
    saved = {"extracted": {"rate": "1800"}}
    rows = validate_ai_reparse_changes(
        saved,
        "nothing about money here",
        [{"field": "rate", "current_value": "1800", "revised_value": "2000"}],
    )
    assert rows == []


def test_reparse_text_block_reason_fuel() -> None:
    reason = reparse_text_document_block_reason(
        "BVD fuel invoice " + ("gallons delivered " * 20)
    )
    assert reason is not None
    assert "fuel invoice" in reason.casefold()


def test_build_reparse_proposal_document_applies_changes() -> None:
    saved = {"extracted": {"rate": "1800"}, "context": {}}
    doc = build_reparse_proposal_document(
        saved,
        filename="rc.pdf",
        pdf_text="rate 2000",
        changes=[{"field": "rate", "current_value": "1800", "revised_value": "2000"}],
    )
    assert doc["extracted"]["rate"] == "2000"
    assert doc["context"]["reparse_path"] == "text_diff_v1"


def test_extract_reparse_pdf_plain_text_digital_fixture() -> None:
    from pathlib import Path

    pdf = Path("docs/_review/fixtures/pdf/Armstrong.pdf").read_bytes()
    text = extract_reparse_pdf_plain_text(pdf)
    assert len(text) > 200
    assert reparse_text_document_block_reason(text) is None


@pytest.mark.asyncio
async def test_propose_load_reparse_single_ai_call(monkeypatch: pytest.MonkeyPatch) -> None:
    from types import SimpleNamespace

    from app.services.load_document_parse_orchestrator import propose_load_reparse

    pdf = open("docs/_review/fixtures/pdf/Armstrong.pdf", "rb").read()
    evidence = SimpleNamespace(
        accepted_parse_json={
            "extracted": {
                "broker_name_snapshot": "Armstrong Transport Group",
                "broker_load_reference": "3872125-1",
                "rate": "2000.00",
                "miles": 721,
                "stops": [
                    {
                        "stop_type": "PICKUP",
                        "city": "Chicago",
                        "state_or_province": "IL",
                        "street": "3620 W 38th St",
                    },
                    {"stop_type": "DELIVERY", "city": "Reidsville", "state_or_province": "NC"},
                ],
            },
            "context": {"document_type": "rate_confirmation"},
        },
        file_sha256="00",
        concurrency_version=1,
    )

    class _Db:
        async def scalar(self, *_args, **_kwargs):
            return evidence

    calls: list[dict] = []

    async def fake_ai(**kwargs):
        calls.append(kwargs)
        return {"changes": []}

    async def fake_dup(*_a, **_k):
        return []

    monkeypatch.setattr(
        "app.services.load_parser_duplicate_precheck.find_exact_pdf_duplicate_candidates",
        fake_dup,
    )

    proposal = await propose_load_reparse(
        _Db(),
        tenant_id=1,
        load_id=1008,
        pdf_bytes=pdf,
        filename="Armstrong.pdf",
        openai_chat_json_schema=fake_ai,
    )
    assert len(calls) == 1
    assert calls[0].get("input_file_bytes") is None
    payload = json.loads(calls[0]["user_text"])
    assert payload["new_pdf_text"]
    assert payload["saved_json"]["broker_load_reference"] == "3872125-1"
    assert "field_rules" in payload
    assert "tenant_identity_exclusion" in payload
    assert _REPARSE_TEXT_DIFF_INSTRUCTIONS in calls[0]["system"]
    assert proposal["changes"] == []
    assert proposal["summary"] == "No changes found."
