"""Platform-wide sanitized extraction priors (no tenant-private values)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class PlatformExtractionSanitizedPattern(Base):
    """
    Sanitized, cross-tenant learnable prior: label/section *patterns*, shape classes, and counts.

    Never store raw PDF text, full addresses, rates, or tenant-specific free-form strings from documents.
    Use normalized broker **family** keys (e.g. TQL) and structural descriptors only.
    """

    __tablename__ = "platform_extraction_sanitized_patterns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true", index=True)

    broker_family_key: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    """Directory-level / public key: e.g. `TQL`, `J_B_HUNT`, `LANDSTAR`, not tenant-specific phrasing from a PDF body."""

    field_path: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    """Target logical field, e.g. `broker_load_reference` (no PII in this column)."""

    source_label_pattern: Mapped[str] = mapped_column(String(256), nullable=False)
    """Normalized label token, e.g. `PO#`, `Load Number` (pattern class, not a one-off long title with shipper name)."""

    source_section_pattern: Mapped[str] = mapped_column(String(256), nullable=False, server_default="")
    """Structural section id: e.g. `header`, `stop_1_pickup`, `bill_to_block` (rejected for stops) — empty string = any."""

    value_shape_class: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    """E.g. `has_digit`, `alnum_8_12`, `currency_like` — not the actual value."""

    section_role: Mapped[str] = mapped_column(String(64), nullable=False, server_default="unknown", index=True)
    """E.g. `pickup_context`, `broker_identity`, `accounting_context`."""

    positive_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    negative_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")

    confidence: Mapped[float | None] = mapped_column(Numeric(5, 4), nullable=True)
    maturity: Mapped[str] = mapped_column(String(32), nullable=False, server_default="observation", index=True)
    """observation | pattern_detected | suggestion | guarded | disputed — align with product maturity model."""

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    """Internal admin notes; must not be used to smuggle PII from tenants."""
