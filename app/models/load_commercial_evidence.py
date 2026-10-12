"""Immutable commercial evidence rows attached to promoted loads."""

from __future__ import annotations

from datetime import datetime
from typing import Any
import uuid

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class LoadCommercialEvidence(Base):
    __tablename__ = "load_commercial_evidence"
    __table_args__ = (
        UniqueConstraint("tenant_id", "workspace_draft_id", name="uq_load_commercial_evidence_tenant_draft"),
        UniqueConstraint(
            "tenant_id",
            "load_id",
            "evidence_kind",
            name="uq_load_commercial_evidence_tenant_load_kind",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "load_id"],
            ["loads.tenant_id", "loads.id"],
            name="fk_load_commercial_evidence_load_tenant",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "workspace_draft_id"],
            ["load_workspace_drafts.tenant_id", "load_workspace_drafts.id"],
            name="fk_load_commercial_evidence_workspace_draft_tenant",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "retention_class = 'commercial_permanent'",
            name="ck_load_commercial_evidence_retention_class",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    load_id: Mapped[int] = mapped_column(Integer, nullable=False)
    evidence_kind: Mapped[str] = mapped_column(String(32), nullable=False, server_default="rate_confirmation_pdf")
    file_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_key: Mapped[str] = mapped_column(Text, nullable=False)
    retention_class: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="commercial_permanent"
    )
    filename: Mapped[str | None] = mapped_column(Text, nullable=True)
    accepted_parse_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    parse_schema_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    workspace_draft_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    promoted_by_platform_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    promoted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
