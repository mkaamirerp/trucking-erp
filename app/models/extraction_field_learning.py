"""Tenant-private extraction field learning (shared spine: Load Lab, loads, trips, email — no platform PII)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


# Origin of the event (which workflow produced / corrected this field).
ORIGIN_LOAD_LAB_RUN = "load_lab_run"
ORIGIN_LOAD_WORKSPACE = "load_workspace"
ORIGIN_TRIP_WORKSPACE = "trip_workspace"
ORIGIN_EMAIL_INGESTION = "email_ingestion"


class ExtractionFieldLearningEvent(Base):
    """
    One row per field-level learning event. Tenant DB only; never copy raw values to platform.

    `origin_id` is opaque: run_id, load_id, trip_id, or email thread id per `origin_type`.
    No FK to load_lab — future origins do not all have a run row.
    """

    __tablename__ = "extraction_field_learning_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)

    origin_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    origin_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)

    field_path: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    event_kind: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    """ai_proposed | operator_override | operator_clear | operator_confirm | ..."""

    proposed_value_json: Mapped[Any | None] = mapped_column(JSONB, nullable=True)
    """Model/parser proposal (e.g. AI line)."""

    final_value_json: Mapped[Any | None] = mapped_column(JSONB, nullable=True)
    """What was accepted as final for this event (e.g. operator save). For ai-only rows often null until confirmed."""

    previous_value_json: Mapped[Any | None] = mapped_column(JSONB, nullable=True)

    correction_type: Mapped[str | None] = mapped_column(String(32), nullable=True)

    source_label: Mapped[str | None] = mapped_column(String(256), nullable=True)
    source_section: Mapped[str | None] = mapped_column(String(256), nullable=True)
    source_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_page: Mapped[int | None] = mapped_column(Integer, nullable=True)

    response_contract: Mapped[str | None] = mapped_column(String(64), nullable=True)
    """e.g. truckerjson | critical_v1_1 — extraction contract / response shape name."""

    parser_version: Mapped[str | None] = mapped_column(String(128), nullable=True)
    """App/parser line (semantic schema, parse pipeline) for reproducibility on tenant only."""

    event_meta: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    """Non-PII pack: e.g. guardrail_count, service version. Do not use for cross-tenant export."""

    actor_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
