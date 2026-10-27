"""Immutable commercial JSON captured when a Load row is first inserted."""

from __future__ import annotations

from datetime import datetime
from typing import Any
import uuid

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class LoadApprovedCommercialSnapshot(Base):
    __tablename__ = "load_approved_commercial_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "load_id",
            "milestone",
            "revision",
            name="uq_load_approved_snapshots_tenant_load_milestone_rev",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "load_id"],
            ["loads.tenant_id", "loads.id"],
            name="fk_load_approved_snapshots_load_tenant",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "commercial_evidence_id"],
            ["load_commercial_evidence.tenant_id", "load_commercial_evidence.id"],
            name="fk_load_approved_snapshots_evidence_tenant",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "milestone IN ('creation')",
            name="ck_load_approved_snapshots_milestone_creation",
        ),
        CheckConstraint(
            "creation_source IN ('workspace_promotion', 'direct_create')",
            name="ck_load_approved_snapshots_creation_source",
        ),
        CheckConstraint(
            "dispatcher_review_claim IN ('none', 'workspace_promotion_reviewed')",
            name="ck_load_approved_snapshots_review_claim",
        ),
        CheckConstraint(
            "("
            "creation_source = 'direct_create' AND dispatcher_review_claim = 'none'"
            ") OR ("
            "creation_source = 'workspace_promotion' "
            "AND dispatcher_review_claim = 'workspace_promotion_reviewed'"
            ")",
            name="ck_load_approved_snapshots_claim_matches_source",
        ),
        CheckConstraint(
            "(commercial_evidence_id IS NULL AND workspace_draft_id IS NULL) "
            "OR (creation_source = 'workspace_promotion')",
            name="ck_load_approved_snapshots_evidence_on_promotion",
        ),
        Index("ix_load_approved_snapshots_tenant_load", "tenant_id", "load_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False)
    load_id: Mapped[int] = mapped_column(Integer, nullable=False)
    milestone: Mapped[str] = mapped_column(String(32), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    schema_version: Mapped[str] = mapped_column(String(64), nullable=False)
    load_concurrency_version: Mapped[int] = mapped_column(Integer, nullable=False)
    creation_source: Mapped[str] = mapped_column(String(32), nullable=False)
    load_status_at_snapshot: Mapped[str] = mapped_column(String(32), nullable=False)
    dispatcher_review_claim: Mapped[str] = mapped_column(String(32), nullable=False)
    commercial_evidence_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    workspace_draft_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_by_platform_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    snapshot_taken_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
