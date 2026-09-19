"""Segment 1 canonical Fuel/Card constants and provenance rules.

Table names follow the design conceptual split: one source batch, many
canonical transactions. Physical names use the `fuel_` tenant-table prefix
already used by `fuel_provider_connections`.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Final
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.services.fuel_money import FuelFloatForbidden, to_decimal

SOURCE_TYPE_PDF = "PDF"
SOURCE_TYPE_STRUCTURED_FILE = "STRUCTURED_FILE"
SOURCE_TYPE_SFTP_FILE = "SFTP_FILE"
SOURCE_TYPE_MANUAL_DRIVER = "MANUAL_DRIVER"
SOURCE_TYPE_API = "API"

SOURCE_TYPES: Final[frozenset[str]] = frozenset(
    {
        SOURCE_TYPE_PDF,
        SOURCE_TYPE_STRUCTURED_FILE,
        SOURCE_TYPE_SFTP_FILE,
        SOURCE_TYPE_MANUAL_DRIVER,
        SOURCE_TYPE_API,
    }
)

PROVIDER_EVENT_PURCHASE = "PURCHASE"
PROVIDER_EVENT_CREDIT = "CREDIT"
PROVIDER_EVENT_REFUND = "REFUND"
PROVIDER_EVENT_REVERSAL = "REVERSAL"
PROVIDER_EVENT_VOID = "VOID"
PROVIDER_EVENT_OTHER = "OTHER"
PROVIDER_EVENT_UNKNOWN = "UNKNOWN"

PROVIDER_EVENT_TYPES: Final[frozenset[str]] = frozenset(
    {
        PROVIDER_EVENT_PURCHASE,
        PROVIDER_EVENT_CREDIT,
        PROVIDER_EVENT_REFUND,
        PROVIDER_EVENT_REVERSAL,
        PROVIDER_EVENT_VOID,
        PROVIDER_EVENT_OTHER,
        PROVIDER_EVENT_UNKNOWN,
    }
)

# Evidenced BVD CUR=CN → CAD. Do not invent other currency aliases.
EVIDENCED_CURRENCY_CANONICAL: Final[dict[str, str]] = {
    "CN": "CAD",
    "CAD": "CAD",
    "USD": "USD",
}

SOURCE_HYDRATION_FORBIDDEN_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "owner_operator_charge_amount",
        "oo_pricing_mode",
        "oo_pricing_rule_id",
        "oo_pricing_rule_version",
        "oo_charge_unit_price",
        "oo_benefit_per_unit",
        "oo_pricing_status",
        "oo_pricing_reason",
        "oo_pricing_inputs_json",
        "truck_id",
        "driver_id",
        "owner_operator_payee_id",
        "classification",
        "financial_responsibility",
        "pricing_agreement_ref",
        "settlement_ref",
        "downstream_module",
        "downstream_ack_status",
        "downstream_ack_ref",
        "gate_status",
    }
)

TZ_SOURCE_PROVIDER_SUPPLIED = "PROVIDER_SUPPLIED"
TZ_SOURCE_PROVIDER_LOCAL_NO_ZONE = "PROVIDER_LOCAL_NO_ZONE"
TZ_SOURCE_DATE_ONLY = "DATE_ONLY"
TZ_SOURCE_UNKNOWN = "UNKNOWN"

TIMEZONE_SOURCES: Final[frozenset[str]] = frozenset(
    {
        TZ_SOURCE_PROVIDER_SUPPLIED,
        TZ_SOURCE_PROVIDER_LOCAL_NO_ZONE,
        TZ_SOURCE_DATE_ONLY,
        TZ_SOURCE_UNKNOWN,
    }
)

UNIT_PRICE_BASIS_VALUES: Final[frozenset[str]] = frozenset(
    {
        "BILLED",
        "EX_TAX",
        "FINAL_GALLON_PRICE",
        "RETAIL_FALLBACK",
        "UNKNOWN",
    }
)

BATCH_STATUS_UPLOADED = "UPLOADED"
BATCH_STATUS_PARSED = "PARSED"
BATCH_STATUS_REVIEW_REQUIRED = "REVIEW_REQUIRED"
BATCH_STATUS_IN_REVIEW = "IN_REVIEW"
BATCH_STATUS_REVIEWED = "REVIEWED"
BATCH_STATUS_READY_FOR_RECONCILIATION = "READY_FOR_RECONCILIATION"
BATCH_STATUS_PROCESSING = "PROCESSING"
BATCH_STATUS_RECONCILIATION_FAILED = "RECONCILIATION_FAILED"
BATCH_STATUS_RECONCILED = "RECONCILED"
BATCH_STATUS_READY_TO_FINALIZE = "READY_TO_FINALIZE"
BATCH_STATUS_FINALIZED = "FINALIZED"
BATCH_STATUS_BLOCKED = "BLOCKED"

BATCH_REVIEW_QUEUE_STATUSES: Final[frozenset[str]] = frozenset(
    {
        BATCH_STATUS_PARSED,
        BATCH_STATUS_REVIEW_REQUIRED,
        BATCH_STATUS_IN_REVIEW,
        BATCH_STATUS_REVIEWED,
        BATCH_STATUS_READY_FOR_RECONCILIATION,
        BATCH_STATUS_BLOCKED,
    }
)

ROW_REVIEW_PENDING = "PENDING"
ROW_REVIEW_CONFIRMED = "CONFIRMED"

ENTITY_TRANSACTION = "TRANSACTION"
ENTITY_CONTROL = "CONTROL"

NEGATIVE_OR_REVERSING_EVENTS: Final[frozenset[str]] = frozenset(
    {
        PROVIDER_EVENT_CREDIT,
        PROVIDER_EVENT_REFUND,
        PROVIDER_EVENT_REVERSAL,
        PROVIDER_EVENT_VOID,
    }
)


class FuelTimestampProvenanceError(ValueError):
    """Invalid combination of provider timestamp and timezone provenance."""


def assert_not_float(value: Any, *, field: str) -> None:
    if isinstance(value, float) and not isinstance(value, bool):
        raise FuelFloatForbidden(f"{field} must not use float")


def interpret_provider_timestamp(
    *,
    source_text: str,
    timezone_source: str,
    timezone_name: str | None = None,
    utc_offset: str | None = None,
    parsed_date: date | None = None,
    parsed_datetime: datetime | None = None,
) -> dict[str, Any]:
    """Store provider time as supplied. Do not invent server/tenant timezone.

    `transaction_date` is the provider/source-local calendar date when that date
    is determinable from the source. It is never derived from a UTC-normalized
    `transaction_datetime` (a local late-night event must not move to the next
    calendar day because UTC crossed midnight).

    `transaction_datetime` (timestamptz) is populated only when the provider
    supplied enough timezone/offset context. Date-only and local-time-without
    zone leave `transaction_datetime` null.
    """
    source = (source_text or "").strip()
    if not source:
        raise FuelTimestampProvenanceError("Provider timestamp source text is required.")
    tz_source = (timezone_source or "").strip().upper()
    if tz_source not in TIMEZONE_SOURCES:
        raise FuelTimestampProvenanceError(f"Unknown timezone source: {timezone_source}")
    if parsed_datetime is not None and parsed_datetime.tzinfo is None:
        raise FuelTimestampProvenanceError(
            "Naive datetimes are not stored as transaction_datetime; "
            "that would silently apply a timezone."
        )

    tz_name = (timezone_name or "").strip() or None
    offset = (utc_offset or "").strip() or None

    if tz_source in {TZ_SOURCE_DATE_ONLY, TZ_SOURCE_PROVIDER_LOCAL_NO_ZONE, TZ_SOURCE_UNKNOWN}:
        if parsed_datetime is not None:
            raise FuelTimestampProvenanceError(
                "transaction_datetime must stay null when timezone is not provider-supplied."
            )
        return {
            "transaction_datetime_source": source,
            "transaction_timezone_source": tz_source,
            "transaction_timezone": tz_name if tz_source != TZ_SOURCE_DATE_ONLY else None,
            "transaction_utc_offset": offset if tz_source != TZ_SOURCE_DATE_ONLY else None,
            "transaction_date": parsed_date,
            "transaction_datetime": None,
        }

    # PROVIDER_SUPPLIED
    if not tz_name and not offset:
        raise FuelTimestampProvenanceError(
            "PROVIDER_SUPPLIED requires timezone name or UTC offset from the provider."
        )
    if tz_name:
        try:
            ZoneInfo(tz_name)
        except ZoneInfoNotFoundError as exc:
            raise FuelTimestampProvenanceError(f"Unknown provider timezone: {tz_name}") from exc
    return {
        "transaction_datetime_source": source,
        "transaction_timezone_source": TZ_SOURCE_PROVIDER_SUPPLIED,
        "transaction_timezone": tz_name,
        "transaction_utc_offset": offset,
        "transaction_date": parsed_date,
        "transaction_datetime": parsed_datetime,
    }


def classify_provider_event_type(raw: str | None) -> tuple[str | None, str]:
    """Return (provider_event_type_raw, canonical provider_event_type).

    Unknown provider terminology is never coerced to PURCHASE. Canonical
    UNKNOWN is REVIEW-eligible later.
    """
    if raw is None:
        return None, PROVIDER_EVENT_UNKNOWN
    preserved = str(raw).strip()
    if preserved == "":
        return None, PROVIDER_EVENT_UNKNOWN
    token = preserved.upper()
    if token in PROVIDER_EVENT_TYPES and token not in {PROVIDER_EVENT_OTHER, PROVIDER_EVENT_UNKNOWN}:
        return preserved, token
    if token in {PROVIDER_EVENT_OTHER, PROVIDER_EVENT_UNKNOWN}:
        return preserved, token
    return preserved, PROVIDER_EVENT_UNKNOWN


def classify_currency(raw: str | None) -> tuple[str | None, str | None]:
    """Return (currency_raw, canonical ISO currency). Unknown raw is preserved.

    Canonical currency stays null when no evidenced mapping exists. Never destroy
    the provider representation (e.g. BVD CN) when mapping to CAD.
    """
    if raw is None:
        return None, None
    preserved = str(raw).strip()
    if preserved == "":
        return None, None
    canonical = EVIDENCED_CURRENCY_CANONICAL.get(preserved.upper())
    return preserved, canonical


def assert_source_hydration_excludes_derived_fields(payload: dict[str, Any]) -> None:
    """Parser/source hydration must not set derived pricing/resolution fields."""
    present = sorted(SOURCE_HYDRATION_FORBIDDEN_FIELDS.intersection(payload))
    if present:
        raise ValueError(
            "Fuel source hydration must not populate derived/resolution fields: "
            + ", ".join(present)
        )


def event_type_preserves_sign(event_type: str, total_amount) -> None:
    """Credits/refunds/reversals/voids must not be rewritten as positive purchases."""
    code = (event_type or "").strip().upper()
    if code not in PROVIDER_EVENT_TYPES:
        raise ValueError(f"Unknown provider event type: {event_type}")
    if code not in NEGATIVE_OR_REVERSING_EVENTS:
        return
    if total_amount is None:
        return
    amount = to_decimal(total_amount)
    if amount > 0:
        raise ValueError(
            f"{code} must keep provider sign; do not rewrite as a positive purchase"
        )
