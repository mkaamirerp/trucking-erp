"""Schemas for tenant-scoped email threads/messages read APIs."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.load import Load
from app.schemas.email_intake_review import EmailIntakeReviewCardOut


def pickup_delivery_summary_from_load(load: Load | None) -> str | None:
    if not load or not load.stops:
        return None
    ordered = sorted(load.stops, key=lambda s: (s.sequence, s.id))
    chunks: list[str] = []
    for s in ordered:
        st = (s.stop_type or "").upper()
        loc = ", ".join(x for x in [s.city, s.state_or_province] if x)
        if st == "PICKUP":
            chunks.append(f"Pickup {loc}" if loc else "Pickup")
        elif st in ("DROP", "DELIVERY"):
            chunks.append(f"Delivery {loc}" if loc else "Delivery")
    return " → ".join(chunks) if chunks else None


class EmailThreadOut(BaseModel):
    id: int
    provider: str
    subject: str | None = None
    participants_json: Any | None = None
    snippet: str | None = None
    last_message_at: datetime | None = None
    message_count: int
    unread_count: int
    linked_load_id: int | None = None
    intake_bucket: str = "needs_review"
    confidence_level: str | None = None
    confidence_score: float | None = None
    routing_reason: str | None = None
    status: str
    created_at: datetime
    updated_at: datetime
    linked_load_number: str | None = None
    #: Denormalized trip_number from linked load when thread is linked (read-only).
    linked_trip_number: str | None = None
    linked_broker_name: str | None = None
    pickup_delivery_summary: str | None = None
    #: Structured intake review row when present (detail GET only in practice).
    intake_review: EmailIntakeReviewCardOut | None = None
    model_config = ConfigDict(from_attributes=True)


def email_thread_to_out(
    thread: Any,
    *,
    linked_load: Load | None = None,
    intake_review: EmailIntakeReviewCardOut | None = None,
) -> EmailThreadOut:
    score = getattr(thread, "confidence_score", None)
    if isinstance(score, Decimal):
        score = float(score)
    ib = getattr(thread, "intake_bucket", None) or "needs_review"
    return EmailThreadOut(
        id=thread.id,
        provider=thread.provider,
        subject=thread.subject,
        participants_json=thread.participants_json,
        snippet=thread.snippet,
        last_message_at=thread.last_message_at,
        message_count=thread.message_count,
        unread_count=thread.unread_count,
        linked_load_id=thread.linked_load_id,
        intake_bucket=ib,
        confidence_level=getattr(thread, "confidence_level", None),
        confidence_score=score,
        routing_reason=getattr(thread, "routing_reason", None),
        status=thread.status,
        created_at=thread.created_at,
        updated_at=thread.updated_at,
        linked_load_number=linked_load.load_number if linked_load else None,
        linked_trip_number=(
            (linked_load.trip_number or "").strip() or None if linked_load else None
        ),
        linked_broker_name=linked_load.broker_name_snapshot if linked_load else None,
        pickup_delivery_summary=pickup_delivery_summary_from_load(linked_load),
        intake_review=intake_review,
    )


class EmailAttachmentOut(BaseModel):
    id: int
    filename: str | None = None
    mime_type: str | None = None
    size_bytes: int | None = None
    is_inline: bool = False
    download_status: str = "metadata_only"
    content_sha256: str | None = Field(default=None, max_length=64)
    external_attachment_id: str
    model_config = ConfigDict(from_attributes=True)


class EmailMessageOut(BaseModel):
    id: int
    thread_id: int
    provider: str
    external_message_id: str
    external_thread_id: str
    direction: str | None = None
    from_email: str | None = None
    to_json: Any | None = None
    cc_json: Any | None = None
    bcc_json: Any | None = None
    subject: str | None = None
    sent_at: datetime | None = None
    received_at: datetime | None = None
    snippet: str | None = None
    body_text: str | None = None
    body_html: str | None = None
    has_attachments: bool
    extraction_status: str | None = None
    created_at: datetime
    updated_at: datetime
    attachments: list[EmailAttachmentOut] = []
    model_config = ConfigDict(from_attributes=True)


class EmailIntakeQrExtractionOut(BaseModel):
    """Supplemental intake signal: persisted QR decode rows for a thread (read path)."""

    id: int
    thread_id: int
    message_id: int
    attachment_id: int | None = None
    raw_value: str
    normalized_value: str | None = None
    extracted_from_source_type: str
    page_number: int | None = None
    format_hint: str | None = None
    linked_load_id: int | None = None
    linked_broker_id: int | None = None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class EmailThreadListResponse(BaseModel):
    items: list[EmailThreadOut]
    page: int
    size: int
    total: int


class EmailThreadLinkLoadBody(BaseModel):
    load_id: int = Field(..., ge=1)


class EmailThreadActionLoadOut(BaseModel):
    id: int
    load_number: str
    status: str


class EmailThreadDraftOrLinkResponse(BaseModel):
    thread: EmailThreadOut
    load: EmailThreadActionLoadOut
