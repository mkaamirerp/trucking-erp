"""Unit tests for person application workflow lane constants."""

from __future__ import annotations

from app.constants.person_application_workflow import (
    WORKFLOW_LANE_HR_PAYROLL,
    WORKFLOW_LANE_PROCESSING,
    WORKFLOW_LANE_SUBMITTED,
    normalize_workflow_lane,
)


def test_normalize_workflow_lane_known() -> None:
    assert normalize_workflow_lane("submitted") == WORKFLOW_LANE_SUBMITTED
    assert normalize_workflow_lane("HR_PAYROLL") == WORKFLOW_LANE_HR_PAYROLL
    assert normalize_workflow_lane("complete") == "complete"


def test_normalize_workflow_lane_unknown_defaults_to_processing() -> None:
    assert normalize_workflow_lane(None) == WORKFLOW_LANE_PROCESSING
    assert normalize_workflow_lane("") == WORKFLOW_LANE_PROCESSING
    assert normalize_workflow_lane("bogus") == WORKFLOW_LANE_PROCESSING
