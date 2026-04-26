"""Load Lab — persisted extraction runs and promote audit (tenant DB)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class LoadLabExtractionRun(Base):
    __tablename__ = "load_lab_extraction_runs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    source_route: Mapped[str] = mapped_column(String(128), nullable=False, server_default="load_lab")
    created_by_platform_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)

    file_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(128), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)

    status: Mapped[str] = mapped_column(String(32), nullable=False)
    extraction_path: Mapped[str | None] = mapped_column(String(32), nullable=True)
    dedupe_prior_run_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("load_lab_extraction_runs.id", ondelete="SET NULL"), nullable=True
    )

    parser_version: Mapped[str] = mapped_column(String(64), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(64), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(64), nullable=False)
    model_name: Mapped[str] = mapped_column(String(128), nullable=False)
    ocr_engine_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    normalizer_version: Mapped[str] = mapped_column(String(64), nullable=False)

    classification_label: Mapped[str | None] = mapped_column(String(64), nullable=True)
    relevance: Mapped[str | None] = mapped_column(String(32), nullable=True)

    normalized_package: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    parse_response: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    ai_model_output: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    field_evidence: Mapped[list[Any] | None] = mapped_column(JSONB, nullable=True)
    contradictions: Mapped[list[Any] | None] = mapped_column(JSONB, nullable=True)
    warnings: Mapped[list[Any] | None] = mapped_column(JSONB, nullable=True)
    pipeline_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Load Lab v2 — OpenAI semantic extraction (isolated; no operational load writes).
    semantic_model_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    semantic_prompt_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    semantic_schema_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    semantic_extract_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    semantic_validation_result: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    # Load Lab v3 — heuristic confidence + contradictions (lab only; read-only in UI).
    lab_confidence: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    lab_review_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    lab_review_summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    promote_audits = relationship(
        "LoadLabPromoteAudit",
        back_populates="run",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class LoadLabPromoteAudit(Base):
    __tablename__ = "load_lab_promote_audits"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    run_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("load_lab_extraction_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    operator_platform_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)

    promote_target_type: Mapped[str] = mapped_column(String(32), nullable=False)
    target_load_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    fields_accepted: Mapped[dict[str, Any] | list[Any] | None] = mapped_column(JSONB, nullable=True)
    fields_blocked: Mapped[dict[str, Any] | list[Any] | None] = mapped_column(JSONB, nullable=True)
    overwrite_decisions: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    outcome: Mapped[str] = mapped_column(String(32), nullable=False)
    outcome_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    run = relationship("LoadLabExtractionRun", back_populates="promote_audits")
