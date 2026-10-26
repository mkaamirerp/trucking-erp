"""Unit tests for draft-json movement assignment extraction (no database)."""

from app.services.load_workspace_draft_promotion import proposed_assignment_from_draft_json


def test_proposed_assignment_reads_camel_and_snake_case() -> None:
    driver, truck, trailer = proposed_assignment_from_draft_json(
        {
            "driver_id": 10,
            "truckId": 20,
            "trailerAssetId": 30,
        }
    )
    assert driver == 10
    assert truck == 20
    assert trailer == 30


def test_proposed_assignment_ignores_zero_and_invalid() -> None:
    assert proposed_assignment_from_draft_json({"driverId": 0, "truckId": "x"}) == (None, None, None)
