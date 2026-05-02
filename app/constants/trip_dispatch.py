"""Locked trip-number rules — see docs/DISPATCH_TRIP_NUMBER_RULE.md."""

# V1: trip minted only when load first enters this status (not on "assigned" alone).
TRIP_ALLOCATED_AT_LOAD_STATUS = "dispatched"

# Active trip is cancelled + load read-model cleared ONLY when leaving `dispatched` for a pre-dispatch
# pool status. Forward/lateral ops (in_transit, delivered, issue_hold, assigned, etc.) MUST NOT cancel.
# Keep in sync with docs/DISPATCH_TRIP_NUMBER_IMPLEMENTATION_PLAN.md §4.3.
PRE_DISPATCH_TRIP_CANCEL_STATUSES = frozenset({"draft", "ready", "unassigned"})

DISPATCH_TRIP_STATUS_ACTIVE = "active"
DISPATCH_TRIP_STATUS_CANCELLED = "cancelled"

# Trip container (trips.status) — operational lifecycle; not the same as dispatch_trips.status strings.
TRIP_CONTAINER_STATUS_PLANNED = "planned"
TRIP_CONTAINER_STATUS_CANCELLED = "cancelled"

JOB_TYPE_FREIGHT_LOAD = "freight_load"

# trip_loads.status_within_trip
TRIP_LOAD_STATUS_WITHIN_PLANNED = "planned"

TRIP_NUMBER_PREFIX_MIN_LEN = 2
TRIP_NUMBER_PREFIX_MAX_LEN = 16
TRIP_NUMERIC_WIDTH = 5
DEFAULT_NEXT_TRIP_NUMERIC = 10_001

TRIP_NUMBER_PREFIX_NOT_CONFIGURED = "TRIP_NUMBER_PREFIX_NOT_CONFIGURED"
DISPATCH_RESOURCES_REQUIRED = "DISPATCH_RESOURCES_REQUIRED"
