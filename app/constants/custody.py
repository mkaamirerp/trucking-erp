"""Load custody / continuity constants (Decision 12 foundation)."""

# Current custody owner (Load snapshot + event after-state)
CUSTODY_OWNER_TRIP = "trip"
CUSTODY_OWNER_TERMINAL = "terminal"
CUSTODY_OWNER_DELIVERED = "delivered"
CUSTODY_OWNER_UNKNOWN = "unknown"

CUSTODY_OWNERS = frozenset(
    {
        CUSTODY_OWNER_TRIP,
        CUSTODY_OWNER_TERMINAL,
        CUSTODY_OWNER_DELIVERED,
        CUSTODY_OWNER_UNKNOWN,
    }
)

# Physical placement at the owner
CUSTODY_PLACEMENT_ON_TRAILER = "on_trailer"
CUSTODY_PLACEMENT_STAGED = "staged"
CUSTODY_PLACEMENT_UNKNOWN = "unknown"

CUSTODY_PLACEMENTS = frozenset(
    {
        CUSTODY_PLACEMENT_ON_TRAILER,
        CUSTODY_PLACEMENT_STAGED,
        CUSTODY_PLACEMENT_UNKNOWN,
    }
)

# Slice 1 allowlist (bootstrap + reserved for later mutation slices)
CUSTODY_EVENT_BOOTSTRAP = "custody_bootstrap"
CUSTODY_EVENT_TRIP_ACCEPT = "trip_accept_custody"
CUSTODY_EVENT_YARD_HANDOFF = "yard_handoff"
CUSTODY_EVENT_TRIP_TAKEOVER = "trip_takeover"
CUSTODY_EVENT_FINAL_DELIVERY = "final_delivery"

CUSTODY_EVENT_TYPES_V1 = frozenset(
    {
        CUSTODY_EVENT_BOOTSTRAP,
        CUSTODY_EVENT_TRIP_ACCEPT,
        CUSTODY_EVENT_YARD_HANDOFF,
        CUSTODY_EVENT_TRIP_TAKEOVER,
        CUSTODY_EVENT_FINAL_DELIVERY,
    }
)

CUSTODY_SOURCE_BOOTSTRAP = "bootstrap"
CUSTODY_SOURCE_API = "api"
