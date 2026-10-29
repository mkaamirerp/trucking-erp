"""Re-parse JSON 1 must include empty saved fields; customer rate is stored but not compared."""

from app.services.load_workspace_draft_document import (
    comparison_baseline,
    reconcile_accepted_parse_json,
    validate_ai_reparse_changes,
)
from types import SimpleNamespace


def test_comparison_baseline_includes_empty_scalars_and_stop_fields() -> None:
    saved = {
        "extracted": {
            "broker_load_reference": None,
            "broker_contact_email_snapshot": None,
            "rate": "1800.00",
            "customer_rate": "1900.00",
            "stops": [
                {
                    "stop_type": "pickup",
                    "reference_number": None,
                    "city": "Chicago",
                    "state_or_province": "IL",
                }
            ],
        }
    }
    baseline = {item["path"]: item["value"] for item in comparison_baseline(saved)["fields"]}
    assert baseline["broker_load_reference"] is None
    assert baseline["broker_contact_email_snapshot"] is None
    assert baseline["rate"] == "1800.00"
    assert "customer_rate" not in baseline
    assert baseline["stops[0].reference_number"] is None
    assert baseline["stops[0].city"] == "Chicago"
    assert baseline["stops[0].postal_code"] is None


def test_cleared_broker_ref_email_and_rate_all_suggest_change() -> None:
    saved = {
        "extracted": {
            "broker_load_reference": None,
            "broker_contact_email_snapshot": None,
            "rate": "1800.00",
            "broker_name_snapshot": "Armstrong",
            "stops": [
                {
                    "stop_type": "pickup",
                    "street": "1 Main",
                    "city": "Chicago",
                    "state_or_province": "IL",
                    "reference_number": None,
                },
                {
                    "stop_type": "delivery",
                    "street": "2 Main",
                    "city": "Dallas",
                    "state_or_province": "TX",
                },
            ],
        }
    }
    revised = {
        "extracted": {
            "broker_load_reference": "3872125-1",
            "broker_contact_email_snapshot": "dispatch@broker.com",
            "rate": "2000.00",
            "broker_name_snapshot": "Armstrong",
            "customer_rate": "2000.00",
            "stops": [
                {
                    "stop_type": "pickup",
                    "street": "1 Main",
                    "city": "Chicago",
                    "state_or_province": "IL",
                    "reference_number": "PU-123",
                },
                {
                    "stop_type": "delivery",
                    "street": "2 Main",
                    "city": "Dallas",
                    "state_or_province": "TX",
                },
            ],
        }
    }
    rows = {row["field"]: row for row in validate_ai_reparse_changes(saved, revised, [])}
    assert rows["broker_load_reference"]["editable"] is True
    assert rows["broker_contact_email_snapshot"]["editable"] is True
    assert rows["rate"]["editable"] is True
    assert rows["stops[0].reference_number"]["editable"] is True
    assert "customer_rate" not in rows


def test_reconcile_full_save_writes_nulls_and_load_metadata() -> None:
    accepted = {"extracted": {"broker_load_reference": "3872125-1", "rate": "1800"}}
    form = SimpleNamespace(
        load_number="Oct-26-0335",
        status="ready",
        driver_id=None,
        truck_id=None,
        trailer_id=None,
        customs_broker_id=None,
        broker_id=None,
        broker_contact_id=None,
        broker_load_reference=None,
        broker_contact_email_snapshot=None,
        rate="1000.00",
        customer_rate="1900.00",
        stops=[],
        references=[],
        broker_name_snapshot="Armstrong",
        broker_contact_name_snapshot=None,
        broker_contact_phone_snapshot=None,
        broker_contact_extension_snapshot=None,
        mode=None,
        equipment_type=None,
        trailer_type=None,
        trailer_size=None,
        commodity=None,
        estimated_weight=None,
        hazmat_flag=False,
        temperature_requirement=None,
        pallet_case_count=None,
        miles=None,
    )
    out = reconcile_accepted_parse_json(accepted, form, only_fields=None)
    assert out["extracted"]["broker_load_reference"] is None
    assert out["extracted"]["broker_contact_email_snapshot"] is None
    assert out["extracted"]["rate"] == "1000.00"
    assert out["extracted"]["customer_rate"] == "1900.00"
    assert out["extracted"]["load_number"] == "Oct-26-0335"
    assert out["extracted"]["status"] == "ready"
    assert out["extracted"]["driver_id"] is None
