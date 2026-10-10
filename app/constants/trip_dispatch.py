"""Locked trip-number rules — see docs/load_trip/MASTER.md."""

# API error code: generic Load PATCH must not create new transitions into dispatched (Slice 1+).
# Load.status = dispatched is legacy board/mint vocabulary. New trip execution must use explicit
# Trip assignment, TripLoad membership, and future package / execution endpoints.
LEGACY_LOAD_STATUS_DISPATCH_DEPRECATED = "LEGACY_LOAD_STATUS_DISPATCH_DEPRECATED"

# Issue 0A writer freeze: Load create/PATCH may only write commercial/readiness statuses.
# Legacy operational values remain readable on historical rows (LoadResponse) but are never written
# through Load APIs; operational lifecycle and equipment belong to Trip.
LOAD_WRITABLE_STATUSES = frozenset({"draft", "ready"})
LEGACY_LOAD_OPERATIONAL_STATUSES = frozenset(
    {
        "unassigned",
        "assigned",
        "dispatched",
        "arrived_pickup",
        "in_transit",
        "arrived_delivery",
        "delivered",
        "issue_hold",
    }
)
LOAD_ASSIGNMENT_FIELDS = ("driver_id", "truck_id", "trailer_id")

LEGACY_LOAD_ASSIGNMENT_DEPRECATED = "LEGACY_LOAD_ASSIGNMENT_DEPRECATED"
LOAD_CREATE_STATUS_MUST_BE_DRAFT = "LOAD_CREATE_STATUS_MUST_BE_DRAFT"
# Issue 3: draft→ready must use POST /loads/{load_id}/mark-ready (authoritative readiness + CAS).
LOAD_STATUS_READY_USE_MARK_READY_ENDPOINT = "LOAD_STATUS_READY_USE_MARK_READY_ENDPOINT"
# Explicit Load PATCH status outside LOAD_WRITABLE_STATUSES (e.g. null); loads.status is NOT NULL.
LOAD_STATUS_NOT_WRITABLE = "LOAD_STATUS_NOT_WRITABLE"
# Rows still holding a legacy operational status cannot change status via Load PATCH (Issue 0B migrates them).
LEGACY_LOAD_STATUS_TRANSITION_BLOCKED = "LEGACY_LOAD_STATUS_TRANSITION_BLOCKED"

# V1 legacy: mint path historically keyed off load entering this status (generic PATCH). Load PATCH no
# longer mints or cancels (Issue 0A); constant kept for legacy readers and dispatch_trips helpers.
TRIP_ALLOCATED_AT_LOAD_STATUS = "dispatched"

# Active trip is cancelled + load read-model cleared ONLY when leaving `dispatched` for a pre-dispatch
# pool status. Forward/lateral ops (in_transit, delivered, issue_hold, assigned, etc.) MUST NOT cancel.
# Keep in sync with docs/load_trip/MASTER.md §6–§7 / Appendix A.
PRE_DISPATCH_TRIP_CANCEL_STATUSES = frozenset({"draft", "ready", "unassigned"})

DISPATCH_TRIP_STATUS_ACTIVE = "active"
DISPATCH_TRIP_STATUS_CANCELLED = "cancelled"

# Trip container (trips.status) — operational lifecycle; not the same as dispatch_trips.status strings.
TRIP_CONTAINER_STATUS_PLANNED = "planned"
TRIP_CONTAINER_STATUS_ASSIGNED = "assigned"
TRIP_CONTAINER_STATUS_IN_PROGRESS = "in_progress"
TRIP_CONTAINER_STATUS_COMPLETED = "completed"
TRIP_CONTAINER_STATUS_CANCELLED = "cancelled"

JOB_TYPE_FREIGHT_LOAD = "freight_load"

# trip_loads.status_within_trip
TRIP_LOAD_STATUS_WITHIN_PLANNED = "planned"
TRIP_LOAD_STATUS_WITHIN_ACTIVE = "active"
TRIP_LOAD_STATUS_WITHIN_COMPLETED = "completed"
TRIP_LOAD_STATUS_WITHIN_REMOVED = "removed"

# OPEN membership: planned|active AND completed_at IS NULL AND removed_at IS NULL
TRIP_LOAD_OPEN_STATUSES = (
    TRIP_LOAD_STATUS_WITHIN_PLANNED,
    TRIP_LOAD_STATUS_WITHIN_ACTIVE,
)

TRIP_NUMBER_PREFIX_MIN_LEN = 2
TRIP_NUMBER_PREFIX_MAX_LEN = 16
TRIP_NUMERIC_WIDTH = 5
DEFAULT_NEXT_TRIP_NUMERIC = 10_001

TRIP_NUMBER_PREFIX_NOT_CONFIGURED = "TRIP_NUMBER_PREFIX_NOT_CONFIGURED"
DISPATCH_RESOURCES_REQUIRED = "DISPATCH_RESOURCES_REQUIRED"
