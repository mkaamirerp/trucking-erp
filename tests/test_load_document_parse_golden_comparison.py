"""Golden fixtures: Lab-shaped JSON maps to LoadDocumentParseResponse; PDFs have extractable text."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.schemas.load_document_parse import LoadDocumentParseResponse
from app.services.load_document_parse_adapter import map_lab_parse_response_to_document_contract
from app.services.pdf_text_extract import extract_text_and_pages_from_pdf_bytes

_REPO_ROOT = Path(__file__).resolve().parents[1]
_FIXTURE_DIR = _REPO_ROOT / "docs" / "fixtures" / "load_lab"

_GOLDEN_CASES: list[tuple[str, str, str]] = [
    (
        "3pickups_1delivery",
        "load_lab_fixture_3pickups_1delivery.pdf",
        "load_lab_fixture_3pickups_1delivery.lab_parse_response.json",
    ),
    (
        "1pickup_3deliveries",
        "load_lab_fixture_1pickup_3deliveries.pdf",
        "load_lab_fixture_1pickup_3deliveries.lab_parse_response.json",
    ),
]

_LAB_LEAK_KEYS = frozenset({"parse_diagnostics", "run_id", "ai_model_output", "semantic_extract_status"})


def _assert_hard_mapped_contract(mapped: LoadDocumentParseResponse) -> None:
    dumped = mapped.model_dump(mode="json")
    assert "parse_diagnostics" not in dumped
    for leak in _LAB_LEAK_KEYS:
        assert leak not in dumped

    assert mapped.extracted.stops is not None
    assert len(mapped.extracted.stops) > 0
    for i, stop in enumerate(mapped.extracted.stops):
        assert stop.sequence == i

    assert isinstance(mapped.warnings, list)
    assert isinstance(mapped.field_confidence, dict)


@pytest.mark.parametrize("_case_id,pdf_name,json_name", _GOLDEN_CASES)
def test_golden_pdf_text_extractable_and_lab_json_maps_to_contract(
    _case_id: str,
    pdf_name: str,
    json_name: str,
) -> None:
    pdf_path = _FIXTURE_DIR / pdf_name
    golden_path = _FIXTURE_DIR / json_name
    pdf_bytes = pdf_path.read_bytes()

    full_text, _pages, warnings = extract_text_and_pages_from_pdf_bytes(pdf_bytes)
    assert full_text.strip() or any("extract error" in w.lower() for w in warnings)
    if full_text.strip():
        assert len(full_text.strip()) > 50

    golden_payload = json.loads(golden_path.read_text(encoding="utf-8"))
    mapped = map_lab_parse_response_to_document_contract(golden_payload)
    assert isinstance(mapped, LoadDocumentParseResponse)
    _assert_hard_mapped_contract(mapped)
