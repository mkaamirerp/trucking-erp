"""Global booking broker merge guardrails (platform). Slice 3+: helpers only — no execute here."""

from __future__ import annotations

from app.models.global_booking_broker import GlobalBookingBroker

# Stable messages for future HTTP mapping (execute/preview).
MERGE_SOURCE_BLOCKED_ALREADY_LOSER = "global_booking_broker_merge_source_blocked_already_loser"
MERGE_SURVIVOR_BLOCKED_ALREADY_LOSER = "global_booking_broker_merge_survivor_blocked_already_loser"


def global_booking_broker_is_merge_loser(broker: GlobalBookingBroker) -> bool:
    """True if this row was retired as a merge **source** (loser) into another global broker."""
    return broker.merged_into_global_broker_id is not None


def global_booking_broker_merge_source_violation(broker: GlobalBookingBroker) -> str | None:
    """If non-None, *broker* must not be used as a merge **source** id."""
    if global_booking_broker_is_merge_loser(broker):
        return MERGE_SOURCE_BLOCKED_ALREADY_LOSER
    return None


def assert_global_booking_broker_eligible_merge_source(broker: GlobalBookingBroker) -> None:
    """Raise ``ValueError`` with a stable message when *broker* cannot be a merge source."""
    violation = global_booking_broker_merge_source_violation(broker)
    if violation is not None:
        raise ValueError(violation)


def global_booking_broker_merge_survivor_violation(broker: GlobalBookingBroker) -> str | None:
    """If non-None, *broker* must not be used as a merge **survivor** id (must remain an active row)."""
    if global_booking_broker_is_merge_loser(broker):
        return MERGE_SURVIVOR_BLOCKED_ALREADY_LOSER
    return None


def assert_global_booking_broker_eligible_merge_survivor(broker: GlobalBookingBroker) -> None:
    """Raise ``ValueError`` when *broker* cannot absorb a merge (already retired as loser)."""
    violation = global_booking_broker_merge_survivor_violation(broker)
    if violation is not None:
        raise ValueError(violation)
