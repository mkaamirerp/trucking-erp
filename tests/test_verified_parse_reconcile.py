"""The saved parser JSON follows the dispatcher form. The parser itself is not involved."""

from types import SimpleNamespace

from app.services.load_workspace_draft_document import (
    extracted_fields_in_draft,
    reconcile_accepted_parse_json,
    values_equivalent,
)


def test_equivalent_money_does_not_count_as_a_change() -> None:
    assert values_equivalent("2500.00", 2500)
    assert not values_equivalent("Chicago", "Boston")
    assert not values_equivalent("PO-100", "PO-200")


def test_create_load_corrections_patch_only_mapped_fields() -> None:
    accepted = {
        "raw_text": "keep this",
        "extracted": {
            "broker_load_reference": "PO-100",
            "rate": "1800.00",
            "temperature_requirement": "34",
            "unmapped_note": "leave me",
            "stops": [
                {"city": "Chicago", "state_or_province": "IL", "facility_code": "CHI-1"},
                {"city": "Dallas", "state_or_province": "TX"},
            ],
        },
    }
    form = SimpleNamespace(
        broker_load_reference="PO-100",
        rate="1800.00",
        temperature_requirement="28",
        stops=[
            SimpleNamespace(
                stop_type="pickup",
                facility_name=None,
                street=None,
                city="Boston",
                state_or_province="IL",
                postal_code=None,
                country=None,
                reference_number=None,
                appointment_type=None,
                appointment_date=None,
                appointment_time_text=None,
                notes=None,
            ),
            SimpleNamespace(
                stop_type="delivery",
                facility_name=None,
                street=None,
                city="Dallas",
                state_or_province="TX",
                postal_code=None,
                country=None,
                reference_number=None,
                appointment_type=None,
                appointment_date=None,
                appointment_time_text=None,
                notes=None,
            ),
        ],
        references=[],
    )
    only = extracted_fields_in_draft(
        {
            "brokerLoadReference": "PO-100",
            "rate": "1800",
            "temperatureRequirement": "28",
            "draftStops": [{"city": "Boston"}],
        }
    )
    out = reconcile_accepted_parse_json(accepted, form, only_fields=only)
    assert out["raw_text"] == "keep this"
    assert out["extracted"]["unmapped_note"] == "leave me"
    assert out["extracted"]["broker_load_reference"] == "PO-100"
    assert out["extracted"]["rate"] == "1800.00"
    assert out["extracted"]["temperature_requirement"] == "28"
    assert out["extracted"]["stops"][0]["city"] == "Boston"
    assert out["extracted"]["stops"][0]["facility_code"] == "CHI-1"
    assert out["extracted"]["stops"][0]["state_or_province"] == "IL"
    assert out["extracted"]["stops"][1]["city"] == "Dallas"
