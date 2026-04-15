"""
People-first operational projection — anti-drift between People and role operational rows.

Architecture (product direction):
- **People** = canonical maintained master record (People workspace).
- **Applications / onboarding** = workflow only; not a second master store for person truth.
- **Role-specific operational tables** (dispatch roster, fleet assignments, etc.) =
  **operational projections** linked via ``person_id``. They carry copies for  dispatch/UI performance and role-specific state, but must **not** become shadow
  master records for person core or role-profile fields when linked.

**``drivers``** is the first table where PATCH is guarded: duplicated People / driver-profile
fields are blocked when ``drivers.person_id`` is set. The same *pattern* applies to future
operational tables: enumerate canonical-on-People columns per table, block PATCH (or PUT)
on those keys when a person link exists, return409 + redirect to People.

This module holds shared constants and response shaping for that pattern — not driver-only
logic scattered in routers.
"""

from __future__ import annotations

from typing import Any, Iterable

# On ``drivers``, these PATCH fields duplicate People-owned or driver-profile-owned truth
# when the row is linked to a person. Keep in sync with ``DriverUpdate`` and canonical
# models (``people``, ``driver_profiles``).
DRIVERS_PATCH_FIELDS_CANONICAL_ON_PEOPLE: frozenset[str] = frozenset(
    {
        "first_name",
        "last_name",
        "email",
        "phone",
        "issuing_country",
        "issuing_region",
        "license_number",
        "license_class",
        "license_issue_date",
        "license_expiry_date",
    }
)


def drivers_patch_blocked_canonical_fields(requested_field_names: set[str]) -> frozenset[str]:
    """Subset of ``requested_field_names`` that are blocked on linked driver rows."""
    return frozenset(requested_field_names & DRIVERS_PATCH_FIELDS_CANONICAL_ON_PEOPLE)


def people_first_operational_patch_conflict_detail(
    *,
    person_id: int,
    blocked_fields: Iterable[str],
    operational_table: str,
    workspace_edit_hint: str,
    operational_fields_hint: str,
    stable_api_code: str,
) -> dict[str, Any]:
    """
    JSON body for HTTP 409 when an operational row linked to ``person_id`` would
    receive edits to canonical-on-People fields.

    ``stable_api_code`` remains per-route for client compatibility (e.g. drivers).
    ``pattern`` + ``operational_table`` document the general rule for new consumers.
    """
    bf = sorted(blocked_fields)
    return {
        "code": stable_api_code,
        "pattern": "people_first_operational_projection",
        "operational_table": operational_table,
        "message": (
            f"This {operational_table} row is linked to person_id={person_id}. "
            f"Canonical person and role-profile fields must be edited in the People workspace "
            f"({workspace_edit_hint}), not on this operational PATCH. "
            f"You can still update operational fields here: {operational_fields_hint}."
        ),
        "person_id": int(person_id),
        "blocked_fields": bf,
    }
