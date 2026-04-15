"""People-level onboarding / setup UI constants (workflow-agnostic; not driver-only)."""

from __future__ import annotations

from typing import Final

# Tenant-level UI mode (platform_tenants.person_setup_ui_mode)
PERSON_SETUP_UI_COMBINED: Final[str] = "combined"
PERSON_SETUP_UI_SEGMENTED: Final[str] = "segmented"
PERSON_SETUP_UI_MODES: Final[frozenset[str]] = frozenset({PERSON_SETUP_UI_COMBINED, PERSON_SETUP_UI_SEGMENTED})

# Person application setup lifecycle (person_applications.setup_status)
SETUP_STATUS_PENDING: Final[str] = "pending"
SETUP_STATUS_PENDING_DOWNSTREAM: Final[str] = "pending_downstream"
SETUP_STATUS_COMPLETE: Final[str] = "complete"
SETUP_STATUSES: Final[frozenset[str]] = frozenset(
    {SETUP_STATUS_PENDING, SETUP_STATUS_PENDING_DOWNSTREAM, SETUP_STATUS_COMPLETE}
)


def normalize_person_setup_ui_mode(value: str | None) -> str:
    """Defensive read fallback: coerce stored/legacy values for display. Invalid/absent -> combined.

    Do **not** use this for admin writes; use ``validate_person_setup_ui_mode_for_write`` instead.
    """
    v = (value or "").strip().lower()
    return v if v in PERSON_SETUP_UI_MODES else PERSON_SETUP_UI_COMBINED


def validate_person_setup_ui_mode_for_write(value: str | None) -> str:
    """Require ``combined`` or ``segmented``; raise ``ValueError`` if invalid (no silent coerce)."""
    v = (value or "").strip().lower()
    if v not in PERSON_SETUP_UI_MODES:
        raise ValueError(
            "invalid_person_setup_ui_mode: must be one of "
            + ", ".join(sorted(PERSON_SETUP_UI_MODES))
        )
    return v
