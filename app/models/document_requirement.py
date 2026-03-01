"""Tenant-scoped document requirements config (which docs are needed per role/form)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class DocumentRequirement(Base):
    __tablename__ = "document_requirements"
    __table_args__ = (
        Index("ix_document_requirements_tenant_scope", "tenant_id", "scope_type", "scope_key"),
        Index("ix_document_requirements_tenant_active", "tenant_id", "is_active"),
        Index("ix_document_requirements_tenant_doc_type", "tenant_id", "doc_type"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)

    scope_type: Mapped[str] = mapped_column(String(30), nullable=False)  # ROLE | FORM
    scope_key: Mapped[str] = mapped_column(String(50), nullable=False)  # DRIVER, DRIVER_INTAKE, etc.
    doc_type: Mapped[str] = mapped_column(String(50), nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    required: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    applies_at_stage: Mapped[str] = mapped_column(String(30), nullable=False, server_default="SUBMIT")  # SUBMIT | POST_SUBMIT
    visibility: Mapped[str] = mapped_column(String(30), nullable=False, server_default="APPLICANT")  # APPLICANT | ADMIN_ONLY

    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
