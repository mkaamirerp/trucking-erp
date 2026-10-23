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
