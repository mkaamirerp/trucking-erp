"""Unit tests for broker_load_reference promotion safety net (no tenant DB)."""

from types import SimpleNamespace

from app.schemas.load import LoadCreate
from app.services.load_workspace_draft_promotion import merge_broker_load_reference_from_accepted_parse

ACCEPTED_PARSE_BROKER_REF_ONLY = {
    "document": {"filename": "ratecon.pdf"},
    "raw_text": "",
    "warnings": [],
    "field_confidence": {},
    "extracted": {
        "broker_load_reference": "3872125-1",
        "references": [],
        "stops": [],
    },
}


def test_merge_broker_load_reference_from_accepted_parse_fills_blank_only() -> None:
    draft = SimpleNamespace(accepted_parse_json=ACCEPTED_PARSE_BROKER_REF_ONLY)
    blank_ref = LoadCreate(
        load_number="REF-UNIT",
        status="draft",
        broker_load_reference=None,
    )
    merged = merge_broker_load_reference_from_accepted_parse(blank_ref, draft)
    assert merged.broker_load_reference == "3872125-1"

    existing = blank_ref.model_copy(update={"broker_load_reference": "KEEP"})
    assert merge_broker_load_reference_from_accepted_parse(existing, draft).broker_load_reference == "KEEP"

# Promotion intentionally receives only the operator-reviewed draft_json stop
# snapshot. Parsing a document alone is not approval to insert its raw stops.
from app.services.load_workspace_draft_mapper import draft_json_to_load_create


def test_reviewed_parser_stops_are_mapped_into_load_create() -> None:
    payload = draft_json_to_load_create({
        "brokerNameSnapshot": "Armstrong Carrier",
        "brokerLoadReference": "3872125-1",
        "rate": "1800.00",
        "draftStops": [
            {"stop_type": "PICKUP", "sequence": 0, "city": "Chicago", "state_or_province": "IL"},
            {"stop_type": "DELIVERY", "sequence": 1, "city": "Reidsville", "state_or_province": "NC"},
        ],
    })
    assert payload.stops is not None
    assert [(s.stop_type, s.city, s.state_or_province) for s in payload.stops] == [
        ("PICKUP", "Chicago", "IL"),
        ("DELIVERY", "Reidsville", "NC"),
    ]


def test_operator_corrected_stop_wins_over_original_parse() -> None:
    payload = draft_json_to_load_create({
        "draftStops": [
            {"stop_type": "PICKUP", "sequence": 0, "city": "Chicago", "state_or_province": "IL"},
            {"stop_type": "DELIVERY", "sequence": 1, "city": "Greensboro", "state_or_province": "NC"},
        ],
    })
    assert payload.stops is not None
    assert payload.stops[1].city == "Greensboro"


def test_unreviewed_parser_stops_are_not_invented_by_mapper() -> None:
    payload = draft_json_to_load_create({"draftStops": []})
    assert payload.stops is None
