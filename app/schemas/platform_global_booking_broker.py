"""Platform admin schemas: global booking broker reference (tenants are read-only consumers)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.utils.broker_identity import normalize_cvor_number_digits


class GlobalBookingBrokerAuditEventOut(BaseModel):
    """Parsed audit row for operators (``detail`` is JSON object when stored as JSON)."""

    id: int
    global_broker_id: int
    action: str
    detail: dict | None = None
    created_at: datetime


class GlobalBookingBrokerCreateIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    legal_name: str | None = Field(default=None, max_length=500)
    display_name: str | None = Field(default=None, max_length=255)
    mc_number: str | None = Field(default=None, max_length=100)
    dot_number: str | None = Field(default=None, max_length=32)
    cvor_number: str | None = Field(default=None, max_length=50)
    canonical_status: str = Field(default="pending", max_length=32)
    notes: str | None = None
    domains: list[str] = Field(default_factory=list)
    known_sender_emails: list[str] = Field(default_factory=list)
    aliases: list[str] = Field(default_factory=list)

    @field_validator("cvor_number")
    @classmethod
    def _cvor_create(cls, v: str | None) -> str | None:
        return normalize_cvor_number_digits(v)


class GlobalBookingBrokerProfilePatchIn(BaseModel):
    """Partial profile update (not promotion). Fields omitted are unchanged."""

    model_config = ConfigDict(extra="forbid")

    cvor_number: str | None = Field(
        default=None,
        description="Set to null or omit to clear when using PATCH with explicit null.",
    )

    @field_validator("cvor_number")
    @classmethod
    def _cvor_profile(cls, v: str | None) -> str | None:
        return normalize_cvor_number_digits(v)


class GlobalBookingBrokerPatchIn(BaseModel):
    """Promotion workflow: approve, return to pending, or mark rejected (excluded from resolver).

    When ``canonical_status`` changes, ``promotion_reason_code`` is **required** and must belong
    to the approve / reject / reopen write set for that transition (see shared JSON contract).
    ``note`` is optional supplemental detail only — not a substitute for a reason code.
    """

    canonical_status: str = Field(..., min_length=1, max_length=32)
    promotion_reason_code: str | None = Field(
        default=None,
        min_length=1,
        max_length=64,
        description="Required if status changes; must match shared promotion reason write set.",
    )
    note: str | None = Field(default=None, max_length=2000)


class GlobalBookingBrokerOut(BaseModel):
    id: int
    name: str
    legal_name: str | None = None
    display_name: str | None = None
    mc_number: str | None = None
    dot_number: str | None = None
    cvor_number: str | None = None
    canonical_status: str
    notes: str | None = None
    merged_into_global_broker_id: int | None = None
    merged_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


class GlobalBookingBrokerDuplicateBrokersMini(BaseModel):
    id: int
    name: str
    display_name: str | None
    canonical_status: str
    mc_number: str | None
    dot_number: str | None
    cvor_number: str | None = None
    merged_into_global_broker_id: int | None = None
    merged_at: datetime | None = None
    model_config = ConfigDict(from_attributes=True)


class GlobalBookingBrokerDuplicateCandidateOut(BaseModel):
    id: int
    broker_low: GlobalBookingBrokerDuplicateBrokersMini
    broker_high: GlobalBookingBrokerDuplicateBrokersMini
    match_signals: list[str]
    review_status: str
    duplicate_review_reason_code: str | None = None
    note: str | None = None
    created_at: datetime
    updated_at: datetime


class GlobalBookingBrokerDuplicateRefreshOut(BaseModel):
    upserted_open: int
    updated_open_signals: int
    removed_stale_open: int
    touched_dismissed_or_ack: int
