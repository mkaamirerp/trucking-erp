"""Golden comparison: regex parse_document path vs static Lab-shaped JSON (Slice 17A-2).

No OpenAI, no DB, no load_lab services, no routers. PDF bytes + JSON + mapper only.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from app.schemas.load_document_parse import LoadDocumentParseResponse
from app.services.load_document_parse import parse_load_workspace_from_pdf_bytes
from app.services.load_document_parse_adapter import map_lab_parse_response_to_document_contract

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

_SOFT_SUMMARY_TOP_KEYS = frozenset(
    {
        "broker_name_snapshot",
        "broker_mc_number_snapshot",
        "broker_dot_number_snapshot",
        "broker_load_reference",
        "rate",
        "miles",
        "equipment_type",
        "trailer_type",
        "trailer_size",
        "commodity",
        "stop_count",
        "reference_count",
        "stops_appointment",
    }
)

_LAB_LEAK_KEYS = frozenset({"parse_diagnostics", "run_id", "ai_model_output", "semantic_extract_status"})


def build_soft_comparison_summary(
    regex: LoadDocumentParseResponse,
    lab: LoadDocumentParseResponse,
) -> dict[str, Any]:
    """Informational diff-friendly snapshot; tests must not assert regex == lab."""
    rx, lx = regex.extracted, lab.extracted

    def stops_dates_times(ex: Any) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for s in ex.stops:
            out.append(
                {
                    "appointment_date": s.appointment_date,
                    "appointment_time_text": s.appointment_time_text,
                }
            )
        return out

    return {
        "broker_name_snapshot": {"regex": rx.broker_name_snapshot, "lab": lx.broker_name_snapshot},
        "broker_mc_number_snapshot": {"regex": rx.broker_mc_number_snapshot, "lab": lx.broker_mc_number_snapshot},
        "broker_dot_number_snapshot": {"regex": rx.broker_dot_number_snapshot, "lab": lx.broker_dot_number_snapshot},
        "broker_load_reference": {"regex": rx.broker_load_reference, "lab": lx.broker_load_reference},
        "rate": {"regex": rx.rate, "lab": lx.rate},
        "miles": {"regex": rx.miles, "lab": lx.miles},
        "equipment_type": {"regex": rx.equipment_type, "lab": lx.equipment_type},
        "trailer_type": {"regex": rx.trailer_type, "lab": lx.trailer_type},
        "trailer_size": {"regex": rx.trailer_size, "lab": lx.trailer_size},
        "commodity": {"regex": rx.commodity, "lab": lx.commodity},
        "stop_count": {"regex": len(rx.stops), "lab": len(lx.stops)},
        "reference_count": {"regex": len(rx.references), "lab": len(lx.references)},
        "stops_appointment": {
            "regex": stops_dates_times(rx),
            "lab": stops_dates_times(lx),
        },
    }


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
def test_golden_pdf_regex_vs_lab_json_contract_and_soft_summary(
    _case_id: str,
    pdf_name: str,
    json_name: str,
) -> None:
    pdf_path = _FIXTURE_DIR / pdf_name
    golden_path = _FIXTURE_DIR / json_name
    pdf_bytes = pdf_path.read_bytes()

    regex_raw = parse_load_workspace_from_pdf_bytes(pdf_bytes, filename=pdf_name)
    regex_out = LoadDocumentParseResponse.model_validate(regex_raw)
    assert isinstance(regex_out, LoadDocumentParseResponse)
    assert isinstance(regex_out.warnings, list)
    assert isinstance(regex_out.field_confidence, dict)

    golden_payload = json.loads(golden_path.read_text(encoding="utf-8"))
    mapped = map_lab_parse_response_to_document_contract(golden_payload)
    assert isinstance(mapped, LoadDocumentParseResponse)
    _assert_hard_mapped_contract(mapped)

    summary = build_soft_comparison_summary(regex_out, mapped)
    assert set(summary.keys()) == _SOFT_SUMMARY_TOP_KEYS
    assert summary["stop_count"]["lab"] == len(mapped.extracted.stops)
    assert summary["reference_count"]["lab"] == len(mapped.extracted.references)
