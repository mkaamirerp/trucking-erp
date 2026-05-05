"""Unit tests for Lab-shaped parse_response → LoadDocumentParseResponse mapper (Slice 17A-1).

Synthetic payloads only — no DB, no OpenAI, no routers.
"""

from __future__ import annotations

import copy

from app.schemas.load_document_parse import LoadDocumentParseResponse
from app.services.load_document_parse_adapter import map_lab_parse_response_to_document_contract


def _minimal_valid_payload() -> dict:
    return {
        "document": {"filename": "synthetic.pdf"},
        "extracted": {
            "broker_name_snapshot": "Example Logistics",
            "broker_load_reference": "REF-001",
            "references": [],
            "stops": [],
        },
        "raw_text": "Synthetic PDF text for contract tests.",
        "warnings": ["[lab] synthetic"],
        "field_confidence": {"broker_name_snapshot": "high"},
        "context": {"load_lab_semantic": True, "semantic_schema_version": "unit_test"},
    }


def test_valid_lab_shaped_payload_validates_as_load_document_parse_response() -> None:
    payload = _minimal_valid_payload()
    out = map_lab_parse_response_to_document_contract(payload)
    assert isinstance(out, LoadDocumentParseResponse)
    assert out.document.filename == "synthetic.pdf"
    assert out.extracted.broker_load_reference == "REF-001"
    assert out.raw_text.startswith("Synthetic")


def test_root_parse_diagnostics_stripped_from_public_response() -> None:
    payload = _minimal_valid_payload()
    payload["parse_diagnostics"] = {
        "party_mentions": [{"name": "Secret"}],
        "broker_confidence_matrix": [],
    }
    out = map_lab_parse_response_to_document_contract(payload)
    dumped = out.model_dump(mode="json")
    assert "parse_diagnostics" not in dumped


def test_unknown_lab_only_root_keys_ignored() -> None:
    payload = _minimal_valid_payload()
    payload["semantic_extract_status"] = "success"
    payload["run_id"] = 999
    payload["ai_model_output"] = {"foo": "bar"}
    out = map_lab_parse_response_to_document_contract(payload)
    dumped = out.model_dump(mode="json")
    assert "run_id" not in dumped
    assert "semantic_extract_status" not in dumped
    assert "ai_model_output" not in dumped


def test_strip_unknown_root_false_still_drops_parse_diagnostics_when_flag_true() -> None:
    """Explicit pop path: full dict copy minus parse_diagnostics."""
    payload = _minimal_valid_payload()
    payload["parse_diagnostics"] = {"internal": True}
    payload["extra_root"] = "x"
    out = map_lab_parse_response_to_document_contract(
        payload,
        strip_unknown_root_keys=False,
        strip_parse_diagnostics=True,
    )
    dumped = out.model_dump(mode="json")
    assert "parse_diagnostics" not in dumped
    # extra_root may be ignored by Pydantic extra handling on nested validation
    assert "document" in dumped


def test_extracted_references_richer_objects_remain_valid() -> None:
    payload = _minimal_valid_payload()
    payload["extracted"]["references"] = [
        {
            "kind": "PO",
            "value": "P123",
            "label": "Customer PO",
            "primary_candidate": True,
            "confidence": "high",
        }
    ]
    out = map_lab_parse_response_to_document_contract(payload)
    assert len(out.extracted.references) == 1
    ref = out.extracted.references[0]
    assert ref.kind == "PO"
    assert ref.value == "P123"
    assert ref.label == "Customer PO"
    assert ref.primary_candidate is True
    assert ref.confidence == "high"


def test_extracted_stops_remain_valid_and_reindexed_for_workspace() -> None:
    """Lab-style 1-based sequences → 0..n-1 after stable sort (see module docstring)."""
    payload = _minimal_valid_payload()
    payload["extracted"]["stops"] = [
        {
            "stop_type": "delivery",
            "sequence": 2,
            "city": "Austin",
            "state_or_province": "TX",
            "appointment_date": "03/15/2026",
        },
        {
            "stop_type": "pickup",
            "sequence": 1,
            "city": "Dallas",
            "state_or_province": "TX",
            "appointment_date": "2026-03-14",
        },
    ]
    out = map_lab_parse_response_to_document_contract(payload)
    assert len(out.extracted.stops) == 2
    # pickup sorts first (sequence 1): becomes 0; delivery becomes 1
    assert out.extracted.stops[0].stop_type == "pickup"
    assert out.extracted.stops[0].sequence == 0
    assert out.extracted.stops[0].appointment_date == "2026-03-14"
    assert out.extracted.stops[1].stop_type == "delivery"
    assert out.extracted.stops[1].sequence == 1
    assert out.extracted.stops[1].appointment_date == "03/15/2026"


def test_reindex_stop_sequences_false_preserves_lab_sequences() -> None:
    payload = _minimal_valid_payload()
    payload["extracted"]["stops"] = [
        {"stop_type": "pickup", "sequence": 1, "city": "Dallas"},
        {"stop_type": "delivery", "sequence": 2, "city": "Austin"},
    ]
    out = map_lab_parse_response_to_document_contract(
        payload,
        reindex_stop_sequences=False,
    )
    assert out.extracted.stops[0].sequence == 1
    assert out.extracted.stops[1].sequence == 2


def test_warnings_and_field_confidence_preserved() -> None:
    payload = _minimal_valid_payload()
    payload["warnings"] = ["a", "b"]
    payload["field_confidence"] = {"rate": "low", "stops": "medium"}
    out = map_lab_parse_response_to_document_contract(payload)
    assert out.warnings == ["a", "b"]
    assert out.field_confidence == {"rate": "low", "stops": "medium"}


def test_context_preserved_and_decoupled_from_mutation_after_map() -> None:
    payload = _minimal_valid_payload()
    payload["context"]["email_thread_id"] = 42
    snapshot = copy.deepcopy(payload["context"])
    out = map_lab_parse_response_to_document_contract(payload)
    assert out.context.get("email_thread_id") == 42
    assert out.context.get("load_lab_semantic") is True
    payload["context"]["email_thread_id"] = 99
    assert out.context.get("email_thread_id") == snapshot["email_thread_id"]


def test_mapper_does_not_mutate_input_payload() -> None:
    payload = _minimal_valid_payload()
    payload["extracted"]["stops"] = [
        {"stop_type": "pickup", "sequence": 5, "city": "X"},
        {"stop_type": "delivery", "sequence": 6, "city": "Y"},
    ]
    frozen = copy.deepcopy(payload)
    map_lab_parse_response_to_document_contract(payload)
    assert payload == frozen


def test_defaults_warnings_and_field_confidence_when_omitted() -> None:
    payload = {
        "document": {"filename": "x.pdf"},
        "extracted": {"references": [], "stops": []},
        "raw_text": "t",
    }
    out = map_lab_parse_response_to_document_contract(payload)
    assert out.warnings == []
    assert out.field_confidence == {}
    assert out.context == {}
