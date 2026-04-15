"""Routing / queue ownership for person applications (distinct from historical status fields)."""

from __future__ import annotations

from typing import Final

# person_applications.current_workflow_lane — queue language for admin onboarding page
WORKFLOW_LANE_SUBMITTED: Final[str] = "submitted"
WORKFLOW_LANE_PROCESSING: Final[str] = "processing"
WORKFLOW_LANE_HR_PAYROLL: Final[str] = "hr_payroll"
WORKFLOW_LANE_COMPLETE: Final[str] = "complete"
WORKFLOW_LANE_REJECTED: Final[str] = "rejected"

WORKFLOW_LANES: Final[frozenset[str]] = frozenset(
    {
        WORKFLOW_LANE_SUBMITTED,
        WORKFLOW_LANE_PROCESSING,
        WORKFLOW_LANE_HR_PAYROLL,
        WORKFLOW_LANE_COMPLETE,
        WORKFLOW_LANE_REJECTED,
    }
)


def normalize_workflow_lane(value: str | None) -> str:
    """Coerce stored value; unknown -> processing (safe in-flight default)."""
    if not value or not isinstance(value, str):
        return WORKFLOW_LANE_PROCESSING
    v = value.strip().lower()
    return v if v in WORKFLOW_LANES else WORKFLOW_LANE_PROCESSING
