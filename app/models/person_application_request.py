"""Admin requests for additional documents on a person application (tenant-scoped)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKeyConstraint, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class PersonApplicationRequest(Base):
    __tablename__ = "person_application_requests"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "application_id"],
            ["person_applications.tenant_id", "person_applications.id"],
            name="fk_person_application_requests_tenant_app_to_applications",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "doc_requirement_id"],
            ["document_requirements.tenant_id", "document_requirements.id"],
            name="fk_person_application_requests_tenant_docreq_to_requirements",
            ondelete="SET NULL",
        ),
        Index("ix_person_application_requests_tenant_application_id", "tenant_id", "application_id"),
        Index("ix_person_application_requests_tenant_status", "tenant_id", "status"),
        Index("ix_person_application_requests_tenant_request_type", "tenant_id", "request_type"),
        Index("ix_person_application_requests_tenant_doc_requirement_id", "tenant_id", "doc_requirement_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    application_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    doc_requirement_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    request_type: Mapped[str] = mapped_column(String(50), nullable=False)
    message_to_applicant: Mapped[str | None] = mapped_column(Text, nullable=True)
    required: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="OPEN")
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_by_user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)  # platform identity
    resolved_by_user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)  # platform identity

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    application: Mapped["PersonApplication"] = relationship(
        "PersonApplication",
        back_populates="requests",
    )
    files: Mapped[list["PersonApplicationFile"]] = relationship(
        "PersonApplicationFile",
        back_populates="request",
        foreign_keys="[PersonApplicationFile.request_id]",
    )
