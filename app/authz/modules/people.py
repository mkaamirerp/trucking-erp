"""People, driver, and driver-document capabilities.

Live people routes still call _require_admin for reads and writes.
That split is not enforced from this catalog.
"""

from __future__ import annotations

from app.authz.spec import CapabilitySpec, ModuleCatalog


def _spec(
    resource: str,
    action: str,
    prospective: str,
    current_contract: str,
    note: str = "",
    *,
    enforcement_approval: str = "not_required",
) -> CapabilitySpec:
    return CapabilitySpec(
        "people",
        resource,
        action,
        prospective,
        current_contract,
        False,
        note,
        enforcement_approval,
    )


CATALOG = ModuleCatalog(
    module="people",
    prefixes=("people.",),
    capabilities=(
        _spec(
            "people.directory",
            "view",
            "read",
            "admin",
            "Live list/detail still require tenant admin. Owner approval is required before enforcement.",
            enforcement_approval="owner_required",
        ),
        _spec("people.directory", "manage", "operational", "admin"),
        _spec(
            "people.drivers",
            "view",
            "read",
            "ungated",
            enforcement_approval="owner_required",
        ),
        _spec(
            "people.drivers",
            "manage",
            "operational",
            "admin",
            "Driver create/update, driver phones and legacy license confirm require tenant admin.",
        ),
        _spec(
            "people.driver_profile",
            "manage",
            "operational",
            "admin",
            "People workspace driver-profile patch still requires tenant admin.",
        ),
        _spec(
            "people.driver_documents",
            "view",
            "read",
            "member",
            enforcement_approval="owner_required",
        ),
        _spec(
            "people.driver_documents",
            "manage",
            "operational",
            "full_access_same_as_admin",
            "Live writes use has_full_access, which is the admin role set today.",
        ),
        _spec(
            "people.compensation",
            "view",
            "admin",
            "admin",
            enforcement_approval="owner_required",
        ),
        _spec("people.compensation", "manage", "admin", "admin"),
        _spec(
            "people.role_configuration",
            "view",
            "admin",
            "admin",
            enforcement_approval="owner_required",
        ),
        _spec("people.role_configuration", "manage", "admin", "admin"),
        _spec("people.audit", "view", "admin", "admin", enforcement_approval="owner_required"),
    ),
)
